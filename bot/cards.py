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

ROOT = Path(__file__).resolve().parent.parent

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
    # Render 등 apt(sudo) 를 쓸 수 없는 빌드 환경용. 빌드 커맨드가 여기로
    # 직접 내려받아 둔다 (docs/09-render-setup.md 참고). 패키지 설치가
    # 가능한 환경(Actions, VPS)에서는 이 파일이 없으므로 자연히 건너뛴다.
    str(ROOT / ".fonts" / "NanumGothic.ttf"),
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


def _cover_crop(image, target_w: int, target_h: int):
    """이미지를 target 박스를 꽉 채우도록 확대한 뒤 중앙을 잘라낸다 (Instagram 식 커버 크롭)."""
    src_w, src_h = image.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    image = image.resize((new_w, new_h))
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return image.crop((left, top, left + target_w, top + target_h))


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


# 사진 위에 명언을 얹어 한 장으로 합성할 때 쓰는 톤. 어느 사진에 얹어도
# 가독성이 나오도록 그림자를 진하게 준다 (배경색을 못 고르므로 카드용
# PALETTE 는 여기선 안 쓰고 흰 글씨 + 검은 그림자로 고정한다).
ACCENT_COLORS = ["#4C8DFF", "#FF9F45", "#3ED598", "#C77DFF", "#FF5C7A"]


def render_photo_quote(
    photo_bytes: bytes,
    text: str,
    rng: random.Random | None = None,
) -> BytesIO | None:
    """사진 위에 명언을 그려 한 장으로 합성한다. 실패하면 None (호출부가 원본 사진으로 대체).

    - 사진은 정사각형(1080×1080)으로 커버 크롭한다.
    - 하단에 어두운 그라데이션을 깔아 글자가 어떤 사진에도 묻히지 않게 한다
      (가독성은 이 스크림만으로 확보하고, 글자에 별도 그림자는 넣지 않는다).
    - 출처/워터마크 문구는 넣지 않는다.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        log.warning("Pillow 가 없어 사진 합성을 할 수 없습니다 (pip install Pillow)")
        return None

    font_path = find_font()
    if not font_path:
        log.warning("한글 폰트를 찾지 못했습니다 (apt install fonts-nanum)")
        return None

    rng = rng or random.Random()

    try:
        base = Image.open(BytesIO(photo_bytes)).convert("RGB")
    except Exception as exc:
        log.warning("사진을 열지 못했습니다: %s", exc)
        return None

    image = _cover_crop(base, SIZE, SIZE)

    # 살짝 어둡게 톤다운 — 흰 글씨가 밝은 사진 위에서도 안 뜨게
    dark = Image.new("RGB", image.size, "#000000")
    image = Image.blend(image, dark, 0.12)

    draw = ImageDraw.Draw(image, "RGBA")
    accent = rng.choice(ACCENT_COLORS)
    max_width = SIZE - MARGIN * 2

    # 글자 수에 맞춰 크기를 줄여가며 하단 60% 안에 들어오는 지점을 찾는다
    text_box_h = int(SIZE * 0.62)
    for size in range(92, 39, -4):
        font = ImageFont.truetype(font_path, size)
        lines = _wrap(draw, text, font, max_width)
        line_height = int(size * 1.42)
        total = line_height * len(lines)
        if total <= text_box_h - 90:
            break
    else:
        lines, font, line_height, total = [text], ImageFont.truetype(font_path, 40), 60, 60

    block_top = SIZE - MARGIN - total - 70
    gradient_top = max(0, block_top - 140)

    # 하단 그라데이션 스크림 — 사진이 무엇이든 글자 가독성을 보장한다
    grad = Image.linear_gradient("L").resize((SIZE, SIZE - gradient_top))
    grad = grad.rotate(180)
    scrim = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    alpha = grad.point(lambda p: int(p * 0.82))
    black = Image.new("RGBA", (SIZE, SIZE - gradient_top), "#000000")
    black.putalpha(alpha)
    scrim.paste(black, (0, gradient_top), black)
    image = Image.alpha_composite(image.convert("RGBA"), scrim)

    draw = ImageDraw.Draw(image, "RGBA")
    y = block_top
    for line in lines:
        width = draw.textlength(line, font=font)
        x = (SIZE - width) / 2
        draw.text((x, y), line, font=font, fill="#FFFFFF")
        y += line_height

    # 포인트 컬러 바 — 명언 카드와 같은 문법으로 채널 정체성 유지
    bar_w = 120
    bar_y = y + 18
    draw.rectangle([(SIZE - bar_w) // 2, bar_y, (SIZE + bar_w) // 2, bar_y + 6], fill=accent)

    image = image.convert("RGB")
    buffer = BytesIO()
    buffer.name = "photo_quote.jpg"
    image.save(buffer, format="JPEG", quality=92, optimize=True)
    buffer.seek(0)
    return buffer
