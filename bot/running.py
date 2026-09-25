"""마라톤 트래킹 — 1km → 풀코스(2027.11). 파라님 2026-09-25 (paracano 기획/20260925-오운완-마라톤-카드.md).

  카드는 전부 아침 06:00 (파라님 「텔 주는 시간은 항상 아침 6시」):
    월~금  오늘의 달리기 — 그 주 3회를 채웠으면 안 보낸다
    토·일  주중에 모자랐으면 보충 카드(주중 2회면 「한 번만 더」)
    월     지난주 요약 + 이번 주 처방
  기록은 날짜로 센다 — 새벽 5시에 달렸어도 그날 미션 완료다. 카드 시각과 무관.
  기록 길: 채널 버튼(주인만) · /run 3.2 28:40 · 스트라바 자동(30분마다, bot/strava.py)
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "content" / "running_plan.json"
GOALS = ROOT / "content" / "goals.json"
RUN_TYPES = {"Run", "TrailRun", "VirtualRun", "Treadmill"}
FEELS = {1: "😀 가뿐", 2: "😐 보통", 3: "😣 힘듦", 4: "🤕 아픔"}
BADGES = [(3.0, "첫 3km"), (5.0, "첫 5km"), (10.0, "첫 10km"), (21.0975, "첫 하프"), (42.195, "첫 풀코스")]

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL,
    day      TEXT NOT NULL,
    km       REAL NOT NULL,
    minutes  REAL,
    feel     INTEGER,
    source   TEXT NOT NULL,
    ext_id   TEXT UNIQUE,
    created  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_state (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def km_of(s: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*km", str(s))
    return float(m.group(1)) if m else 0.0


def stages() -> list[dict]:
    """goals.json 마라톤 단계 → [{차, km, 거리, 기한, 방법}]"""
    out = []
    for s in _load(GOALS).get("마라톤", {}).get("단계", []):
        out.append(dict(s, km=km_of(s["거리"])))
    return out


def bar(frac: float, n: int = 10) -> str:
    f = max(0.0, min(1.0, frac))
    k = round(f * n)
    return "▓" * k + "░" * (n - k)


class Running:
    def __init__(self, store, owner_id: int):
        self.store = store
        self.owner = owner_id
        with store._conn() as c:
            c.executescript(SCHEMA) if hasattr(c, "executescript") else None

    # --- 기록 ----------------------------------------------------------------

    def add(self, day: date, km: float, minutes: float | None = None, source: str = "button",
            ext_id: str | None = None, feel: int | None = None) -> bool:
        with self.store._conn() as c:
            if ext_id and c.execute("SELECT 1 FROM runs WHERE ext_id = ?", (ext_id,)).fetchone():
                return False
            c.execute("INSERT INTO runs (user_id, day, km, minutes, feel, source, ext_id, created) VALUES (?,?,?,?,?,?,?,?)",
                      (self.owner, day.isoformat(), km, minutes, feel, source, ext_id, datetime.now().isoformat()))
        return True

    def set_feel(self, day: date, feel: int) -> None:
        with self.store._conn() as c:
            row = c.execute("SELECT id FROM runs WHERE user_id = ? AND day = ? ORDER BY id DESC LIMIT 1",
                            (self.owner, day.isoformat())).fetchone()
            if row:
                c.execute("UPDATE runs SET feel = ? WHERE id = ?", (feel, row["id"]))

    def runs_between(self, a: date, b: date) -> list[dict]:
        with self.store._conn() as c:
            rows = c.execute("SELECT day, km, minutes, feel, source FROM runs WHERE user_id = ? AND day >= ? AND day <= ? ORDER BY day",
                             (self.owner, a.isoformat(), b.isoformat())).fetchall()
        return [dict(r) for r in rows]

    def run_days(self, a: date, b: date) -> list[str]:
        return sorted({r["day"] for r in self.runs_between(a, b)})

    def longest(self) -> float:
        with self.store._conn() as c:
            row = c.execute("SELECT MAX(km) m FROM runs WHERE user_id = ?", (self.owner,)).fetchone()
        return float(row["m"] or 0.0)

    def total(self) -> float:
        with self.store._conn() as c:
            row = c.execute("SELECT SUM(km) s FROM runs WHERE user_id = ?", (self.owner,)).fetchone()
        return float(row["s"] or 0.0)

    def state(self, k: str, default: str = "") -> str:
        with self.store._conn() as c:
            row = c.execute("SELECT v FROM run_state WHERE k = ?", (k,)).fetchone()
        return row["v"] if row else default

    def set_state(self, k: str, v: str) -> None:
        with self.store._conn() as c:
            c.execute("INSERT OR REPLACE INTO run_state (k, v) VALUES (?, ?)", (k, str(v)))

    # --- 단계·처방 --------------------------------------------------------------

    def stage(self) -> dict | None:
        """아직 못 넘은 첫 단계."""
        top = self.longest()
        for s in stages():
            if top < s["km"]:
                return s
        return None

    def week_index(self) -> int:
        return int(self.state("주차", "1") or 1)

    def prescription(self) -> dict:
        """이번 주 처방 {text, km}. 1단계는 표대로, 그 뒤는 긴 달리기를 주마다 늘리는 식."""
        s = self.stage()
        w = self.week_index()
        plan = _load(PLAN)
        if s is None:
            return {"text": "목표 달성 — 가볍게 유지 달리기 30~40분", "km": 5.0}
        weeks = plan.get(str(s["차"]), {}).get("주", [])
        if weeks:
            it = weeks[min(w, len(weeks)) - 1]
            return {"text": it["처방"], "km": float(it["km"])}
        g = plan.get(str(s["차"]), {})
        long_km = min(s["km"], float(g.get("긴시작", 5)) + float(g.get("긴늘림", 0.75)) * (w - 1))
        easy = max(3.0, round(long_km * 0.55 * 2) / 2)
        return {"text": f"쉬운 달리기 {easy:.1f}km ×2 · 주말 길게 {long_km:.1f}km", "km": easy}

    def advance_week(self, last_mon: date) -> str:
        """월요일마다 — 지난주 3회 채우고 힘듦 2회 미만·아픔 없으면 다음 주차. 아니면 같은 주차 한 번 더."""
        runs = self.runs_between(last_mon, last_mon + timedelta(days=6))
        days = {r["day"] for r in runs}
        hard = sum(1 for r in runs if r.get("feel") == 3)
        hurt = any(r.get("feel") == 4 for r in runs)
        stg = self.stage()
        prev_stage = self.state("단계", "")
        if stg and not prev_stage:
            self.set_state("단계", stg["차"])   # 처음 — 단계만 적고 주차는 아래 규칙대로
        elif stg and prev_stage != str(stg["차"]):
            self.set_state("단계", stg["차"])
            self.set_state("주차", 1)
            return "새 단계"
        if hurt:
            return "아픔 — 이번 주는 쉬어 가며 같은 단계"
        if len(days) >= 3 and hard < 2:
            self.set_state("주차", self.week_index() + 1)
            return "다음 주차"
        return "같은 주차 한 번 더"

    # --- 누적 거리 놀이(서울→부산) ------------------------------------------------

    def route(self) -> dict:
        r = _load(PLAN).get("누적", {})
        return {"이름": r.get("이름", "서울→부산"), "길이": float(r.get("길이", 400)), "도시": r.get("도시", [])}

    def passed_cities(self, before: float, after: float) -> list[str]:
        return [c["이름"] for c in self.route()["도시"] if before < c["km"] <= after]

    # --- 카드 글 -------------------------------------------------------------

    def week_status(self, today: date) -> tuple[int, list[str]]:
        mon = monday(today)
        days = self.run_days(mon, today)
        return len(days), days

    def morning_card(self, today: date) -> tuple[str, list] | None:
        """평일 06:00. 이번 주 3회를 채웠으면 None(안 보냄)."""
        n, days = self.week_status(today)
        today_runs = self.runs_between(today, today)
        if n >= 3 and not today_runs:
            return None
        p = self.prescription()
        s = self.stage()
        top = self.longest()
        head = f"🏃 오늘의 달리기 · {self.week_index()}주차 · 이번 주 {n}/3"
        goal = f"{s['차']}차 {s['거리']}까지 · 최장 {top:.1f}km" if s else "🏁 풀코스 달성!"
        if today_runs:
            km = sum(r["km"] for r in today_runs)
            text = f"{head}\n\n✅ 오늘 이미 {km:.1f}km — 미션 완료\n{goal}\n\n느낌은?"
            return text, self.feel_buttons()
        yday = today - timedelta(days=1)
        y = self.runs_between(yday, yday)
        ytxt = f"\n어제 {sum(r['km'] for r in y):.1f}km ✅" if y else ""
        # 파라님 9/25 「버튼은 몸무게처럼 6개」 — 달린 거리를 바로 누른다
        text = f"{head}\n\n{p['text']}\n(약 {p['km']:.1f}km){ytxt}\n{goal}\n\n달린 거리를 눌러 주세요 · 다른 거리는 봇에게 /run 4.2"
        return text, self.distance_buttons(p["km"])

    def weekend_card(self, today: date) -> tuple[str, list] | None:
        """토·일 06:00 — 이번 주 3회가 안 됐을 때만. 주중 2회면 「한 번만 더」."""
        n, days = self.week_status(today)
        if n >= 3:
            return None
        if today.weekday() == 6 and (today - timedelta(days=1)).isoformat() in days and n <= 1:
            return None   # 어제 보충했는데도 1회 이하 — 이틀 연속 무리는 권하지 않는다
        p = self.prescription()
        if n == 2:
            msg = "주중 2회 ✅ — 오늘 한 번만 더 하면 이번 주 완성"
        else:
            msg = f"이번 주 {n}회 — 주말에 채워 봐요 (이틀 연속 무리는 금지)"
        text = f"🏃 주말 보충 · 이번 주 {n}/3\n\n{msg}\n\n{p['text']}\n(약 {p['km']:.1f}km)\n\n달린 거리를 눌러 주세요 · 다른 거리는 봇에게 /run 4.2"
        return text, self.distance_buttons(p["km"])

    def weekly_text(self, today: date, note: str = "") -> str:
        """월 06:00 — 지난주 요약 + 이번 주 처방."""
        last_mon = monday(today) - timedelta(days=7)
        runs = self.runs_between(last_mon, last_mon + timedelta(days=6))
        days = len({r["day"] for r in runs})
        km = sum(r["km"] for r in runs)
        top = self.longest()
        s = self.stage()
        streak = int(self.state("연속주", "0") or 0)
        tot = self.total()
        rt = self.route()
        L = [f"📊 지난주 달리기  {days}/3회 {'✅' if days >= 3 else ''}".rstrip(),
             f"거리 {km:.1f}km · 최장 {top:.1f}km"]
        if s:
            L.append(f"{s['차']}차 {s['거리']}  {bar(top / s['km'])} {round(100 * top / s['km'])}%")
        L.append(f"목표 달성 연속 {streak}주{' 🔥' if streak >= 2 else ''}")
        L.append(f"누적 {tot:.1f}km — {rt['이름']} {round(100 * tot / rt['길이'])}%")
        p = self.prescription()
        L += ["", f"이번 주: {p['text']}" + (f"\n({note})" if note else "")]
        return "\n".join(L)

    def record_week_streak(self, last_mon: date) -> None:
        days = len(self.run_days(last_mon, last_mon + timedelta(days=6)))
        self.set_state("연속주", (int(self.state("연속주", "0") or 0) + 1) if days >= 3 else 0)

    def distance_buttons(self, p_km: float) -> list:
        base = max(0.5, round(p_km * 2) / 2)
        vals = sorted({max(0.5, base + d) for d in (-1.0, -0.5, 0, 0.5, 1.0, 1.5)})
        return [[{"text": f"{v:g}km", "callback_data": f"run:k:{v:g}"} for v in vals[:3]],
                [{"text": f"{v:g}km", "callback_data": f"run:k:{v:g}"} for v in vals[3:]]]

    def feel_buttons(self) -> list:
        return [[{"text": t, "callback_data": f"run:f:{k}"} for k, t in FEELS.items()]]

    def after_record(self, before_total: float, before_top: float, today: date) -> list[str]:
        """기록 뒤 채널에 알릴 것들 — 주 3회 달성 · 단계 달성 · 첫 거리 배지 · 도시 통과."""
        out = []
        n, _ = self.week_status(today)
        wk = monday(today).isoformat()
        if n >= 3 and self.state("수고주", "") != wk:
            self.set_state("수고주", wk)
            out.append("🎉 이번 주 3회 달성 — 수고했어요!\n나머지는 쉬세요. 다음 주 월요일에 봐요")
        top = self.longest()
        for km, name in BADGES:
            if before_top < km <= top:
                out.append(f"🏅 {name} 달성 — {top:.1f}km")
        for s in stages():
            if before_top < s["km"] <= top:
                left = (date.fromisoformat(s["기한"]) - today).days
                nxt = next((x for x in stages() if x["km"] > s["km"]), None)
                out.append(f"🎉 {s['차']}차 달성 — {s['거리']} 완주!\n"
                           + (f"목표일보다 {left}일 빨랐습니다\n" if left > 0 else "")
                           + (f"다음: {nxt['차']}차 {nxt['거리']} · ~{nxt['기한'][2:].replace('-', '.')}" if nxt else "🏁 최종 목표 달성!"))
        for c in self.passed_cities(before_total, self.total()):
            out.append(f"🚩 {c} 통과 — 누적 {self.total():.1f}km")
        return out
