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

-- 컨디션 기록. 마키마(코치)가 저녁에 물어보고 답을 여기 적는다.
-- 이 값이 있어야 "어제 2점이었는데 오늘도 했구나" 같은 말이 가능해진다.
CREATE TABLE IF NOT EXISTS conditions (
    user_id INTEGER NOT NULL,
    day     TEXT NOT NULL,
    score   INTEGER NOT NULL,          -- 1(최악) ~ 5(최상)
    note    TEXT,
    PRIMARY KEY (user_id, day)
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
            "week": week,
            "total": total,
        }

    # --- 체중 ---------------------------------------------------------------

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

    # --- 컨디션 (마키마가 물어보고 기록) --------------------------------------

    def record_condition(self, user_id: int, day: date, score: int,
                         note: str | None = None) -> None:
        score = max(1, min(5, int(score)))
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO conditions (user_id, day, score, note) "
                "VALUES (?, ?, ?, ?)",
                (user_id, day.isoformat(), score, note),
            )

    def recent_conditions(self, user_id: int, days: int = 7,
                          today: date | None = None) -> list[dict]:
        today = today or date.today()
        since = (today - timedelta(days=days - 1)).isoformat()
        with self._conn() as c:
            rows = c.execute(
                "SELECT day, score, note FROM conditions "
                "WHERE user_id = ? AND day >= ? ORDER BY day DESC",
                (user_id, since),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- 마키마(코치)용 조회 ---------------------------------------------------

    def recent_days(self, user_id: int, days: int = 7,
                    today: date | None = None) -> list[dict]:
        """최근 n일을 하루도 빠짐없이 채워서 돌려준다.

        기록이 없는 날은 done=False 로 명시된다. 빠진 날을 LLM 이 추측하게 두면
        "며칠 쉬었다"를 틀리게 말하므로, 여기서 확정해서 준다.
        """
        today = today or date.today()
        start = today - timedelta(days=days - 1)
        with self._conn() as c:
            rows = c.execute(
                "SELECT day, tier, kind FROM done_log WHERE user_id = ? AND day >= ?",
                (user_id, start.isoformat()),
            ).fetchall()
        by_day = {r["day"]: dict(r) for r in rows}
        out = []
        for i in range(days):
            d = start + timedelta(days=i)
            row = by_day.get(d.isoformat())
            out.append({
                "day": d.isoformat(),
                "done": bool(row and row["kind"] == "done"),
                "tier": row["tier"] if row else None,
            })
        return out

    def missed_in_a_row(self, user_id: int, today: date | None = None,
                        since: date | None = None) -> int:
        """오늘을 제외하고, 어제부터 거꾸로 며칠 연속 안 했는지.

        since (보통 시즌 시작일) 이전으로는 세지 않는다. 이게 없으면 기록이 하나도
        없는 첫날에 "60일 연속 쉬었다"가 나와서 코치가 엉뚱한 말을 하게 된다.
        """
        today = today or date.today()
        with self._conn() as c:
            rows = {
                r["day"] for r in c.execute(
                    "SELECT day FROM done_log WHERE user_id = ? AND kind = 'done'",
                    (user_id,),
                )
            }
        n = 0
        d = today - timedelta(days=1)
        while n < 60 and d.isoformat() not in rows:
            if since and d < since:
                break
            n += 1
            d -= timedelta(days=1)
        return n

    def weight_history(self, user_id: int, limit: int = 12) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT day, kg FROM weights WHERE user_id = ? ORDER BY day DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def weight_baseline(self, user_id: int) -> float | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT kg FROM weights WHERE user_id = ? ORDER BY day ASC LIMIT 1",
                (user_id,),
            ).fetchone()
        return row["kg"] if row else None

    def job_runs_today(self, today: date | None = None) -> list[str]:
        """오늘 이미 발행된 잡 이름. 코치가 같은 말을 두 번 하지 않게 하는 데 쓴다."""
        today = today or date.today()
        with self._conn() as c:
            rows = c.execute("SELECT job, last_run FROM job_runs").fetchall()
        out = []
        for r in rows:
            try:
                if datetime.fromisoformat(r["last_run"]).date() == today:
                    out.append(r["job"])
            except ValueError:
                continue
        return sorted(out)

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
