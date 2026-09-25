"""맥에서 오운완 봇 되살리기 — 채널 ID·주인 ID 를 텔레그램에서 받아 .env 를 채우고 launchd 로 상시 실행한다(2026-09-24).

옛 윈도 노트북에만 있던 .env 가 이사 때 사라졌다(paracano 오답노트 #221). 토큰은 ~/.helth/token.
파라님이 ① 봇에게 /start ② 오운완 채널에 아무 글 하나 — 를 하면 여기서 두 ID 를 집어 넣는다.
    .venv/bin/python deploy/mac-채우기.py      (최대 24시간 기다린다)
"""
import json, os, pathlib, subprocess, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOKEN = (pathlib.Path.home() / ".helth" / "token").read_text().strip()
PLIST = pathlib.Path.home() / "Library" / "LaunchAgents" / "kr.helth.bot.plist"


def api(m, **q):
    url = f"https://api.telegram.org/bot{TOKEN}/{m}"
    data = json.dumps(q).encode() if q else None
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=40))


def main():
    채널 = 주인 = None
    오프셋 = 0
    끝 = time.time() + 24 * 3600
    while time.time() < 끝 and not (채널 and 주인):
        try:
            받은 = api("getUpdates", offset=오프셋, timeout=25).get("result", [])
        except Exception as e:   # 망이 잠깐 끊겨도(9/24 23:25 Connection reset) 기다림을 멈추지 않는다
            print("망 오류 — 10초 뒤 다시", e, flush=True); time.sleep(10); continue
        for u in 받은:
            오프셋 = u["update_id"] + 1
            cp = u.get("channel_post") or u.get("my_chat_member", {})
            if cp.get("chat", {}).get("type") == "channel":
                채널 = cp["chat"]["id"]; print("채널", cp["chat"].get("title"), 채널, flush=True)
            m = u.get("message")
            if m and m.get("chat", {}).get("type") == "private":
                주인 = m["from"]["id"]; print("주인", m["from"].get("first_name"), flush=True)
            if m and m.get("forward_from_chat", {}).get("type") == "channel":
                채널 = m["forward_from_chat"]["id"]; print("채널(전달)", 채널, flush=True)
    if not (채널 and 주인):
        print("24시간 안에 못 받았다 — 채널", 채널, "주인", 주인); return 1
    api("getUpdates", offset=오프셋, timeout=0)   # 받은 것은 소진 — 봇이 같은 /start 를 또 처리하지 않게
    env = ROOT / ".env"
    env.write_text("\n".join([
        f"TELEGRAM_BOT_TOKEN={TOKEN}", f"TELEGRAM_CHANNEL_ID={채널}", "TELEGRAM_BOT_USERNAME=helth_training_bot",
        f"OWNER_USER_ID={주인}", "SOLO_MODE=true", "SEASON_START=2026-07-30", "PHOTO_INTERVAL_MINUTES=60",
        "PHOTO_START_HOUR=16", "PHOTO_END_HOUR=21", "PHOTO_SOURCE=local", "HYROX_RUNS=3", "TZ=Asia/Seoul", ""]), encoding="utf-8")
    env.chmod(0o600)
    ok = subprocess.run([str(ROOT / ".venv" / "bin" / "python"), "-m", "bot", "--check"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    print(ok.stdout[-800:], ok.stderr[-800:])
    if ok.returncode != 0:
        api("sendMessage", chat_id=주인, text="오운완 봇 설정 확인이 실패했습니다 — 클로드가 보고 고칩니다"); return 1
    PLIST.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>kr.helth.bot</string>
<key>ProgramArguments</key><array><string>{ROOT}/.venv/bin/python</string><string>-m</string><string>bot</string></array>
<key>WorkingDirectory</key><string>{ROOT}</string>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>{ROOT}/data/bot.log</string><key>StandardErrorPath</key><string>{ROOT}/data/bot.log</string>
<key>EnvironmentVariables</key><dict><key>TZ</key><string>Asia/Seoul</string></dict>
</dict></plist>
""")
    (ROOT / "data").mkdir(exist_ok=True)
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/kr.helth.bot"], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST)], check=True)
    api("sendMessage", chat_id=주인, text="✅ 오운완 봇이 맥미니에서 다시 돕니다. 기록(스트릭)은 오늘부터 새로 쌓입니다.")
    print("끝"); return 0


if __name__ == "__main__":
    sys.exit(main())
