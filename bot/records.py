"""달리기 기록실 — 야구처럼 기록을 무지무지 잰다. 파라님 2026-09-28
「기상천외한 기록들을 만들어. 월요일 연속 몇 회 등. 야구가 기록의 경기인 것처럼. 기록을 무지무지 만들어」.

  세션 = {"day": "2026-09-28", "hm": "20:28"|None, "km", "minutes", "hr", "steps", "kcal"}  (runs 표 한 줄 = 달리기 한 번)
  evaluate(before, new)  새 달리기 하나가 세운 기록들(글 줄). before = 넣기 전 전부.
  tagline(all, new)      매 달리기 알림에 붙는 야구 한 줄 — 안타 종류 · 시즌 타율 · 홈런 수
  board(all)             월요일 요약의 기록판

야구 말:
  안타 = 달린 날 · 타수 = 첫 달리기 날부터 오늘까지 날 수 → 타율 = 안타/타수
  한 번 거리로 단타(<2km) · 2루타(2~3) · 3루타(3~5) · 홈런(5km+)
  멀티히트 = 하루 두 번 이상 · 사이클링 히트 = 한 주에 단타·2루타·3루타·홈런 다
  개막전 = 매달 1일 달리기
"""
from __future__ import annotations

from datetime import date, timedelta

요일 = "월화수목금토일"
HITS = [(5.0, "홈런", 4), (3.0, "3루타", 3), (2.0, "2루타", 2), (0.0, "단타", 1)]
MAX_LINES = 10


def hit(km: float) -> tuple[str, int]:
    for lo, name, n in HITS:
        if km >= lo:
            return name, n
    return "단타", 1


