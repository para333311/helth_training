"""Render/Webhook용 HTTP 서버.

- GET /, /health : UptimeRobot 헬스체크
- POST /telegram/webhook/{secret} : 텔레그램 inbound update 수신
- 기존 스케줄러 발행 기능 유지 (백그라운드 스레드)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request

from .commands import CommandHandler
from .config import load_config
from .content import Content
from .feeds import YoutubeFeeds
from .jobs import Publisher
from .main import build_scheduler, build_store
from .photos import build_source
from .tg import Telegram, TelegramError

log = logging.getLogger("web")

ACK_PREFIX = "✅ 자료 받았습니다"
DONE_PREFIX = "✅ 분석 완료"
FAIL_PREFIX = "⚠️ 처리 실패"
SKIP_PREFIXES = (ACK_PREFIX, DONE_PREFIX, FAIL_PREFIX)

DEFAULT_ALLOWED_UPDATES = [
    "message",
    "edited_message",
    "channel_post",
    "edited_channel_post",
    "callback_query",
    "poll",
    "message_reaction",
    "message_reaction_count",
]


class TTLCache:
    """아주 단순한 TTL 캐시 (중복 update/메시지 루프 방지)."""

    def __init__(self, ttl_seconds: int = 300, max_items: int = 4096):
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self._data: OrderedDict[Any, float] = OrderedDict()
        self._lock = threading.Lock()

    def _purge(self, now: float | None = None) -> None:
        now = now or time.time()
        while self._data:
            _, exp = next(iter(self._data.items()))
            if exp > now:
                break
            self._data.popitem(last=False)
        while len(self._data) > self.max_items:
            self._data.popitem(last=False)

    def add(self, key: Any) -> None:
        with self._lock:
            self._purge()
            self._data[key] = time.time() + self.ttl_seconds

    def contains(self, key: Any) -> bool:
        with self._lock:
            self._purge()
            return key in self._data


class BotRuntime:
    def __init__(self) -> None:
        self.cfg = load_config(require_channel=False)
        self.tg = Telegram(self.cfg.token)
        self.store = build_store(self.cfg)
        self.content = Content(self.cfg.data_dir)
        self.feeds = YoutubeFeeds(self.cfg.data_dir / "youtube_channels.json")
        self.photos = build_source(self.cfg, self.store)
        self.publisher = Publisher(self.cfg, self.tg, self.store, self.content, self.photos, self.feeds)
        self.scheduler = build_scheduler(self.cfg, self.publisher, self.store)
        self.handler = CommandHandler(self.cfg, self.tg, self.store, self.content)

        self.base_url = os.environ.get("BASE_URL", "").strip().rstrip("/")
        self.webhook_secret = os.environ.get("WEBHOOK_SECRET", "").strip()
        self.webhook_secret_token = os.environ.get("TELEGRAM_WEBHOOK_SECRET_TOKEN", "").strip()
        self.admin_chat_id = os.environ.get("ADMIN_CHAT_ID", "").strip()
        self.diag_token = os.environ.get("DIAG_TOKEN", "").strip()

        self.enable_scheduler = os.environ.get("ENABLE_SCHEDULER", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        self._stop_event = threading.Event()
        self._scheduler_thread: threading.Thread | None = None

        self.update_cache = TTLCache(ttl_seconds=600, max_items=8192)
        self.outbound_cache = TTLCache(ttl_seconds=300, max_items=8192)
        self.media_group_ack_cache = TTLCache(ttl_seconds=8, max_items=2048)

        self.bot_id: int | None = None
        self.bot_username: str = ""
        self.last_error_message: str = ""
        self.webhook_configured = False

    def start(self) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)-7s %(name)-8s %(message)s",
            datefmt="%H:%M:%S",
        )

        try:
            me = self.tg.get_me()
            self.bot_id = me.get("id")
            self.bot_username = me.get("username", "")
            self.handler.register_commands()
            log.info("bot ready username=@%s", self.bot_username or "?")
        except Exception as exc:  # noqa: BLE001
            self.last_error_message = f"get_me_failed: {type(exc).__name__}"
            log.exception("봇 초기화 실패")

        if self.enable_scheduler:
            self._start_scheduler_thread()
        else:
            log.info("scheduler disabled by ENABLE_SCHEDULER=false")

        self._configure_webhook_if_possible()

    def stop(self) -> None:
        self._stop_event.set()
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=2)

    def _start_scheduler_thread(self) -> None:
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return

        def run() -> None:
            log.info("scheduler thread started")
            while not self._stop_event.is_set():
                try:
                    self.scheduler.tick(datetime.now(self.cfg.tz))
                except Exception:  # noqa: BLE001
                    self.last_error_message = "scheduler_tick_failed"
                    log.exception("ERR scheduler_tick_failed")
                self._stop_event.wait(10)
            log.info("scheduler thread stopped")

        self._scheduler_thread = threading.Thread(target=run, name="scheduler-thread", daemon=True)
        self._scheduler_thread.start()

    def _configure_webhook_if_possible(self) -> None:
        if not (self.base_url and self.webhook_secret):
            log.info("webhook auto-setup skipped (BASE_URL/WEBHOOK_SECRET missing)")
            return

        try:
            url = f"{self.base_url}/telegram/webhook/{self.webhook_secret}"
            self.tg.set_webhook(
                url=url,
                allowed_updates=DEFAULT_ALLOWED_UPDATES,
                secret_token=self.webhook_secret_token or None,
            )
            self.webhook_configured = True
            log.info("webhook configured")
        except Exception as exc:  # noqa: BLE001
            self.last_error_message = f"set_webhook_failed: {type(exc).__name__}"
            log.exception("ERR set_webhook_failed")

    def _normalize_message(self, update: dict) -> tuple[str | None, dict | None]:
        for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
            if key in update:
                return key, update[key]
        return None, None

    @staticmethod
    def _content_type(msg: dict) -> str:
        if msg.get("photo"):
            return "photo"
        if msg.get("document"):
            return "document"
        if msg.get("audio"):
            return "audio"
        if msg.get("voice"):
            return "voice"
        if msg.get("video"):
            return "video"
        if msg.get("animation"):
            return "animation"
        if msg.get("text"):
            return "text"
        if msg.get("caption"):
            return "caption"
        return "unknown"

    def _is_self_message(self, msg: dict) -> bool:
        chat_id = msg.get("chat", {}).get("id")
        msg_id = msg.get("message_id")
        sender = msg.get("from", {})

        if chat_id is not None and msg_id is not None and self.outbound_cache.contains((chat_id, msg_id)):
            return True

        if sender.get("is_bot"):
            return True

        if self.bot_id and sender.get("id") == self.bot_id:
            return True

        text = (msg.get("text") or msg.get("caption") or "").strip()
        return bool(text and any(text.startswith(prefix) for prefix in SKIP_PREFIXES))

    @staticmethod
    def _needs_ack(msg: dict) -> bool:
        text = (msg.get("text") or "").strip()
        if text.startswith("/"):
            return False
        content_keys = ("text", "photo", "document", "audio", "voice", "video", "animation", "caption")
        return any(msg.get(k) for k in content_keys) or bool(msg.get("media_group_id"))

    def _send_admin_error(self, text: str) -> None:
        if not self.admin_chat_id:
            return
        try:
            sent = self.tg.send_message(self.admin_chat_id, f"{FAIL_PREFIX}\n{text}")
            self.outbound_cache.add((sent.get("chat", {}).get("id"), sent.get("message_id")))
        except Exception:  # noqa: BLE001
            log.exception("ERR admin_notify_failed")

    def _send_failure(self, chat_id: int | str | None, reply_to: int | None, reason: str) -> None:
        if chat_id is None:
            return
        try:
            sent = self.tg.send_message(
                chat_id,
                f"{FAIL_PREFIX}했습니다. 사유: {reason}",
                reply_to_message_id=reply_to,
            )
            self.outbound_cache.add((sent.get("chat", {}).get("id"), sent.get("message_id")))
        except Exception:  # noqa: BLE001
            log.exception("ERR failure_notice_send_failed chat_id=%s reply_to=%s", chat_id, reply_to)

    def process_update_safe(self, update: dict) -> None:
        update_id = update.get("update_id")
        if update_id is not None:
            if self.update_cache.contains(update_id):
                log.info("SKIP duplicate_update update_id=%s", update_id)
                return
            self.update_cache.add(update_id)

        msg_type, msg = self._normalize_message(update)
        if msg:
            chat_id = msg.get("chat", {}).get("id")
            msg_id = msg.get("message_id")
            content = self._content_type(msg)
            log.info(
                "IN update_received update_id=%s type=%s chat_id=%s msg_id=%s content=%s",
                update_id,
                msg_type,
                chat_id,
                msg_id,
                content,
            )

            if self._is_self_message(msg):
                log.info("SKIP self_message chat_id=%s msg_id=%s", chat_id, msg_id)
                return

            try:
                if self._needs_ack(msg):
                    group_id = msg.get("media_group_id")
                    if group_id:
                        dedupe_key = (chat_id, group_id)
                        if self.media_group_ack_cache.contains(dedupe_key):
                            log.info("SKIP media_group_duplicate_ack chat_id=%s media_group_id=%s", chat_id, group_id)
                        else:
                            self.media_group_ack_cache.add(dedupe_key)
                            self._send_ack(chat_id, msg_id)
                    else:
                        self._send_ack(chat_id, msg_id)

                self.handler.handle_update(update)
                log.info("OUT result_sent chat_id=%s msg_id=%s", chat_id, msg_id)
            except Exception as exc:  # noqa: BLE001
                reason = type(exc).__name__
                self.last_error_message = f"webhook_process_failed: {reason}"
                log.exception(
                    "ERR webhook_process_failed chat_id=%s msg_id=%s error=%s",
                    chat_id,
                    msg_id,
                    reason,
                )
                self._send_failure(chat_id, msg_id, reason)
                self._send_admin_error(f"chat_id={chat_id} msg_id={msg_id} error={reason}")
            return

        try:
            self.handler.handle_update(update)
        except Exception as exc:  # noqa: BLE001
            reason = type(exc).__name__
            self.last_error_message = f"webhook_process_failed: {reason}"
            log.exception("ERR webhook_process_failed update_id=%s error=%s", update_id, reason)
            self._send_admin_error(f"update_id={update_id} error={reason}")

    def _send_ack(self, chat_id: int | str | None, reply_to: int | None) -> None:
        if chat_id is None:
            return
        sent = self.tg.send_message(
            chat_id,
            f"{ACK_PREFIX}. 분석 시작합니다.",
            reply_to_message_id=reply_to,
        )
        out_chat = sent.get("chat", {}).get("id")
        out_msg_id = sent.get("message_id")
        if out_chat is not None and out_msg_id is not None:
            self.outbound_cache.add((out_chat, out_msg_id))
        log.info("OUT ack_sent chat_id=%s reply_to=%s", chat_id, reply_to)

    def diag(self) -> dict[str, Any]:
        pending_updates = None
        webhook_url = ""
        try:
            info = self.tg.get_webhook_info()
            pending_updates = info.get("pending_update_count")
            webhook_url = info.get("url", "")
        except Exception:  # noqa: BLE001
            pass

        return {
            "ok": True,
            "service": "helth_training",
            "version": os.environ.get("RENDER_GIT_COMMIT", "unknown"),
            "scheduler_running": bool(self._scheduler_thread and self._scheduler_thread.is_alive()),
            "webhook_configured": bool(webhook_url),
            "bot_username": self.bot_username,
            "bot_id": self.bot_id,
            "pending_update_count": pending_updates,
            "last_error_message": self.last_error_message,
        }


def create_app(runtime: BotRuntime | None = None) -> FastAPI:
    app = FastAPI(title="helth_training", version="1.0.0")
    app.state.runtime = runtime

    @app.on_event("startup")
    async def _startup() -> None:
        if app.state.runtime is None:
            app.state.runtime = BotRuntime()
        app.state.runtime.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        if app.state.runtime is not None:
            app.state.runtime.stop()

    @app.get("/")
    async def root() -> dict[str, Any]:
        return {"ok": True, "service": "helth_training"}

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "status": "healthy"}

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True, "status": "healthy"}

    @app.get("/diag")
    async def diag(
        token: str = Query(default=""),
        x_diag_token: str = Header(default="", alias="X-Diag-Token"),
    ) -> dict[str, Any]:
        if app.state.runtime is None:
            raise HTTPException(status_code=503, detail="runtime not ready")
        expected = app.state.runtime.diag_token
        if not expected or (token != expected and x_diag_token != expected):
            raise HTTPException(status_code=401, detail="unauthorized")
        return app.state.runtime.diag()

    @app.post("/telegram/webhook/{secret}")
    async def telegram_webhook(
        secret: str,
        request: Request,
        background_tasks: BackgroundTasks,
        x_telegram_secret: str = Header(default="", alias="X-Telegram-Bot-Api-Secret-Token"),
    ) -> dict[str, Any]:
        rt: BotRuntime | None = app.state.runtime
        if rt is None:
            raise HTTPException(status_code=503, detail="runtime not ready")

        if not rt.webhook_secret or secret != rt.webhook_secret:
            raise HTTPException(status_code=404, detail="not found")

        if rt.webhook_secret_token and x_telegram_secret != rt.webhook_secret_token:
            raise HTTPException(status_code=403, detail="forbidden")

        update = await request.json()
        background_tasks.add_task(rt.process_update_safe, update)
        return {"ok": True}

    return app


app = create_app()
