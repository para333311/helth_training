# 06. 봇 설치와 운영

## 이 봇이 하는 일

| 시각 | 발행 | 비고 |
|---|---|---|
| **30분마다 07~22시** | 자극 드롭 (영상 / 사진 / 명언 카드) | 밤에는 쉰다 |
| **07:30** | 오늘의 3단 미션 | 요일 테마 자동 |
| **12:30** (평일) / **15:00** (주말) | 귀찮음 응급처치 · 270kcal 카드 | 수·일은 kcal 카드 |
| **18:00** | 하이록스 WOD | 헬스장용, 1km 달리기×근력 스테이션 교차, 매일 |
| **금 18:00** | 근육 상식 퀴즈 | 하이록스 WOD 와 같은 시각(금요일만 겹침) |
| **22:00** | 오운완 체크인 | |
| **일 21:00** | 주간 결산 | |
| **격주 일 20:00** | 리셋 데이 | |

하루 총 **34~35건** 발행된다 (자극 드롭만 30건). 혼자 쓰는 비공개 채널이면 이 정도가 적당하고,
너무 잦다 싶으면 `PHOTO_INTERVAL_MINUTES` 를 60~180 으로 늘리는 걸 권장한다.

---

## 설치

```bash
pip install -r requirements.txt

# 명언 카드에 한글 폰트가 필요하다 (없으면 명언 카드만 건너뛴다)
sudo apt install fonts-nanum        # Debian/Ubuntu
# macOS/Windows 는 시스템 기본 한글 폰트를 자동으로 찾는다
```

```bash
cp .env.example .env
# .env 를 열어 TELEGRAM_BOT_TOKEN 과 TELEGRAM_CHANNEL_ID 를 채운다
```

---

## 비공개 채널의 chat ID 찾기

비공개 채널은 `@채널이름` 이 없어서 **숫자 ID 가 필수**다.

1. 봇을 채널 관리자로 추가한다 (권한은 **"메시지 관리" 하나면 충분**)
2. 채널에 아무 글이나 하나 올린다
3. 아래를 실행한다

```bash
python -m bot --chatid
```

```
  channel      -1001234567890  같이보는 오운완
```

이 숫자를 `.env` 의 `TELEGRAM_CHANNEL_ID` 에 넣는다.

### 내 user_id 찾기

`OWNER_USER_ID` 는 주간 결산에 내 스트릭을 표시하는 데 쓴다.
봇과의 1:1 대화에서 `/start` 를 보낸 뒤 봇 로그를 보거나, `@userinfobot` 에게 아무 메시지나 보내면 나온다.

---

## 점검과 시험 발행

```bash
python -m bot --check          # 토큰·채널 연결과 재고 확인
python -m bot --list           # 잡 이름 목록
python -m bot --once mission   # 아침 미션을 지금 한 번 발행
python -m bot --once photo     # 자극 드롭을 지금 한 번 발행
python -m bot --once checkin   # 밤 체크인
python -m bot --once weekly    # 주간 결산
```

`--once` 는 스케줄과 무관하게 즉시 보내므로, 채널에 어떻게 보이는지 확인할 때 쓴다.

## 어디서 돌릴 것인가

**코드를 레포에 올려두는 것만으로는 아무 메시지도 안 나간다.** 어딘가에서 실제로 실행돼야 한다.

| 방법 | 장점 | 단점 |
|---|---|---|
| **GitHub Actions** | 서버 불필요, 무료, 레포에 이미 설정됨 | DM 명령 불가, 발행이 몇 분 늦을 수 있음 |
| **집 PC** | 즉시 시작, 전부 동작 | PC 꺼지면 멈춤 |
| **라즈베리파이 · 미니PC** | 24시간, 전부 동작 | 기기 필요 |
| **클라우드 VM** | 24시간, 전부 동작 | 설정 필요 |

혼자 쓰는 채널이고 시간별 자극이 1순위라면 **GitHub Actions 로 시작**하는 게 가장 빠르다.
나중에 `/done` 같은 DM 명령이 필요해지면 그때 상시 실행으로 옮기면 된다.

### 방법 A. GitHub Actions (서버 없이)

`.github/workflows/publish.yml` 이 30분마다 스케줄을 확인해 발행한다.

**설정** — 레포 → Settings → Secrets and variables → Actions

