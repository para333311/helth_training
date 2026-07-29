# 07. 라즈베리파이로 상시 실행

GitHub Actions 는 "정해진 시간에 채널에 글 올리기"만 한다. `/done`, `/streak`,
사진 제출처럼 **봇이 사용자 메시지를 실시간으로 받아야 하는 기능**은 봇이 계속
떠 있어야 동작한다. 그래서 라즈베리파이 같은 상시 전원 기기가 필요하다.

이 문서를 따라 하면 라즈베리파이가 24시간 봇을 돌리고, 재부팅돼도 자동으로 다시 켜진다.

---

## GitHub Actions 와의 역할 분담

**둘 다 켜둘 필요는 없다. 라즈베리파이 하나만 켜면 전부 된다.**

| | GitHub Actions | 라즈베리파이 |
|---|---|---|
| 채널 자동 발행 | ✅ | ✅ |
| `/done`, `/streak`, `/skip` | ❌ | ✅ |
| 사진 DM 제출 | ❌ | ✅ |
| 서버 관리 필요 | 없음 | 있음 (전원, 인터넷) |

라즈베리파이를 상시로 켜둘 수 있으면 **Actions 워크플로는 꺼두는 걸 권장한다.**
둘 다 켜두면 같은 시간에 미션이 두 번 발행될 수 있다.

레포 → Actions → 왼쪽 "채널 발행" → 우측 상단 **"..." → Disable workflow**

---

## 준비물

- 라즈베리파이 (3 이상이면 충분, Zero 2 W 도 가능)
- 인터넷 연결 (유선 권장, 무선도 무방)
- SD카드에 Raspberry Pi OS 설치 완료, SSH 접속 가능 상태

여기서부터는 라즈베리파이에 SSH 로 접속한 상태를 기준으로 한다.

```bash
ssh pi@라즈베리파이_IP주소
```

---

## 1. 필수 패키지 설치

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv git fonts-nanum
```

`fonts-nanum` 은 명언 카드에 쓰는 한글 폰트다. 빠뜨리면 명언 카드만 조용히 건너뛴다.

---

## 2. 레포 클론

```bash
cd ~
git clone https://github.com/para333311/helth_training.git
cd helth_training
```

이미 클론했다면:

```bash
cd ~/helth_training
git pull
```

---

## 3. 가상환경 + 의존성 설치

라즈베리파이는 시스템 파이썬을 직접 건드리면 다른 프로그램이 깨질 수 있어서 가상환경을 쓴다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 4. .env 설정

```bash
cp .env.example .env
nano .env
```

Actions 에서 이미 쓰던 값을 그대로 옮기면 된다.

```bash
TELEGRAM_BOT_TOKEN=여기에_토큰
TELEGRAM_CHANNEL_ID=@helth_training
TELEGRAM_BOT_USERNAME=helth_training_bot
OWNER_USER_ID=1423971696
SOLO_MODE=true
SEASON_START=2026-07-30
PHOTO_INTERVAL_MINUTES=60
PHOTO_START_HOUR=7
PHOTO_END_HOUR=22
UNSPLASH_ACCESS_KEY=여기에_키
TZ=Asia/Seoul
```

저장은 `Ctrl+O` → `Enter` → `Ctrl+X`.

**`data/helth.db` 를 GitHub Actions 에서 쓰던 것과 공유하지 않는다.** 라즈베리파이가 처음부터
스트릭을 다시 세기 시작한다는 뜻이다. Actions 로 쌓인 기록을 가져오고 싶으면 알려달라 — 마이그레이션은 별도로 준비한다.

---

## 5. 동작 확인

```bash
python -m bot --check
```

```
발행 대상: 같이보는 오운완 (channel, id=-100...)
설정 정상입니다.
```

이게 뜨면 준비 끝. `Ctrl+C` 로 종료하고 다음 단계로.

---

## 6. 상시 실행 등록 (systemd)

수동으로 `python -m bot` 을 띄워두면 SSH 연결이 끊기는 순간 봇도 죽는다.
systemd 서비스로 등록하면 백그라운드에서 계속 돌고, 재부팅돼도 자동으로 다시 켜진다.

```bash
sudo nano /etc/systemd/system/helth-bot.service
```

아래 내용을 붙여넣는다. `pi` 를 실제 로그인 계정 이름으로 바꾼다 (`whoami` 로 확인).

```ini
[Unit]
Description=혼자보는 운동 봇
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/pi/helth_training
ExecStart=/home/pi/helth_training/.venv/bin/python -m bot
Restart=always
RestartSec=10
User=pi

[Install]
WantedBy=multi-user.target
```

등록 및 시작:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now helth-bot
```

상태 확인:

```bash
sudo systemctl status helth-bot
```

`active (running)` 이 초록색으로 뜨면 성공이다.

---

## 7. 로그 보기

```bash
journalctl -u helth-bot -f
```

`-f` 는 실시간 tail. 채널에 뭔가 발행될 때마다 여기 로그가 찍힌다.

```
발행 대상: 같이보는 오운완 (channel, id=-100...)
발행함 [사진] → 같이보는 오운완 (channel) msg=42 ...
```

빠져나가려면 `Ctrl+C` (봇은 계속 돈다. 로그 보기만 종료되는 것).

---

## 8. 재부팅 테스트

```bash
sudo reboot
```

1분 정도 기다렸다가 다시 SSH 접속해서:

```bash
sudo systemctl status helth-bot
```

`active (running)` 이면 성공. 이제 전원만 꽂혀 있으면 정전이나 재부팅 후에도 알아서 켜진다.

---

## 9. DM 기능 시험

텔레그램에서 봇(`@helth_training_bot`)을 검색해서 **1:1 대화**를 연다 (채널이 아니라 봇 자체).

```
/start
/mission
/done
/streak
```

`/done` 을 보내면 "💪 오운완 기록됨" 과 함께 연속 일수가 뜨면 정상이다.
사진을 그냥 보내면 채널 로테이션에 익명으로 들어가고 오운완도 같이 기록된다.

---

## 업데이트하는 법

코드나 콘텐츠를 바꾼 뒤 라즈베리파이에 반영하려면:

```bash
cd ~/helth_training
git pull
sudo systemctl restart helth-bot
```

재시작 시 밀린 슬롯을 몰아서 발행하지 않는다 (`scheduler.py` 의 `GRACE` 참고).

---

## 문제 해결

| 증상 | 확인 |
|---|---|
| `status` 가 `failed` | `journalctl -u helth-bot -n 50` 으로 에러 확인 |
| 봇은 뜨는데 발행이 없음 | `.env` 의 `TELEGRAM_CHANNEL_ID` 재확인 |
| 재부팅 후 다시 안 뜸 | `sudo systemctl enable helth-bot` 다시 실행 (enable 빠뜨림) |
| DM 명령이 안 먹음 | Actions 워크플로가 아직 켜져 있어서 두 프로세스가 충돌 → Actions 비활성화 |
| SD카드 걱정 | `data/helth.db` 는 자주 쓰기가 발생한다. 장기 운영 시 SD카드 대신 USB SSD 부팅을 권장 |
