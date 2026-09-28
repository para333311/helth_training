"""걷기 기록실 — 걷기 운동(삼성헬스 WALKING·HIKING) + 하루 걸음. 파라님 2026-09-28 「걷기도 기록 재 줘」.

  walks 표      걷기 운동 한 번 = 한 줄(runs 와 같은 꼴). 기록은 records.evaluate(…, 종목="걷기") — 야구는 달리기 전용.
  steps_daily   하루 걸음 합계. 오늘 것은 15분마다 고쳐 쓰고, 만보·2만보를 넘는 순간 축하.
                어제 것은 아침(09시 뒤 첫 동기화)에 결산 — 하루 최다·만보 연속·요일·주·월·누적·7일 평균.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

요일 = "월화수목금토일"
SCHEMA = """
CREATE TABLE IF NOT EXISTS walks (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    day      TEXT NOT NULL,
    hm       TEXT,
    km       REAL NOT NULL,
    minutes  REAL,
    hr       INTEGER,
    steps    INTEGER,
    kcal     INTEGER,
    ext_id   TEXT UNIQUE,
    created  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS steps_daily (day TEXT PRIMARY KEY, steps INTEGER NOT NULL);
"""
GOAL = 10000
STEP_M = 0.7   # 한 걸음 약 0.7m — 재미용 환산


class Walking:
    def __init__(self, store):
        self.store = store
        with store._conn() as c:
            c.executescript(SCHEMA) if hasattr(c, "executescript") else None

    # --- 걷기 운동 ---------------------------------------------------------
    def add(self, w: dict, ext_id: str) -> bool:
        with self.store._conn() as c:
            if c.execute("SELECT 1 FROM walks WHERE ext_id = ?", (ext_id,)).fetchone():
                return False
            c.execute("INSERT INTO walks (day, hm, km, minutes, hr, steps, kcal, ext_id, created) VALUES (?,?,?,?,?,?,?,?,?)",
                      (w["day"], w.get("hm"), w["km"], w.get("minutes"), w.get("hr") or None, w.get("steps") or None,
                       w.get("kcal") or None, ext_id, datetime.now().isoformat()))
        return True

    def all(self) -> list[dict]:
        with self.store._conn() as c:
            rows = c.execute("SELECT day, hm, km, minutes, hr, steps, kcal FROM walks ORDER BY day, hm, id").fetchall()
        return [dict(r) for r in rows]

    # --- 하루 걸음 ---------------------------------------------------------
    def steps(self) -> dict:
        with self.store._conn() as c:
            return {r["day"]: int(r["steps"]) for r in c.execute("SELECT day, steps FROM steps_daily").fetchall()}

    def set_steps(self, d: date, n: int) -> int:
        """적고, 전에 적힌 값을 돌려준다."""
        old = self.steps().get(d.isoformat(), 0)
        if n > old:   # 파일은 하루 동안 늘기만 한다 — 줄어든 값(늦게 온 조각 파일)은 무시
            with self.store._conn() as c:
                c.execute("INSERT OR REPLACE INTO steps_daily (day, steps) VALUES (?, ?)", (d.isoformat(), n))
        return old


def _streak(ok: set, end: date) -> int:
    n = 0
    while (end - timedelta(days=n)).isoformat() in ok:
        n += 1
    return n


def _max_streak(ok: set) -> int:
    best = 0
    for d in ok:
        s = date.fromisoformat(d)
        if (s - timedelta(days=1)).isoformat() not in ok:
            n = 0
            while (s + timedelta(days=n)).isoformat() in ok:
                n += 1
            best = max(best, n)
    return best


def live(hist: dict, d: date, old: int, new: int) -> list[str]:
    """오늘 걸음이 문턱을 넘는 순간 — 만보·1.5만·2만·3만·4만."""
    out = []
    for m in (GOAL, 15000, 20000, 30000, 40000):
        if old < m <= new:
            ok = {k for k, v in hist.items() if v >= GOAL} | {d.isoformat()}
            s = _streak(ok, d)
            out.append(f"👣 {'만보' if m == GOAL else f'{m // 10000}만보' if m % 10000 == 0 else f'{m:,}보'} 돌파! 지금 {new:,}걸음"
                       + (f" · 만보 {s}일 연속" if s >= 2 else ""))
    return out


def settle(hist: dict, d: date) -> list[str]:
    """d(어제) 하루 걸음 결산 — 세운 기록들. hist 는 d 까지 포함한 {날: 걸음}."""
    n = hist.get(d.isoformat(), 0)
    ds = d.isoformat()
    past = {k: v for k, v in hist.items() if k < ds}
    out: list[str] = []
    if not past:
        return out
    if n > max(past.values()):
        out.append(f"🏆 하루 최다 걸음 신기록 {n:,}보 (전 {max(past.values()):,})")
    wd = [v for k, v in past.items() if date.fromisoformat(k).weekday() == d.weekday()]
    if wd and n > max(wd) and n <= max(past.values()):
        out.append(f"📆 {요일[d.weekday()]}요일 최다 걸음 {n:,}보 (전 {max(wd):,})")
    # 만보 연속
    ok = {k for k, v in hist.items() if v >= GOAL and k <= ds}
    if n >= GOAL:
        s = _streak(ok, d)
        best = _max_streak({k for k in ok if k < ds})
        if s >= 2 and s > best:
            out.append(f"🔥 만보 {s}일 연속 — 최장 연속 신기록")
        elif s in (3, 5, 7, 10, 14, 21, 30, 50, 100):
            out.append(f"🔥 만보 {s}일 연속")
        cnt = len(ok)
        if cnt in (5, 10, 20, 30, 50, 100, 200, 365):
            out.append(f"🎖 만보 통산 {cnt}일")
        mo = [k for k in ok if k[:7] == ds[:7]]
        if len(mo) in (10, 15, 20, 25) :
            out.append(f"📅 이번 달 만보 {len(mo)}일")
    for m, name in ((20000, "2만보"), (30000, "3만보"), (40000, "4만보")):
        if n >= m and not any(v >= m for v in past.values()):
            out.append(f"🆕 첫 {name} 달성")
    # 7일 평균 최고
    def avg7(end: date) -> float:
        vs = [hist.get((end - timedelta(days=i)).isoformat()) for i in range(7)]
        return sum(v for v in vs if v) / 7 if all(v is not None for v in vs) else 0
    a = avg7(d)
    prev = [avg7(date.fromisoformat(k)) for k in past]
    if a and prev and a > max(prev) and max(prev) > 0:
        out.append(f"📈 7일 평균 최고 {int(a):,}보 (전 {int(max(prev)):,})")
    # 주·월 합계 — 주는 일요일, 월은 말일에 결산
    if d.weekday() == 6:
        mon = d - timedelta(days=6)
        wk = sum(v for k, v in hist.items() if mon.isoformat() <= k <= ds)
        weeks: dict = {}
        for k, v in past.items():
            kk = date.fromisoformat(k)
            m0 = (kk - timedelta(days=kk.weekday())).isoformat()
            if m0 < mon.isoformat():
                weeks[m0] = weeks.get(m0, 0) + v
        if weeks and wk > max(weeks.values()):
            out.append(f"🏆 주간 최다 걸음 {wk:,}보 (전 {max(weeks.values()):,})")
    if (d + timedelta(days=1)).day == 1:
        mt = sum(v for k, v in hist.items() if k[:7] == ds[:7])
        months: dict = {}
        for k, v in past.items():
            if k[:7] < ds[:7]:
                months[k[:7]] = months.get(k[:7], 0) + v
        if months and mt > max(months.values()):
            out.append(f"🏆 월간 최다 걸음 {mt:,}보 (전 {max(months.values()):,})")
    # 누적
    tb = sum(past.values())
    for m in (100_000, 250_000, 500_000, 1_000_000, 2_000_000, 3_000_000, 5_000_000, 10_000_000):
        if tb < m <= tb + n:
            out.append(f"🛣 누적 {m // 10000}만 보 돌파 — 약 {m * STEP_M / 1000:,.0f}km 걸음")
    # 숫자 놀이
    s = str(n)
    if len(s) >= 4 and len(set(s)) == 1:
        out.append(f"🎰 럭키 걸음 {n:,}보")
    elif s in "0123456789" and len(s) >= 4:
        out.append(f"🔢 계단 걸음 {n:,}보")
    elif len(s) >= 4 and s == s[::-1]:
        out.append(f"🔄 대칭 걸음 {n:,}보")
    return out


def settle_text(hist: dict, d: date) -> str:
    n = hist.get(d.isoformat(), 0)
    week = [hist.get((d - timedelta(days=i)).isoformat(), 0) for i in range(7)]
    ok = {k for k, v in hist.items() if v >= GOAL and k <= d.isoformat()}
    head = f"👣 어제({d.month}/{d.day} {요일[d.weekday()]}) 걸음 {n:,}보" + (" ✅ 만보" if n >= GOAL else f" · 만보까지 {GOAL - n:,}")
    L = [head, f"· 7일 평균 {sum(week) // 7:,}보 · 약 {n * STEP_M / 1000:.1f}km · 만보 연속 {_streak(ok, d)}일"]
    rec = settle(hist, d)
    return "\n".join(L + ([""] + rec if rec else []))