`Secrets` 탭에 추가:

| 이름 | 값 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather 토큰 |
| `TELEGRAM_CHANNEL_ID` | `-100...` 숫자 ID |
| `OWNER_USER_ID` | 내 user_id (선택) |
| `UNSPLASH_ACCESS_KEY` | 스톡 사진 키 (선택) |

`Variables` 탭에 추가 (선택):

| 이름 | 예시 |
|---|---|
| `SEASON_START` | `2026-07-30` |
| `PHOTO_INTERVAL_MINUTES` | `30` |
| `TELEGRAM_BOT_USERNAME` | `내봇이름_bot` |

**시험 발행** — Actions 탭 → "채널 발행" → Run workflow → 잡 선택 후 실행.
스케줄을 기다리지 않고 바로 보내볼 수 있다.

> ⚠️ **DM 명령은 이 방식으로 동작하지 않는다.** `/done`, `/streak`, 사진 전송은
> 봇이 계속 떠 있으면서 수신해야 하므로 아래 상시 실행이 필요하다.
> 발행(사진·미션·체크인·결산)만 필요하면 Actions 로 충분하다.

> 예약 실행은 GitHub 이 혼잡할 때 몇 분에서 십여 분 늦게 뜬다.
> 그래서 `JOB_GRACE_MINUTES=40` 으로 지연을 흡수한다. 07:30 미션이 07:45에 나갈 수는 있어도
> 통째로 누락되지는 않는다.

### 방법 B. 상시 실행 (전부 동작)

```bash
python -m bot
```

systemd 로 돌리는 경우:

```ini
# /etc/systemd/system/helth-bot.service
[Unit]
Description=혼자보는 운동 봇
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/helth_training
ExecStart=/usr/bin/python3 -m bot
Restart=always
RestartSec=10
User=helth

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now helth-bot
journalctl -u helth-bot -f
```

봇이 꺼져 있던 동안 지나간 슬롯은 **다시 보내지 않는다.**
재시작 직후 밀린 사진 10장이 한꺼번에 쏟아지는 걸 막기 위해서다 (`scheduler.py` 의 `GRACE`).

---

## 자극 드롭의 3가지 소스

30분마다 아래 세 가지를 번갈아 낸다. 앞의 것이 안 되면 다음으로 넘어가고,
전부 안 되면 텍스트로 대체하므로 **그 시간대가 비는 일은 없다.**

### 1. 유튜브 링크 (가장 강한 자극)

한국 홈트/헬스 채널의 최신 영상을 링크로 보낸다. 텔레그램이 제목과 썸네일을 자동으로 붙인다.

```bash
python -m bot --addfeed https://www.youtube.com/@채널핸들
python -m bot --feeds     # 등록 목록
```

유튜브가 채널마다 공개 제공하는 RSS 를 읽는다. API 키가 필요 없고,
영상을 재업로드하지 않고 **원본 링크만** 보내므로 저작권 문제가 없다.

> 좋아하는 홈트 채널 3~5개를 등록해두면 "남들도 지금 하고 있다"는 신호가 계속 들어온다.
> 게다가 누르면 바로 따라할 수 있어서, 사진보다 실제 운동으로 이어질 확률이 높다.

### 2. 사진

우선순위대로 찾는다.

| 순서 | 소스 | 설정 |
|---|---|---|
| 1 | **내가 봇에 보낸 오운완 사진** | 봇 DM 에 사진 전송 |
| 2 | `content/photos/` 폴더 | 파일을 넣기만 하면 됨 |
| 3 | Unsplash / Pexels | API 키 필요 (무료) |

봇 DM 으로 사진을 보내면 채널 로테이션에 **익명으로** 들어가고, 오운완도 자동 기록된다.
`/myphotos 삭제` 로 언제든 전량 삭제할 수 있다.

혼자 쓰는 채널에서 하루 16장을 본인 사진만으로 채울 수는 없으므로,
**Unsplash 나 Pexels 키를 하나 넣는 걸 권장한다.** 둘 다 무료이고 발급에 2분이면 된다.

> ⚠️ 인스타그램 등에서 남의 사진을 긁어오는 기능은 없고, 넣지 않는다.
> 타인의 저작물인 동시에 알아볼 수 있는 사람이 찍힌 이미지라 저작권과 초상권을 함께 침해한다.
> 공개 계정이라도 "볼 수 있게 공개"는 열람 허용이지 재배포 허용이 아니다.

