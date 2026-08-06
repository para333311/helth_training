"""텔레그램 Bot API 얇은 래퍼. 필요한 메서드만."""

from __future__ import annotations

import json
import logging
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger("tg")

API = "https://api.telegram.org/bot{token}/{method}"

# 채널 리액션 집계와 투표 결과를 받으려면 명시적으로 요청해야 한다.
ALLOWED_UPDATES = [
    "message",
    "channel_post",
    "callback_query",
    "poll",
    "message_reaction",
    "message_reaction_count",
]


class TelegramError(RuntimeError):
    pass


class Telegram:
    def __init__(self, token: str, timeout: int = 30):
        self._token = token
        self._timeout = timeout
        self._session = requests.Session()

    def _url(self, method: str) -> str:
        return API.format(token=self._token, method=method)

    def _redact(self, text: str) -> str:
        """봇 토큰은 URL 경로의 일부라, 네트워크 예외 메시지에 그대로 찍혀 나올 수 있다
        (예: requests.ConnectionError 가 실패한 URL 전체를 포함하는 경우). 로그·예외
        메시지로 나가기 전에 항상 이걸 거친다."""
        return text.replace(self._token, "***") if self._token else text

    def call(self, method: str, files: dict | None = None, **params: Any) -> Any:
        """재시도 포함 API 호출. 429 는 retry_after 를 존중한다.

        dict/list 값(reply_markup, options 등)은 폼 데이터로 못 보내므로 자동으로
        JSON 문자열로 바꾼다 — 호출부에서 매번 json.dumps 할 필요가 없다.
        """
        payload = {
            k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
            for k, v in params.items()
            if v is not None
        }
        last_error: Exception | None = None

        for attempt in range(4):
            try:
                resp = self._session.post(
                    self._url(method), data=payload, files=files, timeout=self._timeout
                )
                body = resp.json()
            except Exception as exc:  # 네트워크 오류
                last_error = self._redact(str(exc))
                time.sleep(2**attempt)
                continue

            if body.get("ok"):
                return body["result"]

            code = body.get("error_code")
            desc = body.get("description", "")

            if code == 429:
                wait = body.get("parameters", {}).get("retry_after", 5)
                log.warning("rate limited, %ss 대기", wait)
                time.sleep(wait + 1)
                continue

            # 4xx 는 재시도해도 같은 결과다
            if code and 400 <= code < 500:
                raise TelegramError(f"{method} 실패 [{code}]: {desc}")

            last_error = TelegramError(f"{method} 실패 [{code}]: {desc}")
            time.sleep(2**attempt)

        raise TelegramError(f"{method} 최종 실패: {last_error}")

    # --- 발행 ---------------------------------------------------------------

    def send_message(self, chat_id: str | int, text: str, **kw: Any) -> dict:
        kw.setdefault("disable_web_page_preview", True)
        return self.call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode=kw.pop("parse_mode", None),
            **kw,
        )

    def send_photo(
        self,
        chat_id: str | int,
        photo: str | Path | BytesIO,
        caption: str | None = None,
        **kw: Any,
    ) -> dict:
        """Path 와 BytesIO 는 업로드, str 은 URL 또는 file_id 로 취급."""
        if isinstance(photo, Path):
            with photo.open("rb") as fh:
                return self.call(
                    "sendPhoto",
                    files={"photo": (photo.name, fh)},
                    chat_id=chat_id,
                    caption=caption,
                    **kw,
                )
        if isinstance(photo, BytesIO):
            photo.seek(0)
            return self.call(
                "sendPhoto",
                files={"photo": (getattr(photo, "name", "image.png"), photo)},
                chat_id=chat_id,
                caption=caption,
                **kw,
            )
        return self.call("sendPhoto", chat_id=chat_id, photo=photo, caption=caption, **kw)

    def send_poll(
        self,
        chat_id: str | int,
        question: str,
        options: list[str],
        *,
        is_anonymous: bool = True,
        **kw: Any,
    ) -> dict:
        import json

        return self.call(
            "sendPoll",
            chat_id=chat_id,
            question=question,
            options=json.dumps(options, ensure_ascii=False),
            is_anonymous=is_anonymous,
            **kw,
        )

    def send_quiz(
        self, chat_id: str | int, question: str, options: list[str], correct: int, explanation: str
    ) -> dict:
        return self.send_poll(
            chat_id,
            question,
            options,
            type="quiz",
            correct_option_id=correct,
            explanation=explanation[:200],
        )

    def pin(self, chat_id: str | int, message_id: int) -> Any:
        return self.call("pinChatMessage", chat_id=chat_id, message_id=message_id,
                         disable_notification=True)

    # --- 수신 ---------------------------------------------------------------

    def get_updates(self, offset: int | None, timeout: int = 20) -> list[dict]:
        import json

        try:
            return self.call(
                "getUpdates",
                offset=offset,
                timeout=timeout,
                allowed_updates=json.dumps(ALLOWED_UPDATES),
            )
        except TelegramError as exc:
            log.warning("getUpdates: %s", exc)
            return []

    def get_me(self) -> dict:
        return self.call("getMe")

    # --- 파일 다운로드 --------------------------------------------------------

    def download_file_bytes(self, file_id: str) -> bytes:
        """구독자가 DM 으로 보낸 사진(file_id)의 실제 바이트를 받아온다.

        사진 위에 명언을 합성하려면 원본 픽셀이 필요하다. 다운로드한 바이트는
        합성 후 즉시 버려지며 디스크에 저장하지 않는다 (photos.py 의 저장 정책과 동일).
        """
        info = self.call("getFile", file_id=file_id)
        path = info["file_path"]
        url = f"https://api.telegram.org/file/bot{self._token}/{path}"
        try:
            resp = self._session.get(url, timeout=self._timeout)
            resp.raise_for_status()
        except Exception as exc:
            raise TelegramError(f"getFile 다운로드 실패: {self._redact(str(exc))}") from None
        return resp.content
