"""단계별 목표(몸무게·마라톤) 카드와 주간 몸무게 버튼. 파라님 2026-09-25.

  goals_text(store, owner)   목표 카드 글(지금 단계·남은 양 표시)
  weight_card(last)          주간 몸무게 카드의 버튼 — 마지막 기록 ±0.5 단위
  callback "wt:<kg>"         주인만 기록(채널 버튼이라 다른 구독자가 눌러도 안 적힌다)
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

GOALS = Path(__file__).resolve().parent.parent / "content" / "goals.json"


def load() -> dict:
    try:
        return json.loads(GOALS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def 다음단계(kg: float, g: dict) -> dict | None:
    for s in g.get("몸무게", {}).get("단계", []):
        if kg > s["kg"]:
            return s
    return None


def 날(d: str) -> str:
    y, m, dd = d.split("-")
    return f"{y[2:]}.{int(m)}.{int(dd)}"


def goals_text(last_kg: float | None, longest_km: float = 0.0) -> str:
    g = load()
    w, r = g.get("몸무게", {}), g.get("마라톤", {})
    now = last_kg if last_kg is not None else w.get("시작")
    nxt = 다음단계(now, g) if now is not None else None
    L = ["🎯 2027 목표", "", f"⚖️ 몸무게  지금 {now:.1f}kg"]
    for s in w.get("단계", []):
        mark = "✅" if now is not None and now <= s["kg"] else ("👉" if s is nxt else "·")
        L.append(f"{mark} {s['차']}차 {s['kg']:.0f}kg  ~{날(s['기한'])}")
    if nxt:
        L.append(f"   다음까지 {now - nxt['kg']:.1f}kg")
    from .running import km_of
    지금 = f"최장 {longest_km:.1f}km" if longest_km else r.get("시작", "")
    L += ["", f"🏃 마라톤  지금 {지금}"]
    first_open = True
    for s in r.get("단계", []):
        done = longest_km >= km_of(s["거리"])
        mark = "✅" if done else ("👉" if first_open else "·")
        if not done:
            first_open = False
        L.append(f"{mark} {s['차']}차 {s['거리']}  ~{날(s['기한'])}")
        L.append(f"   {s['방법']}")
    return "\n".join(L)


def weight_buttons(last: float) -> list[list[dict]]:
    def b(v: float) -> dict:
        return {"text": f"{v:.1f}", "callback_data": f"wt:{v:.1f}"}
    base = round(last * 2) / 2
    return [[b(base - 1.5), b(base - 1.0), b(base - 0.5)],
            [b(base), b(base + 0.5), b(base + 1.0)]]
