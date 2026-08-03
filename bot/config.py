"""환경변수 기반 설정. 봇 토큰은 코드에 절대 넣지 않는다."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    """의존성 없이 .env 를 읽어 os.environ 에 채운다. 이미 있는 값은 덮지 않는다.

    인코딩은 utf-8 로 읽는다. Windows PowerShell 의
    `Set-Content -Encoding UTF8` 은 파일 앞에 BOM(\\ufeff)을 붙이는데,
    이걸 utf-8 로 읽으면 첫 줄 키가 "\\ufeffTELEGRAM_BOT_TOKEN" 이 되어
    토큰이 없다는 엉뚱한 오류가 난다. utf-8 는 BOM 이 있으면 벗기고
    없으면 그냥 읽으므로 양쪽 다 안전하다.
    """
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    token: str
    channel_id: str
    tz: ZoneInfo

    # 사진 발행
    photo_interval_minutes: int
    photo_start_hour: int  # 포함
    photo_end_hour: int  # 포함 — 이 시각 이후로는 사진을 보내지 않는다 (밤에는 쉼)
    photo_source: str  # local | unsplash | pexels
    photo_query: str
    unsplash_key: str
    pexels_key: str

    # 하이록스 WOD (헬스장) — 1km 달리기와 근력 스테이션을 번갈아 배치.
    # 러닝 횟수는 3회로 시작하고, 감당되면 늘려간다.
    hyrox_runs: int

    # 시즌
    season_start: date
    season_days: int
    season_name: str
    goal_kg: float

    # 혼자 쓰는 비공개 채널이면 True.
    # 투표·채널 집계처럼 여러 명을 전제로 한 기능을 끄고,
    # 주간 결산을 본인 기록 기준으로 바꾼다.
    solo_mode: bool
    owner_id: int

    # 경로
    data_dir: Path = field(default_factory=lambda: ROOT / "content" / "data")
    photo_dir: Path = field(default_factory=lambda: ROOT / "content" / "photos")
    db_path: Path = field(default_factory=lambda: ROOT / "data" / "helth.db")

    # Cloudflare D1 (선택). 셋 다 있으면 로컬 SQLite 대신 D1 을 쓴다.
    # Render 무료 플랜처럼 재시작마다 디스크가 초기화되는 곳에서 기록을 지키기 위함.
    # docs/09-render-setup.md 참고.
    cf_account_id: str = ""
    cf_d1_database_id: str = ""
    cf_api_token: str = ""

    @property
    def bot_username_hint(self) -> str:
        return os.environ.get("TELEGRAM_BOT_USERNAME", "").lstrip("@")

    def day_index(self, today: date) -> int:
        """시즌 시작일 기준 D+n (1부터)."""
        return (today - self.season_start).days + 1


def load_config(require_channel: bool = True) -> Config:
    """require_channel=False 는 --chatid 전용.

    채널 ID 를 찾으려고 실행하는 명령이 채널 ID 가 없다고 거부당하면 안 된다.
    """
    load_dotenv()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN 이 없습니다.\n"
            "  1) .env.example 를 .env 로 복사\n"
            "  2) BotFather 에서 받은 토큰을 TELEGRAM_BOT_TOKEN 에 입력\n"
            "토큰을 코드나 git 에 넣지 마세요."
        )

    channel = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel and require_channel:
        raise SystemExit(
            "TELEGRAM_CHANNEL_ID 이 없습니다.\n"
            "  공개 채널: @채널이름\n"
            "  비공개 채널: -100 으로 시작하는 숫자 ID (python -m bot --chatid 로 찾기)"
        )

    raw_start = os.environ.get("SEASON_START", "").strip()
    season_start = date.fromisoformat(raw_start) if raw_start else date.today()

    return Config(
        token=token,
        channel_id=channel,
        tz=ZoneInfo(os.environ.get("TZ", "Asia/Seoul")),
        photo_interval_minutes=max(5, _int("PHOTO_INTERVAL_MINUTES", 30)),
        photo_start_hour=_int("PHOTO_START_HOUR", 7),
        photo_end_hour=_int("PHOTO_END_HOUR", 22),
        photo_source=os.environ.get("PHOTO_SOURCE", "local").strip().lower(),
        photo_query=os.environ.get("PHOTO_QUERY", "home workout,gym motivation,fitness").strip(),
        unsplash_key=os.environ.get("UNSPLASH_ACCESS_KEY", "").strip(),
        pexels_key=os.environ.get("PEXELS_API_KEY", "").strip(),
        hyrox_runs=max(1, _int("HYROX_RUNS", 3)),
        season_start=season_start,
        season_days=_int("SEASON_DAYS", 84),
        season_name=os.environ.get("SEASON_NAME", "3kg 프로젝트").strip(),
        goal_kg=float(os.environ.get("GOAL_KG", "3.0")),
        solo_mode=os.environ.get("SOLO_MODE", "true").strip().lower() in {"1", "true", "yes"},
        owner_id=_int("OWNER_USER_ID", 0),
        cf_account_id=os.environ.get("CF_ACCOUNT_ID", "").strip(),
        cf_d1_database_id=os.environ.get("CF_D1_DATABASE_ID", "").strip(),
        cf_api_token=os.environ.get("CF_API_TOKEN", "").strip(),
    )
