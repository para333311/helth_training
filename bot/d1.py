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

import requests


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

    def execute(self, sql: str, params: tuple = ()) -> _Cursor:
        resp = requests.post(
            self._url, headers=self._headers,
            json={"sql": sql, "params": list(params)}, timeout=20,
        )
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
