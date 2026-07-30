"""내 운동 데이터 스냅샷.

    python -m bot --brief          터미널에서 읽는 형태
    python -m bot --brief --json   프로그램이 읽는 형태

지금 상태를 한 화면으로 보는 용도다. 연속 며칠인지, 며칠 쉬었는지, 체중을 잰 지
얼마나 됐는지를 매번 손으로 세지 않아도 된다.

날짜 계산과 판단은 전부 여기서 끝내서 flags 로 내보낸다. 읽는 쪽은 flags 만
보면 되므로, 나중에 이 출력을 다른 도구에 물리더라도 같은 계산을 다시
구현할 필요가 없다.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from .content import WEEKDAY_THEME

# 이 일수 이상 체중을 안 재면 stale 로 본다. 주 1회(일요일) 원칙이라 8일.
WEIGHT_STALE_DAYS = 8

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def build_brief(cfg, store, content=None, feeds=None,
                now: datetime | None = None) -> dict:
    now = now or datetime.now(cfg.tz)
    today: date = now.date()
    uid = cfg.owner_id

    stats = store.stats(uid, today) if uid else {"streak": 0, "best": 0, "week": 0, "total": 0}
    last7 = store.recent_days(uid, 7, today) if uid else []
    missed = store.missed_in_a_row(uid, today, since=cfg.season_start) if uid else 0
    conds = store.recent_conditions(uid, 7, today) if uid else []
    weights = store.weight_history(uid, 12) if uid else []
    baseline = store.weight_baseline(uid) if uid else None

    cond_scores = [c["score"] for c in conds]
    cond_latest = conds[0] if conds else None
    cond_avg = round(sum(cond_scores) / len(cond_scores), 1) if cond_scores else None

    latest_w = weights[0] if weights else None
    lost = round(baseline - latest_w["kg"], 1) if (baseline and latest_w) else None
    days_since_weigh = None
    if latest_w:
        days_since_weigh = (today - date.fromisoformat(latest_w["day"])).days

    # 최근 2회 체중 비교 — 정체 판단용
    stalled = False
    if len(weights) >= 2:
        stalled = abs(weights[0]["kg"] - weights[1]["kg"]) < 0.3

    day_index = cfg.day_index(today)
    weekday = today.weekday()

    brief = {
        "generated_at": now.isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "weekday": WEEKDAY_KO[weekday],
        "theme": WEEKDAY_THEME.get(weekday, ("", ""))[1],
        "season": {
            "name": cfg.season_name,
            "day": day_index,
            "total_days": cfg.season_days,
            "week": max(1, (day_index - 1) // 7 + 1),
            "goal_kg": cfg.goal_kg,
        },
        "streak": {"current": stats["streak"], "best": stats["best"]},
        "week_done": stats["week"],
        "total_done": stats["total"],
        "missed_in_a_row": missed,
        "last_7_days": last7,
        "condition": {
            "latest": cond_latest,
            "avg_7d": cond_avg,
            "log": conds,
        },
        "weight": {
            "latest_kg": latest_w["kg"] if latest_w else None,
            "measured_on": latest_w["day"] if latest_w else None,
            "days_since_weigh": days_since_weigh,
            "baseline_kg": baseline,
            "lost_kg": lost,
            "history": weights,
        },
        "published_today": store.job_runs_today(today),
        "sources": {
            "youtube_channels": len(feeds.channels()) if feeds else 0,
            "my_photos": store.count_photos(),
            "stock_api": bool(cfg.unsplash_key or cfg.pexels_key),
        },
    }

    # missed 는 오늘을 빼고 어제부터 거꾸로 센다. 그래서 오늘 이미 했더라도
    # 어제 안 했으면 missed 는 1 이상이다. 아래 두 플래그를 done_today 로
    # 막지 않으면 "오늘 끊긴다"와 "오늘 이미 했다"가 동시에 켜진다.
    done_today = bool(last7 and last7[-1]["done"])

    # --- 판단은 여기서 확정한다. 읽는 쪽은 해석만 하면 된다. ---
    brief["flags"] = {
        # 3일 이상 쉬었고 오늘도 아직 안 했다 → 진입장벽을 최저로
        "slipping": missed >= 3 and not done_today,
        # 어제 안 했고 오늘도 아직 → 오늘 하면 이어진다. 가장 중요한 개입 시점
        "streak_at_risk": missed == 1 and not done_today,
        # 5일 이상 연속 → 과훈련을 같이 경계한다
        "on_fire": stats["streak"] >= 5,
        # 컨디션 2 이하가 3일 이상 → 🔴은 피하고 쉬는 쪽으로
        "needs_rest": len(cond_scores) >= 3 and all(s <= 2 for s in cond_scores[:3]),
        # 오늘 컨디션 기록이 없다 → /condition 으로 남기면 꺼진다
        "condition_stale": not conds or conds[0]["day"] != today.isoformat(),
        # 체중을 8일 이상 안 쟀다
        "weight_stale": days_since_weigh is None or days_since_weigh >= WEIGHT_STALE_DAYS,
        # 체중 정체 → 운동보다 270kcal(식사) 쪽 문제다
        "weight_stalled": stalled,
        # 오늘 오운완이 기록됐다
        "done_today": done_today,
        # 자극 소스가 없어 텍스트만 나가는 상태
        "no_media_source": (
            brief["sources"]["youtube_channels"] == 0
            and brief["sources"]["my_photos"] == 0
            and not brief["sources"]["stock_api"]
        ),
        "season_over": day_index > cfg.season_days,
    }
    return brief


def _bar(done: bool) -> str:
    return "■" if done else "·"


def format_brief(b: dict) -> str:
    """터미널에서 눈으로 확인할 때 쓰는 형태."""
    s, w, c, f = b["season"], b["weight"], b["condition"], b["flags"]
    week_line = "".join(_bar(d["done"]) for d in b["last_7_days"])

    lines = [
        f"{b['today']} ({b['weekday']}) · {b['theme']}",
        f"{s['name']}  D+{s['day']}/{s['total_days']}  {s['week']}주차",
        "",
        f"연속        {b['streak']['current']}일 (최고 {b['streak']['best']}일)",
        f"이번 주     {b['week_done']}/7      최근7일 {week_line}",
        f"누적        {b['total_done']}일",
    ]
    if b["missed_in_a_row"]:
        lines.append(f"쉰 날       어제부터 {b['missed_in_a_row']}일 연속")

    if c["latest"]:
        lines.append(f"컨디션      {c['latest']['score']}/5 ({c['latest']['day']})"
                     + (f"  7일 평균 {c['avg_7d']}" if c["avg_7d"] else ""))
    else:
        lines.append("컨디션      기록 없음")

    if w["latest_kg"]:
        lost = f"  −{w['lost_kg']}kg" if w["lost_kg"] else ""
        lines.append(f"체중        {w['latest_kg']}kg ({w['measured_on']}, "
                     f"{w['days_since_weigh']}일 전){lost}")
    else:
        lines.append("체중        기록 없음")

    on = [k for k, v in f.items() if v]
    lines += ["", "flags: " + (", ".join(on) if on else "없음")]
    if b["published_today"]:
        lines.append("오늘 발행: " + ", ".join(b["published_today"]))
    return "\n".join(lines)


def dump_json(b: dict) -> str:
    return json.dumps(b, ensure_ascii=False, indent=2)
