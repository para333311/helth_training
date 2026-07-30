#!/usr/bin/env python3
"""`.env` 인코딩 회귀 테스트.

Windows 에서 `.env` 를 만들면 BOM(Byte Order Mark)이 붙는 경우가 많다.

  Set-Content -Encoding UTF8    → BOM 붙음 (PowerShell 5.1)
  메모장 "UTF-8로 저장"          → 버전에 따라 붙음

BOM 을 utf-8 로 읽으면 첫 줄 키가 "\\ufeffTELEGRAM_BOT_TOKEN" 이 되어
토큰을 넣었는데도 "TELEGRAM_BOT_TOKEN 이 없습니다" 라는 엉뚱한 오류가 난다.
원인을 찾기 매우 어려운 종류의 실패라서 테스트로 못 박아둔다.

실행:
    python tests/env_encoding.py

의존성 없음. 네트워크도 쓰지 않는다.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import load_dotenv  # noqa: E402

BOM = b"\xef\xbb\xbf"

# ── 본문 두 종류 ──────────────────────────────────────────────────────
#
# BOM 은 파일의 맨 앞 3바이트다. 그래서 첫 줄이 무엇이냐에 따라 피해가 다르다.
#
#   첫 줄이 주석  → BOM 이 주석에 흡수돼서 아무 일도 안 생긴다 (운이 좋은 경우)
#   첫 줄이 키    → 키 이름이 "\ufeffTELEGRAM_BOT_TOKEN" 이 되어 값을 못 읽는다
#
# 실제 사고는 두 번째에서 난다. 그래서 두 경우를 모두 시험한다.

KEYLINES = (
    "TELEGRAM_BOT_TOKEN=123456:AAtestToken\n"
    "TELEGRAM_CHANNEL_ID=@helth_training\n"
    "SEASON_NAME=3kg 프로젝트\n"
    "GOAL_KG=3.0\n"
)

# 첫 줄이 키 — BOM 에 취약한 배치
BODY_KEY_FIRST = KEYLINES

# 첫 줄이 주석 — BOM 이 흡수되는 배치
BODY_COMMENT_FIRST = "# 이 파일은 커밋되지 않는다\n" + KEYLINES

KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID", "SEASON_NAME", "GOAL_KG")

failures: list[str] = []


def check(label: str, data: bytes) -> None:
    """주어진 바이트로 .env 를 만들고 값이 제대로 읽히는지 본다."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / ".env"
        path.write_bytes(data)

        # load_dotenv 는 setdefault 를 쓰므로 기존 값을 반드시 비운다
        for k in KEYS:
            os.environ.pop(k, None)

        load_dotenv(path)

        expected = {
            "TELEGRAM_BOT_TOKEN": "123456:AAtestToken",
            "TELEGRAM_CHANNEL_ID": "@helth_training",
            "SEASON_NAME": "3kg 프로젝트",
            "GOAL_KG": "3.0",
        }
        bad = {k: os.environ.get(k) for k, v in expected.items() if os.environ.get(k) != v}
        if bad:
            failures.append(label)
            print(f"  FAIL  {label}")
            for k, got in bad.items():
                print(f"          {k}: {got!r} (기대: {expected[k]!r})")
        else:
            print(f"  ok    {label}")


def check_missing_file() -> None:
    """파일이 없으면 조용히 넘어가야 한다 (환경변수만으로도 돌 수 있어야 함)."""
    with tempfile.TemporaryDirectory() as d:
        try:
            load_dotenv(Path(d) / "없는파일.env")
        except Exception as exc:  # noqa: BLE001
            failures.append("없는 파일")
            print(f"  FAIL  없는 파일: 예외가 났다 → {exc!r}")
            return
    print("  ok    없는 파일은 조용히 무시")


def main() -> int:
    print(".env 인코딩 회귀 테스트\n")

    def crlf(s: str) -> str:
        return s.replace("\n", "\r\n")

    # 첫 줄이 키인 배치 — 여기가 진짜 사고 지점이다
    check("첫줄=키 · BOM 없음 · LF", BODY_KEY_FIRST.encode("utf-8"))
    check("첫줄=키 · BOM 있음 · LF   ← utf-8 로 읽으면 실패", BOM + BODY_KEY_FIRST.encode("utf-8"))
    check("첫줄=키 · BOM 있음 · CRLF ← utf-8 로 읽으면 실패", BOM + crlf(BODY_KEY_FIRST).encode("utf-8"))

    # 첫 줄이 주석인 배치 — BOM 이 흡수돼서 무해하다
    check("첫줄=주석 · BOM 있음 · LF", BOM + BODY_COMMENT_FIRST.encode("utf-8"))
    check("첫줄=주석 · BOM 없음 · CRLF", crlf(BODY_COMMENT_FIRST).encode("utf-8"))

    check_missing_file()

    print()
    if failures:
        print(f"실패 {len(failures)}건: {', '.join(failures)}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
