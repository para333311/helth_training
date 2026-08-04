"""엔트리포인트.

    python -m bot                 상시 실행 (발행 + 명령 수신)
    python -m bot --serve         수신 전용. 발행은 GitHub Actions 등 외부가 맡을 때
    python -m bot --once photo    특정 잡을 즉시 1회 발행 (테스트용)
    python -m bot --list          잡 이름 목록
    python -m bot --chatid        비공개 채널의 숫자 chat ID 찾기
    python -m bot --check         설정과 채널 연결만 점검하고 종료

데이터 조회·기록 (터미널에서 직접. 자세한 건 docs/06-bot-setup.md)

    python -m bot --brief [--json]        내 운동 데이터 스냅샷
    python -m bot --say "텍스트"           채널에 한 줄 직접 발행
    python -m bot --record condition=3    컨디션·체중·오운완 기록
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from .brief import build_brief, dump_json, format_brief
from .commands import CommandHandler
from .config import load_config
from .content import Content
from .d1 import D1Connection
from .feeds import YoutubeFeeds
from .jobs import Publisher
from .photos import build_source
from .scheduler import DailyJob, IntervalJob, Scheduler
from .store import SchemaMismatch, Store
from .tg import Telegram, TelegramError

log = logging.getLogger("main")


def build_store(cfg) -> Store:
    """CF_ACCOUNT_ID/CF_D1_DATABASE_ID/CF_API_TOKEN 이 다 있으면 Cloudflare D1(원격,
    영구 저장)을 쓰고, 없으면 기존처럼 로컬 SQLite 파일을 쓴다. docs/09-render-setup.md 참고."""
    if cfg.cf_account_id and cfg.cf_d1_database_id and cfg.cf_api_token:
        d1 = D1Connection(cfg.cf_account_id, cfg.cf_d1_database_id, cfg.cf_api_token)
        return Store(cfg.db_path, d1=d1)
    return Store(cfg.db_path)


def build_scheduler(cfg, pub: Publisher, store: Store) -> Scheduler:
    sched = Scheduler(store, cfg.tz)

    # 1시간 주기 자극 (사진 ↔ 유튜브 링크 교대) — 밤에는 쉰다 (기본 06~22시)
    sched.add(
        IntervalJob(
            name="photo",
            fn=pub.motivation_drop,
            minutes=cfg.photo_interval_minutes,
            start_hour=cfg.photo_start_hour,
            end_hour=cfg.photo_end_hour,
        )
    )

    # 아침 미션
    sched.add(DailyJob(name="mission", fn=pub.morning_mission, hour=6, minute=30))

    # 낮 자극 (평일) — 수/일은 270kcal 카드로 자동 전환
    sched.add(
        DailyJob(name="quickfix", fn=pub.quick_fix, hour=12, minute=30, weekdays=(0, 1, 2, 3, 4))
    )
    sched.add(DailyJob(name="quickfix_weekend", fn=pub.quick_fix, hour=15, minute=0,
                       weekdays=(5, 6)))

    # 금요일 근육 상식 퀴즈
    sched.add(DailyJob(name="quiz", fn=pub.quiz, hour=18, minute=0, weekdays=(4,)))

    # 매일 저녁 6시 하이록스 WOD (크로스핏 보드 스타일)
    sched.add(DailyJob(name="hyrox", fn=pub.hyrox_wod, hour=18, minute=0))

    # 밤 체크인
    sched.add(DailyJob(name="checkin", fn=pub.night_checkin, hour=22, minute=0))

    # 일요일 주간 결산
    sched.add(DailyJob(name="weekly", fn=pub.weekly_report, hour=21, minute=0, weekdays=(6,)))

    # 2주에 한 번 리셋 데이
    sched.add(
        DailyJob(
            name="reset_day",
            fn=pub.reset_day,
            hour=20,
            minute=0,
            weekdays=(6,),
            every_n_weeks=2,
        )
    )

    return sched


def find_chat_id(tg: Telegram, rounds: int = 12) -> None:
    """비공개 채널은 @username 이 없어 숫자 ID 가 필요하다.

    사용법: 채널에 아무 글이나 하나 올린 뒤 이 명령을 실행한다.
    봇이 아직 한 번도 폴링하지 않았다면 최근 24시간의 채널 글이 대기열에 남아 있다.
    """
    print("최근 채널 글에서 chat ID 를 찾는 중...\n")
    offset = None
    seen: dict[int, tuple[str, str]] = {}

    for _ in range(rounds):
        updates = tg.get_updates(offset, timeout=10)
        for update in updates:
            offset = update["update_id"] + 1
            for key in ("channel_post", "edited_channel_post", "message", "my_chat_member"):
                chat = update.get(key, {}).get("chat")
                if chat and chat["id"] not in seen:
                    seen[chat["id"]] = (chat.get("type", "?"),
                                        chat.get("title") or chat.get("first_name", ""))
        if seen:
            break

    if not seen:
        print("아무것도 못 찾았습니다.\n")
        print("확인할 것:")
        print("  1. 봇이 채널 관리자로 추가돼 있는지")
        print("  2. 봇을 관리자로 추가한 뒤에 채널에 글을 올렸는지")
        print("  3. 그 글이 24시간 이내인지 (오래되면 텔레그램이 큐에서 버립니다)")
        print("\n채널에 아무 글이나 새로 올리고 다시 실행해보세요.")
        return

    print("찾았습니다:\n")
    for chat_id, (chat_type, title) in seen.items():
        print(f"  {chat_type:10} {chat_id:>16}  {title}")

    channels = [c for c, (t, _) in seen.items() if t == "channel"]
    if channels:
        print(f"\n→ TELEGRAM_CHANNEL_ID 에 넣을 값:  {channels[0]}")
    else:
        print("\n채널(channel) 타입이 안 보입니다. 봇이 채널 관리자인지 확인하세요.")


def _start_health_server(port: int) -> None:
    """Render 같은 Web Service 플랫폼용 최소 HTTP 응답.

    발행·명령 처리와는 무관하다. 무료 플랜은 인바운드 HTTP 트래픽이
    일정 시간 없으면 슬립하므로, 외부 핑 서비스(UptimeRobot 등)가 이
    포트를 주기적으로 두드려 봇 프로세스를 깨어있게 하는 용도다.
    PORT 환경변수가 없는 노트북·VPS 실행에서는 이 서버가 켜지지 않는다.
    """

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_args) -> None:
            pass  # 핑마다 로그 찍히면 도배된다

    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


TIERS = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def record_values(cfg, store: Store, pairs: list[str]) -> int:
    """컨디션·체중·오운완을 DB 에 적는다.

    같은 값을 텔레그램 DM 명령(/condition, /weight, /done)으로도 넣을 수 있다.
    이쪽은 노트북 터미널에서 직접 쓸 때의 경로다.
    """
    today = datetime.now(cfg.tz).date()
    uid = cfg.owner_id
    ok = True

    for pair in pairs:
        key, _, raw = pair.partition("=")
        key, raw = key.strip().lower(), raw.strip()
        if not raw:
            print(f"값이 없습니다: {pair!r}  (예: condition=3)")
            ok = False
            continue

        if key == "condition":
            try:
                score = int(raw)
            except ValueError:
                print(f"condition 은 1~5 정수입니다: {raw!r}")
                ok = False
                continue
            if not 1 <= score <= 5:
                print(f"condition 은 1~5 범위입니다: {score}")
                ok = False
                continue
            store.record_condition(uid, today, score)
            print(f"컨디션 {score}/5 기록 ({today})")

        elif key == "weight":
            try:
                kg = float(raw)
            except ValueError:
                print(f"weight 는 숫자입니다: {raw!r}")
                ok = False
                continue
            if not 25 <= kg <= 300:
                print(f"체중이 범위를 벗어납니다: {kg}")
                ok = False
                continue
            _, lost = store.record_weight(uid, today, kg)
            msg = f"체중 {kg}kg 기록 ({today})"
            if lost is not None:
                msg += f" · 시작 대비 {lost:+.1f}kg"
            print(msg)

        elif key == "done":
            tier = raw.lower()
            if tier not in TIERS:
                print(f"done 은 green|yellow|red 입니다: {raw!r}")
                ok = False
                continue
            res = store.record_done(uid, today, tier=tier)
            print(f"오운완 {TIERS[tier]} 기록 · 연속 {res['streak']}일 "
                  f"(최고 {res['best']}일)"
                  + ("  [오늘 이미 기록돼 있었음]" if res["already"] else ""))

        else:
            print(f"모르는 항목입니다: {key!r}  (condition / weight / done)")
            ok = False

    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except SchemaMismatch as exc:
        # 트레이스백은 원인을 가린다. 조치 방법만 그대로 보여준다.
        print(str(exc), file=sys.stderr)
        return 1


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bot")
    parser.add_argument("--once", metavar="JOB", help="잡 1회 즉시 실행")
    parser.add_argument("--tick", action="store_true",
                        help="스케줄을 한 번만 확인하고 종료 (cron / GitHub Actions 용)")
    parser.add_argument("--list", action="store_true", help="잡 목록 출력")
    parser.add_argument("--chatid", action="store_true", help="채널 chat ID 찾기")
    parser.add_argument("--check", action="store_true", help="설정 점검만")
    parser.add_argument("--addfeed", metavar="URL", help="유튜브 채널 등록 (URL 또는 @핸들)")
    parser.add_argument("--feeds", action="store_true", help="등록된 유튜브 채널 목록")
    parser.add_argument("-v", "--verbose", action="store_true")

    coach = parser.add_argument_group("데이터 조회·기록")
    coach.add_argument("--brief", action="store_true",
                       help="내 운동 데이터 스냅샷 출력")
    coach.add_argument("--json", action="store_true", help="--brief 를 JSON 으로")
    coach.add_argument("--say", metavar="TEXT",
                       help="이 텍스트를 채널에 그대로 발행한다")
    coach.add_argument("--by", metavar="NAME", default="",
                       help='--say 에 서명을 붙인다. 예: --by 코치')
    coach.add_argument("--pin", action="store_true", help="--say 한 글을 고정한다")
    coach.add_argument("--record", metavar="K=V", action="append", default=[],
                       help="데이터 기록. condition=1~5 / weight=71.2 / done=green|yellow|red "
                            "(여러 번 지정 가능)")
    coach.add_argument("--serve", action="store_true",
                       help="수신 전용. 내장 스케줄러를 끈다 (발행을 외부가 맡을 때)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    # --brief / --record 는 채널로 아무것도 보내지 않으므로 채널 설정 없이도 돌아야 한다.
    offline = args.brief or bool(args.record)
    cfg = load_config(require_channel=not (args.chatid or offline))
    feeds = YoutubeFeeds(cfg.data_dir / "youtube_channels.json")

    if args.addfeed:
        entry = feeds.add(args.addfeed)
        if entry:
            print(f"등록: {entry['name']}  ({entry['channel_id']})")
            return 0
        print("등록하지 못했습니다. 채널 URL 이나 @핸들이 맞는지 확인하세요.")
        return 1

    if args.feeds:
        items = feeds.channels()
        if not items:
            print("등록된 채널이 없습니다.\n  python -m bot --addfeed https://www.youtube.com/@채널명")
        for item in items:
            print(f"  {item['channel_id']}  {item['name']}")
        return 0

    # --- 네트워크가 필요 없는 명령들 ----------------------------------------
    # 텔레그램에 붙기 전에 처리한다. 노트북이 오프라인이어도 데이터는 읽/쓰기 가능해야 한다.

    if args.record:
        store = build_store(cfg)
        if not cfg.owner_id:
            print("OWNER_USER_ID 가 설정돼 있지 않아 누구 기록인지 알 수 없습니다.")
            print("  .env 에 OWNER_USER_ID=<내 텔레그램 user id> 를 넣으세요.")
            return 1
        return record_values(cfg, store, args.record)

    if args.brief:
        store = build_store(cfg)
        content = Content(cfg.data_dir)
        b = build_brief(cfg, store, content, feeds)
        print(dump_json(b) if args.json else format_brief(b))
        return 0

    tg = Telegram(cfg.token)

    if args.chatid:
        find_chat_id(tg)
        return 0

    store = build_store(cfg)
    content = Content(cfg.data_dir)
    photos = build_source(cfg, store)
    pub = Publisher(cfg, tg, store, content, photos, feeds)
    sched = build_scheduler(cfg, pub, store)

    if args.list:
        for name in sched.job_names():
            print(name)
        return 0

    try:
        me = tg.get_me()
    except TelegramError as exc:
        log.error("봇 토큰이 유효하지 않습니다: %s", exc)
        return 1

    log.info("봇 @%s 로 접속했습니다", me.get("username", "?"))

    # 발행 대상을 먼저 확인해서 로그에 남긴다.
    # 채널 ID 를 잘못 넣으면 발행 자체는 성공하고 엉뚱한 곳(주로 봇 DM)으로 가는데,
    # 이걸 찍어두지 않으면 "성공했다는데 채널에 없다"에서 막힌다.
    if not args.chatid:
        try:
            chat = tg.call("getChat", chat_id=cfg.channel_id)
            kind = chat.get("type", "?")
            log.info(
                "발행 대상: %s (%s, id=%s)",
                chat.get("title") or chat.get("username") or chat.get("first_name", "?"),
                kind, chat.get("id"),
            )
            if kind != "channel":
                log.warning("대상이 채널이 아닙니다 (%s). TELEGRAM_CHANNEL_ID 를 확인하세요.", kind)
                log.warning("공개 채널이면 @채널이름, 비공개면 -100 으로 시작하는 숫자 ID 입니다.")
        except TelegramError as exc:
            log.error("채널에 접근할 수 없습니다: %s", exc)
            log.error("TELEGRAM_CHANNEL_ID=%r · 봇이 채널 관리자인지 확인하세요.", cfg.channel_id)
            return 1

    if args.say:
        # 정형 발행 말고 한 줄을 직접 올릴 때 쓴다.
        # --by 를 주면 본문 끝에 서명이 붙어서 정형 발행과 구분된다.
        text = args.say.strip()
        if not text:
            log.error("--say 에 빈 문자열이 왔습니다.")
            return 1
        if args.by:
            text = f"{text}\n\n— {args.by.strip()}"
        try:
            msg = tg.send_message(cfg.channel_id, text)
        except TelegramError as exc:
            log.error("발행 실패: %s", exc)
            return 1
        log.info("발행함 [%s] msg=%s", args.by or "헬스봇", msg.get("message_id"))
        if args.pin:
            try:
                tg.pin(cfg.channel_id, msg["message_id"])
                log.info("고정했습니다.")
            except TelegramError as exc:
                log.warning("고정 실패: %s", exc)
        return 0

    if args.check:
        log.info(
            "미션 %d개 · 하이록스 WOD %d개 · 자극문구 %d개 · 퀴즈 %d개 · 내 사진 %d장 · 유튜브 채널 %d개",
            len(content.missions), len(content.hyrox), len(content.quick_fixes), len(content.quizzes),
            store.count_photos(), len(feeds.channels()),
        )
        if not feeds.channels() and not cfg.unsplash_key and not cfg.pexels_key \
                and store.count_photos() == 0:
            log.warning("사진·영상 소스가 하나도 없습니다. 시간별 자극이 텍스트만 나갑니다.")
            log.warning("  python -m bot --addfeed https://www.youtube.com/@채널명")
        log.info("설정 정상입니다.")
        return 0

    if args.once:
        now = datetime.now(cfg.tz)
        if not sched.run_named(args.once, now):
            log.error("그런 잡이 없습니다: %s (--list 로 확인)", args.once)
            return 1
        return 0

    if args.tick:
        # 상시 실행 대신 외부 cron 이 주기적으로 부르는 모드.
        # 명령 수신(getUpdates)은 하지 않으므로 /done 같은 DM 명령은 동작하지 않는다.
        sched.tick(datetime.now(cfg.tz))
        return 0

    handler = CommandHandler(cfg, tg, store, content)
    handler.register_commands()

    port = os.environ.get("PORT")
    if port:
        threading.Thread(target=_start_health_server, args=(int(port),), daemon=True).start()
        log.info("헬스체크 서버 시작 (포트 %s) — Web Service 슬립 방지용", port)

    if args.serve:
        # 발행은 GitHub Actions 등 외부가 맡고, 이 프로세스는 수신만 한다.
        # 내장 스케줄러까지 돌면 같은 미션이 두 번 올라간다.
        log.info("수신 전용 모드 — 내장 스케줄러를 끕니다. 발행은 외부에서 지시하세요.")
    else:
        log.info(
            "사진 %d분 주기 (%02d~%02d시), 미션 06:30, 체크인 22:00",
            cfg.photo_interval_minutes, cfg.photo_start_hour, cfg.photo_end_hour,
        )
    log.info("시작합니다. Ctrl+C 로 종료.")

    while True:
        try:
            handler.poll(timeout=15)  # 명령 수신 (긴 폴링이 곧 틱 간격이 된다)
            if not args.serve:
                sched.tick()
        except KeyboardInterrupt:
            log.info("종료합니다.")
            return 0
        except Exception:
            log.exception("루프 오류 — 10초 후 계속")
            time.sleep(10)


if __name__ == "__main__":
    sys.exit(main())
