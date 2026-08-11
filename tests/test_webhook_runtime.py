from __future__ import annotations

import logging

from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.webapp import BotRuntime, TTLCache, create_app


class DummyHandler:
    def __init__(self, should_raise: bool = False):
        self.should_raise = should_raise
        self.calls = 0

    def handle_update(self, update: dict) -> None:
        self.calls += 1
        if self.should_raise:
            raise RuntimeError("boom")


class DummyTG:
    def __init__(self):
        self.sent: list[dict] = []

    def send_message(self, chat_id, text, **kwargs):
        msg = {
            "chat": {"id": chat_id},
            "message_id": len(self.sent) + 1,
            "text": text,
            "kwargs": kwargs,
        }
        self.sent.append(msg)
        return msg


class DummyRuntime:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.diag_token = "diag-token"
        self.webhook_secret = "hook-secret"
        self.webhook_secret_token = "header-secret"
        self.updates: list[dict] = []

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def process_update_safe(self, update: dict):
        self.updates.append(update)

    def diag(self):
        return {"ok": True, "service": "helth_training"}


def make_runtime() -> BotRuntime:
    rt = object.__new__(BotRuntime)
    rt.update_cache = TTLCache(ttl_seconds=600)
    rt.outbound_cache = TTLCache(ttl_seconds=300)
    rt.media_group_ack_cache = TTLCache(ttl_seconds=8)
    rt.handler = DummyHandler()
    rt.tg = DummyTG()
    rt.bot_id = 123456
    rt.last_error_message = ""
    rt.admin_chat_id = ""
    rt.webhook_secret = "hook-secret"
    rt.webhook_secret_token = "header-secret"
    rt.diag_token = "diag-token"
    rt.bot_username = "bot"
    rt._scheduler_thread = None
    return rt


def test_health_and_root_200():
    runtime = DummyRuntime()
    app = create_app(runtime=runtime)
    client = TestClient(app)

    r1 = client.get("/")
    r2 = client.get("/health")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["ok"] is True
    assert r2.json()["status"] == "healthy"


def test_channel_post_photo_calls_ack():
    rt = make_runtime()

    update = {
        "update_id": 1,
        "channel_post": {
            "message_id": 10,
            "chat": {"id": -1001, "type": "channel"},
            "from": {"id": 555, "is_bot": False},
            "photo": [{"file_id": "abc", "file_size": 10}],
        },
    }

    rt.process_update_safe(update)

    assert len(rt.tg.sent) == 1
    assert rt.tg.sent[0]["text"].startswith("✅ 자료 받았습니다")


def test_message_document_calls_ack():
    rt = make_runtime()

    update = {
        "update_id": 2,
        "message": {
            "message_id": 11,
            "chat": {"id": 9988, "type": "private"},
            "from": {"id": 777, "is_bot": False, "first_name": "u"},
            "document": {"file_id": "doc1"},
        },
    }

    rt.process_update_safe(update)

    assert len(rt.tg.sent) == 1
    assert "분석 시작합니다" in rt.tg.sent[0]["text"]


def test_media_group_ack_once():
    rt = make_runtime()

    base = {
        "chat": {"id": -1001, "type": "channel"},
        "from": {"id": 888, "is_bot": False},
        "media_group_id": "group-1",
        "photo": [{"file_id": "p"}],
    }

    rt.process_update_safe({"update_id": 3, "channel_post": {**base, "message_id": 21}})
    rt.process_update_safe({"update_id": 4, "channel_post": {**base, "message_id": 22}})

    assert len(rt.tg.sent) == 1


def test_self_message_skipped():
    rt = make_runtime()

    update = {
        "update_id": 5,
        "channel_post": {
            "message_id": 99,
            "chat": {"id": -1001, "type": "channel"},
            "from": {"id": rt.bot_id, "is_bot": True},
            "text": "✅ 자료 받았습니다. 분석 시작합니다.",
        },
    }

    rt.process_update_safe(update)
    assert len(rt.tg.sent) == 0


def test_no_secret_leak_in_logs(caplog):
    rt = make_runtime()
    rt.handler = DummyHandler(should_raise=True)
    fake_token = "123456:SECRET_TOKEN_VALUE"

    update = {
        "update_id": 6,
        "message": {
            "message_id": 30,
            "chat": {"id": 5555, "type": "private"},
            "from": {"id": 777, "is_bot": False},
            "text": "hello",
        },
    }

    with caplog.at_level(logging.INFO):
        rt.process_update_safe(update)

    logs = "\n".join(caplog.messages)
    assert fake_token not in logs
