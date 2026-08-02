"""채널에 발행하는 개별 잡들."""

from __future__ import annotations

import logging
import random
from datetime import date, datetime

from .cards import render_photo_quote, render_quote
from .content import WEEKDAY_THEME, Content, progress_bar
from .photos import PhotoSource
from .store import Store
from .tg import Telegram, TelegramError

log = logging.getLogger("jobs")

# 채널 인원이 이 수보다 적으면 "87명이 인증했습니다" 류의 숫자 문구를 생략한다.
# 구독자 2명짜리 채널에서 숫자를 노출하면 오히려 의욕이 깎인다.
MIN_MEMBERS_FOR_STATS = 15

MILESTONES = {7: "일주일 채우셨습니다.\n습관이 만들어지기 시작하는 지점이 딱 여기입니다.",
              21: "3주입니다.\n이제 안 하는 게 어색해지기 시작합니다.",
              50: "50일.\n여기까지 오셨으면 이건 이미 습관입니다.",
              84: "시즌 완주입니다.\n84일 전의 나와 지금의 나는 다른 사람입니다."}


class Publisher:
    def __init__(self, cfg, tg: Telegram, store: Store, content: Content,
                 photos: PhotoSource | None, feeds=None):
        self.cfg = cfg
        self.tg = tg
        self.store = store
        self.content = content
        self.photos = photos
        self.feeds = feeds
        self._member_count: int | None = None

    # --- 도우미 -------------------------------------------------------------

    def _rng(self, salt: str, now: datetime) -> random.Random:
        """같은 슬롯에서 재시도해도 같은 결과가 나오도록 시드를 고정."""
        return random.Random(f"{salt}:{now:%Y-%m-%d-%H}")

    def _today(self, now: datetime) -> date:
        return now.date()

    def _d_index(self, now: datetime) -> int:
        return self.cfg.day_index(self._today(now))

    def _week_rotation(self, now: datetime) -> int:
        return max(0, (self._d_index(now) - 1) // 7)

    def member_count(self) -> int:
        if self._member_count is None:
            try:
                self._member_count = self.tg.call(
                    "getChatMemberCount", chat_id=self.cfg.channel_id)
            except TelegramError:
                self._member_count = 0
        return self._member_count

    def _send(self, text: str, **kw) -> dict | None:
        try:
            msg = self.tg.send_message(self.cfg.channel_id, text, **kw)
        except TelegramError as exc:
            log.error("발행 실패: %s", exc)
            return None
        self._log_sent("텍스트", msg, text.split("\n")[0])
        return msg

    def _log_sent(self, kind: str, msg: dict | None, summary: str = "") -> None:
        """무엇을 어디로 보냈는지 남긴다.

        성공했을 때 아무 로그도 없으면 "발행은 됐다는데 채널에 없다"는 상황에서
        어디로 갔는지 추적할 방법이 사라진다.
        """
        if not msg:
            return
        chat = msg.get("chat", {})
        where = chat.get("title") or chat.get("username") or chat.get("first_name", "?")
        log.info(
            "발행함 [%s] → %s (%s, id=%s) msg=%s %s",
            kind, where, chat.get("type", "?"), chat.get("id", "?"),
            msg.get("message_id", "?"), summary[:40],
        )

    # --- 잡 -----------------------------------------------------------------

    def motivation_drop(self, now: datetime) -> None:
        """1시간 주기 자극. 세 종류를 돌려가며 낸다.

          0) 유튜브 링크  — "남들도 지금 하고 있다"는 신호가 가장 세고, 누르면 따라할 수 있다
          1) 사진        — 내가 보낸 오운완 사진 또는 스톡
          2) 명언 카드    — 직접 그린 이미지

        앞의 것이 안 되면 뒤로 넘어가고, 전부 안 되면 텍스트로 대체한다.
        어떤 경우에도 그 시간대가 비지 않는다.
        """
        order = now.hour % 3

        if order == 0 and self.feeds and self._video_drop(now):
            return
        if order == 2 and self._quote_drop(now):
            return
        if self._photo_drop(now):
            return
        # 사진 소스가 비어 있으면 명언 카드로, 그것도 안 되면 텍스트로
        if self._quote_drop(now):
            return
        self._text_drop(now)

    def _quote_drop(self, now: datetime) -> bool:
        """명언 카드를 그려서 보낸다. Pillow 나 한글 폰트가 없으면 False."""
        if not self.content.quotes:
            return False

        rng = self._rng("quote", now)
        # 30개를 다 돌기 전에 같은 명언이 다시 나오지 않게 순환시킨다
        unseen = set(self.store.unseen("quote", [q["text"] for q in self.content.quotes]))
        pool = [q for q in self.content.quotes if q["text"] in unseen] or self.content.quotes
        quote = rng.choice(pool)

        image = render_quote(quote["text"], quote.get("source"), rng)
        if image is None:
            return False

        try:
            msg = self.tg.send_photo(self.cfg.channel_id, image, caption=None)
        except TelegramError as exc:
            log.error("명언 카드 발행 실패: %s", exc)
            return False

        self._log_sent("명언카드", msg, quote["text"].replace("\n", " "))
        self.store.mark_seen("quote", quote["text"])
        return True

    def _video_drop(self, now: datetime) -> bool:
        rng = self._rng("video", now)
        try:
            video = self.feeds.pick(rng, self.store)
        except Exception as exc:
            log.warning("피드 조회 실패: %s", exc)
            return False

        if not video:
            return False

        rng2 = self._rng("vcaption", now)
        card = self.content.pick(self.content.photo_captions, rng2)
        hook = card["text"] if card else "남들은 오늘도 하고 있습니다."

        # 링크만 보낸다 — 영상을 재업로드하지 않는다. 미리보기는 텔레그램이 붙인다.
        text = f"{hook}\n\n▶️ {video.title}\n{video.channel}\n\n{video.url}"
        msg = self._send(text, disable_web_page_preview=False)
        if msg:
            self.store.mark_seen("video", video.video_id)
            return True
        return False

    def _photo_drop(self, now: datetime) -> bool:
        """사진에 명언을 합성해 한 장으로 낸다. 캡션(출처 줄)은 붙이지 않는다.

        합성이 안 되면(Pillow/폰트 없음, 다운로드 실패 등) 원본 사진 + 캡션으로
        조용히 대체한다 — 이 시간대가 아예 비는 것보다는 낫다.
        """
        rng = self._rng("photo", now)
        caption_card = self.content.pick(self.content.photo_captions, rng)
        caption = caption_card["text"] if caption_card else "오늘도 하나만."

        photo = self.photos.fetch(self.cfg.photo_query, rng, self.store) if self.photos else None
        if photo is None:
            return False

        composited = None
        raw = photo.load_bytes(self.tg)
        if raw is not None:
            composited = render_photo_quote(raw, caption, rng)

        try:
            if composited is not None:
                msg = self.tg.send_photo(self.cfg.channel_id, composited)
            else:
                # 합성 실패 폴백 — 원본 사진 그대로, 캡션은 텍스트로 얹는다
                full = f"{caption}\n\n{photo.credit}" if photo.credit else caption
                msg = self.tg.send_photo(self.cfg.channel_id, photo.ref, caption=full)
        except TelegramError as exc:
            log.error("사진 발행 실패: %s", exc)
            return False

        self._log_sent("사진", msg, caption)
        if photo.key:
            self.store.mark_seen("photo", photo.key)
            if getattr(self.photos, "name", "") == "chain":
                self.store.mark_photo_used(photo.key)
        return True

    def _text_drop(self, now: datetime) -> None:
        rng = self._rng("photo", now)
        card = self.content.pick(self.content.photo_captions, rng)
        self._send(f"{card['text'] if card else '오늘도 하나만.'}\n\n💪")

    def morning_mission(self, now: datetime) -> None:
        mission = self.content.mission_for(self._today(now), self._week_rotation(now))
        if not mission:
            log.warning("미션 재고가 비어 있습니다")
            return
        text = self.content.render_mission(mission, self._today(now), self._d_index(now))
        self._send(text)

    def hyrox_wod(self, now: datetime) -> None:
        """매일 저녁 6시, 헬스장용 하이록스 WOD.

        1km 달리기와 근력 스테이션을 번갈아 배치한다 (러닝 → 스테이션 → 러닝 → …).
        러닝 횟수는 HYROX_RUNS(기본 3)만큼, 스테이션은 재고를 다 쓸 때까지 안 겹치게 순환한다.
        """
        pool_size = len(self.content.hyrox)
        if not pool_size:
            log.warning("하이록스 스테이션 재고가 비어 있습니다")
            return
        n = min(self.cfg.hyrox_runs, pool_size)

        rng = self._rng("hyrox", now)
        unseen = set(self.store.unseen("hyrox", [s["name"] for s in self.content.hyrox]))
        pool = [s for s in self.content.hyrox if s["name"] in unseen] or self.content.hyrox
        if len(pool) < n:
            pool = self.content.hyrox
        stations = rng.sample(pool, n)

        self._send(self.content.render_hyrox(stations, self._d_index(now)))
        for station in stations:
            self.store.mark_seen("hyrox", station["name"])

    def quick_fix(self, now: datetime) -> None:
        rng = self._rng("quickfix", now)
        # 수/일요일은 270kcal 카드, 나머지는 귀찮음 응급처치
        if now.weekday() in (2, 6) and self.content.kcal_cards:
            card = self.content.pick(self.content.kcal_cards, rng)
            self._send(self.content.render_kcal(card))
            return
        card = self.content.pick(self.content.quick_fixes, rng)
        if card:
            self._send(self.content.render_quick_fix(card))

    def quiz(self, now: datetime) -> None:
        rng = self._rng("quiz", now)
        q = self.content.pick(self.content.quizzes, rng)
        if not q:
            return
        try:
            self.tg.send_quiz(
                self.cfg.channel_id, q["question"], q["options"], q["correct"], q["explanation"]
            )
        except TelegramError as exc:
            log.error("퀴즈 발행 실패: %s", exc)

    def night_checkin(self, now: datetime) -> None:
        """밤 인증 회수. 3일에 한 번은 투표, 나머지는 인라인 버튼.

        solo_mode 에서는 투표를 쓰지 않는다 — 혼자 하는 익명 투표는 의미가 없다.

        버튼은 텔레그램 "리액션"이 아니라 진짜 인라인 키보드다. 리액션은 봇에게
        익명 총계로만 오지만, 인라인 버튼은 콜백에 누른 사람의 user_id 가 그대로
        온다 — 그래서 채널에서 바로 눌러도 개인 스트릭이 정확히 기록된다
        (commands.py 의 콜백 핸들러 참고).
        """
        d = self._d_index(now)

        milestone = MILESTONES.get(d)
        if milestone:
            self._send(f"🎉 D+{d}\n\n{milestone}\n\n💪")
            return

        if not self.cfg.solo_mode and d % 3 == 0:
            try:
                msg = self.tg.send_poll(
                    self.cfg.channel_id,
                    "오늘 어디까지 하셨나요?",
                    ["🟢 귀찮음 모드", "🟡 보통 모드", "🔴 여유 모드", "😮‍💨 오늘은 패스"],
                )
                poll = msg.get("poll", {})
                if poll.get("id"):
                    self.store.record_poll(poll["id"], self._today(now), poll)
                return
            except TelegramError as exc:
                log.error("투표 발행 실패: %s", exc)

        lines = ["🌙 오운완 체크", "", "오늘 미션, 하셨나요?", "", "아래 버튼 하나만 눌러주세요."]

        if not self.cfg.solo_mode and self.member_count() >= MIN_MEMBERS_FOR_STATS:
            week = self.store.week_summary(self._today(now))["reactions"].get("💪", 0)
            if week:
                lines += ["", f"이번 주 누적 💪 {week}회."]

        if self.cfg.solo_mode and self.cfg.owner_id:
            stats = self.store.stats(self.cfg.owner_id, self._today(now))
            if stats["streak"]:
                lines += ["", f"현재 연속 {stats['streak']}일 · 이번 주 {stats['week']}/7일"]

        keyboard = {
            "inline_keyboard": [[
                {"text": "💪 했다", "callback_data": "checkin:done"},
                {"text": "😮‍💨 오늘은 못 했다", "callback_data": "checkin:skip"},
            ]]
        }

        msg = self._send("\n".join(lines), reply_markup=keyboard)
        if msg:
            self.store.mark_seen("checkin_msg", str(msg.get("message_id")))

    def weekly_report(self, now: datetime) -> None:
        today = self._today(now)
        d = self._d_index(now)
        week_no = max(1, (d + 6) // 7)
        summary = self.store.week_summary(today)

        # 시즌 진행 게이지는 일수 기준 (체중은 개인 데이터라 채널에 공개하지 않는다)
        bar = progress_bar(d, self.cfg.season_days)

        lines = [
            f"📊 {self.cfg.season_name} · {week_no}주차 결산",
            "",
            f"{bar}  D+{d} / {self.cfg.season_days}",
            "",
        ]

        if self.cfg.solo_mode:
            lines += self._solo_week_lines(today)
        elif self.member_count() >= MIN_MEMBERS_FOR_STATS:
            tiers = summary["tiers"]
            total_votes = sum(tiers.values())
            lines += [f"이번 주 오운완  {summary['done_total']}회"]
            if total_votes:
                pct = {k: round(v * 100 / total_votes) for k, v in tiers.items()}
                lines += [
                    "",
                    "난이도 분포",
                    f"🟢 {pct['🟢']}%   🟡 {pct['🟡']}%   🔴 {pct['🔴']}%",
                    "",
                    "🟢가 제일 많습니다. 그게 정상이고, 그게 목표입니다.",
                ]
        else:
            lines += [
                "이번 주도 채널이 살아있었습니다.",
                "",
                "숫자는 아직 안 셉니다.",
                "지금은 며칠 했는지보다 안 그만두는 게 전부입니다.",
            ]

        nxt = " · ".join(f"{WEEKDAY_THEME[i][0][0]} {WEEKDAY_THEME[i][1]}" for i in range(7))
        lines += ["", "━━━━━━━━━━━", "", "다음 주 예고", nxt, "", "내일 아침 7:30에 뵙겠습니다."]

        self._send("\n".join(lines))

    def _solo_week_lines(self, today: date) -> list[str]:
        """혼자 쓰는 채널의 주간 결산 — 채널 집계 대신 본인 기록을 보여준다."""
        if not self.cfg.owner_id:
            return [
                "이번 주도 채널이 살아있었습니다.",
                "",
                "OWNER_USER_ID 를 설정하면 여기에 내 기록이 나옵니다.",
            ]

        stats = self.store.stats(self.cfg.owner_id, today)
        photos = self.store.count_photos(self.cfg.owner_id)

        lines = [
            f"이번 주   {stats['week']} / 7일",
            f"연속      {stats['streak']}일",
            f"최고 기록 {stats['best']}일",
            f"누적      {stats['total']}일",
        ]
        if photos:
            lines.append(f"모은 사진 {photos}장")

        lines.append("")
        if stats["week"] >= 5:
            lines.append("이 정도면 충분합니다. 다음 주도 이대로만.")
        elif stats["week"] >= 2:
            lines.append("빠진 날이 있어도 이번 주는 성공입니다.")
        else:
            lines.append("이번 주는 거의 못 했네요.\n그래도 채널은 안 나가셨습니다. 그거면 다음 주가 있습니다.")

        return lines

    def reset_day(self, now: datetime) -> None:
        """2주에 한 번, 스트릭 끊긴 사람을 위한 공식 사면."""
        self._send(
            "🔄 리셋 데이\n\n"
            "지난주에 며칠 빠지셨나요? 상관없습니다.\n"
            "오늘부터 다시 D+1입니다.\n\n"
            "이 채널엔 실패가 없습니다.\n"
            "멈춘 기간이 있고, 다시 시작한 날이 있을 뿐입니다.\n\n"
            "내일 아침 7:30에 뵙겠습니다."
        )
