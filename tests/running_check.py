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
c = R.morning_card(mon); t("월 카드 나감 · 버튼 없음 · 삼성헬스 자동", c and c[1] == [] and "삼성헬스" in c[0])
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
R2.add(mon, 2); R2.add(mon + timedelta(days=1), 2)
R2.set_state("단계", 1)
t("2회 → 같은 주차", "같은 주차" in R2.advance_week(mon) and R2.week_index() == 1)

# 기록실 (파라님 9/28 「갱신하면 축하 · 기상천외한 기록 무지무지」)
from bot.records import evaluate, tagline, board, hit
K = Running(Store(Path(tempfile.mkdtemp()) / "k.db"), 1)
def run(d, km, mins, hm, hr=None, steps=None, kcal=None):
    new = {"day": d.isoformat(), "hm": hm, "km": km, "minutes": mins, "hr": hr, "steps": steps, "kcal": kcal}
    r = K.records(K.all_runs(), new); K.add(d, km, mins, "shealth", None, hm=hm, hr=hr, steps=steps, kcal=kcal)
    return r
d0 = date(2026, 9, 21)   # 월
t("첫 달리기 = 기록실 개장", any("개장" in x for x in run(d0, 1.9, 18.0, "18:28", 119, 1000, 143)))
r = run(d0 + timedelta(days=7), 0.8, 6.3, "05:44", 134)
t("짧게 한 번 — 1회 최장 아님", not any("1회 최장" in x for x in r))
t("월요일 2주 연속 출석", any("월요일 2주 연속" in x for x in r))
t("첫 새벽 달리기", any("첫 새벽" in x for x in r))
t("가장 이른 출발", any("가장 이른 출발 05:44" in x for x in r))
r = run(d0 + timedelta(days=7), 1.2, 9.0, "14:34", 127)
t("하루 합계 2.0 > 1.9 → 하루 최장", any("하루 최장" in x for x in r))
t("멀티히트", any("멀티히트" in x for x in r))
t("같은 날 두 번째 — 연속 축하 안 함", not any("연속 달리기" in x for x in r))
t("1km+ 최고 페이스", any("1km+ 최고 페이스" in x for x in r))
t("주간 최장 2.0 > 1.9", any("주간 최장" in x for x in r))
r = run(d0 + timedelta(days=8), 2.5, 25.0, "21:30", 150)
t("1회 최장 2.5", any("1회 최장" in x for x in r))
t("2일 연속 — 최장 연속 신기록", any("2일 연속" in x and "신기록" in x for x in r))
t("최장 시간 25분", any("최장 시간" in x for x in r))
t("가장 늦은 출발", any("가장 늦은 출발" in x for x in r))
t("가장 불태운 달리기(심박)", any("불태운" in x for x in r))
t("3연속 거리 늘림", any("3연속 거리" in x for x in r))
r = run(d0 + timedelta(days=9), 5.3, 50.0, "07:10")
t("시즌 1호 홈런", any("1호 홈런" in x for x in r))
t("누적 10km 돌파", any("누적 10km" in x for x in r))
t("시간대 사이클(아침으로 다섯 번째)", any("시간대 사이클" in x for x in r))
r = run(d0 + timedelta(days=9), 3.33, 30.0, "12:00")
t("럭키 거리 3.33", any("럭키" in x for x in r))
t("사이클링 히트(단타·2루타·3루타·홈런 한 주)", any("사이클링 히트" in x for x in r))
r = evaluate(K.all_runs(), {"day": "2026-10-01", "hm": "06:00", "km": 1.0, "minutes": 9.0})
t("개막전(1일)", any("10월 개막전" in x for x in r))
r = evaluate(K.all_runs(), {"day": "2026-10-10", "hm": "06:00", "km": 1.0, "minutes": 9.0})
t("복귀", any("일 만의 복귀" in x for x in r))
t("안타 종류", hit(1.0)[0] == "단타" and hit(2.1)[0] == "2루타" and hit(3.5)[0] == "3루타" and hit(5)[0] == "홈런")
tg = tagline(K.all_runs(), K.all_runs()[-1], d0 + timedelta(days=9))
t("타율 — 10타수 4안타 .400", "10타수 4안타" in tg and ".400" in tg)
t("기록실 판", any("1회 최장 5.30km" in x for x in board(K.all_runs(), d0 + timedelta(days=9))))
s = K.summary(d0 + timedelta(days=8))
t("요약: 오늘 2.5 · 이번 주 2회", abs(s["오늘km"] - 2.5) < 1e-9 and s["주회"] == 2)
t("누적 도시 통과", R.passed_cities(30, 40) == ["수원"])
print(f"{ok} OK, {bad} FAIL"); sys.exit(1 if bad else 0)
