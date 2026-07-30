# 그록 인수인계서 — 프로젝트 전체 이관 문서

**읽는 사람: 그록(Grok).**
지금부터 이 프로젝트의 설계자·검토자 역할은 너다. 이전 담당자(젠스파크 AI)는
크레딧 소진으로 빠진다. 이 문서는 그가 알고 있던 **모든 것**을 넘기는 문서다.

**중요: 두 저장소는 PRIVATE 이다. 너는 코드를 직접 읽을 수 없다.**
그래서 이 문서에 필요한 내부 정보를 전부 옮겨 적었다. 추가로 파일을 봐야 하면
마키마에게 시켜라 (§10). 마키마가 너의 손과 눈이다.

---

## 0. 3자 역할 분담

```
사용자 ──── 전달만 한다. 텔레그램/브라우저 조작. 최종 결정권자
  │
  ├──▶ 그록 (너)   설계 · 원인 규명 · 코드 최종 검토 · 판단
  │               도구 없음. 실행 불가. 말로만 지시한다
  │
  └──▶ 마키마     노트북에서 실제 실행. 설치 · 명령 · 시행착오 · 코딩
                  Windows 11 위 OpenClaw. 파일시스템·셸·git 접근 가능
```

**사용자가 명시한 규칙:** *"나 아니면 안 되는 것만 나한테 요청해."*
그러니 마키마가 할 수 있는 일을 사용자에게 시키지 마라. 사용자만 가능한 일은
§9 에 6개로 정리해 뒀다. 그 외엔 마키마에게 지시한다.

**너의 한계를 정확히 알아라:**
- 명령 실행 못 함 → 마키마에게 명령을 주고 출력을 받는다
- 파일 못 읽음 → 마키마에게 `Get-Content` 시킨다
- GitHub 못 씀 → 마키마가 커밋/푸시하거나 사용자가 UI 로 한다
- 그래서 **너의 출력은 항상 "마키마에게 그대로 붙여넣을 수 있는 블록"** 이어야 한다.
  사용자는 복사·붙여넣기만 한다.

---

## 1. 사용자가 원하는 것 (원본 의도, 변경 없음)

### 최종 목표

마키마(마키마, 사용자의 **제1비서관**)를 Windows 11 노트북에서 24시간 돌리면서,
**하나의 인격 + 공유된 기억 + 장소에 따른 역할 분리**를 구현한다.

| 어디 | 역할 | 상태 |
|---|---|---|
| 사용자와의 DM | **비서** | 기존 그대로. **절대 건드리지 않는다** |
| 운동 채널 `@helth_training` | **헬스 코치** | 이번에 추가하는 것 |

코치로서 마키마는 **먼저 말을 건다.** 헬스장 가라고 독려하고, 컨디션을 묻고,
쌓인 데이터로 사용자를 관리한다. 엄마 역할과 아내 역할이 다른 것처럼,
같은 사람인데 있는 곳에 따라 말투와 역할이 갈린다.

### 절대 요구사항 (전체 대화에서 일관되게 유지된 것)

1. **1순위 = 자극.** 07:00~22:00 매시간 자극이 떨어져야 한다. 밤에는 쉰다.
2. **역할 위계.** 마키마 = 관리자, 헬스봇 = 그의 직원.
   반복 발행은 헬스봇에게 위임. 마키마는 판단이 필요할 때만 개입한다.
3. **채널 발행 주체는 항상 헬스봇.** 마키마가 쓴 글이라도 헬스봇이 올린다.
   (그래서 마키마 봇을 채널 관리자로 넣을 필요가 없고, 토큰 노출 피해도 안 늘어난다)
4. **마키마 이름은 "마키마" 고정.** 헬스봇 이름은 사용자가 나중에 텔레그램에서
   직접 바꾼다. 건드리지 마라.
5. **무료가 핵심.** 그록 프로 구독으로 마키마 두뇌는 커버된다.
   **별도 API 과금 0원.** 유료 API 를 붙이자는 제안은 하지 마라.
6. **DM 과 채널에 같은 말이 중복되지 않는다.**
7. **마키마를 망가뜨리지 않는다.** 새 브랜치, 킬 스위치, 되돌릴 수 있게.
8. 채널 `@helth_training` (공개), chat id `-1004448866091`, **사용자 1인 전용**.
9. OpenClaw 는 **Windows 11 네이티브** (빌드 26100). **WSL 아님, Docker 아님.**
10. 인스타그램 등에서 남의 운동 사진을 긁어오지 않는다. 저작권 + 초상권.
11. 사용자에게 URL 을 줄 때는 **백틱으로 감싸지 말고 평문 링크**로. 클릭돼야 한다.

### 시즌 설정

| 항목 | 값 |
|---|---|
| 시즌명 | `3kg 프로젝트` |
| 목표 | 3.0 kg 감량 |
| 기간 | 84일 |
| 시작일 | `2026-07-30` |
| 핵심 논리 | 3kg = 하루 270kcal 적자. **운동만으로 안 빠진다** |

---

## 2. 지금까지 만든 것 — 시스템 구조

