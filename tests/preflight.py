#!/usr/bin/env python3
"""실행 환경 사전 점검. 봇을 띄우기 전에 이걸 먼저 돌린다.

목적: 실패 원인을 사람이 추측하지 않게 만든다. 특히 Windows 에서
"토큰을 넣었는데 없다고 한다", "시간대를 못 찾는다" 같은 원인 파악이
어려운 실패를 이 스크립트가 대신 지목한다.

    python tests/preflight.py           # 로컬 점검만 (네트워크 안 씀)
    python tests/preflight.py --net     # 텔레그램/스톡 API 까지 확인

비밀값은 절대 그대로 출력하지 않는다 (앞 4자 + 길이만).
종료코드: 0 = 치명적 문제 없음, 1 = 봇이 못 뜨는 문제 있음
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FATAL: list[str] = []
WARN: list[str] = []

# Windows PowerShell 5.1 은 ANSI 색상을 해석하지 않고 그대로 출력한다.
# 색이 안 되는 환경에서는 기호만 쓴다 (읽기 어려워지지 않게).
_COLOR = sys.stdout.isatty() and os.environ.get("TERM") not in (None, "", "dumb")


def _tag(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def ok(msg: str) -> None:
    print(f"  {_tag('ok   ', '32')} {msg}")


def fatal(msg: str, fix: str) -> None:
    FATAL.append(msg)
    print(f"  {_tag('FATAL', '31')} {msg}")
    print(f"          → {fix}")


def warn(msg: str, fix: str) -> None:
    WARN.append(msg)
    print(f"  {_tag('warn ', '33')} {msg}")
    print(f"          → {fix}")


def mask(v: str) -> str:
    """비밀값을 안전하게 표기한다."""
    if not v:
        return "(비어 있음)"
    return f"{v[:4]}… (길이 {len(v)})"


# ── 1. 파이썬 ────────────────────────────────────────────────────────────
def check_python() -> None:
    v = sys.version_info
    print(f"\n[1] 파이썬  {sys.version.split()[0]}  ({sys.executable})")
    if v < (3, 11):
        fatal(
            f"3.11 이상이 필요하다 (현재 {v.major}.{v.minor})",
            "https://www.python.org/downloads/ 에서 설치. 'Add python.exe to PATH' 체크",
        )
    else:
        ok(f"{v.major}.{v.minor} — 요구사항 충족")
    if v >= (3, 14):
        warn(
            f"{v.major}.{v.minor} 는 검증 범위(3.11~3.13)보다 새롭다",
            "문제가 생기면 tests/brief_smoke.py 와 tests/env_encoding.py 결과를 함께 보고",
        )


# ── 2. 패키지 ────────────────────────────────────────────────────────────
def check_packages() -> None:
    print("\n[2] 패키지")
    try:
        import requests  # noqa: F401

        ok(f"requests {requests.__version__}")
    except ImportError:
        fatal("requests 없음", "pip install -r requirements.txt")

    try:
        import PIL

        ok(f"Pillow {PIL.__version__} (명언 카드용)")
    except ImportError:
        warn("Pillow 없음 — 명언 카드만 건너뛴다", "pip install Pillow")


# ── 3. 시간대 (Windows 최대 함정) ────────────────────────────────────────
def check_timezone() -> None:
    print("\n[3] 시간대")
    tzname = os.environ.get("TZ", "Asia/Seoul")
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(tzname)
        ok(f"{tzname} 확인")
    except Exception as exc:  # noqa: BLE001
        fatal(
            f"{tzname} 를 찾을 수 없다 ({type(exc).__name__})",
            "pip install tzdata  ← Windows 에는 시간대 DB 가 없어서 반드시 필요하다",
        )


# ── 4. SQLite ────────────────────────────────────────────────────────────
def check_sqlite() -> None:
    print("\n[4] SQLite")
    try:
        with tempfile.TemporaryDirectory() as d:
            con = sqlite3.connect(Path(d) / "t.db")
            con.execute("CREATE TABLE t (a TEXT)")
            con.execute("INSERT INTO t VALUES (?)", ("한글",))
            con.commit()
            got = con.execute("SELECT a FROM t").fetchone()[0]
            con.close()
        ok(f"쓰기/읽기 정상 (sqlite {sqlite3.sqlite_version}, 한글 왕복: {got})")
    except Exception as exc:  # noqa: BLE001
        fatal(f"SQLite 실패: {exc!r}", "디스크 권한 확인")


# ── 5. 한글 폰트 ─────────────────────────────────────────────────────────
def check_font() -> None:
    print("\n[5] 한글 폰트 (명언 카드)")
    try:
        from bot.cards import find_font

        p = find_font()
        if p:
            ok(f"{p}")
        else:
            warn("한글 폰트를 못 찾음 — 카드에 글자가 깨진다", "Windows: 맑은 고딕 기본 설치됨. 리눅스: apt install fonts-nanum")
    except Exception as exc:  # noqa: BLE001
        warn(f"폰트 확인 건너뜀 ({type(exc).__name__})", "Pillow 설치 후 다시 확인")


# ── 6. .env ──────────────────────────────────────────────────────────────
REQUIRED = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID")
RECOMMENDED = ("OWNER_USER_ID", "TELEGRAM_BOT_USERNAME", "SEASON_START")
SECRET_KEYS = {"TELEGRAM_BOT_TOKEN", "UNSPLASH_ACCESS_KEY", "PEXELS_API_KEY"}


def check_env() -> None:
    print("\n[6] .env")
    path = ROOT / ".env"
    if not path.exists():
        fatal(f"{path} 가 없다", "cp .env.example .env 후 값 채우기")
        return

    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        first = raw[3:].split(b"\n", 1)[0].decode("utf-8", "replace").strip()
        if first.startswith("#"):
            ok("BOM 있음 — 첫 줄이 주석이라 무해")
        else:
            ok("BOM 있음 — utf-8-sig 로 읽으므로 무해")

    from bot.config import load_dotenv

    load_dotenv(path)

    for k in REQUIRED:
        v = os.environ.get(k, "").strip()
        if not v:
            fatal(f"{k} 비어 있음", f".env 에서 {k} 채우기")
        else:
            ok(f"{k} = {mask(v) if k in SECRET_KEYS else v}")

    for k in RECOMMENDED:
        v = os.environ.get(k, "").strip()
        if not v:
            hint = {
                "OWNER_USER_ID": "비면 --brief 가 전부 0 으로 나온다. @userinfobot 에서 확인",
                "TELEGRAM_BOT_USERNAME": "체크인 링크가 빠진다",
                "SEASON_START": "비면 매일 D+1 로 나온다",
            }[k]
            warn(f"{k} 비어 있음", hint)
        else:
            ok(f"{k} = {v}")

    for k in ("UNSPLASH_ACCESS_KEY", "PEXELS_API_KEY"):
        v = os.environ.get(k, "").strip()
        if v:
            ok(f"{k} = {mask(v)}")
    if not (os.environ.get("UNSPLASH_ACCESS_KEY") or os.environ.get("PEXELS_API_KEY")):
        warn("스톡 API 키가 둘 다 없다", "사진 대신 명언 카드만 나간다")


# ── 7. 설정 로드 ─────────────────────────────────────────────────────────
def check_config() -> None:
    print("\n[7] 설정 로드")
    if FATAL:
        print("  건너뜀 — 위에 치명적 문제가 있어 어차피 실패한다")
        return
    try:
        from bot.config import load_config

        cfg = load_config(require_channel=False)
        ok(f"시즌 D+{cfg.day_index()}/{cfg.season_days} · 목표 {cfg.goal_kg}kg · solo={cfg.solo_mode}")
        ok(f"발행 시간 {cfg.photo_start_hour}~{cfg.photo_end_hour}시 · {cfg.photo_interval_minutes}분 간격")
    except SystemExit:
        fatal("load_config 가 설정 부족으로 종료했다", "위 [6] 항목을 먼저 해결")
    except Exception as exc:  # noqa: BLE001
        fatal(f"load_config 실패: {type(exc).__name__}: {exc}", "위 항목들을 먼저 해결")


# ── 8. 네트워크 (--net) ──────────────────────────────────────────────────
def check_net() -> None:
    print("\n[8] 네트워크 (--net)")
    import requests

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    channel = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not token:
        fatal("토큰이 없어 네트워크 점검 불가", "[6] 먼저 해결")
        return

    base = f"https://api.telegram.org/bot{token}"
    try:
        me = requests.get(f"{base}/getMe", timeout=15).json()
    except Exception as exc:  # noqa: BLE001
        fatal(f"텔레그램 연결 실패: {type(exc).__name__}", "인터넷/방화벽 확인")
        return

    if not me.get("ok"):
        fatal(f"토큰 거부됨: {me.get('description')}", "BotFather → /mybots → API Token 재확인")
        return
    bot_id = me["result"]["id"]
    ok(f"봇 @{me['result']['username']} ({me['result']['first_name']})")

    chat = requests.get(f"{base}/getChat", params={"chat_id": channel}, timeout=15).json()
    if not chat.get("ok"):
        fatal(f"채널 조회 실패: {chat.get('description')}", "TELEGRAM_CHANNEL_ID 확인. 봇이 채널 관리자인가?")
        return
    c = chat["result"]
    if c.get("type") != "channel":
        fatal(f"발행 대상이 채널이 아니다 (type={c.get('type')})", "TELEGRAM_CHANNEL_ID 를 @채널이름 으로 고치기")
    else:
        ok(f"채널 「{c.get('title')}」 id={c.get('id')}")

    mem = requests.get(
        f"{base}/getChatMember", params={"chat_id": c.get("id"), "user_id": bot_id}, timeout=15
    ).json()
    if mem.get("ok"):
        r = mem["result"]
        if r.get("status") != "administrator":
            fatal(f"봇이 관리자가 아니다 (status={r.get('status')})", "채널 → 관리자 → 봇 추가")
        else:
            ok("봇 권한: administrator")
            if r.get("can_post_messages"):
                ok("메시지 게시 가능")
            else:
                fatal("메시지 게시 권한 없음", "채널 관리자 설정에서 '메시지 게시' 켜기")
            if r.get("can_pin_messages"):
                ok("메시지 고정 가능")
            else:
                warn("메시지 고정 권한 없음 — --pin 이 실패한다", "채널 → 관리자 → 봇 → '메시지 고정' 켜기")

    pend = requests.get(f"{base}/getWebhookInfo", timeout=15).json().get("result", {})
    n = pend.get("pending_update_count", 0)
    if pend.get("url"):
        fatal(f"웹훅이 설정돼 있다 ({pend['url']})", "폴링과 충돌한다. deleteWebhook 필요")
    elif n:
        ok(f"웹훅 없음 (대기 중 업데이트 {n}건 — 봇 첫 실행 때 처리된다)")
    else:
        ok("웹훅 없음")

    for name, url, headers, params in (
        ("Unsplash", "https://api.unsplash.com/photos/random", {}, {"client_id": os.environ.get("UNSPLASH_ACCESS_KEY", ""), "query": "gym"}),
        ("Pexels", "https://api.pexels.com/v1/search", {"Authorization": os.environ.get("PEXELS_API_KEY", "")}, {"query": "gym", "per_page": 1}),
    ):
        key = params.get("client_id") or headers.get("Authorization")
        if not key:
            continue
        try:
            code = requests.get(url, headers=headers, params=params, timeout=15).status_code
            (ok if code == 200 else warn)(
                f"{name} HTTP {code}", f"{name} 키 재확인"
            ) if code != 200 else ok(f"{name} HTTP 200")
        except Exception as exc:  # noqa: BLE001
            warn(f"{name} 연결 실패 ({type(exc).__name__})", "일시적일 수 있다")


def main() -> int:
    ap = argparse.ArgumentParser(description="헬스봇 실행 환경 점검")
    ap.add_argument("--net", action="store_true", help="텔레그램/스톡 API 까지 확인")
    args = ap.parse_args()

    print("헬스봇 환경 점검")
    print(f"레포: {ROOT}")

    check_python()
    check_packages()
    check_timezone()
    check_sqlite()
    check_font()
    check_env()
    check_config()
    if args.net:
        check_net()

    print("\n" + "─" * 60)
    if FATAL:
        print(f"치명적 문제 {len(FATAL)}건 — 봇이 뜨지 않는다:")
        for m in FATAL:
            print(f"  · {m}")
        if WARN:
            print(f"경고 {len(WARN)}건")
        return 1

    if WARN:
        print(f"치명적 문제 없음. 경고 {len(WARN)}건 (동작은 한다):")
        for m in WARN:
            print(f"  · {m}")
    else:
        print("전부 정상. 봇을 띄워도 된다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
