"""콘텐츠 재고 로딩 + 메시지 렌더링."""

from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

WEEKDAY_THEME = {
    0: ("월요일", "리부트"),
    1: ("화요일", "하체"),
    2: ("수요일", "코어"),
    3: ("목요일", "유산소"),
    4: ("금요일", "상체"),
    5: ("토요일", "챌린지"),
    6: ("일요일", "리셋"),
}

FOOTER = "────────\n하나라도 했으면 💪"


class Content:
    def __init__(self, data_dir: Path):
        self._dir = data_dir
        self.missions = self._load("missions.json")
        self.quick_fixes = self._load("quick_fixes.json")
        self.kcal_cards = self._load("kcal_cards.json")
        self.quizzes = self._load("quizzes.json")
        self.photo_captions = self._load("photo_captions.json")
        self.quotes = self._load("quotes.json")
        self.hyrox = self._load("hyrox.json")

    def _load(self, name: str) -> list:
        path = self._dir / name
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    # --- 선택 ---------------------------------------------------------------

    def mission_for(self, day: date, rotation: int = 0) -> dict | None:
        """요일 테마에 맞는 미션. rotation 으로 주차별로 다른 걸 고른다."""
        theme = WEEKDAY_THEME[day.weekday()][1]
        pool = [m for m in self.missions if m.get("theme") == theme]
        if not pool:
            pool = self.missions
        if not pool:
            return None
        return pool[rotation % len(pool)]

    def pick(self, bucket: list, rng: random.Random) -> dict | None:
        return rng.choice(bucket) if bucket else None

    # --- 렌더링 -------------------------------------------------------------

    def render_mission(self, mission: dict, day: date, d_index: int) -> str:
        label, theme = WEEKDAY_THEME[day.weekday()]
        lines = [
            f"🗓 D+{d_index} · {label} · {theme}",
            "",
            mission["title"],
            "",
            f"🟢 {mission['green']}",
            f"🟡 {mission['yellow']}",
            f"🔴 {mission['red']}",
        ]
        if mission.get("note"):
            lines += ["", mission["note"]]
        lines += ["", FOOTER]
        return "\n".join(lines)

    RUN_PACE = {"green": "조깅 페이스", "yellow": "테스트 페이스", "red": "레이스 페이스"}

    def render_hyrox(self, stations: list[dict], d_index: int) -> str:
        """1km 달리기와 근력 스테이션을 번갈아 배치한 헬스장용 하이록스 WOD.

        러닝으로 시작해서 러닝-스테이션을 스테이션 개수만큼 반복한다
        (실제 하이록스와 같은 순서: 러닝 → 스테이션 → 러닝 → 스테이션 …).
        """
        n = len(stations)
        lines = [f"🏋️ 하이록스 WOD · D+{d_index}", "", f"러닝 {n}회 × 근력 스테이션 {n}개, 교차", ""]
        for tier, mark in (("green", "🟢"), ("yellow", "🟡"), ("red", "🔴")):
            lines.append(mark)
            step = 1
            for station in stations:
                lines.append(f"{step}) 🏃 1km 달리기 ({self.RUN_PACE[tier]})")
                step += 1
                lines.append(f"{step}) 🏋️ {station['name']} {station[tier]}")
                step += 1
            lines.append("")
        lines += ["러닝과 근력 스테이션을 교차하는 하이록스 기본 구조입니다. 러닝 횟수는 나중에 늘려갑니다.", ""]
        lines.append(FOOTER)
        return "\n".join(lines)

    def render_quick_fix(self, card: dict) -> str:
        return card["text"]

    def render_kcal(self, card: dict) -> str:
        return f"오늘의 270kcal\n\n{card['text']}"


def progress_bar(done: float, total: float, width: int = 10) -> str:
    if total <= 0:
        return "░" * width
    ratio = max(0.0, min(1.0, done / total))
    filled = int(round(ratio * width))
    return "▓" * filled + "░" * (width - filled)
