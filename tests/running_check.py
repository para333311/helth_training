"""마라톤 트래킹 논리 시험 — python tests/running_check.py (임시 DB)"""
import sys, tempfile
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot.store import Store
from bot.running import Running, monday

ok = bad = 0
def t(name, cond):
    global ok, bad
    print(("  o " if cond else "  X ") + name); ok += cond; bad += (not cond)

st = Store(Path(tempfile.mkdtemp()) / "t.db")
R = Running(st, 1)
mon = date(2026, 9, 28)   # 월
t("첫 주 처방 = 1주차", "1분 달리기" in R.prescription()["text"])
c = R.morning_card(mon); t("월 카드 나감 · 버튼 3개", c and len(c[1][0]) == 3)
R.add(mon, 2.0)   # 새벽 5시에 달린 것처럼 — 날짜만 본다
c = R.morning_card(mon); t("오늘 이미 달렸으면 「미션 완료」", c and "미션 완료" in c[0])
R.add(mon + timedelta(days=2), 2.2)
t("주중 2회 → 토 보충 「한 번만 더」", "한 번만 더" in R.weekend_card(mon + timedelta(days=5))[0])
news = (R.add(mon + timedelta(days=5), 3.1), R.after_record(4.2, 2.2, mon + timedelta(days=5)))[1]
t("3회 → 수고했어요", any("수고했어요" in n for n in news))
t("첫 3km 배지", any("첫 3km" in n for n in news))
R3 = Running(Store(Path(tempfile.mkdtemp()) / "v.db"), 1)
for i in range(3): R3.add(mon + timedelta(days=i), 2)
t("주중 3회 채우면 목요일 카드 없음", R3.morning_card(mon + timedelta(days=3)) is None)
t("3회면 주말 보충도 없음", R3.weekend_card(mon + timedelta(days=5)) is None)
t("다음 주 월 카드는 다시 나감", R.morning_card(mon + timedelta(days=7)) is not None)
R.record_week_streak(mon); note = R.advance_week(mon)
t("3회·무리 없음 → 다음 주차", R.week_index() == 2)
t("연속주 1", R.state("연속주") == "1")
R.add(mon + timedelta(days=8), 5.2)
news = R.after_record(9.3, 3.1, mon + timedelta(days=8))
t("5km 넘으면 1차 달성", any("1차 달성" in n for n in news))
t("다음 단계 = 2차", R.stage()["차"] == 2)
R2 = Running(Store(Path(tempfile.mkdtemp()) / "u.db"), 1)
R2.add(mon, 2, feel=4); R2.add(mon + timedelta(days=1), 2); R2.add(mon + timedelta(days=2), 2)
R2.set_state("단계", 1)
t("아픔 → 같은 주차", "아픔" in R2.advance_week(mon) and R2.week_index() == 1)
t("거리 버튼 6개", sum(len(r) for r in R.distance_buttons(3.0)) == 6)
t("누적 도시 통과", R.passed_cities(30, 40) == ["수원"])
print(f"{ok} OK, {bad} FAIL"); sys.exit(1 if bad else 0)
