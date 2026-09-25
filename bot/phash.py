"""사진 지문(dHash) — 같은 사진을 두 번 올려도(다시 압축돼 파일이 달라도) 알아본다. 파라님 2026-09-25 「중복 사진 삭제」."""
from __future__ import annotations

import io

# 64비트 지문 중 다른 비트가 이 수 이하면 같은 사진으로 본다(재압축·크기 차이는 0~3, 다른 사진은 보통 15 넘게).
SAME = 5


def dhash(raw: bytes) -> str | None:
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("L").resize((9, 8), Image.LANCZOS)
    except Exception:
        return None
    px = list(im.getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (1 if px[y * 9 + x] > px[y * 9 + x + 1] else 0)
    return f"{bits:016x}"


def distance(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def find_same(h: str, known: list[tuple[str, str]]) -> str | None:
    """known = [(file_id, phash)] 중 h 와 같은 사진의 file_id."""
    for fid, k in known:
        if k and distance(h, k) <= SAME:
            return fid
    return None
