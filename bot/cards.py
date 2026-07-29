"""동기부여 명언 카드 생성.

명언 이미지를 인터넷에서 가져오지 않고 직접 그린다.
문구는 직접 쓴 것이거나 저작권이 만료된 인용이고, 배경은 단색이라
출처 문제가 없다. 한글 폰트만 있으면 어디서든 같은 결과가 나온다.

02번 문서의 이미지 규칙을 그대로 따른다.
  · 정사각형 1080×1080
  · 단색 배경 + 큰 글자 (배경 사진 위에 글씨를 얹지 않는다)
  · 색은 소수의 고정 팔레트에서만 (매번 톤이 바뀌면 채널 정체성이 흐려진다)
"""

from __future__ import annotations

import logging
import random
from io import BytesIO
from pathlib import Path

log = logging.getLogger("cards")

SIZE = 1080
MARGIN = 110

# 어두운 배경 + 밝은 글씨 고정. 텔레그램 다크모드에서 눈이 편하고 톤이 일정하다.
PALETTE = [
    ("#12161C", "#F2F5F8", "#4C8DFF"),
    ("#1A1410", "#F6F1EA", "#FF9F45"),
    ("#101A16", "#EFF7F2", "#3ED598"),
    ("#181018", "#F6EFF6", "#C77DFF"),
    ("#1C1218", "#F8EFF2", "#FF5C7A"),
]

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumSquareRoundB.ttf",
    "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",  # macOS
    "C:/Windows/Fonts/malgunbd.ttf",  # Windows
    "C:/Windows/Fonts/malgun.ttf",
]


def find_font() -> str | None:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    # 마지막 수단: 시스템에서 한글 폰트를 훑는다
    for root in ("/usr/share/fonts", "/Library/Fonts", "C:/Windows/Fonts"):
        base = Path(root)
        if not base.exists():
            continue
        for pattern in ("**/*Nanum*.ttf", "**/*Gothic*.ttf", "**/*CJK*.ttc"):
            for hit in base.glob(pattern):
                return str(hit)
    return None


def available() -> bool:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return find_font() is not None


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    """한국어는 어절 단위로 줄바꿈한다."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split(" ")
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if draw.textlength(trial, font=font) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def render_quote(text: str, source: str | None = None,
                 rng: random.Random | None = None) -> BytesIO | None:
    """명언 카드 PNG 를 메모리에 그려서 돌려준다. 실패하면 None."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        log.warning("Pillow 가 없어 명언 카드를 만들 수 없습니다 (pip install Pillow)")
        return None

    font_path = find_font()
    if not font_path:
        log.warning("한글 폰트를 찾지 못했습니다 (apt install fonts-nanum)")
        return None

    rng = rng or random.Random()
    bg, fg, accent = rng.choice(PALETTE)

    image = Image.new("RGB", (SIZE, SIZE), bg)
    draw = ImageDraw.Draw(image)

    # 글자 수에 맞춰 크기를 줄여가며 한 화면에 들어오는 지점을 찾는다
    max_width = SIZE - MARGIN * 2
    for size in range(96, 39, -4):
        font = ImageFont.truetype(font_path, size)
        lines = _wrap(draw, text, font, max_width)
        line_height = int(size * 1.45)
        total = line_height * len(lines)
        if total <= SIZE - MARGIN * 2 - 120:
            break
    else:
        return None

    y = (SIZE - total) // 2 - 20
    for line in lines:
        width = draw.textlength(line, font=font)
        draw.text(((SIZE - width) / 2, y), line, font=font, fill=fg)
        y += line_height

    # 하단 악센트 바
    bar_w = 120
    draw.rectangle(
        [(SIZE - bar_w) // 2, SIZE - MARGIN - 40, (SIZE + bar_w) // 2, SIZE - MARGIN - 34],
        fill=accent,
    )

    if source:
        small = ImageFont.truetype(font_path, 34)
        width = draw.textlength(source, font=small)
        draw.text(((SIZE - width) / 2, SIZE - MARGIN + 4), source, font=small, fill=accent)

    buffer = BytesIO()
    buffer.name = "quote.png"
    image.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer
