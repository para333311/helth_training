"""봇 1:1 대화 명령어. 개인 스트릭은 여기서만 정확히 집계된다.

채널 리액션은 봇에게 익명 총계(message_reaction_count)로만 오기 때문에
누가 눌렀는지 알 수 없다. 개인 기록을 원하는 사람만 DM 으로 넘어온다.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime

from .content import Content, progress_bar
from .store import Store
from .tg import Telegram, TelegramError

log = logging.getLogger("cmd")

HELP = """혼자보는 운동 봇

/done    오늘 오운완 기록
/streak  내 연속 기록
/skip    오늘은 패스 (기록 유지)
/mission 오늘의 미션 다시 보기
/random  지금 할 수 있는 30초 운동
/weight  체중 기록 (예: /weight 62.4)
/condition 오늘 컨디션 기록 (예: /condition 3, 1~5)
/myphotos 내가 보낸 사진 수 / 전부 삭제
/help    이 목록

📷 사진을 그냥 보내면 채널에 익명으로 올라갑니다.

🟢만 해도 오운완입니다. 진심입니다."""

PHOTO_THANKS = """📷 사진 받았습니다.

시간마다 올라가는 자극 사진에 익명으로 들어갑니다.
보낸 사람 이름은 채널에 절대 표시되지 않습니다.

마음이 바뀌면 /myphotos 로 언제든 전부 삭제할 수 있습니다.

⚠️ 본인이 찍은 사진만 보내주세요.
남의 사진(인스타 등에서 가져온 것)은 보내면 안 됩니다.
얼굴이 나오는 게 부담되면 운동 기구, 물병, 매트,
땀 흘린 바닥 사진도 충분히 자극이 됩니다."""

WELCOME = """👋 혼자보는 운동

헬스장 안 갑니다.
몸 사진 안 올립니다.

매일 미션이 3단계로 나옵니다.
🟢 1~2분  🟡 5~8분  🔴 15분

어느 걸 하든 오운완입니다.

운동한 날 여기에 /done 만 보내주세요.
연속 기록을 세어드립니다.

⚠️ 통증이 있으면 즉시 멈추세요. 기존 질환이 있거나
임신 중이거나 심혈관 질환이 있다면 시작 전 전문가와
상의하세요. 이 채널은 의료 조언이 아닙니다.