**사진 위에 `photo_captions.json` 문구를 직접 합성해서 한 장으로 낸다** (별도 캡션 줄 없음).
한/영 문구가 재고에 섞여 있어 랜덤으로 나온다. 하단 그라데이션 + 그림자 처리로 어떤 사진
위에도 글자가 읽힌다. Pillow/한글 폰트가 없으면 합성만 조용히 건너뛰고 원본 사진 +
캡션 텍스트로 대체된다(그 시간대가 비지는 않는다).

### 3. 명언 카드

`content/data/quotes.json` 의 문구를 1080×1080 이미지로 **직접 그려서** 보낸다.
인터넷에서 명언 이미지를 가져오지 않으므로 출처 문제가 없다.

- 30개를 다 돌기 전에는 같은 명언이 다시 나오지 않는다
- 어두운 배경 5종 팔레트 고정 (매번 톤이 바뀌면 채널 정체성이 흐려진다)
- 문구를 추가하려면 `quotes.json` 에 `{"text": "...", "source": "..."}` 를 넣으면 된다 (`source` 는 선택)
- Pillow 나 한글 폰트가 없으면 이 소스만 조용히 건너뛴다

---

## 봇 명령어 (1:1 대화)

| 명령 | 동작 |
|---|---|
| `/done` | 오늘 오운완 기록 |
| `/streak` | 연속·최고·주간·누적 기록 |
| `/skip` | 오늘은 패스 (기록 유지) |
| `/mission` | 오늘의 미션 다시 보기 |
| `/random` | 지금 할 수 있는 30초 운동 |
| `/weight 62.4` | 체중 기록 (본인만 조회) |
| `/condition 3` | 오늘 컨디션 기록 (1~5) |
| `/myphotos` | 내가 보낸 사진 수 / 전량 삭제 |

**사진을 그냥 보내면** 채널 로테이션에 익명 등록되고 오운완도 함께 기록된다.

### 터미널에서 직접 (봇이 안 떠 있어도 됨)

DM 명령과 같은 일을 노트북 터미널에서도 할 수 있다.
`--brief` 와 `--record` 는 **로컬 DB 만 읽고 쓰므로 인터넷이 끊겨 있어도, `TELEGRAM_CHANNEL_ID` 가 없어도 동작한다.**

```bash
python -m bot --brief                 # 지금 상태 한 화면으로
python -m bot --brief --json          # 같은 내용을 JSON 으로

python -m bot --record condition=3    # 1~5
python -m bot --record weight=71.2
python -m bot --record done=green     # green | yellow | red
python -m bot --record condition=4 --record done=yellow   # 여러 개 한 번에

python -m bot --say "오늘은 계단만"                  # 채널에 한 줄 직접 발행
python -m bot --say "이번 시즌 규칙" --pin           # 발행하고 고정
python -m bot --say "쉬는 날입니다" --by 코치         # 끝에 "— 코치" 서명
```

`--brief` 출력 예시:

```
2026-07-30 (목) · 유산소
3kg 프로젝트  D+7/84  1주차

연속        1일 (최고 1일)
이번 주     1/7      최근7일 ······■
누적        1일
컨디션      2/5 (2026-07-30)  7일 평균 2.0
체중        기록 없음

flags: slipping, weight_stale
```

`flags` 는 날짜 계산이 끝난 상태로 나온다 — 며칠 쉬었는지, 체중을 잰 지 며칠 됐는지를
직접 세지 않아도 된다.

| flag | 뜻 |
|---|---|
| `streak_at_risk` | 어제 안 함. 오늘 하면 이어짐 |
| `slipping` | 3일 이상 안 함 |
| `on_fire` | 5일 이상 연속 |
| `needs_rest` | 컨디션 2 이하가 3일 연속 |
| `condition_stale` | 오늘 컨디션 기록 없음 |
| `weight_stale` | 8일 이상 안 쟀음 |
| `weight_stalled` | 최근 2회 차이 0.3kg 미만 |
| `done_today` | 오늘 오운완 기록됨 |
| `no_media_source` | 자극 소스가 하나도 없음 |
| `season_over` | 시즌 84일 지남 |

