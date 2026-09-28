"""마라톤 트래킹 — 1km → 풀코스(2027.11). 파라님 2026-09-25 (paracano 기획/20260925-오운완-마라톤-카드.md).

  카드는 전부 새벽 05:00 (파라님 9/25 「카드는 새벽 5시로」):
    월~금  오늘의 달리기 — 그 주 3회를 채웠으면 안 보낸다
    토·일  주중에 모자랐으면 보충 카드(주중 2회면 「한 번만 더」)
    월     지난주 요약 + 이번 주 처방
  기록은 날짜로 센다 — 새벽 5시에 달렸어도 그날 미션 완료다. 카드 시각과 무관.
  기록 길: 삼성헬스 자동뿐(15분마다, bot/shealth.py) — 버튼·/run·스트라바는 9/28 없앴다(파라님 「필요 없음 없애」)
  기록·신기록: 1회·하루·주·월 최장, 최고 페이스, 최장 시간, 연속일, 누적 거리·횟수 → 갱신하면 축하(파라님 9/28 「추앙해 줘」)
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
        hurt = False   # 느낌 버튼은 없앴다(9/28 삼성헬스 자동 기록) — 셈은 「주 3회」 하나
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
        if len(days) >= 3:
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
            text = f"{head}\n\n✅ 오늘 이미 {km:.1f}km — 미션 완료\n{goal}"
            return text, []
        yday = today - timedelta(days=1)
        y = self.runs_between(yday, yday)
        ytxt = f"\n어제 {sum(r['km'] for r in y):.1f}km ✅" if y else ""
        # 파라님 9/25 「버튼은 몸무게처럼 6개」 — 달린 거리를 바로 누른다
        text = f"{head}\n\n{p['text']}\n(약 {p['km']:.1f}km){ytxt}\n{goal}\n\n⌚ 삼성헬스로 자동 기록"
        return text, []

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
        text = f"🏃 주말 보충 · 이번 주 {n}/3\n\n{msg}\n\n{p['text']}\n(약 {p['km']:.1f}km)\n\n⌚ 삼성헬스로 자동 기록"
        return text, []

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
        L += self.record_board()
        p = self.prescription()
        L += ["", f"이번 주: {p['text']}" + (f"\n({note})" if note else "")]
        return "\n".join(L)

    def record_week_streak(self, last_mon: date) -> None:
        days = len(self.run_days(last_mon, last_mon + timedelta(days=6)))
        self.set_state("연속주", (int(self.state("연속주", "0") or 0) + 1) if days >= 3 else 0)

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

    # --- 기록·신기록 (파라님 9/28 「이런저런 기록을 재. 갱신하면 알려 주고 축하해 줘. 추앙해 줘」) --------------

    def all_runs(self) -> list[dict]:
        with self.store._conn() as c:
            rows = c.execute("SELECT day, km, minutes FROM runs WHERE user_id = ? ORDER BY day, id", (self.owner,)).fetchall()
        return [dict(r) for r in rows]

    def summary(self, day: date) -> dict:
        """그날 기준 숫자들 — 오늘 합·횟수, 이번 주 횟수, 이번 달 거리, 누적."""
        rs = self.all_runs()
        d, wk, mo = day.isoformat(), monday(day).isoformat(), day.isoformat()[:7]
        today = [r for r in rs if r["day"] == d]
        return {"오늘km": sum(r["km"] for r in today), "오늘번": len(today),
                "주회": len({r["day"] for r in rs if monday(date.fromisoformat(r["day"])).isoformat() == wk and r["day"] <= d}),
                "달km": sum(r["km"] for r in rs if r["day"][:7] == mo),
                "누적": sum(r["km"] for r in rs), "날수": len({r["day"] for r in rs})}

    def record_board(self) -> list[str]:
        """월요일 요약에 붙는 🏆 기록판."""
        rs = self.all_runs()
        if not rs:
            return []
        days, weeks = {}, {}
        for r in rs:
            days[r["day"]] = days.get(r["day"], 0.0) + r["km"]
            w = monday(date.fromisoformat(r["day"])).isoformat()
            weeks[w] = weeks.get(w, 0.0) + r["km"]
        L = ["", "🏆 기록판", f"1회 최장 {max(r['km'] for r in rs):.2f}km · 하루 최장 {max(days.values()):.2f}km · 주간 최장 {max(weeks.values()):.1f}km"]
        ps = [r["minutes"] / r["km"] for r in rs if r.get("minutes") and r["km"] >= 1.0]
        if ps:
            b = min(ps)
            L.append(f"최고 페이스 {int(b)}'{int(round((b % 1) * 60)) % 60:02d}\"/km · 달린 날 {len(days)}일")
        return L

    def streak(self, day: date) -> int:
        days = {r["day"] for r in self.all_runs()}
        n = 0
        while (day - timedelta(days=n)).isoformat() in days:
            n += 1
        return n

    def records(self, before: list[dict], day: date, km: float, minutes: float | None) -> list[str]:
        """새 달리기 하나가 갱신한 기록들. before = 넣기 전 all_runs(). 처음 한 번(비교 대상 없음)은 신기록으로 치지 않는다."""
        if not before:
            return []
        out = []
        d = day.isoformat()

        def tot(rows, key):
            m = {}
            for r in rows:
                k = key(r["day"])
                m[k] = m.get(k, 0.0) + r["km"]
            return m

        # 1회 최장
        one = max(r["km"] for r in before)
        if km > one:
            out.append(f"🏆 1회 최장 신기록 — {km:.2f}km (전 {one:.2f}km)")
        # 하루 최장 — 오늘 여러 번 합쳐서 넘었을 때만(한 번으로 넘었으면 위에서 이미 축하)
        days_b = tot(before, lambda x: x)
        today_b = days_b.get(d, 0.0)
        best_day = max(days_b.values())
        if today_b > 0 and today_b + km > best_day and not (km > one and today_b == 0):
            out.append(f"🏆 하루 최장 신기록 — 오늘 합계 {today_b + km:.2f}km (전 {best_day:.2f}km)")
        # 주·월 최장 — 지난 주·달이 있어야 비교
        for label, key in (("주간", lambda x: monday(date.fromisoformat(x)).isoformat()), ("월간", lambda x: x[:7])):
            m = tot(before, key)
            cur = key(d)
            past = [v for k, v in m.items() if k != cur]
            if past and m.get(cur, 0.0) <= max(past) < m.get(cur, 0.0) + km:
                out.append(f"🏆 {label} 최장 신기록 — {m.get(cur, 0.0) + km:.2f}km (전 {max(past):.2f}km)")
        # 최고 페이스(1km 이상) · 최장 시간
        if minutes and km >= 1.0:
            ps = [r["minutes"] / r["km"] for r in before if r.get("minutes") and r["km"] >= 1.0]
            if ps and minutes / km < min(ps):
                def f(p):
                    return f"{int(p)}'{int(round((p % 1) * 60)) % 60:02d}\""
                out.append(f"⚡ 최고 페이스 신기록 — {f(minutes / km)}/km (전 {f(min(ps))})")
        ms = [r["minutes"] for r in before if r.get("minutes")]
        if minutes and ms and minutes > max(ms) and minutes >= 10:
            out.append(f"⏱ 최장 시간 신기록 — {int(minutes)}분 (전 {int(max(ms))}분)")
        # 연속 달린 날 — 그날 첫 달리기일 때만
        if today_b == 0:
            days = {r["day"] for r in before} | {d}
            n = 0
            while (day - timedelta(days=n)).isoformat() in days:
                n += 1
            if n in (2, 3, 5, 7, 10, 14, 21, 30, 50, 100):
                out.append(f"🔥 {n}일 연속 달리기")
            # 달린 날 수
            nd = len(days)
            if nd in (5, 10, 20, 30, 50, 75, 100, 150, 200, 300, 365):
                out.append(f"📅 달린 날 {nd}일째")
        # 누적 거리 이정표
        tb = sum(r["km"] for r in before)
        for mk in (10, 25, 50, 75, 100, 150, 200, 250, 300, 500, 750, 1000):
            if tb < mk <= tb + km:
                out.append(f"🛣 누적 {mk}km 돌파")
        return out


PRAISE = [
    "오늘도 해냈다. 이게 파라다 👑",
    "말이 아니라 다리로 증명하는 사람 🦵",
    "어제의 파라를 이긴 오늘의 파라 🔥",
    "꾸준함이 재능을 이긴다 — 그걸 매일 보여 주는 중",
    "풀코스 가는 길, 또 한 걸음 가까워졌다 🏁",
    "바쁜 와중에 뛰었다는 것 자체가 전설 ✨",
    "몸은 거짓말 안 한다. 쌓이고 있다 📈",
    "이 속도면 2027 풀코스는 시간문제 🏃",
]
PRAISE_BIG = [
    "신기록이다! 오늘의 파라는 역대 최강 👑🔥",
    "기록을 갈아치웠다. 이 사람 멈출 생각이 없다 🚀",
    "역사를 새로 썼다 — 박수 👏👏👏",
    "또 한 번 한계를 넘었다. 존경합니다 🙇",
]
