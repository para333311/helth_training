"""마키마(코치)가 발언 전에 읽는 요약 데이터.

`python -m bot --brief --json` 이 이 모듈의 출력이다.
숫자는 전부 여기서 계산해서 넘긴다 — 호출부(LLM)가 직접 세면 틀리기 쉽고,
틀린 숫자로 독려하면 신뢰가 깨진다는 게 secretary1/openclaw/coach-persona.md 의 전제다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .content import WEEKDAY_THEME

JOB_NAMES = [
    "mission", "photo", "quickfix", "quickfix_weekend",
    "quiz", "checkin", "weekly", "reset_day",
]

# coach-persona.md 의 flag 표와 1:1 대응.
WEIGHT_STALE_DAYS = 8
WEIGHT_STALLED_KG = 0.3
SLIPPING_DAYS = 3
ON_FIRE_STREAK = 5
NEEDS_REST_WINDOW = 3
NEEDS_REST_MAX_CONDITION = 2


@dataclass
class Brief:
    date: str
    day_index: int
    season_days: int
    theme: str
    streak: int
    best_streak: int
    week: int
    total: int
    condition_today: int | None
    weight_today: float | None
    flags: list[str] = field(default_factory=list)
    published_today: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "day_index": self.day_index,
            "season_days": self.season_days,
            "theme": self.theme,
            "streak": self.streak,
            "best_streak": self.best_streak,
            "week": self.week,
            "total": self.total,
            "condition_today": self.condition_today,
            "weight_today": self.weight_today,
            "flags": self.flags,
            "published_today": self.published_today,
        }


def _has_media_source(cfg, store) -> bool:
    if cfg.unsplash_key or cfg.pexels_key:
        return True
    if store.count_photos() > 0:
        return True
    if cfg.photo_dir.exists() and any(
        p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} for p in cfg.photo_dir.iterdir()
    ):
        return True
    return False


def build_brief(cfg, store, content, feeds, today: date) -> Brief:
    if not cfg.owner_id:
        raise ValueError(
            "OWNER_USER_ID 가 없습니다. --brief 는 누구 데이터를 읽을지 알아야 합니다."
        )

    uid = cfg.owner_id
    stats = store.stats(uid, today)
    d_index = cfg.day_index(today)
    theme = WEEKDAY_THEME[today.weekday()][1]

    done_today = store.done_on(uid, today)
    condition_today = store.condition_on(uid, today)
    last_weight = store.last_weight(uid)
    weight_today = last_weight[1] if last_weight and last_weight[0] == today else None

    flags: list[str] = []

    # gap: last_done 이후 며칠 지났는가. gap==1 이면 어제까지는 정상(오늘만 아직).
    # gap==2 면 정확히 어제 하루가 비었다 — 오늘이 그걸 만회할 마지막 기회.
    # gap>=3 이면 이미 여러 날 비었다 — 급한 회복보다 진입장벽을 낮추는 쪽.
    last_done = stats["last_done"]
    gap = (today - last_done).days if last_done else None

    if d_index > 1 and not done_today:
        if gap == 2:
            flags.append("streak_at_risk")
        elif gap is None or gap >= SLIPPING_DAYS:
            flags.append("slipping")

    if stats["streak"] >= ON_FIRE_STREAK:
        flags.append("on_fire")

    recent = store.recent_conditions(uid, today, NEEDS_REST_WINDOW)
    if all(c is not None and c <= NEEDS_REST_MAX_CONDITION for c in recent):
        flags.append("needs_rest")

    if condition_today is None:
        flags.append("condition_stale")

    if last_weight is None or (today - last_weight[0]).days >= WEIGHT_STALE_DAYS:
        flags.append("weight_stale")

    two = store.last_two_weights(uid)
    if len(two) == 2 and abs(two[0][1] - two[1][1]) < WEIGHT_STALLED_KG:
        flags.append("weight_stalled")

    if done_today:
        flags.append("done_today")

    if not _has_media_source(cfg, store):
        flags.append("no_media_source")

    if d_index > cfg.season_days:
        flags.append("season_over")

    return Brief(
        date=today.isoformat(),
        day_index=d_index,
        season_days=cfg.season_days,
        theme=theme,
        streak=stats["streak"],
        best_streak=stats["best"],
        week=stats["week"],
        total=stats["total"],
        condition_today=condition_today,
        weight_today=weight_today,
        flags=flags,
        published_today=store.published_today(JOB_NAMES, today),
    )


def render_text(brief: Brief) -> str:
    lines = [
        f"date: {brief.date}",
        f"day_index: {brief.day_index}/{brief.season_days}",
        f"theme: {brief.theme}",
        f"streak: {brief.streak} (best {brief.best_streak}, week {brief.week}/7, total {brief.total})",
        f"condition_today: {brief.condition_today if brief.condition_today is not None else '없음'}",
        f"weight_today: {brief.weight_today if brief.weight_today is not None else '없음'}",
        f"flags: {', '.join(brief.flags) if brief.flags else '(없음)'}",
        f"published_today: {', '.join(brief.published_today) if brief.published_today else '(없음)'}",
    ]
    return "\n".join(lines)