def band(hm: str | None) -> str | None:
    if not hm:
        return None
    h = int(hm[:2])
    if 4 <= h < 7:
        return "새벽"
    if 7 <= h < 11:
        return "아침"
    if 11 <= h < 17:
        return "낮"
    if 17 <= h < 21:
        return "저녁"
    return "밤"


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _mon(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _pace(p: float) -> str:
    s = int(round(p * 60))
    return f"{s // 60}'{s % 60:02d}\""


def _sum(rows, key) -> dict:
    m: dict = {}
    for r in rows:
        k = key(r)
        m[k] = m.get(k, 0.0) + r["km"]
    return m


def _cnt(rows, key) -> dict:
    m: dict = {}
    for r in rows:
        k = key(r)
        m[k] = m.get(k, 0) + 1
    return m


def _streak_days(days: set, end: date) -> int:
    n = 0
    while (end - timedelta(days=n)).isoformat() in days:
        n += 1
    return n


def _max_streak(days: set) -> int:
    best = 0
    for d in days:
        if (_d(d) - timedelta(days=1)).isoformat() not in days:
            best = max(best, _run_len(days, _d(d)))
    return best


def _run_len(days: set, start: date) -> int:
    n = 0
    while (start + timedelta(days=n)).isoformat() in days:
        n += 1
    return n


def _crossed(before: float, after: float, marks) -> list:
    return [m for m in marks if before < m <= after]


def evaluate(before: list[dict], new: dict, 종목: str = "달리기") -> list[str]:
    """새 운동이 세운 기록들 — 중요한 것부터. 처음은 「첫 기록」 하나만.
    종목 = 「달리기」(야구 기록 포함) · 「걷기」(파라님 9/28 「걷기도 기록 재 줘」 — 야구는 달리기 전용)."""
    ball = 종목 == "달리기"
    if not before:
        return [f"🎉 역사적인 첫 {종목} — {종목} 기록실 개장"]
    out: list[str] = []
    after = before + [new]
    d, km, mins = new["day"], new["km"], new.get("minutes") or 0.0
    dd = _d(d)
    days_b = {r["day"] for r in before}
    first_today = d not in days_b
    wk = lambda r: _mon(_d(r["day"])).isoformat()
    mo = lambda r: r["day"][:7]

    # ── 거리 ────────────────────────────────────────────────
    one = max(r["km"] for r in before)
    if km > one:
        out.append(f"🏆 1회 최장 신기록 {km:.2f}km (전 {one:.2f})")
    day_b = _sum(before, lambda r: r["day"])
    tb = day_b.get(d, 0.0)
    if tb > 0 and tb + km > max(day_b.values()):
        out.append(f"🏆 하루 최장 신기록 {tb + km:.2f}km (전 {max(day_b.values()):.2f})")
    for label, key in (("주간", wk), ("월간", mo)):
        m = _sum(before, key)
        cur = key(new)
        past = [v for k, v in m.items() if k != cur]
        if past and m.get(cur, 0.0) <= max(past) < m.get(cur, 0.0) + km:
            out.append(f"🏆 {label} 최장 신기록 {m.get(cur, 0.0) + km:.2f}km (전 {max(past):.2f})")
    same_wd = [r["km"] for r in before if _d(r["day"]).weekday() == dd.weekday()]
    if same_wd and km > max(same_wd) and km <= one:
        out.append(f"📆 {요일[dd.weekday()]}요일 최장 {km:.2f}km (전 {max(same_wd):.2f})")

    # ── 속도·시간 ─────────────────────────────────────────────
    if mins and km >= 1.0:
        for lo in (1, 3, 5, 10, 21.0975):
            if km < lo:
                break
            ps = [r["minutes"] / r["km"] for r in before if r.get("minutes") and r["km"] >= lo]
            if ps and mins / km < min(ps):
                name = "하프" if lo > 20 else f"{lo}km+"
                out.append(f"⚡ {name} 최고 페이스 {_pace(mins / km)}/km (전 {_pace(min(ps))})")
    ms = [r["minutes"] for r in before if r.get("minutes")]
    if mins >= 10 and ms and mins > max(ms):
        out.append(f"⏱ 최장 시간 신기록 {int(mins)}분 (전 {int(max(ms))}분)")

    # ── 야구 ────────────────────────────────────────────────
    h, _ = hit(km)
    if not ball:
        pass
    elif h == "홈런":
        n = sum(1 for r in after if r["km"] >= 5.0)
        out.append(f"⚾ 시즌 {n}호 홈런! ({km:.2f}km)")
    elif h == "3루타":
        n = sum(1 for r in after if 3.0 <= r["km"] < 5.0)
        if n in (1, 5, 10, 20, 30, 50):
            out.append(f"⚾ 시즌 {n}번째 3루타")
    today_n = sum(1 for r in before if r["day"] == d) + 1
    if ball and today_n == 2:
        out.append("⚾ 멀티히트 경기 (하루 2번)")
    elif ball and today_n >= 3:
        out.append(f"⚾ 맹타 — 하루 {today_n}안타")
    cnt_b = _cnt(before, lambda r: r["day"])
    if today_n >= 2 and today_n > max(cnt_b.values()):
        out.append(f"🔁 하루 최다 {종목} 신기록 {today_n}번")
    week_hits_b = {hit(r["km"])[0] for r in before if wk(r) == wk(new)}
    if ball and len(week_hits_b) < 4 and len(week_hits_b | {h}) == 4:
        out.append("⚾🌈 사이클링 히트! (한 주에 단타·2루타·3루타·홈런)")
    if first_today and dd.day == 1:
        out.append(f"🎌 {dd.month}월 개막전 출전" + ("" if ball else f" ({종목})"))

    # ── 연속 ────────────────────────────────────────────────
    if first_today:
        days_a = days_b | {d}
        s = _streak_days(days_a, dd)
        best_b = _max_streak(days_b) if days_b else 0
        if s >= 2 and s > best_b:
            out.append(f"🔥 {s}일 연속 {종목} — 최장 연속 신기록" + (f" ({s}경기 연속 안타)" if ball else ""))
        elif s in (3, 5, 7, 10, 14, 21, 30, 50, 100):
            out.append(f"🔥 {s}일 연속 {종목}" + (f" ({s}경기 연속 안타)" if ball else ""))
        # 같은 요일 몇 주 연속
        n = 0
        while (dd - timedelta(weeks=n)).isoformat() in days_a:
            n += 1
        if n >= 2:
            out.append(f"📆 {요일[dd.weekday()]}요일 {n}주 연속 출석")
        # 복귀
        prev = max((x for x in days_b if x < d), default=None)
        if prev and (dd - _d(prev)).days >= 4:
            out.append(f"🦅 {(dd - _d(prev)).days}일 만의 {종목} 복귀 — 돌아온 파라")
        # 요일 그랜드슬램
        if len({_d(x).weekday() for x in days_b}) < 7 and len({_d(x).weekday() for x in days_a}) == 7:
            out.append(f"🗓 {종목} 요일 그랜드슬램 — 월~일 모든 요일")
        # 월요일 특별
        if dd.weekday() == 0:
            n = sum(1 for x in days_a if _d(x).weekday() == 0)
            if n in (1, 5, 10, 20, 30, 52):
                out.append(f"😤 월요병 격파 {n}회")
        # 주말 전사
        if dd.weekday() in (5, 6):
            other = (dd + timedelta(days=1 if dd.weekday() == 5 else -1)).isoformat()
            if other in days_b:
                n, sat = 0, dd - timedelta(days=dd.weekday() - 5)
                while (sat - timedelta(weeks=n)).isoformat() in days_a and (sat - timedelta(weeks=n) + timedelta(days=1)).isoformat() in days_a:
                    n += 1
                out.append(f"🛡 주말 전사 — 토·일 모두" + (f" {n}주 연속" if n >= 2 else ""))
        # 주간·월간 달린 날 최다
        for label, key in (("주간", wk), ("월간", mo)):
            db = {}
            for r in before:
                db.setdefault(key(r), set()).add(r["day"])
            cur = key(new)
            past = [len(v) for k, v in db.items() if k != cur]
            now = len(db.get(cur, set())) + 1
            if past and now == max(past) + 1:
                out.append(f"📅 {label} 최다 출석 {now}일")

    # 연속 거리 늘림 · 연속 페이스 향상 (달리기 순서대로)
    seq = after
    n = 1
    while n < len(seq) and seq[-n]["km"] > seq[-n - 1]["km"]:
        n += 1
    if n >= 3:
        out.append(f"📈 {n}연속 거리 늘림")
    pv = [r for r in after if r.get("minutes") and r["km"] >= 0.5]
    if pv and pv[-1] is new:
        n = 1
        while n < len(pv) and pv[-n]["minutes"] / pv[-n]["km"] < pv[-n - 1]["minutes"] / pv[-n - 1]["km"]:
            n += 1
        if n >= 3:
            out.append(f"🚀 {n}연속 페이스 단축")
    # 주간 거리 N주 연속 증가
    wsum = _sum(after, wk)
    ks = sorted(wsum)
    if len(ks) >= 2 and ks[-1] == wk(new):
        last = wsum[ks[-2]]
        if wsum[ks[-1]] - km <= last < wsum[ks[-1]]:
            n = 1
            while n < len(ks) and wsum[ks[-n]] > wsum[ks[-n - 1]] and (_d(ks[-n]) - _d(ks[-n - 1])).days == 7:
                n += 1
            if n >= 2:
                out.append(f"📊 주간 거리 {n - 1}주 연속 증가")

    # ── 시간대 ──────────────────────────────────────────────
    b = band(new.get("hm"))
    if b:
        bands_b = [band(r.get("hm")) for r in before if r.get("hm")]
        n = bands_b.count(b) + 1
        if n == 1:
            out.append(f"🆕 첫 {b} {종목}")
        elif n in (5, 10, 20, 30, 50, 100):
            titles = ({"새벽": "새벽의 지배자", "아침": "아침형 인간", "낮": "대낮의 질주자", "저녁": "퇴근길 러너", "밤": "밤의 추적자"} if ball else
                      {"새벽": "새벽 산책가", "아침": "아침 산보꾼", "낮": "점심 산책러", "저녁": "저녁 산책의 달인", "밤": "밤길 방랑자"})
            out.append(f"🕐 {b} {종목} {n}회 — {titles[b]}")
        if len(set(bands_b)) < 5 and len(set(bands_b) | {b}) == 5:
            out.append("🎡 시간대 사이클 — 새벽·아침·낮·저녁·밤 전부")
        hms = [r["hm"] for r in before if r.get("hm")]
        if hms and new["hm"] < min(hms) and int(new["hm"][:2]) >= 3:
            out.append(f"🌅 가장 이른 출발 {new['hm']} (전 {min(hms)})")
        if hms and new["hm"] > max(hms) and int(new["hm"][:2]) >= 18:
            out.append(f"🌙 가장 늦은 출발 {new['hm']} (전 {max(hms)})")

    # ── 몸 ─────────────────────────────────────────────────
    if new.get("hr") and km >= 1.0:
        hrs = [r["hr"] for r in before if r.get("hr") and r["km"] >= 1.0]
        if hrs and new["hr"] < min(hrs):
            out.append(f"🧘 가장 평온한 {종목} — 평균 심박 {new['hr']} (전 {min(hrs)})")
        if hrs and new["hr"] > max(hrs):
            out.append(f"❤️‍🔥 가장 불태운 {종목} — 평균 심박 {new['hr']} (전 {max(hrs)})")

    # ── 누적 ────────────────────────────────────────────────
    t = sum(r["km"] for r in before)
    for m in _crossed(t, t + km, (10, 25, 42.195, 50, 75, 100, 150, 200, 250, 300, 400, 500, 750, 1000, 2000)):
        out.append(f"🛣 누적 {'풀코스 한 번 분량(42.195km)' if m == 42.195 else f'{m}km'} 돌파")
    n = len(after)
    if n in (10, 25, 50, 100, 150, 200, 300, 500, 1000):
        out.append(f"🎖 통산 {n}번째 {종목}")
    if first_today and len(days_b) + 1 in (10, 20, 30, 50, 100, 200, 365):
        out.append(f"📅 통산 {len(days_b) + 1}일째 달린 날")
    tm = sum(r.get("minutes") or 0 for r in before) / 60
    for m in _crossed(tm, tm + mins / 60, (1, 3, 5, 10, 24, 50, 100)):
        out.append(f"⏳ {종목} 누적 {m}시간" + (" — 꼬박 하루를" if m == 24 else ""))
    kb = sum(r.get("kcal") or 0 for r in before)
    ka = kb + (new.get("kcal") or 0)
    for m in _crossed(kb, ka, range(2000, 200001, 2000)):
        out.append(f"🍗 누적 {m:,}kcal — 치킨 {m // 2000}마리 태움(약)")
    sb = sum(r.get("steps") or 0 for r in before)
    for m in _crossed(sb, sb + (new.get("steps") or 0), (10000, 50000, 100000, 250000, 500000, 1000000)):
        out.append(f"👣 {종목} 누적 {m:,}걸음")

    # ── 숫자 놀이 ─────────────────────────────────────────────
    s2 = f"{km:.2f}".replace(".", "")
    if len(set(s2)) == 1:
        out.append(f"🎰 럭키 거리 {km:.2f}km")
    elif s2 == s2[::-1] and len(s2) >= 3:
        out.append(f"🔄 대칭 거리 {km:.2f}km")
    if f"{km:.2f}" == f"{dd.month}.{dd.day:02d}":
        out.append(f"🤯 날짜 거리 — {dd.month}/{dd.day}에 {km:.2f}km")
    return out


def trim(lines: list[str]) -> list[str]:
    if len(lines) <= MAX_LINES:
        return lines
    return lines[:MAX_LINES] + [f"…외 {len(lines) - MAX_LINES}개 기록"]


def tagline(all_rows: list[dict], new: dict, today: date) -> str:
    """⚾ 2루타 · 시즌 타율 .667 (3타수 2안타) · 홈런 0"""
    days = {r["day"] for r in all_rows}
    first = min(_d(x) for x in days)
    ab = (today - first).days + 1
    avg = len(days) / ab if ab else 0
    hr = sum(1 for r in all_rows if r["km"] >= 5.0)
    a = f"{avg:.3f}".lstrip("0") if avg < 1 else "1.000"
    return f"⚾ {hit(new['km'])[0]} · 시즌 타율 {a} ({ab}타수 {len(days)}안타) · 홈런 {hr}"


def board(all_rows: list[dict], today: date) -> list[str]:
    """월요일 기록판."""
    if not all_rows:
        return []
    days = {r["day"] for r in all_rows}
    dsum = _sum(all_rows, lambda r: r["day"])
    wsum = _sum(all_rows, lambda r: _mon(_d(r["day"])).isoformat())
    L = ["", "🏆 기록실",
         f"1회 최장 {max(r['km'] for r in all_rows):.2f}km · 하루 {max(dsum.values()):.2f}km · 주간 {max(wsum.values()):.1f}km"]
    ps = [r["minutes"] / r["km"] for r in all_rows if r.get("minutes") and r["km"] >= 1.0]
    ms = [r["minutes"] for r in all_rows if r.get("minutes")]
    if ps:
        L.append(f"최고 페이스 {_pace(min(ps))}/km · 최장 시간 {int(max(ms))}분")
    L.append(f"최장 연속 {_max_streak(days)}일 · 통산 {len(all_rows)}번 · {len(days)}일")
    hits = _cnt(all_rows, lambda r: hit(r["km"])[0])
    L.append(tagline(all_rows, all_rows[-1], today).split(" · ", 1)[1]
             + f" · 단타 {hits.get('단타', 0)} · 2루타 {hits.get('2루타', 0)} · 3루타 {hits.get('3루타', 0)}")
    bands = _cnt([r for r in all_rows if r.get("hm")], lambda r: band(r["hm"]))
    if bands:
        L.append("시간대 " + " · ".join(f"{k} {v}" for k, v in sorted(bands.items(), key=lambda x: -x[1])))
    return L
