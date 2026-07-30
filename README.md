# 혼자보는 운동 — 텔레그램 채널/봇 기획

헬스장 가기 귀찮은 사람들을 위한 오운완 채널. 기획 문서와 콘텐츠 재고를 관리하는 레포.

> **컨셉 한 줄**
> 남한테 보여주려고 하는 운동 말고, 나만 아는 오운완.

---

## 핵심 설계 3가지

**1. 난이도 3단 구조** — 매일 미션은 🟢(1~2분) / 🟡(5~8분) / 🔴(15분)으로 제시하고, **어느 걸 해도 오운완으로 인정**한다. "오늘은 못 하겠다"는 선택지를 없애는 게 이 채널의 전부다.

**2. 인증은 1탭** — 사진 인증 요구는 컨셉 위반이자 참여율 자살. 💪 이모지 하나 누르면 끝. 못 한 사람도 😮‍💨 를 누를 수 있게 한다.

**3. 12주 시즌제** — 무한 연재는 운영자가 먼저 지친다. 시즌 사이 1주 휴방을 공식화하고, 그 주에 다음 시즌 콘텐츠를 일괄 제작한다.

---

## 문서

| 문서 | 내용 |
|---|---|
| [01. 채널 구조](docs/01-channel-structure.md) | 채널+댓글그룹+봇 하이브리드, 발행 리듬, 요일 로테이션, 3kg 프로젝트 |
| [02. 콘텐츠 형식](docs/02-content-formats.md) | 글/이미지/영상 활용법, 텔레그램 고유 기능, 안 하는 것 |
| [03. 매일 콘텐츠 10선](docs/03-daily-content-ideas.md) | 아이디어 10개 + 주간 편성표 |
| [04. 오운완 인증](docs/04-verification-system.md) | 3단계 계단 구조, 스트릭 규칙, 인증률 장치 |
| [05. 장기 유지 구조](docs/05-operations.md) | 배치 제작, 재고 관리, 번아웃 방지, 지표 |
| [06. 봇 설치와 운영](docs/06-bot-setup.md) | 설치, chat ID 찾기, 자극 소스 3종, 명령어 |
| [07. 라즈베리파이 상시 실행](docs/07-raspberry-pi.md) | DM 명령(`/done` 등)이 필요할 때 24시간 운영 (Linux) |
| [08. Windows 노트북 상시 실행](docs/08-windows-setup.md) | 위와 동일한 목적, Windows 작업 스케줄러 버전 |
| [09. 마키마 코치 연동](docs/09-makima-coach.md) | 비서 AI(OpenClaw)가 코치 역할을 하고 헬스봇이 발행을 맡는 구조 |

## 콘텐츠 예시

| 파일 | 내용 |
|---|---|
| [핀 메시지](content/samples/pinned-welcome.md) | 채널 고정 메시지 |
| [아침 미션](content/samples/daily-mission.md) | 요일별 7개 |
| [밤 체크인](content/samples/night-checkin.md) | 인증 회수 메시지 5종 |
| [귀찮음 응급처치](content/samples/quick-fixes.md) | 상황별 12개 |
| [주간 결산](content/samples/weekly-report.md) | 주간/시즌 결산 |

---

## 봇 실행

```bash
pip install -r requirements.txt
sudo apt install fonts-nanum          # 명언 카드용 한글 폰트

cp .env.example .env                  # 토큰과 채널 ID 입력
python -m bot --chatid                # 비공개 채널의 숫자 ID 찾기
python -m bot --check                 # 연결 점검
python -m bot --once photo            # 시험 발행
python -m bot                         # 상시 실행
```

### 매시 정각(07~22시) 자극 드롭

세 소스를 번갈아 낸다. 앞의 것이 안 되면 다음으로 넘어가므로 그 시간대가 비지 않는다.

| 소스 | 내용 | 준비 |
|---|---|---|
| **유튜브 링크** | 홈트 채널 최신 영상 (공개 RSS, 링크만 발행) | `--addfeed <채널URL>` |
| **사진** | 내가 보낸 오운완 → `content/photos/` → 스톡 API | 봇 DM 전송 또는 API 키 |
| **명언 카드** | `quotes.json` 문구를 1080×1080 이미지로 직접 생성 | Pillow + 한글 폰트 |

> 남의 사진을 인스타그램 등에서 긁어오는 기능은 없다. 타인의 저작물이자
> 초상권이 걸린 이미지라 재게시할 수 없다. 자세한 이유는 [06번 문서](docs/06-bot-setup.md#1-유튜브-링크-가장-강한-자극) 참조.

전체 발행 스케줄과 명령어는 [06번 문서](docs/06-bot-setup.md)에 있다.

---

## 보안

**봇 토큰은 레포에 커밋하지 않는다.**

- 환경변수 `TELEGRAM_BOT_TOKEN` 으로만 주입 (`.env.example` 참고)
- `.env` 는 `.gitignore` 에 등록되어 있음
- 토큰이 노출되면 즉시 **BotFather → `/revoke`** 로 재발급
- 봇에는 필요한 최소 권한만 부여

---

## 안전 고지

이 레포의 운동 콘텐츠는 의료 조언이 아니다. 채널 발행물에는 통증 시 중단 안내와 기존 질환·임신·심혈관 질환 보유자의 사전 상담 권고를 상시 포함한다.