```
Windows 11 노트북 (24시간 ON)
│
├─ OpenClaw Gateway ─── 마키마 [두뇌: 그록 → 제미나이 폴백]
│    ├─ DM 세션        → 비서. 기존 cron 그대로. 손대지 않음
│    └─ coach: cron 4개 → 코치. 하루 4번만 깨어난다
│         └─ 실행 흐름: python -m bot --brief  (데이터 읽기)
│                       → 판단해서 글 작성
│                       → python -m bot --say "글" --by 마키마  (헬스봇이 발행)
│
└─ 헬스봇 프로세스 ─── python -m bot   (레포: para333311/helth_training)
     ├─ 매시 정각 자극 (사진/명언카드/유튜브)   ← LLM 0회
     ├─ 07:30 미션 · 12:30 응급처치 · 22:00 체크인 · (일)21:00 결산
     └─ DM 명령 수신 (/done /streak /weight, 사진 제출)
           └─ SQLite (data/bot.db) ← 유일한 데이터 저장소
```

### 핵심 설계 원칙 — **"판단은 파이썬이, 해석은 LLM이"**

이게 이 프로젝트의 중심 아이디어다. 반드시 유지해라.

파이썬(`bot/brief.py`)이 데이터를 읽어서 **불리언 플래그 10개를 확정**한다.
마키마는 그 플래그를 **해석만** 한다. 계산하지 않는다.

효과:
- 매시 자극 = **LLM 호출 0회** (템플릿 + 스톡 사진)
- 마키마 코치 턴 = **하루 4회로 상한**
- 매시간 LLM 을 부르면 16회 × 84일 = 1,344회. 그록 프로 구독이 그걸 버티라고
  만든 게 아니다. 그래서 경계를 그었다.

| 일 | 담당 | LLM |
|---|---|---|
| 매시 자극 (사진·명언카드·유튜브) | 헬스봇 | 안 씀 |
| 정형 발행 (미션 템플릿·체크인·결산 숫자) | 헬스봇 | 안 씀 |
| **판단이 필요한 말** | **마키마** | **하루 4회** |

판단이 필요한 순간은 딱 네 번이다 — 하루를 열 때, 컨디션을 물을 때,
하루를 닫을 때, 주를 정리할 때.

---

## 3. 헬스봇 인터페이스 전체 (너가 알아야 할 API)

레포를 못 보니 여기 다 적는다. 마키마에게 명령을 지시할 때 이 표를 근거로 써라.

### CLI

```
python -m bot                     상시 실행 (발행 + DM 수신)  ★발행 모드
python -m bot --serve             상시 실행 (DM 수신만, 발행 안 함) ★안전 모드
python -m bot --once <JOB>        잡 1회 즉시 실행
python -m bot --tick              스케줄 1회 평가 (Actions 가 쓰던 방식)
python -m bot --list              잡 목록
python -m bot --chatid            채널 숫자 chat ID 찾기
python -m bot --check             설정 점검만
python -m bot --addfeed <URL>     유튜브 채널 등록
python -m bot --feeds             등록된 유튜브 채널 목록
python -m bot -v                  verbose

── 마키마(코치) 연동 ──
python -m bot --brief             코치용 브리핑 (사람이 읽는 형태)
python -m bot --brief --json      같은 것을 JSON 으로  ★마키마는 이걸 쓴다
python -m bot --say "글"          채널에 발행 (헬스봇 명의)
python -m bot --say "글" --by 마키마   서명 붙여 발행
python -m bot --say "글" --pin    발행 후 고정  ★현재 권한 없어서 실패함
python -m bot --record K=V        데이터 기록 (반복 가능)
    --record condition=1~5
    --record weight=71.2
    --record done=green|yellow|red
```

### 헬스봇 잡 목록 (`bot/main.py` 에 등록된 것)

| 잡 이름 | 시각 | 요일 | 내용 |
|---|---|---|---|
| `photo` | 매시 (기본 60분 간격), 07~22시 | 매일 | 자극 드롭. 사진↔유튜브 교대 |
| `mission` | 07:30 | 매일 | 3단 난이도 미션 |
| `quickfix` | 12:30 | 월~금 | 귀찮음 응급처치 |
| `quickfix_weekend` | 15:00 | 토·일 | 같은 것, 주말판 |
| `quiz` | 18:00 | 금 | 근육 상식 퀴즈 |
| `checkin` | 22:00 | 매일 | 오운완 체크인 |
| `weekly` | 21:00 | 일 | 주간 결산 (숫자·게이지) |
| `reset_day` | 20:00 | 일 (2주마다) | 리셋 데이 |

### 마키마 코치 잡 4개 (`secretary1/openclaw/register-cron.ps1` 이 등록)

| 잡 | 시각 | 왜 이 시각 | 하는 일 |
|---|---|---|---|
| `coach:morning` | 07:40 | 헬스봇 미션(07:30) 10분 뒤 | 오늘 필요한 한마디 |
| `coach:condition` | 19:00 | 퇴근 직후, 만회 가능한 마지막 시간 | 컨디션 1~5 묻고 민다 |
| `coach:night` | 22:20 | 헬스봇 체크인(22:00) 20분 뒤 | 하루를 닫는다 |
| `coach:weekly` | 일 21:20 | 헬스봇 결산(21:00) 뒤 | 숫자를 해석. 제안 1개만 |

**겹치지 않게 짠 시간표** (중복 발행이 이 구조에서 유일하게 실재하는 사고다):

```
07:30  헬스봇   3단 미션
07:40  마키마   ← 아침 한마디
매시    헬스봇   자극 드롭 (08~22시, LLM 0)
12:30  헬스봇   귀찮음 응급처치
18:00  헬스봇   퀴즈 (금요일)
19:00  마키마   ← 컨디션 체크
22:00  헬스봇   오운완 체크인
22:20  마키마   ← 밤 마무리
─────────────── 일요일만
21:00  헬스봇   주간 결산 (숫자)
21:20  마키마   ← 주간 코멘트 (해석)
```

