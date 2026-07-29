"""사진 소스.

저작권 원칙: 인터넷/SNS 에서 남의 오운완 사진을 긁어오지 않는다.
타인의 저작물이자 대부분 초상권이 걸린 이미지다. 아래 세 경로만 쓴다.

  local    — 직접 촬영/제작해 content/photos/ 에 넣은 이미지 (기본값)
  unsplash — Unsplash API. 무료 라이선스, 출처 표기 자동 첨부
  pexels   — Pexels API. 무료 라이선스, 출처 표기 자동 첨부

어느 소스도 사용할 수 없으면 None 을 돌려주고, 호출부가 텍스트 카드로 대체한다.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from pathlib import Path

import requests

log = logging.getLogger("photos")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class Photo:
    """발행할 사진 한 장. ref 는 로컬 경로이거나 원격 URL."""

    ref: Path | str
    credit: str | None = None
    key: str = ""


class PhotoSource:
    name = "none"

    def fetch(self, query: str, rng: random.Random, store=None) -> Photo | None:
        raise NotImplementedError


class SubmittedPhotos(PhotoSource):
    """구독자가 봇 DM 으로 직접 보낸 오운완 사진.

    현실감이 가장 높은 소스이고, 본인이 보낸 것이라 권리 문제가 없다.
    Telegram file_id 를 그대로 재전송하므로 이미지를 서버에 보관하지 않는다.
    채널에는 익명으로 나간다 — 보낸 사람 이름을 절대 붙이지 않는다.
    """

    name = "submitted"

    def __init__(self, store):
        self._store = store

    def fetch(self, query: str, rng: random.Random, store=None) -> Photo | None:
        rows = self._store.submitted_photos()
        if not rows:
            return None
        # used 오름차순으로 정렬돼 있으므로, 가장 적게 나간 것들 중에서 고른다
        fewest = rows[0]["used"]
        pool = [r for r in rows if r["used"] == fewest]
        item = rng.choice(pool)
        return Photo(ref=item["file_id"], credit=item.get("caption") or None,
                     key=item["file_id"])


class LocalPhotos(PhotoSource):
    """content/photos/ 순환. 전부 한 번씩 나간 뒤에 다시 처음부터."""

    name = "local"

    def __init__(self, directory: Path):
        self._dir = directory

    def _all(self) -> list[Path]:
        if not self._dir.exists():
            return []
        return sorted(p for p in self._dir.iterdir()
                      if p.suffix.lower() in IMAGE_EXT and p.is_file())

    def fetch(self, query: str, rng: random.Random, store=None) -> Photo | None:
        files = self._all()
        if not files:
            return None

        keys = [p.name for p in files]
        pool = store.unseen("photo", keys) if store else keys
        chosen_name = rng.choice(pool)
        chosen = next(p for p in files if p.name == chosen_name)

        # 같은 이름의 .txt 가 있으면 출처/문구로 사용
        sidecar = chosen.with_suffix(".txt")
        credit = sidecar.read_text(encoding="utf-8").strip() if sidecar.exists() else None
        return Photo(ref=chosen, credit=credit, key=chosen.name)


class UnsplashPhotos(PhotoSource):
    """https://unsplash.com/documentation — 출처 표기와 download 트래킹이 이용약관 조건."""

    name = "unsplash"

    def __init__(self, access_key: str):
        self._key = access_key

    def fetch(self, query: str, rng: random.Random, store=None) -> Photo | None:
        term = rng.choice([q.strip() for q in query.split(",") if q.strip()] or ["workout"])
        try:
            resp = requests.get(
                "https://api.unsplash.com/photos/random",
                params={"query": term, "orientation": "portrait", "content_filter": "high"},
                headers={"Authorization": f"Client-ID {self._key}"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.warning("unsplash 실패: %s", exc)
            return None

        if isinstance(data, list):
            data = data[0] if data else None
        if not data:
            return None

        user = data.get("user", {})
        credit = f"📷 {user.get('name', 'Unsplash')} / Unsplash"

        # API 이용약관상 필요한 download 엔드포인트 호출 (실패해도 발행은 계속)
        try:
            dl = data.get("links", {}).get("download_location")
            if dl:
                requests.get(dl, headers={"Authorization": f"Client-ID {self._key}"}, timeout=10)
        except Exception:
            pass

        return Photo(
            ref=data["urls"]["regular"],
            credit=credit,
            key=data.get("id", ""),
        )


class PexelsPhotos(PhotoSource):
    """https://www.pexels.com/api/documentation/ — 출처 표기가 이용약관 조건."""

    name = "pexels"

    def __init__(self, api_key: str):
        self._key = api_key

    def fetch(self, query: str, rng: random.Random, store=None) -> Photo | None:
        term = rng.choice([q.strip() for q in query.split(",") if q.strip()] or ["workout"])
        try:
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                params={"query": term, "orientation": "portrait", "per_page": 40},
                headers={"Authorization": self._key},
                timeout=15,
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
        except Exception as exc:
            log.warning("pexels 실패: %s", exc)
            return None

        if not photos:
            return None

        keys = [str(p["id"]) for p in photos]
        pool = store.unseen("photo", keys) if store else keys
        pick_id = rng.choice(pool)
        item = next(p for p in photos if str(p["id"]) == pick_id)

        return Photo(
            ref=item["src"]["large"],
            credit=f"📷 {item.get('photographer', 'Pexels')} / Pexels",
            key=str(item["id"]),
        )


class ChainedPhotos(PhotoSource):
    """앞에서부터 사진이 나오는 소스를 쓴다. 전부 비면 None → 호출부가 텍스트로 대체."""

    name = "chain"

    def __init__(self, sources: list[PhotoSource]):
        self._sources = sources

    def fetch(self, query: str, rng: random.Random, store=None) -> Photo | None:
        for source in self._sources:
            try:
                photo = source.fetch(query, rng, store)
            except Exception as exc:
                log.warning("%s 소스 실패: %s", source.name, exc)
                continue
            if photo is not None:
                return photo
        return None


def build_source(cfg, store=None) -> PhotoSource:
    """우선순위: 구독자 제출 → 로컬 폴더 → 스톡 API.

    구독자가 보낸 실제 사진이 가장 현실감 있으므로 항상 맨 앞에 둔다.
    """
    sources: list[PhotoSource] = []

    if store is not None:
        sources.append(SubmittedPhotos(store))

    sources.append(LocalPhotos(cfg.photo_dir))

    if cfg.unsplash_key:
        sources.append(UnsplashPhotos(cfg.unsplash_key))
    if cfg.pexels_key:
        sources.append(PexelsPhotos(cfg.pexels_key))

    if cfg.photo_source in {"unsplash", "pexels"} and not (cfg.unsplash_key or cfg.pexels_key):
        log.warning("PHOTO_SOURCE=%s 인데 API 키가 없습니다.", cfg.photo_source)

    return ChainedPhotos(sources)
