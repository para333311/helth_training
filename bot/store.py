"""SQLite 저장소. 스트릭, 체중, 사진 순환, 잡 실행 이력, 리액션/투표 집계."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from .d1 import D1Connection

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

-- 컨디션 기록. /condition 1~5 DM 명령으로 직접 남긴다.
-- needs_rest 판단(컨디션 2 이하가 3일 연속)의 근거가 된다.
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


# 코드가 실제로 SELECT 하는 컬럼들. 스키마가 바뀐 뒤 기존 DB 를 열었을 때
# 어디가 어긋났는지 즉시 알기 위한 것이다.
EXPECTED_COLUMNS = {
    "users": {"user_id", "current_streak", "best_streak", "last_done"},
    "done_log": {"user_id", "day", "tier", "kind"},
    "weights": {"user_id", "day", "kg"},
    "conditions": {"user_id", "day", "score"},
    "job_runs": {"job", "last_run"},
    "submitted_photos": {"file_id", "user_id", "caption", "used"},
}


class SchemaMismatch(RuntimeError):
    pass


# claim_run() 이 "같은 슬롯을 노리는 두 번째 트리거"를 걸러내는 최소 간격.
# Render 상시 실행과 GitHub Actions --tick 이 몇 초~몇 분 차이로 겹쳐 들어오는
# 상황을 흡수할 만큼은 넉넉해야 하고, 가장 촘촘한 잡(사진, 30분 간격)의
# 진짜 다음 실행을 막지 않을 만큼은 짧아야 한다.
CLAIM_GAP = timedelta(minutes=5)


class Store:
    def __init__(self, path: Path, d1: D1Connection | None = None):
        """d1 을 주면 로컬 SQLite 파일 대신 Cloudflare D1(원격, 영구 저장)을 쓴다.

        Render 무료 플랜처럼 재시작마다 디스크가 초기화되는 환경에서, 로컬
        파일(path)에 의존하면 스트릭·제출 사진·순환 기록이 통째로 날아간다.
        d1 이 있으면 그 문제를 피해서 기록이 재시작을 넘어 유지된다.
        """
        self._d1 = d1
        if d1 is None:
            path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        with self._conn() as c:
            c.executescript(SCHEMA)
            self._verify_schema(c)

    @staticmethod
    def _verify_schema(conn) -> None:
        """기존 DB 가 지금 코드와 맞는지 확인한다.

        `CREATE TABLE IF NOT EXISTS` 는 이미 있는 테이블을 절대 고치지 않는다.
        그래서 스키마를 바꾼 뒤 옛 DB 를 열면 테이블 생성은 조용히 넘어가고,
        한참 뒤 엉뚱한 곳에서 "no such column: ..." 로 죽는다.
        여기서 미리 잡아서 무엇을 해야 하는지까지 알려준다.
        """
        problems = []
        for table, expected in EXPECTED_COLUMNS.items():
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            if not rows:
                continue  # 방금 만들어졌거나 아직 안 쓰는 테이블
            actual = {r["name"] for r in rows}
            missing = expected - actual
            if missing:
                problems.append(f"  {table}: {', '.join(sorted(missing))} 컬럼이 없음")

        if problems:
            raise SchemaMismatch(
                "DB 스키마가 지금 코드와 맞지 않습니다:\n"
                + "\n".join(problems)
                + "\n\n예전 버전이 만든 DB 입니다. 기록이 아깝지 않으면 지우고 다시 만드세요:\n"
                "  rm data/helth.db      (Windows: del data\\helth.db)\n"
                "기록을 살려야 하면 지우기 전에 파일을 복사해두고 알려주세요."
            )

    @contextmanager
    def _conn(self):
        if self._d1 is not None:
            yield self._d1
            return
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

    def claim_run(self, job: str, when: datetime) -> bool:
        """이 슬롯을 "내가 처리한다"고 원자적으로 선점한다.

        Render(상시 실행)와 GitHub Actions(외부 --tick)가 같은 job_runs 를
        같이 보게 되면서, 둘이 거의 동시에 같은 잡을 due 로 판단하고 둘 다
        발행해버리는 경합이 생길 수 있다. INSERT ... ON CONFLICT DO UPDATE ...
        WHERE 는 SQLite/D1 양쪽에서 단일 문장으로 원자 실행된다.

        WHERE 는 "새로 쓰려는 값보다 예전 것"이 아니라 "지금(when)보다
        CLAIM_GAP 이상 예전 것"인지를 본다 — 새 값과 비교하면 시간은 항상
        앞으로만 가므로 거의 항상 통과해버려서 아무것도 막지 못한다. 두
        트리거가 몇 초~몇 분 간격으로 같은 슬롯을 노리는 상황에서, 먼저
        선점한 기록이 아직 CLAIM_GAP 이내로 신선하면 뒤따라온 쪽은 조용히
        진다 — changes 로 그걸 구분해서 승자만 True 를 받는다.
        """
        boundary = (when - CLAIM_GAP).isoformat()
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO job_runs (job, last_run) VALUES (?, ?) "
                "ON CONFLICT(job) DO UPDATE SET last_run = excluded.last_run "
                "WHERE job_runs.last_run < ?",
                (job, when.isoformat(), boundary),
            )
        return cur.rowcount > 0

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
        month_start = today.replace(day=1)
        with self._conn() as c:
            row = c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            week = c.execute(
                "SELECT COUNT(*) n FROM done_log "
                "WHERE user_id = ? AND kind = 'done' AND day >= ?",
                (user_id, monday.isoformat()),
            ).fetchone()["n"]
            month = c.execute(
                "SELECT COUNT(*) n FROM done_log "
                "WHERE user_id = ? AND kind = 'done' AND day >= ?",
                (user_id, month_start.isoformat()),
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
            "week_days": today.weekday() + 1,   # 이번 주 경과일(월=1 ~ 일=7) — 진행바 분모
            "month": month,
            "month_days": today.day,            # 이번 달 경과일 — 진행바 분모
            "total": total,
        }

    def missing_recent_days(self, user_id: int, today: date, limit: int = 3) -> list[date]:
        """이번 주(월요일 ~ 어제) 중 기록이 아예 없는 날. 최근 날짜부터.

        체크인 버튼을 놓친 날을 나중에라도 채울 수 있게 캐치업 버튼을 만드는 데 쓴다.
        오늘은 포함하지 않는다 — 오늘은 지금 누른 버튼이 이미 채운다.
        지난주 이전으로는 넘어가지 않는다 — 너무 오래된 날짜까지 계속 들이밀면
        도움이 아니라 부담이 된다.
        """
        monday = today - timedelta(days=today.weekday())
        with self._conn() as c:
            rows = {
                r["day"] for r in c.execute(
                    "SELECT day FROM done_log WHERE user_id = ? AND day >= ? AND day < ?",
                    (user_id, monday.isoformat(), today.isoformat()),
                )
            }
        out: list[date] = []
        d = today - timedelta(days=1)
        while d >= monday:
            if d.isoformat() not in rows:
                out.append(d)
            d -= timedelta(days=1)
        return out[:limit]

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

    # --- 컨디션 --------------------------------------------------------------

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

    # --- 요약(--brief)용 조회 ---------------------------------------------------

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
        없는 첫날에 "60일 연속 쉬었다"가 나와서 엉뚱한 숫자가 표시된다.
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
        """오늘 이미 발행된 잡 이름. 같은 내용을 두 번 내보내지 않으려고 쓴다."""
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