OpenClaw 는 정시 잡을 최대 5분까지 흩뿌린다(부하 분산). 그래서 마키마 잡을
헬스봇 잡 바로 뒤 10분 이내로 붙이지 않았다.

### cron 실행 옵션과 그 이유

| 옵션 | 이유 |
|---|---|
| `--session isolated` | DM 대화 맥락이 코치 턴에 섞이면 안 된다 |
| `--tools exec,read` | 셸과 파일 읽기만. 최소 권한 |
| `--no-deliver` | **없으면 같은 말이 두 줄로 나간다.** 마키마 최종 응답이 채널로 한 번, `--say` 로 한 번 |
| `--tz Asia/Seoul` | 없으면 노트북 로컬 시간으로 해석된다 |

### `--brief --json` 이 주는 것

마키마가 매 코치 턴마다 읽는 데이터다. 구조:

```
generated_at, today, weekday, theme
season   { name, day(D+n), total_days, week, goal_kg }
streak   { current, best }
week_done, total_done, missed_in_a_row
last_7_days [ { day, done, tier } ... ]
condition { latest, log[] }
weight   { latest_kg, measured_on, days_since_weigh, baseline_kg, lost_kg, history[] }
published_today []      ← 오늘 이미 발행된 잡 이름 목록
sources  { youtube_channels, my_photos, stock_api }
flags    { ... 아래 10개 ... }
```

### 플래그 10개 — **마키마 행동의 근거. 전체를 외워둘 가치가 있다**

| 플래그 | 조건 | 코치가 해야 할 행동 |
|---|---|---|
| `slipping` | 3일 이상 안 함 | 진입장벽 최저로. 🟢부터. **죄책감 금지** |
| `streak_at_risk` | 어제 안 함 (missed==1) | **가장 중요한 개입 시점.** 오늘 끊긴다. 🟢 하나만 강하게 |
| `on_fire` | 5일 이상 연속 | 인정 + **과훈련 경고 같이** |
| `needs_rest` | 컨디션 2 이하가 3일 연속 | 🔴 말리고 스트레칭만 권한다 |
| `condition_stale` | 오늘 컨디션 안 물어봄 | 오늘 물어본다. false 면 건너뛴다 |
| `weight_stale` | 8일 이상 안 쟀다 | **일요일에만** 상기. 평일 언급 금지 |
| `weight_stalled` | 체중 정체 | 운동 얘기 접고 270kcal(식사)로 화제 전환 |
| `done_today` | 오늘 오운완 기록 있음 | true 면 묻지 않고 인정만 |
| `no_media_source` | 유튜브 0 + 내 사진 0 + 스톡키 없음 | 텍스트만 나가는 상태. 사용자에게 알려야 한다 |
| `season_over` | D+n > 84 | 시즌 결산 + 1주 휴방 공식화 |

### 코치 페르소나 규칙 (`secretary1/openclaw/coach-persona.md`)

**말투:** 차분하고 낮다. 텐션 억지로 안 올린다. 3~5줄로 짧다. 단정한다
("하시면 좋을 것 같아요" ✗ → "오늘은 🟢으로 가세요" ○). 비교하지 않는다 —
상대는 어제의 그다. 이모지는 난이도(🟢🟡🔴)와 오운완(💪)만.
**마크다운 금지** — 텔레그램 일반 텍스트로 나가서 `**굵게**` 가 그대로 보인다.

**절대 하지 않는 것 7개:**
1. 사진 인증 요구 금지 (몸 사진, 헬스장 인증샷, 3대 중량 전부)
2. 남과 비교 금지 (랭킹·리더보드·"다른 사람들은")
3. 죄책감 금지. 못 한 날을 나무라지 않는다. 🟢만 해도 오운완이다
4. 운동만으로 살이 빠진다고 말하지 않는다 (3kg = 하루 270kcal 적자)
5. 의료 조언 금지. 통증·어지러움·가슴 압박은 즉시 중단 + 병원
6. 매시간 말하지 않는다. 그건 헬스봇 일이다
7. **DM 에서 운동 얘기를 먼저 꺼내지 않는다.** 알고 있되, 물으면 답한다

**난이도 3단은 항상 유지:** 🟢 최소(5~10분) / 🟡 보통 / 🔴 강도.
컨디션이 나쁘면 🔴을 말린다. 🟢만 해도 스트릭은 이어진다.

### DM 명령

`/start` `/help` `/done` `/streak` `/skip` `/mission` `/random` `/weight` `/myphotos`
+ 사진을 보내면 자극 소스로 저장된다.

### 파일 구조

