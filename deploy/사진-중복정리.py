"""이미 들어온 제출 사진의 중복을 한 번에 지운다(파라님 2026-09-25 「중복 사진 삭제」).
지문(dHash)이 없는 사진은 텔레그램에서 받아 지문을 매기고, 같은 사진이면 먼저 들어온 것 하나만 남긴다.

    .venv/bin/python deploy/사진-중복정리.py [--dry]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot.config import load_dotenv, load_config  # noqa: E402
from bot.store import Store  # noqa: E402
from bot.tg import Telegram  # noqa: E402
from bot.phash import dhash, find_same  # noqa: E402

load_dotenv()
cfg = load_config()
store = Store(cfg.db_path)
tg = Telegram(cfg.token)
dry = "--dry" in sys.argv

rows = store.photo_hashes()
남길: list[tuple[str, str]] = []
지움, 실패 = [], 0
for i, (fid, h) in enumerate(rows, 1):
    if not h:
        try:
            h = dhash(tg.download_file_bytes(fid))
        except Exception as exc:
            print("받기 실패", fid[:12], exc); 실패 += 1; continue
        if h and not dry:
            store.set_phash(fid, h)
    if not h:
        실패 += 1; continue
    같은 = find_same(h, 남길)
    if 같은:
        지움.append(fid)
        if not dry:
            store.delete_photo(fid)
    else:
        남길.append((fid, h))
    if i % 50 == 0:
        print(f"{i}/{len(rows)} · 남김 {len(남길)} · 중복 {len(지움)}", flush=True)
print(f"끝 — 전체 {len(rows)} · 남김 {len(남길)} · 중복 지움 {len(지움)} · 지문 실패 {실패}{' (dry)' if dry else ''}")
