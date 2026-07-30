"""SQLite 저장소. 스트릭, 체중, 사진 순환, 잡 실행 이력, 리액션/투표 집계."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY,
    name           TEXT,
    first_seen     TEXT NOT NULL,
    current_streak INTEGER NOT NULL DEFAULT 0,
    best_streak    INTEGER NOT NULL DEFAULT 0,
    last_done      TEXT
);

CREATE TABLE IF NOT EXISTS done_log (
    user_id INTEGER NOT NULL,
    day     TEXT NOT NULL,
    tier    TEXT NOT NULL DEFAULT 'green',
    kind    TEXT NOT NULL DEFAULT 'done',   -- done | skip
    PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS weights (
    user_id INTEGER NOT NULL,
    day     TEXT NOT NULL,
    kg      REAL NOT NULL,
    PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS job_runs (
    job      TEXT PRIMARY KEY,
    last_run TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seen_items (
    bucket TEXT NOT NULL,
    key    TEXT NOT NULL,
    seen   TEXT NOT NULL,
    PRIMARY KEY (bucket, key)
);

CREATE TABLE IF NOT EXISTS reactions (
    message_id INTEGER NOT NULL,
    emoji      TEXT NOT NULL,
    count      INTEGER NOT NULL,
    day        TEXT NOT NULL,
    PRIMARY KEY (message_id, emoji)
);

CREATE TABLE IF NOT EXISTS poll_results (
    poll_id TEXT PRIMARY KEY,
    day     TEXT NOT NULL,
    data    TEXT NOT NULL
);

-- 코치(마키마)가 물어서 받은 컨디션 자기평가. 1~5.
CREATE TABLE IF NOT EXISTS conditions (
    user_id INTEGER NOT NULL,
    day     TEXT NOT NULL,
    value   INTEGER NOT NULL,
    PRIMARY KEY (user_id, day)
);

-- 구독자가 봇 DM 으로 직접 보낸 오운완 사진.
-- file_id 만 저장하고 재전송하므로 이미지 파일을 따로 보관하지 않는다.
-- 본인이 /myphotos 로 언제든 전량 삭제(동의 철회)할 수 있어야 한다.
CREATE TABLE IF NOT EXISTS submitted_photos (
    file_id  TEXT PRIMARY KEY,
    user_id  INTEGER NOT NULL,
    caption  TEXT,
    created  TEXT NOT NULL,
    used     INTEGER NOT NULL DEFAULT 0
);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- 잡 실행 이력 --------------------------------------------------------

    def last_run(self, job: str) -> datetime | None:
        with self._conn() as c:
            row = c.execute("SELECT last_run FROM job_runs WHERE job = ?", (job,)).fetchone()
        return datetime.fromisoformat(row["last_run"]) if row else None

    def published_today(self, job_names: list[str], today: date) -> list[str]:
        """오늘 날짜에 last_run 이 찍힌 잡 이름들. tz 는 호출부가 이미 반영한 datetime 을 넘긴다는 전제."""
        done = []
        for name in job_names:
            when = self.last_run(name)
            if when and when.date() == today:
                done.append(name)
        return done

    def mark_run(self, job: str, when: datetime) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO job_runs (job, last_run) VALUES (?, ?) "
                "ON CONFLICT(job) DO UPDATE SET last_run = excluded.last_run",
                (job, when.isoformat()),
            )

    # --- 중복 방지 순환 (사진, 문구) ------------------------------------------

    def unseen(self, bucket: str, keys: list[str]) -> list[str]:
        """아직 안 쓴 키 목록. 전부 소진되면 버킷을 비우고 처음부터 다시."""
        if not keys:
            return []
        with self._conn() as c:
            seen = {r["key"] for r in c.execute(
                "SELECT key FROM seen_items WHERE bucket = ?", (bucket,))}
            remaining = [k for k in keys if k not in seen]
            if not remaining:
                c.execute("DELETE FROM seen_items WHERE bucket = ?", (bucket,))
                remaining = list(keys)
        return remaining

    def mark_seen(self, bucket: str, key: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO seen_items (bucket, key, seen) VALUES (?, ?, ?)",
                (bucket, key, datetime.now().isoformat()),
            )

    # --- 스트릭 -------------------------------------------------------------

    def ensure_user(self, user_id: int, name: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO users (user_id, name, first_seen) VALUES (?, ?, ?)",
                (user_id, name, datetime.now().isoformat()),
            )

    def record_done(self, user_id: int, today: date, tier: str = "green",
                    kind: str = "done") -> dict:
        """오늘 완료 기록. 스트릭 규칙은 04번 문서 참조 — 끊겨도 최고 기록은 남긴다."""
        with self._conn() as c:
            # users 행이 없으면 아래 UPDATE 가 0건이 되어 스트릭이 저장되지 않는다.
            # 호출 경로마다 ensure_user 를 기억하는 대신 여기서 보장한다.
            c.execute(
                "INSERT OR IGNORE INTO users (user_id, first_seen) VALUES (?, ?)",
                (user_id, datetime.now().isoformat()),
            )
            row = c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            last_done = date.fromisoformat(row["last_done"]) if row["last_done"] else None
            streak = row["current_streak"]
            best = row["best_streak"]

            already = c.execute(
                "SELECT 1 FROM done_log WHERE user_id = ? AND day = ?",
                (user_id, today.isoformat()),
            ).fetchone()

            if not already:
                if last_done == today - timedelta(days=1):
                    streak += 1
                elif last_done == today:
                    pass
                else:
                    streak = 1
                best = max(best, streak)

            c.execute(
                "INSERT OR REPLACE INTO done_log (user_id, day, tier, kind) VALUES (?, ?, ?, ?)",
                (user_id, today.isoformat(), tier, kind),
            )
            c.execute(
                "UPDATE users SET current_streak = ?, best_streak = ?, last_done = ? "
                "WHERE user_id = ?",
                (streak, best, today.isoformat(), user_id),
            )
        return {"streak": streak, "best": best, "already": bool(already)}

    def stats(self, user_id: int, today: date) -> dict:
        monday = today - timedelta(days=today.weekday())
        with self._conn() as c:
            row = c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            week = c.execute(
                "SELECT COUNT(*) n FROM done_log "
                "WHERE user_id = ? AND kind = 'done' AND day >= ?",
                (user_id, monday.isoformat()),
            ).fetchone()["n"]
            total = c.execute(
                "SELECT COUNT(*) n FROM done_log WHERE user_id = ? AND kind = 'done'",
                (user_id,),
            ).fetchone()["n"]
        return {
            "streak": row["current_streak"] if row else 0,
            "best": row["best_streak"] if row else 0,
            "last_done": date.fromisoformat(row["last_done"]) if row and row["last_done"] else None,
            "week": week,
            "total": total,
        }

    def done_on(self, user_id: int, day: date) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM done_log WHERE user_id = ? AND day = ? AND kind = 'done'",
                (user_id, day.isoformat()),
            ).fetchone()
        return row is not None

    # --- 컨디션 ---------------------------------------------------------------

    def record_condition(self, user_id: int, day: date, value: int) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO conditions (user_id, day, value) VALUES (?, ?, ?)",
                (user_id, day.isoformat(), value),
            )

    def condition_on(self, user_id: int, day: date) -> int | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT value FROM conditions WHERE user_id = ? AND day = ?",
                (user_id, day.isoformat()),
            ).fetchone()
        return row["value"] if row else None

    def recent_conditions(self, user_id: int, today: date, n_days: int) -> list[int | None]:
        """오늘부터 거꾸로 n_days 일. 기록 없는 날은 None."""
        return [self.condition_on(user_id, today - timedelta(days=i)) for i in range(n_days)]

    # --- 체중 ---------------------------------------------------------------

    def last_weight(self, user_id: int) -> tuple[date, float] | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT day, kg FROM weights WHERE user_id = ? ORDER BY day DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        return (date.fromisoformat(row["day"]), row["kg"]) if row else None

    def last_two_weights(self, user_id: int) -> list[tuple[date, float]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT day, kg FROM weights WHERE user_id = ? ORDER BY day DESC LIMIT 2",
                (user_id,),
            ).fetchall()
        return [(date.fromisoformat(r["day"]), r["kg"]) for r in rows]

    def record_weight(self, user_id: int, today: date, kg: float) -> tuple[float, float | None]:
        with self._conn() as c:
            first = c.execute(
                "SELECT kg FROM weights WHERE user_id = ? ORDER BY day ASC LIMIT 1", (user_id,)
            ).fetchone()
            c.execute(
                "INSERT OR REPLACE INTO weights (user_id, day, kg) VALUES (?, ?, ?)",
                (user_id, today.isoformat(), kg),
            )
        baseline = first["kg"] if first else kg
        return kg, (baseline - kg) if first else None

    # --- 채널 집계 (주간 결산용) ---------------------------------------------

    def record_reaction_count(self, message_id: int, day: date, counts: dict[str, int]) -> None:
        with self._conn() as c:
            for emoji, n in counts.items():
                c.execute(
                    "INSERT OR REPLACE INTO reactions (message_id, emoji, count, day) "
                    "VALUES (?, ?, ?, ?)",
                    (message_id, emoji, n, day.isoformat()),
                )

    def record_poll(self, poll_id: str, day: date, data: dict) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO poll_results (poll_id, day, data) VALUES (?, ?, ?)",
                (poll_id, day.isoformat(), json.dumps(data, ensure_ascii=False)),
            )

    # --- 구독자 제출 사진 -----------------------------------------------------

    def add_photo(self, file_id: str, user_id: int, caption: str | None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO submitted_photos (file_id, user_id, caption, created) "
                "VALUES (?, ?, ?, ?)",
                (file_id, user_id, caption, datetime.now().isoformat()),
            )

    def submitted_photos(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT file_id, user_id, caption, used FROM submitted_photos "
                "ORDER BY used ASC, created ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_photo_used(self, file_id: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE submitted_photos SET used = used + 1 WHERE file_id = ?", (file_id,))

    def count_photos(self, user_id: int | None = None) -> int:
        with self._conn() as c:
            if user_id is None:
                row = c.execute("SELECT COUNT(*) n FROM submitted_photos").fetchone()
            else:
                row = c.execute(
                    "SELECT COUNT(*) n FROM submitted_photos WHERE user_id = ?", (user_id,)
                ).fetchone()
        return row["n"]

    def delete_user_photos(self, user_id: int) -> int:
        """동의 철회. 본인이 보낸 사진을 전량 삭제한다."""
        with self._conn() as c:
            cur = c.execute("DELETE FROM submitted_photos WHERE user_id = ?", (user_id,))
            return cur.rowcount

    def week_summary(self, today: date) -> dict:
        start = (today - timedelta(days=6)).isoformat()
        with self._conn() as c:
            reacts = c.execute(
                "SELECT emoji, SUM(count) n FROM reactions WHERE day >= ? GROUP BY emoji",
                (start,),
            ).fetchall()
            polls = c.execute(
                "SELECT data FROM poll_results WHERE day >= ?", (start,)
            ).fetchall()
            active = c.execute(
                "SELECT COUNT(DISTINCT user_id) n FROM done_log "
                "WHERE kind = 'done' AND day >= ?",
                (start,),
            ).fetchone()["n"]
            done_total = c.execute(
                "SELECT COUNT(*) n FROM done_log WHERE kind = 'done' AND day >= ?", (start,)
            ).fetchone()["n"]

        tiers = {"🟢": 0, "🟡": 0, "🔴": 0, "😮‍💨": 0}
        for row in polls:
            data = json.loads(row["data"])
            for opt in data.get("options", []):
                for key in tiers:
                    if opt.get("text", "").startswith(key):
                        tiers[key] += opt.get("voter_count", 0)

        return {
            "reactions": {r["emoji"]: r["n"] for r in reacts},
            "tiers": tiers,
            "active_users": active,
            "done_total": done_total,
        }