> `OWNER_USER_ID` 가 비어 있으면 `--brief` 가 전부 0 으로 나온다. `.env` 에 넣어둘 것.

### 자가 진단

```bash
python tests/preflight.py --net     # 환경 전반 (파이썬·패키지·폰트·.env·API)
python tests/env_encoding.py        # .env BOM 회귀
python tests/brief_smoke.py         # --brief flags 로직
```

`preflight.py` 는 문제가 있으면 원인과 조치를 한국어로 같이 출력한다.
종료 코드 0 이면 봇이 뜰 수 있는 상태다.

### 스트릭 규칙

04번 문서의 설계를 그대로 구현했다.

- 🟢 도 완전한 1일 — 난이도와 무관
- 연속이 끊겨도 **최고 기록은 지우지 않는다**
- `/skip` 은 스트릭을 유지한다
- 주간 지표(`n/7일`)를 병행해서 연속이 끊겨도 볼 숫자가 남는다

---

## 콘텐츠 재고

| 파일 | 개수 | 용도 |
|---|---|---|
| `missions.json` | 28 | 요일 테마별 4개씩 · 주차마다 순환 |
| `hyrox.json` | 12 | 하이록스 근력 스테이션 · 다 쓸 때까지 안 겹치게 순환 |
| `quick_fixes.json` | 20 | 귀찮음 응급처치 |
| `photo_captions.json` | 24 | 사진·영상에 붙는 한 줄 |
| `quotes.json` | 54 | 명언 카드 |
| `kcal_cards.json` | 14 | 270kcal 카드 |
| `quizzes.json` | 10 | 근육 상식 퀴즈 |

미션 28개는 요일 테마마다 4개씩이라 **4주 주기로 순환**한다. 12주 시즌이면 3바퀴 돈다.
05번 문서에 적었듯 재사용은 문제가 되지 않지만, 지겨우면 `missions.json` 에 추가하면 자동으로 순환에 들어간다.

하이록스 WOD 는 헬스장용이다. 1km 달리기와 근력 스테이션을 번갈아 배치한다
(러닝 → 스테이션 → 러닝 → 스테이션 …, 실제 하이록스와 같은 순서). `hyrox.json` 은
스테이션 재고이고, 매일 `HYROX_RUNS`(기본 3)개를 안 겹치게 골라 러닝과 교차시킨다.
재고가 지겨워지면 `hyrox.json` 에 같은 형식(`name`/`green`/`yellow`/`red`)으로 추가하면 된다.
러닝 횟수를 늘리고 싶으면 `.env` 의 `HYROX_RUNS` 를 올린다 (예: 8 = 실제 하이록스 레이스와 동일한 8회).

---

## 보안

- **토큰을 코드나 git 에 넣지 않는다.** `.env` 는 `.gitignore` 에 있다
- 노출되면 즉시 BotFather → `/revoke`
- 채널 관리자 권한은 **"메시지 관리" 하나면 충분하다.** 채널 정보 수정·사용자 차단·초대 링크 권한은 꺼두는 게 안전하다
- 체중·스트릭은 로컬 SQLite(`data/helth.db`)에만 저장되고 채널에 공개되지 않는다

---

## 문제 해결

| 증상 | 원인 |
|---|---|
| `채널에 접근할 수 없습니다` | 봇이 관리자가 아니거나 chat ID 가 틀림 → `--chatid` |
| 사진 대신 텍스트만 나옴 | 사진 소스가 전부 비어 있음 → 스톡 API 키를 넣거나 봇에 사진 전송 |
| 명언 카드가 안 나옴 | Pillow 미설치 또는 한글 폰트 없음 → `pip install Pillow`, `apt install fonts-nanum` |
| 유튜브가 안 나옴 | 채널 미등록 → `--addfeed` |
| 발행 시각이 어긋남 | 서버 타임존 → `.env` 의 `TZ=Asia/Seoul` |
| **아무것도 안 옴** | 봇이 실행 중이 아님 → 위 "어디서 돌릴 것인가" |
| 채널에 친 `/start` 가 무반응 | 정상. 봇 명령은 **1:1 대화창**에서만 동작한다 |
| Actions 는 도는데 발행이 없음 | Secrets 미설정 → 로그에서 `TELEGRAM_BOT_TOKEN 이 없습니다` 확인 |