/help 로 나머지 명령어를 볼 수 있습니다."""


class CommandHandler:
    def __init__(self, cfg, tg: Telegram, store: Store, content: Content):
        self.cfg = cfg
        self.tg = tg
        self.store = store
        self.content = content
        self._offset: int | None = None

    # --- 업데이트 루프 -------------------------------------------------------

    def poll(self, timeout: int = 15) -> None:
        for update in self.tg.get_updates(self._offset, timeout=timeout):
            self._offset = update["update_id"] + 1
            try:
                self._dispatch(update)
            except Exception:
                log.exception("업데이트 처리 실패")

    def _dispatch(self, update: dict) -> None:
        if "message" in update:
            self._on_message(update["message"])
        elif "callback_query" in update:
            self._on_callback(update["callback_query"])
        elif "poll" in update:
            poll = update["poll"]
            self.store.record_poll(poll["id"], datetime.now(self.cfg.tz).date(), poll)
        elif "message_reaction_count" in update:
            item = update["message_reaction_count"]
            counts = {r["type"].get("emoji", "?"): r["total_count"]
                      for r in item.get("reactions", [])
                      if r.get("type", {}).get("type") == "emoji"}
            self.store.record_reaction_count(
                item["message_id"], datetime.now(self.cfg.tz).date(), counts
            )

    # --- 채널 인라인 버튼 ------------------------------------------------------

    def _on_callback(self, cq: dict) -> None:
        """밤 체크인 인라인 버튼 클릭.

        리액션(message_reaction_count)과 달리 콜백은 누른 사람의 user_id 가
        그대로 오기 때문에, DM 을 따로 열지 않아도 채널에서 바로 개인 스트릭이
        기록된다.
        """
        data = cq.get("data", "")
        user = cq.get("from", {})
        user_id = user.get("id")
        toast = ""

        if user_id and data in ("checkin:done", "checkin:skip"):
            self.store.ensure_user(user_id, user.get("first_name", ""))
            today = datetime.now(self.cfg.tz).date()

            if data == "checkin:done":
                result = self.store.record_done(user_id, today)
                if result["already"]:
                    toast = "이미 기록돼 있어요."
                else:
                    stats = self.store.stats(user_id, today)
                    toast = f"💪 기록됨 · 연속 {stats['streak']}일"
            else:
                self.store.record_done(user_id, today, tier="none", kind="skip")
                toast = "오늘은 패스로 기록했어요. 연속 기록은 유지됩니다."

        try:
            self.tg.call("answerCallbackQuery", callback_query_id=cq["id"], text=toast or None)
        except TelegramError as exc:
            log.warning("콜백 응답 실패: %s", exc)

    # --- 메시지 -------------------------------------------------------------

    def _on_message(self, msg: dict) -> None:
        chat = msg.get("chat", {})
        if chat.get("type") != "private":
            return  # 채널/그룹 메시지는 명령으로 취급하지 않는다

        user = msg.get("from", {})
        user_id = user.get("id")
        name = user.get("first_name", "")
        if not user_id:
            return

        self.store.ensure_user(user_id, name)

        # 사진을 그냥 보내면 채널 로테이션에 익명으로 등록한다
        if msg.get("photo"):
            self._on_photo(user_id, msg)
            return

        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            return
        command, _, args = text.partition(" ")
        command = command.split("@")[0].lower()

        handler = {
            "/start": self._start,
            "/help": self._help,
            "/done": self._done,
            "/streak": self._streak,
            "/skip": self._skip,
            "/mission": self._mission,
            "/random": self._random,
            "/weight": self._weight,
            "/condition": self._condition,
            "/myphotos": self._myphotos,
        }.get(command)

        if handler:
            handler(user_id, args.strip())
        else:
            self._reply(user_id, "모르는 명령입니다.\n\n" + HELP)

    def _reply(self, chat_id: int, text: str) -> None:
        try:
            self.tg.send_message(chat_id, text)
        except TelegramError as exc:
            log.warning("응답 실패: %s", exc)

    # --- 개별 명령 -----------------------------------------------------------

    def _start(self, uid: int, _: str) -> None:
        self._reply(uid, WELCOME)

    def _help(self, uid: int, _: str) -> None:
        self._reply(uid, HELP)

    def _done(self, uid: int, args: str) -> None:
        tier = {"녹색": "green", "노랑": "yellow", "빨강": "red",
                "🟢": "green", "🟡": "yellow", "🔴": "red"}.get(args.strip(), "green")
        today = datetime.now(self.cfg.tz).date()
        result = self.store.record_done(uid, today, tier)
        stats = self.store.stats(uid, today)
        d = self.cfg.day_index(today)

        head = "이미 오늘 기록돼 있습니다." if result["already"] else "💪 오운완 기록됨"
        self._reply(
            uid,
            f"{head}\n\n"
            f"현재 연속  {stats['streak']}일\n"
            f"최고 기록  {stats['best']}일\n"
            f"이번 주    {stats['week']} / 7일\n\n"
            f"{self.cfg.season_name}  D+{d} / {self.cfg.season_days}",
        )

    def _streak(self, uid: int, _: str) -> None:
        today = datetime.now(self.cfg.tz).date()
        stats = self.store.stats(uid, today)
        d = self.cfg.day_index(today)
        bar = progress_bar(d, self.cfg.season_days)
        self._reply(
            uid,
            f"📊 내 기록\n\n"
            f"현재 연속  {stats['streak']}일\n"
            f"최고 기록  {stats['best']}일\n"
            f"이번 주    {stats['week']} / 7일\n"
            f"누적       {stats['total']}일\n\n"
            f"{self.cfg.season_name}\n{bar}  D+{d} / {self.cfg.season_days}",
        )

    def _skip(self, uid: int, _: str) -> None:
        today = datetime.now(self.cfg.tz).date()
        self.store.record_done(uid, today, tier="none", kind="skip")
        self._reply(
            uid,
            "오늘은 패스로 기록했습니다.\n\n"
            "연속 기록은 그대로 유지됩니다.\n"
            "쉬는 날도 계획의 일부입니다. 내일 뵙겠습니다.",
        )

    def _mission(self, uid: int, _: str) -> None:
        now = datetime.now(self.cfg.tz)
        today = now.date()
        d = self.cfg.day_index(today)
        mission = self.content.mission_for(today, max(0, (d - 1) // 7))
        if not mission:
            self._reply(uid, "오늘 미션을 찾지 못했습니다.")
            return
        self._reply(uid, self.content.render_mission(mission, today, d))

    def _random(self, uid: int, _: str) -> None:
        card = self.content.pick(self.content.quick_fixes, random.Random())
        self._reply(uid, card["text"] if card else "스쿼트 10개. 지금.")

    def _weight(self, uid: int, args: str) -> None:
        try:
            kg = float(args.replace("kg", "").strip())
            if not 20 <= kg <= 400:
                raise ValueError
        except ValueError:
            self._reply(uid, "숫자를 같이 보내주세요.\n예: /weight 62.4")
            return

        today = datetime.now(self.cfg.tz).date()
        _, lost = self.store.record_weight(uid, today, kg)

        lines = [f"기록했습니다: {kg}kg", "", "이 기록은 본인만 볼 수 있습니다."]
        if lost is not None:
            bar = progress_bar(max(0.0, lost), self.cfg.goal_kg)
            lines += ["", f"{bar}  {lost:+.1f} / -{self.cfg.goal_kg}kg"]
        lines += [
            "",
            "체중은 일요일 아침 한 번만 재세요.",
            "매일 재면 물 마신 양 때문에 출렁여서 의욕만 깎입니다.",
        ]
        self._reply(uid, "\n".join(lines))

    def _condition(self, uid: int, args: str) -> None:
        try:
            value = int(args.strip())
            if not 1 <= value <= 5:
                raise ValueError
        except ValueError:
            self._reply(uid, "1~5 사이 숫자로 보내주세요.\n예: /condition 3")
            return

        today = datetime.now(self.cfg.tz).date()
        self.store.record_condition(uid, today, value)
        self._reply(uid, f"기록했습니다: 오늘 컨디션 {value}/5\n\n내일 아침 미션에 반영됩니다.")

    # --- 사진 제출 -----------------------------------------------------------

    def _on_photo(self, uid: int, msg: dict) -> None:
        # 가장 큰 해상도의 file_id 를 저장한다
        sizes = msg.get("photo", [])
        if not sizes:
            return
        file_id = max(sizes, key=lambda s: s.get("file_size", 0))["file_id"]
        caption = (msg.get("caption") or "").strip() or None

        self.store.add_photo(file_id, uid, caption)
        total = self.store.count_photos()

        # 사진을 보냈다는 건 운동을 했다는 뜻이므로 오운완도 같이 기록
        today = datetime.now(self.cfg.tz).date()
        self.store.record_done(uid, today)
        stats = self.store.stats(uid, today)

        self._reply(
            uid,
            f"{PHOTO_THANKS}\n\n"
            f"━━━━━━━━━━━\n\n"
            f"💪 오운완도 같이 기록했습니다.\n"
            f"현재 연속  {stats['streak']}일\n"
            f"모인 사진  {total}장",
        )

    def _myphotos(self, uid: int, args: str) -> None:
        mine = self.store.count_photos(uid)

        if args.strip() in {"삭제", "delete", "지워"}:
            removed = self.store.delete_user_photos(uid)
            self._reply(uid, f"{removed}장 전부 삭제했습니다.\n앞으로 채널에 올라가지 않습니다.")
            return

        if mine == 0:
            self._reply(
                uid,
                "아직 보낸 사진이 없습니다.\n\n"
                "운동하고 사진 한 장 보내주세요.\n"
                "얼굴 안 나와도 됩니다. 매트, 물병, 땀 흘린 바닥도 충분합니다.",
            )
            return

        self._reply(
            uid,
            f"📷 내가 보낸 사진  {mine}장\n\n"
            f"전부 삭제하려면\n/myphotos 삭제",
        )

    # --- 명령 목록 등록 -------------------------------------------------------

    def register_commands(self) -> None:
        import json

        commands = [
            {"command": "done", "description": "오늘 오운완 기록"},
            {"command": "streak", "description": "내 연속 기록"},
            {"command": "skip", "description": "오늘은 패스"},
            {"command": "mission", "description": "오늘의 미션"},
            {"command": "random", "description": "30초 운동 추천"},
            {"command": "weight", "description": "체중 기록"},
            {"command": "condition", "description": "오늘 컨디션 기록 (1~5)"},
            {"command": "myphotos", "description": "내가 보낸 사진 관리"},
            {"command": "help", "description": "명령어 목록"},
        ]
        try:
            self.tg.call("setMyCommands", commands=json.dumps(commands, ensure_ascii=False))
        except TelegramError as exc:
            log.warning("명령어 등록 실패: %s", exc)