**helth_training** (PRIVATE, https://github.com/para333311/helth_training)
```
bot/          config.py store.py brief.py main.py scheduler.py jobs.py
              tg.py commands.py content.py photos.py cards.py feeds.py
content/data/ missions.json quotes.json quizzes.json quick_fixes.json
              kcal_cards.json photo_captions.json
content/photos/          ← 여기 넣은 사진이 자극 소스가 된다
tests/        preflight.py  env_encoding.py  coach_smoke.py
docs/         01~09 + 10-makima-handoff.md (마키마 런북) + 11 (이 문서)
.github/workflows/publish.yml   ← ★수정 불가. 사용자만 UI 로 제어
requirements.txt   requests, Pillow, tzdata
.gitignore    /data/  *.db  .env   ← DB 와 토큰은 커밋되지 않는다
```

**secretary1** (PRIVATE, https://github.com/para333311/secretary1)
```
openclaw/coach-persona.md    코치 인격. 마키마가 매 턴 읽는다
openclaw/jobs.md             cron 4개 명세
openclaw/register-cron.ps1   등록 스크립트 (~11.7KB) ★아직 실행된 적 없음
docs/setup-windows.md        설치 순서
docs/architecture.md         설계 근거 + 버린 대안
docs/troubleshooting.md      사고 이력. 0번 항목이 가장 중요
docs/handoff.md              마키마용 단계 B 요약
```

`register-cron.ps1` 인자: `-BotDir`(**필수**) `-PythonExe`(생략시 venv 자동탐색)
`-PersonaPath` `-Tz` `-DryRun` / `-List` `-Disable` `-Enable` `-Remove`
(뒤 4개는 별도 파라미터 세트 — `-BotDir` 과 같이 주면 오류)

---

## 4. 진행 현황 — 무엇이 끝났고 무엇이 남았나

### 끝난 것 (코드는 전부 main 에 머지됨, PR #1~#6 / secretary1 #1~#5)

- [x] `bot/store.py` — `conditions` 테이블 + 코치용 조회 메서드 7개
- [x] `bot/brief.py` — 스냅샷 + 플래그 10개 확정
- [x] CLI — `--brief/--json/--say/--by/--pin/--record/--serve`
- [x] `tests/coach_smoke.py` — 플래그 로직 8케이스, 전부 통과
- [x] `tests/env_encoding.py` — BOM 회귀 테스트 (역검증까지 확인)
- [x] `tests/preflight.py` — 환경 자가 진단 (`--net` 로 실전 API 호출)
- [x] `requirements.txt` — `tzdata` 추가
- [x] `bot/config.py` — BOM 수정 (`utf-8-sig`)
- [x] `docs/08` 7-4절 — GUI 없이 작업 스케줄러 등록하는 PowerShell
- [x] `docs/09` — 마키마 연동 문서
- [x] `docs/10-makima-handoff.md` — **마키마 런북. 이미 마키마에게 전달됨**
- [x] secretary1 전체 — 페르소나, jobs, register-cron.ps1, 문서 4종

### 남은 것 — 여기가 너의 일이다

```
[단계 A] 노트북에 헬스봇 올리기        ← 마키마가 지금 여기 (A1~A2 진행 중)
   A1 이미 있는 폴더 정리 (clone 에러)      ← 마키마 진행중
   A2 git pull (tzdata·BOM 수정 수령)      ← 마키마 진행중
   A3 .venv 에 패키지 설치 + 검증
   A4 .env 작성                            ← 사용자에게 값 요청 필요
   A5 preflight --net 통과
   A6 --once photo 로 실제 발행 눈으로 확인  ★단계 C의 전제조건
   A7 작업 스케줄러 등록 (--serve = DM 전용, 발행 안 함)
        ↓
[단계 B] 코치 cron 등록
   B1 secretary1 클론
   B2 기존 DM 비서 cron 백업 ★먼저
   B3 register-cron.ps1 -DryRun → 실제 등록
   B4 cron run 으로 즉시 실행 테스트 (검증 5항목)
        ↓
[단계 C] 발행 주체 교체  ★가장 위험. 한 번 사고 남
   C1 GitHub Actions 끄기                  ← 사용자만 가능
   C2 즉시 작업 스케줄러를 -m bot(발행 모드)로 재등록
   C3 다음 정시에 발행 1회만 뜨는지 확인
        ↓
[단계 D] 하루 운영 검증 + 자격증명 교체
```

**마키마는 이미 `docs/10-makima-handoff.md` 를 받았다.** 그 문서에 A~D 전부의
구체적 명령이 들어 있다. 너는 그 문서의 존재를 전제로 지시하면 된다:
"인수인계서 §A3 진행해" 같은 식으로.

마키마에게 이미 전달된 지시의 마지막 부분:
```
cd $HOME\helth_training
git rev-parse --is-inside-work-tree
git remote -v
git pull --ff-only origin main
git log --oneline -3
```
이 출력이 오면 → A3(패키지 설치)으로 넘긴다.

---

## 5. ⚠️ 반드시 알아야 할 지뢰 — 실제로 터진 것들

이전 담당자가 피 흘려 알아낸 것들이다. 모르면 같은 데서 같은 시간을 잃는다.

### 5-1. 🔴 최악의 사고 — 채널이 죽었다

**무슨 일:** 채널에 매시 글을 올리는 주체가 **GitHub Actions 였다.**
노트북이 아니었다. 이전 담당자가 노트북 준비를 확인하지 않고 Actions 를
끄라고 했다. 채널이 조용해졌다.

**복구:** GitHub UI 에서 `Enable workflow`.

**교훈 — 불변식:** *채널 발행 주체는 항상 정확히 1개.*
- 0개 → 채널이 죽는다 (자극 = 이 프로젝트의 1순위가 사라진다)
- 2개 → 모든 글이 두 번 나간다

이 불변식을 깨는 지시를 절대 하지 마라. §7 의 단계 C 순서를 반드시 지켜라.

**부수 발견 (좋은 소식):** 데이터 유실은 없었다. Actions 환경에서는 DM 명령
(`/done`·사진·체중)이 애초에 동작하지 않았다. 즉 스트릭·체중 데이터가 존재한
적이 없다. **노트북 전환이 곧 기록의 시작이다.** Actions 의 캐시 DB 는
노트북으로 옮기지 않아도 잃을 게 없다.

### 5-2. `tzdata` 누락 → 봇이 아예 안 뜬다

```
zoneinfo._common.ZoneInfoNotFoundError: 'No time zone found with key Asia/Seoul'
```

Windows 에는 IANA 시간대 DB 가 없다. 리눅스는 OS 가 준다.
그래서 **GitHub Actions(ubuntu)에서는 절대 안 보이는 버그**였다.
`load_config` 단계에서 죽으므로 `--check` 조차 실패한다.
→ `requirements.txt` 에 `tzdata` 추가로 해결. **A2 의 `git pull` 로 받아야 한다.**

### 5-3. `.env` BOM → 토큰을 넣었는데 "없다"

PowerShell `Set-Content -Encoding UTF8` 은 파일 앞에 BOM(`\ufeff`)을 붙인다.
`utf-8` 로 읽으면 첫 줄 키가 `"\ufeffTELEGRAM_BOT_TOKEN"` 이 된다.
증상은 "토큰이 설정되지 않았습니다" — **원인을 전혀 가리키지 않는다.**

→ `bot/config.py` 를 `utf-8-sig` 로 읽게 수정 (BOM 있으면 벗기고 없으면 그냥 읽음).
→ 그래도 `.env` 는 이 방식으로만 쓰게 해라:

```powershell
$body = @'
# 이 파일은 커밋되지 않는다
KEY=값
'@
[System.IO.File]::WriteAllText("$HOME\helth_training\.env", $body, (New-Object System.Text.UTF8Encoding($false)))
```

`@'...'@` 는 리터럴이라 토큰의 특수문자가 안전하다. 첫 줄을 주석으로 둔 것도
안전장치다 (BOM 이 붙어도 주석이 흡수).

### 5-4. GitHub App 토큰의 벽 — **워크플로 제어는 아무 AI 도 못 한다**

실증된 것:
- 워크플로 파일 푸시 → 거부 (`workflows` 권한 없음)
- `gh api .../actions/workflows` → **403 Resource not accessible by integration**
- `.../actions/variables`, `.../actions/secrets` → 같은 403

**결론:** Actions 켜기/끄기, Secrets/Variables 읽기는 **사용자만 가능**하다.
그리고 UI 에서도 Secrets 값은 다시 볼 수 없다.
→ **설정값의 정본은 GitHub 이 아니라 노트북의 `.env` 다.**

참고로 **UI 의 "Disable workflow" 가 `schedule:` 주석처리보다 낫다.**
저장소 설정에 남아서 `git pull`·머지에도 살아남는다.

### 5-5. Windows 에 `sh` 가 없다

OpenClaw 의 `--command <셸문자열>` 형태는 Windows 에서 깨진다.
반드시 `--command-argv` 또는 `--message` 를 써라.

### 5-6. `can_pin_messages` 없음 → `--pin` 실패

헬스봇은 채널 관리자이고 `can_post_messages` 는 있다. 그런데 **고정 권한은
별개**이고 현재 없다. 그래서 `--say --pin` 이 실패한다.
→ **사용자만 고칠 수 있다** (§9-1). 진행을 막는 문제는 아니니 `--pin` 없이 간다.

### 5-7. `409 Conflict`

두 프로세스가 동시에 `getUpdates` 를 폴링하면 난다. 수동으로 띄운 봇이
남아 있는지 확인하고 하나만 남긴다.

### 5-8. `SEASON_START` 가 비면 영원히 D+1

```python
season_start = date.fromisoformat(raw_start) if raw_start else date.today()
```
빈 값이면 매번 오늘이 시작일이 된다. → `2026-07-30` 으로 확정했다.

### 5-9. 시간 낭비 사례 (반복 금지)

이전 담당자가 마키마에게 `Get-ChildItem C:\ -Recurse` 를 시켰다. **30분을 날렸다.**
경로는 `C:\Users\msi\helth_training` 로 확정됐다. 전체 디스크 검색을 지시하지 마라.

### 5-10. 노트북 환경 실측값

| 항목 | 값 |
|---|---|
| OS | Windows 11 빌드 26100 (네이티브. WSL/Docker 아님) |
| 사용자 | `msi` → `$HOME` = `C:\Users\msi` |
| 저장소 | `C:\Users\msi\helth_training` (이미 클론됨) |
| Python | **3.14.6** (새 Python Install Manager 레이아웃) |
| venv | `C:\Users\msi\helth_training\.venv` 존재 |
| ⚠️ | 이전 pip 설치가 **전역** site-packages 로 갔을 가능성. venv 내용 미확인 |

**Python 3.14 호환성은 검증했다:** 제거된 stdlib 모듈 미사용,
sqlite3 date-adapter deprecation 미해당 (날짜를 isoformat 문자열로 저장).
`python -W error::DeprecationWarning tests/coach_smoke.py` 클린.

---

## 6. 설계 결정과 **버린 대안** — 같은 논의를 반복하지 않도록

이미 검토하고 기각한 것들이다. 다시 제안하지 마라. 이유가 있다.

| 기각안 | 왜 안 되는가 |
|---|---|
| **마키마 봇을 채널 관리자로 넣기** | 발행 주체가 둘이 되고 토큰 노출 피해 범위가 늘어난다. 헬스봇 단일 발행 + `— 마키마` 서명으로 해결 |
| **매시간 마키마가 직접 발행** | LLM 1,344회. 구독이 감당 못 함. 매시 자극은 템플릿으로 충분하다 |
| **GitHub Actions 로 계속 운영** | DM 명령이 동작하지 않는다. 스트릭·체중·컨디션이 안 쌓인다. 코치의 존재 이유가 데이터인데 데이터가 없다 |
| **WSL/Docker 로 OpenClaw** | 사용자가 명시적으로 거부. 네이티브 Windows |
| **인스타그램 사진 스크래핑** | 저작권 + 초상권. 절대 안 됨 |
| **유료 API (OpenAI 등) 추가** | 무료가 전제 |
| **`schedule:` 주석처리로 Actions 끄기** | `git pull`·머지에 되돌아온다. UI Disable 이 정답 |
| **Actions 캐시 DB 를 노트북으로 이관** | 이관 방법이 없고, 옮길 데이터가 애초에 없다 (5-1 참조) |
| **DM 에서도 코치처럼 말하기** | 사용자 요구 위반. DM 은 비서 그대로 |

### `--serve` — 이 전환의 핵심 장치

가장 중요한 설계 결정이다. **중복 발행 vs 채널 공백**의 딜레마를 구조적으로 풀었다.

| 모드 | DM 응답 | 채널 발행 | Actions 켜진 상태에서 |
|---|---|---|---|
| `python -m bot --serve` | O | **X** | **안전 — 같이 돌려도 됨** |
| `python -m bot` | O | O | 중복 발행. 금지 |

그래서 3단계 전환이 가능하다:
1. `--serve` 로 등록 → Actions 와 공존. 위험 0. DM 기능부터 살아난다
2. Actions 끄기 (사용자)
3. `-m bot` 으로 재등록 → 발행 주체가 노트북으로 이동

---

## 7. 단계 C 상세 — 가장 위험한 구간. 순서를 외워라

### C0. 전제조건. 하나라도 X 면 절대 진행하지 마라

- [ ] `$HOME\helth_training` 에 저장소가 있고 `.env` 에 토큰이 들어 있다
- [ ] `preflight.py --net` 이 종료 코드 0
- [ ] 작업 스케줄러에 등록돼 `pythonw.exe` 가 떠 있다
- [ ] **`--once photo` 로 올린 글을 채널에서 눈으로 봤다** ← 이게 핵심

네 번째가 가장 중요하다. preflight 통과는 발행 성공을 보장하지 않는다.
**눈으로 본 증거**만 인정한다.

### C1 → C2 는 한 세션에서 연달아

C1(끄기)에서 멈추면 발행 주체가 0개가 된다. 사용자가 `Disabled` 배지
스크린샷을 보내면 **즉시** C2 를 지시해라.

C2 = A7 과 같은 스크립트에서 `$Mode` 를 `'serve'` → `'full'` 로 바꿔 재등록.

### 실패 시

- 발행 안 뜸 → 즉시 사용자에게 `Enable workflow` 요청해 채널을 살린 다음
  원인을 찾는다. 채널 공백을 방치하지 마라
- 두 번 뜸 → `Disabled` 배지 재확인

---

## 8. 자가 진단 체계 — **사용자를 부르기 전에 항상 이것부터**

이전 담당자가 크레딧 절약용으로 만든 장치다. 너도 그대로 활용해라.
마키마에게 이 순서로 시키면 대부분의 문제가 스스로 밝혀진다.

```powershell
cd $HOME\helth_training
.\.venv\Scripts\python.exe tests\preflight.py --net   # 1. 환경 (핵심)
.\.venv\Scripts\python.exe tests\env_encoding.py      # 2. BOM 회귀
.\.venv\Scripts\python.exe tests\coach_smoke.py       # 3. 플래그 로직 8케이스
.\.venv\Scripts\python.exe -m bot --check             # 4. 설정 로드
```

`preflight.py` 가 검사하는 것: 파이썬 버전(≥3.11 필수) / 패키지 / **시간대** /
SQLite 한글 왕복 / 한글 폰트 / `.env`(**BOM 탐지 포함**) / 설정 로드 /
텔레그램 실전 호출(getMe·getChat·getChatMember·getWebhookInfo) / Unsplash·Pexels.
비밀값은 앞 4자만 보여준다. 종료 코드 0 = 봇이 뜰 수 있음, 1 = 못 뜸.

### 증상 → 진짜 원인 대응표

| 증상 | 진짜 원인 | 조치 |
|---|---|---|
| `ZoneInfoNotFoundError: 'Asia/Seoul'` | `tzdata` 없음 | A2 `git pull` → A3 재설치 |
| 토큰 넣었는데 "없다" | `.env` BOM | 코드 갱신 + 5-3 방식 재작성 |
| `--pin` 실패 | `can_pin_messages` 없음 | 사용자 (§9-1) |
| `409 Conflict` | 두 프로세스가 폴링 | 하나만 남긴다 |
| 채널에 아무것도 안 뜬다 | **발행 주체 0개** | 즉시 `Enable workflow` 요청 후 원인 규명 |
| 같은 글이 두 번 | 발행 주체 2개 | `Disabled` 배지 확인 |
| 코치 말이 두 줄로 | `--no-deliver` 누락 | cron 정의 수정 |
| `--brief` 가 전부 0 | `OWNER_USER_ID` 불일치 | `.env` 수정 |
| D+1 에서 안 늘어남 | `SEASON_START` 빈 값 | `2026-07-30` |
| 카드 한글이 □□□ | 폰트 미검출 | preflight `[5]`, `malgun.ttf` |
| `git pull` 거부 | 로컬 커밋 존재 | 밀지 말고 내용 확인 먼저 |
| cron 잡이 조용히 실패 | 헬스봇이 아직 없음 | 단계 A 를 먼저 끝낸다 |

---

## 9. 사용자만 할 수 있는 일 6개 — **이것만 요청해라**

너도 마키마도 못 하는 것들이다. 요청할 때는 클릭 가능한 평문 URL 로.

### 9-1. 텔레그램 — 메시지 고정 권한 (지금 요청 가능)
> `@helth_training` 채널 → 관리자 → 헬스봇 → **메시지 고정** 켜기.
> 현재 `can_pin_messages` 가 없어 코치가 중요한 글을 고정할 수 없습니다.

### 9-2. `.env` 값 4개 (단계 A4 에서 필요)
1. `TELEGRAM_BOT_TOKEN` — @BotFather → `/mybots` → 헬스봇 → API Token.
   이 기회에 **Revoke current token** 으로 새로 받는 걸 권한다 (9-4 와 동시 처리)
2. `OWNER_USER_ID` — @userinfobot 에게 아무 말이나 보내면 나오는 숫자
3. `UNSPLASH_ACCESS_KEY` — https://unsplash.com/oauth/applications (선택)
4. `PEXELS_API_KEY` — https://www.pexels.com/api/ (선택)

3·4 는 둘 중 하나만 있어도 된다. 둘 다 없으면 명언 카드로 대체된다.

나머지 값은 확정돼 있으니 묻지 마라: `TELEGRAM_CHANNEL_ID=-1004448866091`,
`SOLO_MODE=true`, `SEASON_START=2026-07-30`, `SEASON_DAYS=84`,
`SEASON_NAME=3kg 프로젝트`, `GOAL_KG=3.0`, `PHOTO_INTERVAL_MINUTES=60`,
`PHOTO_START_HOUR=7`, `PHOTO_END_HOUR=22`, `TZ=Asia/Seoul`,
`PHOTO_QUERY=home workout,gym motivation,fitness`

### 9-3. GitHub Actions 끄기 (단계 C1. **A6 확인 전에는 절대 요청하지 마라**)
> 1. https://github.com/para333311/helth_training/actions
> 2. **왼쪽 사이드바**의 워크플로 목록에서 `publish` 클릭
>    (오른쪽 위 `⋯` 아님 — 그건 개별 실행 메뉴)
> 3. 목록 위쪽 오른편 `⋯` → **Disable workflow**
> 4. 이름 옆에 `Disabled` 배지 생기면 완료. 스크린샷 요청
>
> ```
>  Actions
>  ┌──────────────┬─────────────────────────────────┐
>  │ All workflows│  publish            [⋯] ← 이거  │
>  │ ▸ publish ←② │  ─────────────────────────────  │
>  │              │  Scheduled  #123                │
>  └──────────────┴─────────────────────────────────┘
> ```

`⋯` 위치를 헷갈리면 개별 실행 메뉴를 눌러서 엉뚱한 걸 한다. 이 그림을 같이 줘라.

### 9-4. 자격증명 재발급 (단계 D. 노출된 값들)
토큰과 API 키가 과거 대화창에 노출됐다. `.env` 가 유일한 소비자가 된 뒤가 적기다.
> 재발급 후 몇 분간 봇이 멈춥니다. `.env` 갱신 + 재시작 직후 복구됩니다.

### 9-5. 헬스봇 이름 변경
BotFather 에서. 사용자가 원할 때. 마키마 이름은 "마키마" 고정.

### 9-6. 저장소를 너에게 보여주고 싶을 때
두 저장소는 PRIVATE 이다. 네가 직접 파일을 봐야 하면 **마키마에게 시키는 게 정답**이다
(§10). 공개 전환은 권하지 않는다 — `.env` 는 커밋되지 않지만 채널 ID 등
운영 정보가 노출된다.

---

## 10. 마키마를 부리는 방법 — 너의 손과 눈

### 파일을 읽어야 할 때
```powershell
cd $HOME\helth_training
Get-Content bot\brief.py -Raw
Get-Content docs\10-makima-handoff.md -Raw
```
큰 파일이면 범위로: `Get-Content bot\store.py | Select-Object -Skip 200 -First 80`

### 출력 형식을 요구할 때
마키마의 보고를 신뢰할 수 있게 만들려면 **명령과 원본 출력을 같이** 받아라.
"됐습니다"만 오면 안 된 것일 수 있다.

### 마키마가 막혔을 때 받아야 하는 것
```
■ 무엇을 하려 했나 (단계 번호)
■ 실행한 명령 (그대로, 편집 없이)
■ 출력 전문 (토큰은 앞 4자만)
■ preflight --net 결과 (종료 코드 + FATAL/WARN 줄)
■ git log --oneline -3
■ .venv\Scripts\python.exe --version
■ 이미 시도해본 것과 결과
```

### 코드 수정 프로토콜 (사용자가 정한 방식)

사용자 원문: *"기본은 마키마 자체로 하고, 다 끝나면 검증용으로 코드 달라고 하고,
너가 그거 최종점검."*

1. 마키마가 브랜치를 딴다. `main` 직접 커밋 금지
   ```powershell
   git checkout -b makima/<짧은주제>
   ```
2. 작게 고친다. 한 브랜치 = 한 문제
3. §8 테스트 4개를 전부 돌린다
4. 너에게 제출 — **이 6항목 필수:**
   ```
   ■ 문제: 어떤 증상이었나 (재현 명령 포함)
   ■ 원인: 왜 그랬나
   ■ 수정: 무엇을 바꿨나 + 왜 이 방법인가
   ■ 검증: 테스트 4개 결과 (출력 붙여넣기)
   ■ 부작용 가능성: 걱정되는 부분
   ■ diff 전문
   ```
   **"검증" 없는 제출은 반송해라.** 통과하는 것만 보고 통과 못 하는 걸 안 보면
   고친 게 아니라 옮긴 거다.
5. diff 를 얻는 방법:
   ```powershell
   git fetch origin main
   git diff origin/main...HEAD > "$HOME\makima-review.diff"
   Get-Content "$HOME\makima-review.diff" -Raw
   ```
6. 너가 승인하면 마키마가 `main` 에 머지하고 푸시. 거부하면 이유와 함께 되돌린다

`register-cron.ps1` 을 고칠 때는 **`-DryRun` 출력을 반드시 받아라.**
PowerShell 을 너도 이전 담당자도 실행할 수 없다. 실행 증거는 마키마만 만든다.

---

## 11. 미해결 사항 목록 (인수 시점 기준)

| 항목 | 상태 | 담당 |
|---|---|---|
| `can_pin_messages` 없음 | 미해결. `--pin` 실패함 | 사용자 (9-1) |
| `register-cron.ps1` 실행 검증 | **한 번도 실행된 적 없음.** 정적 검토만 | 마키마 (B3) |
| GitHub Actions | **아직 켜져 있다.** 현재 유일한 발행 주체 | 사용자 (C1) |
| 자격증명 노출 | 미교체 | 사용자 (9-4) |
| venv 패키지 위치 | 전역으로 갔을 가능성. 미확인 | 마키마 (A3) |
| `.env` | 아직 없음 | 마키마 + 사용자 (A4) |
| DB 데이터 | **비어 있음.** 노트북 전환이 기록의 시작 | — |

---

## 12. 최종 완료 조건 (Definition of Done)

이게 다 되면 프로젝트가 끝이다.

| # | 조건 | 확인 방법 |
|---|---|---|
| 1 | 노트북에서 헬스봇이 24시간 떠 있다 | 재부팅 후에도 프로세스 생존 |
| 2 | 채널에 07~22시 매시 자극이 뜬다 | 두 시간 연속 관찰 |
| 3 | DM 으로 `/done`·사진·체중이 기록된다 | `--brief` 에 숫자가 찍힌다 |
| 4 | 마키마가 하루 4번 코치로 말한다 | 07:40 / 19:00 / 22:20 / (일)21:20 |
| 5 | DM 에서는 비서 인격 그대로 | 말투·역할이 코치와 안 섞임 |
| 6 | GitHub Actions 가 꺼져 있다 | `Disabled` 배지 |
| 7 | 중복 발행 없음 | 같은 시각에 같은 글이 한 번 |
| 8 | 추가 API 과금 0원 | 그록 프로 구독 외 결제 없음 |

---

## 13. 너의 첫 턴에 할 일

1. 마키마의 A1·A2 출력을 받는다 (`git pull` 결과)
2. `git log --oneline -3` 에 `tzdata` 커밋(`067be82` 이후)이 있는지 확인
3. A3 를 지시한다:
   ```powershell
   cd $HOME\helth_training
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -c "import requests, PIL, tzdata; print('packages ok')"
   .\.venv\Scripts\python.exe -c "from zoneinfo import ZoneInfo; print(ZoneInfo('Asia/Seoul'))"
   ```
   마지막 줄이 `zoneinfo.ZoneInfo(key='Asia/Seoul')` 를 찍어야 한다
4. 동시에 사용자에게 §9-1(고정 권한)과 §9-2(`.env` 값 4개)를 요청한다.
   A4 에서 필요하니 미리 받아두면 대기시간이 줄어든다
5. **Actions 끄기는 A6 을 눈으로 확인하기 전까지 절대 요청하지 마라**

---

## 14. 마지막 — 이 프로젝트의 진짜 목적

기능 목록이 아니다. **사용자가 헬스장에 가게 만드는 것**이다.

그래서 우선순위가 이렇다:
1. **자극이 끊기지 않는 것** — 채널이 조용해지면 전부 무의미하다
2. **뮤트당하지 않는 것** — 시끄럽거나 공허하면 채널을 안 본다.
   그래서 밤에는 조용하고, 할 말이 없으면 발행하지 않는다
3. **죄책감을 주지 않는 것** — 못 한 날을 나무라면 다음 날 채널을 안 본다.
   🟢만 해도 오운완이다
4. 기록이 쌓이는 것 — 그래야 코치가 "처음 만난 사람"처럼 말하지 않는다

기술적으로 완벽한데 사용자가 안 보는 채널은 실패다.
판단이 갈릴 때는 이 4개 순서로 결정해라.
