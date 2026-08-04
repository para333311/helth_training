"""Cloudflare D1 REST API 를 sqlite3 Connection/Cursor 인터페이스처럼 감싼다.

store.py 는 sqlite3 를 직접 쓰도록 짜여 있다. Render 무료 플랜은 영구 디스크가
없어서 로컬 SQLite 파일(data/helth.db)이 재시작마다 초기화되는데, 이 클래스를
_conn() 에 끼워 넣으면 store.py 의 SQL 코드를 한 줄도 안 바꾸고 D1(원격,
영구 저장)로 그대로 돌릴 수 있다.

D1 REST API 는 호출마다 독립된 HTTP 요청이라 sqlite3 같은 진짜 트랜잭션
(BEGIN/COMMIT/ROLLBACK)은 없다. 이 봇은 사용자 1~2명 규모라 동시쓰기 충돌
위험이 사실상 없으므로 감수한다.
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger("d1")

# (연결, 응답) 제한 시간. 예전에 20초 단일 타임아웃을 썼다가 Cloudflare 응답이
# 느려진 순간 메인 루프가 오래 막혀 있었고(ReadTimeout 로그 확인됨), 그 여파로
# 봇 전체가 응답 없는 상태로 몇 시간씩 굳어버린 적이 있다. 짧게 끊고 재시도하는
# 편이 오래 막혀 있는 것보다 안전하다.
TIMEOUT = (5, 10)
RETRIES = 1
RETRY_BACKOFF = 1.5


class D1Error(RuntimeError):
    pass


class _Cursor:
    def __init__(self, rows: list[dict], rowcount: int):
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self) -> dict | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict]:
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class D1Connection:
    """sqlite3.Connection 대체품. execute/executescript 만 store.py 가 실제로 쓴다."""

    def __init__(self, account_id: str, database_id: str, api_token: str):
        self._url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/d1/database/{database_id}/query"
        )
        self._headers = {"Authorization": f"Bearer {api_token}"}

    def _post_with_retry(self, sql: str, params: tuple) -> requests.Response:
        for attempt in range(1, RETRIES + 2):
            try:
                return requests.post(
                    self._url, headers=self._headers,
                    json={"sql": sql, "params": list(params)}, timeout=TIMEOUT,
                )
            except requests.exceptions.RequestException as exc:
                if attempt > RETRIES:
                    raise
                log.warning("D1 요청 실패(%d/%d), %.1f초 후 재시도: %s",
                            attempt, RETRIES, RETRY_BACKOFF * attempt, exc)
                time.sleep(RETRY_BACKOFF * attempt)

    def execute(self, sql: str, params: tuple = ()) -> _Cursor:
        resp = self._post_with_retry(sql, params)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise D1Error(f"D1 쿼리 실패: {data.get('errors')} · sql={sql[:80]}")

        result = (data.get("result") or [{}])[0]
        rows = result.get("results") or []
        meta = result.get("meta") or {}
        return _Cursor(rows, meta.get("changes", 0))

    def executescript(self, script: str) -> None:
        # D1 REST API 는 호출당 statement 하나만 받으므로 세미콜론으로 쪼갠다.
        for stmt in script.split(";"):
            stmt = stmt.strip()
            if stmt:
                self.execute(stmt)

    def commit(self) -> None:
        pass  # 호출마다 즉시 반영되므로 커밋할 게 없다

    def close(self) -> None:
        pass
