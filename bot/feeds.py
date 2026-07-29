"""유튜브 채널 RSS 피드.

유튜브는 채널마다 공개 RSS 를 제공한다 (외부 구독용으로 공식 제공하는 것).
    https://www.youtube.com/feeds/videos.xml?channel_id=UC...

여기서는 영상을 재업로드하지 않고 **원본 링크만** 발행한다.
텔레그램이 링크 미리보기로 제목과 썸네일을 붙여주므로 자극 효과는 그대로이고,
클릭하면 원작자 채널로 가므로 저작권 문제가 없다.
"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import requests

log = logging.getLogger("feeds")

RSS = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

UA = {"User-Agent": "Mozilla/5.0 (compatible; helth-training-bot/1.0)"}


@dataclass
class Video:
    title: str
    url: str
    channel: str
    video_id: str


def resolve_channel_id(url_or_handle: str) -> str | None:
    """채널 URL 이나 @핸들에서 UC... 채널 ID 를 뽑아낸다. API 키 불필요."""
    value = url_or_handle.strip()

    if value.startswith("UC") and len(value) == 24:
        return value

    if not value.startswith("http"):
        value = f"https://www.youtube.com/{value if value.startswith('@') else '@' + value}"

    try:
        resp = requests.get(value, headers=UA, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("채널 페이지를 못 읽었습니다 (%s): %s", url_or_handle, exc)
        return None

    for pattern in (r'"channelId":"(UC[\w-]{22})"', r'channel/(UC[\w-]{22})'):
        match = re.search(pattern, resp.text)
        if match:
            return match.group(1)

    log.warning("채널 ID 를 찾지 못했습니다: %s", url_or_handle)
    return None


class YoutubeFeeds:
    """등록된 채널들의 최신 영상 중 아직 안 보낸 것 하나를 고른다."""

    def __init__(self, path: Path):
        self._path = path

    # --- 채널 목록 관리 -------------------------------------------------------

    def channels(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("%s 를 읽지 못했습니다", self._path)
            return []

    def add(self, url_or_handle: str) -> dict | None:
        channel_id = resolve_channel_id(url_or_handle)
        if not channel_id:
            return None

        items = self.channels()
        if any(c["channel_id"] == channel_id for c in items):
            log.info("이미 등록된 채널입니다")
            return None

        name = self._channel_title(channel_id) or url_or_handle
        entry = {"name": name, "channel_id": channel_id, "source": url_or_handle}
        items.append(entry)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return entry

    def _channel_title(self, channel_id: str) -> str | None:
        try:
            resp = requests.get(RSS.format(cid=channel_id), headers=UA, timeout=15)
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.content)
            node = root.find("atom:title", NS)
            return node.text if node is not None else None
        except Exception:
            return None

    # --- 영상 수집 -----------------------------------------------------------

    def _videos(self, channel: dict, limit: int = 8) -> list[Video]:
        try:
            resp = requests.get(RSS.format(cid=channel["channel_id"]), headers=UA, timeout=15)
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.content)
        except Exception as exc:
            log.warning("피드 실패 (%s): %s", channel.get("name"), exc)
            return []

        videos = []
        for entry in root.findall("atom:entry", NS)[:limit]:
            vid = entry.find("yt:videoId", NS)
            title = entry.find("atom:title", NS)
            if vid is None or title is None:
                continue
            videos.append(
                Video(
                    title=title.text or "",
                    url=f"https://www.youtube.com/watch?v={vid.text}",
                    channel=channel.get("name", ""),
                    video_id=vid.text or "",
                )
            )
        return videos

    def pick(self, rng: random.Random, store=None) -> Video | None:
        channels = self.channels()
        if not channels:
            return None

        rng.shuffle(channels)
        pool: list[Video] = []
        for channel in channels[:4]:  # 매번 전부 긁지 않는다
            pool.extend(self._videos(channel))
            if len(pool) >= 12:
                break

        if not pool:
            return None

        if store is not None:
            keys = [v.video_id for v in pool]
            unseen = set(store.unseen("video", keys))
            candidates = [v for v in pool if v.video_id in unseen] or pool
        else:
            candidates = pool

        return rng.choice(candidates)
