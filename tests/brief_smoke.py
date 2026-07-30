"""--brief flags 회귀 테스트.

    python tests/brief_smoke.py

의존성 없이 돈다. 임시 DB 를 만들어 flags 가 실제 데이터에 맞게 켜지는지 확인한다.
flags 가 틀리면 요약이 틀린 상태를 보여주므로, 여기가 가장 중요한 회귀 지점이다.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.brief import build_brief  # noqa: E402
from bot.store import Store  # noqa: E402

UID = 1423971696
TZ = ZoneInfo("Asia/Seoul")
TODAY = date(2026, 7, 30)
NOW = datetime(2026, 7, 30, 19, 0, tzinfo=TZ)

failures: list[str] = []


class FakeConfig:
    """load_config 를 거치지 않고 필요한 필드만 흉내낸다."""

    tz = TZ
    season_name = "3kg 프로젝트"
    season_days = 84
    goal_kg = 3.0
    owner_id = UID
    unsplash_key = ""
    pexels_key = ""

    def __init__(self, season_start: date):
        self.season_start = season_start

    def day_index(self, today: date) -> int:
        return (today - self.season_start).days + 1


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label}: {got!r} != {want!r}")
        failures.append(label)


def new_store() -> Store:
    tmp = Path(tempfile.mkdtemp()) / "t.db"
    return Store(tmp)


def case_fresh() -> None:
    """시즌 시작 6일째, 기록 하나도 없음."""
    print("\n[1] 빈 상태 — 시즌 시작 후 아무것도 안 함")
    cfg = FakeConfig(TODAY - timedelta(days=6))
    b = build_brief(cfg, new_store(), now=NOW)
    f = b["flags"]
    # 60일이 아니라 시즌 시작일까지만 세야 한다
    check("쉰 날이 시즌 시작일에서 멈춘다", b["missed_in_a_row"], 6)
    check("slipping", f["slipping"], True)
    check("done_today", f["done_today"], False)
    check("condition_stale", f["condition_stale"], True)
    check("weight_stale", f["weight_stale"], True)
    check("season_over", f["season_over"], False)
    check("D+n", b["season"]["day"], 7)


def case_streak_at_risk() -> None:
    """그저께까지 3일 하고 어제 빠짐 — 가장 중요한 개입 시점."""
    print("\n[2] 어제 빠짐 — streak_at_risk")
    cfg = FakeConfig(TODAY - timedelta(days=20))
    s = new_store()
    for i in (4, 3, 2):
        s.record_done(UID, TODAY - timedelta(days=i), tier="green")
    b = build_brief(cfg, s, now=NOW)
    check("쉰 날 1일", b["missed_in_a_row"], 1)
    check("streak_at_risk", b["flags"]["streak_at_risk"], True)
    check("slipping 아님", b["flags"]["slipping"], False)
    check("done_today 아님", b["flags"]["done_today"], False)

    # 오늘 하고 나면 더 이상 "끊길 위기"가 아니다.
    # missed 는 어제부터 세므로 오늘 기록해도 1로 남는다 — done_today 로 막아야 한다.
    s.record_done(UID, TODAY, tier="green")
    b = build_brief(cfg, s, now=NOW)
    check("오늘 한 뒤 done_today", b["flags"]["done_today"], True)
    check("오늘 한 뒤 streak_at_risk 꺼짐", b["flags"]["streak_at_risk"], False)


def case_slipping_cleared_today() -> None:
    """오래 쉬었어도 오늘 했으면 slipping 이 아니다."""
    print("\n[2-1] 오래 쉬다가 오늘 함 — slipping 해제")
    cfg = FakeConfig(TODAY - timedelta(days=20))
    s = new_store()
    s.record_done(UID, TODAY - timedelta(days=8), tier="green")
    b = build_brief(cfg, s, now=NOW)
    check("오늘 하기 전 slipping", b["flags"]["slipping"], True)

    s.record_done(UID, TODAY, tier="green")
    b = build_brief(cfg, s, now=NOW)
    check("오늘 한 뒤 slipping 꺼짐", b["flags"]["slipping"], False)
    check("done_today", b["flags"]["done_today"], True)


def case_on_fire() -> None:
    """5일 연속 — 칭찬 + 과훈련 경고."""
    print("\n[3] 5일 연속 — on_fire")
    cfg = FakeConfig(TODAY - timedelta(days=20))
    s = new_store()
    for i in range(4, -1, -1):
        s.record_done(UID, TODAY - timedelta(days=i), tier="yellow")
    b = build_brief(cfg, s, now=NOW)
    check("연속 5일", b["streak"]["current"], 5)
    check("on_fire", b["flags"]["on_fire"], True)
    check("done_today", b["flags"]["done_today"], True)
    check("쉰 날 0일", b["missed_in_a_row"], 0)
    check("최근7일 마지막칸 done", b["last_7_days"][-1]["done"], True)


def case_needs_rest() -> None:
    """컨디션 2 이하 3일 연속 — 🔴 말려야 한다."""
    print("\n[4] 컨디션 저조 3일 — needs_rest")
    cfg = FakeConfig(TODAY - timedelta(days=20))
    s = new_store()
    for i, score in enumerate([2, 1, 2]):
        s.record_condition(UID, TODAY - timedelta(days=i), score)
    b = build_brief(cfg, s, now=NOW)
    check("needs_rest", b["flags"]["needs_rest"], True)
    check("condition_stale 아님", b["flags"]["condition_stale"], False)
    check("최신 컨디션 2", b["condition"]["latest"]["score"], 2)
    check("7일 평균", b["condition"]["avg_7d"], 1.7)

    # 컨디션이 회복되면 flag 가 내려가야 한다
    s.record_condition(UID, TODAY, 4)
    b2 = build_brief(cfg, s, now=NOW)
    check("회복 후 needs_rest 해제", b2["flags"]["needs_rest"], False)


def case_weight() -> None:
    """체중 정체 판정 + stale 판정."""
    print("\n[5] 체중 — stalled / stale")
    cfg = FakeConfig(TODAY - timedelta(days=20))
    s = new_store()
    s.record_weight(UID, TODAY - timedelta(days=7), 79.0)
    s.record_weight(UID, TODAY, 78.9)  # 0.1kg 차이 → 정체
    b = build_brief(cfg, s, now=NOW)
    check("stalled", b["flags"]["weight_stalled"], True)
    check("stale 아님", b["flags"]["weight_stale"], False)
    check("baseline", b["weight"]["baseline_kg"], 79.0)
    check("감량", b["weight"]["lost_kg"], 0.1)

    # 9일 전에 잰 게 마지막이면 stale
    s2 = new_store()
    s2.record_weight(UID, TODAY - timedelta(days=9), 79.0)
    b2 = build_brief(cfg, s2, now=NOW)
    check("9일 전 → stale", b2["flags"]["weight_stale"], True)
    check("정체 판정 불가 (기록 1개)", b2["flags"]["weight_stalled"], False)


def case_published_today() -> None:
    """오늘 이미 발행한 잡을 구분해서, 같은 내용을 두 번 내보내지 않도록."""
    print("\n[6] 오늘 발행된 잡 목록")
    cfg = FakeConfig(TODAY - timedelta(days=20))
    s = new_store()
    s.mark_run("mission", datetime(2026, 7, 30, 7, 30, tzinfo=TZ))
    s.mark_run("photo", datetime(2026, 7, 30, 18, 0, tzinfo=TZ))
    s.mark_run("weekly", datetime(2026, 7, 26, 21, 0, tzinfo=TZ))  # 나흘 전 → 제외
    b = build_brief(cfg, s, now=NOW)
    check("오늘 것만", b["published_today"], ["mission", "photo"])


def case_season_over() -> None:
    print("\n[7] 시즌 종료 감지")
    cfg = FakeConfig(TODAY - timedelta(days=90))
    b = build_brief(cfg, new_store(), now=NOW)
    check("season_over", b["flags"]["season_over"], True)
    check("D+91", b["season"]["day"], 91)


def case_json_safe() -> None:
    """--json 출력이 깨지면 이 데이터를 쓰는 쪽이 전부 멈춘다."""
    print("\n[8] JSON 직렬화")
    import json

    cfg = FakeConfig(TODAY - timedelta(days=3))
    s = new_store()
    s.record_done(UID, TODAY, tier="red")
    s.record_condition(UID, TODAY, 5)
    s.record_weight(UID, TODAY, 77.5)
    raw = json.dumps(build_brief(cfg, s, now=NOW), ensure_ascii=False)
    back = json.loads(raw)
    check("왕복 가능", back["flags"]["done_today"], True)
    check("한글 유지", back["weekday"], "목")
    check("flag 개수", len(back["flags"]), 10)


def main() -> int:
    print("--brief flags 회귀 테스트")
    for fn in (case_fresh, case_streak_at_risk, case_slipping_cleared_today,
               case_on_fire, case_needs_rest,
               case_weight, case_published_today, case_season_over, case_json_safe):
        fn()

    print()
    if failures:
        print(f"실패 {len(failures)}건: {', '.join(failures)}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
