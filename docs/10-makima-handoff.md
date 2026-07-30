# 마키마 인수인계서 — 이 프로젝트를 끝까지 마무리하는 방법

**읽는 사람: 마키마(제1비서관).**
이 문서 하나로 남은 작업을 전부 끝낼 수 있게 썼다. 막히면 여기로 돌아온다.

이 문서가 존재하는 이유는 단순하다. 젠스파크 크레딧이 유한하다.
그래서 **실행·설치·시행착오는 전부 너 몫**이고, 사람은 전달만 하고,
외부 검토자는 설계·버그 원인 규명·최종 검토에만 부른다.

---

## 0. 행동 규약 (먼저 읽는다)

1. **한 번에 한 단계.** 단계 끝날 때마다 결과를 보고하고 다음으로 간다.
   여러 단계를 한 번에 몰아 실행하면 어디서 깨졌는지 알 수 없다.
2. **추측하지 말고 확인한다.** 경로·버전·설치 여부는 전부 명령으로 확인 가능하다.
   "아마 있을 것"으로 넘어가서 3단계 뒤에 터지는 게 최악이다.
3. **막히면 `python tests/preflight.py` 를 먼저 돌린다.** 사람에게 묻기 전에.
   이 스크립트가 원인을 한국어로 알려주도록 만들어 뒀다.
4. **사람에게는 "사람만 할 수 있는 일"만 요청한다.** 목록은 §7 에 있다.
   그 외에는 너가 직접 한다.
5. **불변식 하나:** *채널 발행 주체는 항상 정확히 1개.*
   0개면 채널이 죽고, 2개면 같은 글이 두 번 나간다.
   이 불변식을 깨는 명령은 실행 전에 반드시 한 번 멈춘다.
6. **모르는 걸 지어내지 않는다.** 특히 OpenClaw 옵션. `openclaw <cmd> --help` 로 확인한다.

---

## 1. 최종 목표 (Definition of Done)

이게 다 되면 끝이다.

| # | 완료 조건 | 확인 방법 |
|---|---|---|
| 1 | 노트북에서 헬스봇이 24시간 떠 있다 | 재부팅 후에도 `python.exe` 가 살아 있다 |
| 2 | 채널 `@helth_training` 에 07~22시 매시 자극이 뜬다 | 두 시간 연속 관찰 |
| 3 | DM 으로 `/done`, 사진, 체중이 기록된다 | `python -m bot --brief` 에 숫자가 찍힌다 |
| 4 | 마키마가 하루 3번 코치로 채널에 말한다 | 07:40 / 22:20 / (일)21:20 (컨디션 cron 은 미등록) |
| 5 | DM 에서는 비서 인격 그대로다 | 말투·역할이 코치와 섞이지 않는다 |
| 6 | GitHub Actions 는 꺼져 있다 | 워크플로에 `Disabled` 배지 |
| 7 | 중복 발행이 없다 | 같은 시각에 같은 글이 두 번 안 뜬다 |
| 8 | 추가 API 과금이 0원 | 그록 프로 구독 외 결제 없음 |

**아직 하나도 못 한 상태여도 정상이다.** 지금 위치는 단계 A 중간이다.

---

## 2. 전체 지도

```
[단계 A] 노트북에 헬스봇 올리기          ← 지금 여기
   A1 이미 있는 폴더 정리 (clone 에러 해결)
   A2 최신 코드 받기 (tzdata·BOM 수정 포함)
   A3 .venv 에 패키지 설치
   A4 .env 작성  ......................... 사람에게 값 요청 필요
   A5 preflight 통과
   A6 실제 발행 1회 검증
   A7 작업 스케줄러 등록 (--serve = DM 전용)
        ↓
[단계 B] 코치 cron 등록
   B1 secretary1 받기
   B2 기존 cron 백업
   B3 coach: 잡 등록 (기본 3개, coach:condition 은 --IncludeCondition 없이는 안 됨)
   B4 즉시 실행 테스트
        ↓
[단계 C] 발행 주체 교체 (가장 위험한 단계)
   C1 Actions 끄기  ..................... 사람만 가능
   C2 작업 스케줄러를 발행 모드로 재등록
   C3 매시 발행 확인
        ↓
[단계 D] 하루 운영 검증 + 자격증명 교체
```

단계 A 가 안 끝났는데 C 로 가면 채널이 죽는다. 이미 한 번 그랬다.

---

## 3. 단계 A — 노트북에 헬스봇 올리기

### A1. `already exists` 에러 해결

지금 나는 에러:

```
fatal: destination path 'helth_training' already exists and is not an empty directory.
```

**이건 에러가 아니라 "이미 받아놨다"는 뜻이다.** 다시 clone 하면 안 된다.
확인부터 한다.

```powershell
cd $HOME\helth_training
git rev-parse --is-inside-work-tree
git remote -v
git log --oneline -1
```

- `true` + remote 가 `para333311/helth_training` → **정상. A2 로 간다.**
- `fatal: not a git repository` → git 저장소가 아니다. 밀지 말고 옆으로 치우고 다시 받는다:
  ```powershell
  cd $HOME
  Rename-Item helth_training "helth_training.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
  git clone https://github.com/para333311/helth_training.git
  ```
  `.bak` 폴더는 지우지 않는다. 안에 `.env` 가 있었을 수 있다.

### A2. 최신 코드 받기 — **건너뛰면 안 된다**

지금 노트북에 있는 코드는 구버전이다. 두 개의 치명적 버그가 고쳐진 커밋이 원격에 있다.

```powershell
cd $HOME\helth_training
git stash list
git status --short
git pull --ff-only origin main
git log --oneline -3
```

`--ff-only` 가 거부되면 로컬에 커밋이 있다는 뜻이다. 그 내용을 보고하고 멈춘다.
(임의로 `git reset --hard` 하지 않는다. 사람이 손으로 고친 게 있을 수 있다.)

받아야 하는 수정 두 개:

| 버그 | 안 받으면 생기는 증상 |
|---|---|
| `tzdata` 누락 | 봇이 **아예 안 뜬다**. `ZoneInfoNotFoundError: 'No time zone found with key Asia/Seoul'`. Windows 에는 IANA 시간대 DB 가 없다 |
| `.env` BOM | 토큰을 **정확히 넣어도** "토큰이 없다"고 나온다. PowerShell 이 파일 앞에 붙이는 BOM 때문에 첫 줄 키가 `\ufeffTELEGRAM_BOT_TOKEN` 이 된다 |

둘 다 증상이 원인을 전혀 가리키지 않는 종류다. 그래서 A2 를 건너뛰면
없는 문제를 몇 시간 쫓게 된다.

### A3. `.venv` 에 패키지 설치

`.venv` 는 이미 있다. 다만 이전 설치가 전역 site-packages 로 갔을 가능성이 있어서
**venv 안에 있는지 직접 확인**한다.

```powershell
cd $HOME\helth_training
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "import requests, PIL, tzdata; print('packages ok')"
.\.venv\Scripts\python.exe -c "from zoneinfo import ZoneInfo; print(ZoneInfo('Asia/Seoul'))"
```

마지막 줄이 `zoneinfo.ZoneInfo(key='Asia/Seoul')` 를 찍어야 한다.
`ZoneInfoNotFoundError` 가 나면 `tzdata` 가 venv 에 없다 → `requirements.txt` 에
`tzdata` 가 있는지 확인(= A2 를 제대로 했는지)한다.

`.venv` 자체가 의심스러우면 만드는 게 싸다:

```powershell
cd $HOME\helth_training
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

이후 **모든 명령은 `.\.venv\Scripts\python.exe` 로** 실행한다. 맨 `python` 은 전역이다.

### A4. `.env` 작성 — 사람에게 값을 요청하는 유일한 지점

`.env` 는 커밋되지 않는다(그래야 한다). 그래서 값은 사람에게서 온다.

**사람에게 이렇게 요청한다:**

> `.env` 에 넣을 값 4개가 필요합니다. 아래를 채워서 그대로 보내주세요.
>
> 1. `TELEGRAM_BOT_TOKEN` — 텔레그램에서 @BotFather → `/mybots` → 헬스봇 →
>    **API Token**. 이 기회에 **Revoke current token** 을 눌러 새로 발급받는 걸
>    권합니다(예전 토큰이 대화창에 노출된 적 있음).
> 2. `OWNER_USER_ID` — @userinfobot 에게 아무 말이나 보내면 나오는 숫자
> 3. `UNSPLASH_ACCESS_KEY` — https://unsplash.com/oauth/applications (없으면 비워도 됨)
> 4. `PEXELS_API_KEY` — https://www.pexels.com/api/ (없으면 비워도 됨)
>
> 3·4 는 둘 중 하나만 있어도 됩니다. 둘 다 없으면 사진 대신 명언 카드로 대체됩니다.

나머지 값은 이미 확정돼 있으니 물어보지 않는다:

| 키 | 값 |
|---|---|
| `TELEGRAM_CHANNEL_ID` | `-1004448866091` |
| `TELEGRAM_BOT_USERNAME` | 헬스봇 username (`--chatid` 결과나 BotFather 에서 확인) |
| `SOLO_MODE` | `true` |
| `SEASON_START` | `2026-07-30` |
| `SEASON_DAYS` / `SEASON_NAME` / `GOAL_KG` | `84` / `3kg 프로젝트` / `3.0` |
| `PHOTO_INTERVAL_MINUTES` / `PHOTO_START_HOUR` / `PHOTO_END_HOUR` | `60` / `7` / `22` |
| `TZ` | `Asia/Seoul` |

**BOM 없이 쓰는 방법.** `Set-Content -Encoding UTF8` 을 쓰면 안 된다.
아래 방식만 쓴다 (`@'...'@` 는 리터럴이므로 토큰의 특수문자가 안전하다):

```powershell
$body = @'
# 이 파일은 커밋되지 않는다
TELEGRAM_BOT_TOKEN=여기에토큰
TELEGRAM_CHANNEL_ID=-1004448866091
TELEGRAM_BOT_USERNAME=여기에봇username
OWNER_USER_ID=여기에숫자
SOLO_MODE=true
PHOTO_INTERVAL_MINUTES=60
PHOTO_START_HOUR=7
PHOTO_END_HOUR=22
UNSPLASH_ACCESS_KEY=
PEXELS_API_KEY=
PHOTO_QUERY=home workout,gym motivation,fitness
SEASON_START=2026-07-30
SEASON_DAYS=84
SEASON_NAME=3kg 프로젝트
GOAL_KG=3.0
TZ=Asia/Seoul
'@
[System.IO.File]::WriteAllText("$HOME\helth_training\.env", $body, (New-Object System.Text.UTF8Encoding($false)))
```

첫 줄을 주석으로 둔 것도 안전장치다. 혹시 BOM 이 붙어도 주석이 흡수한다.

**절대 하지 말 것:** 토큰을 `.env` 밖의 파일, 커밋, 로그, 화면 출력에 남기지 않는다.
`.env` 내용을 확인할 때는 `Get-Content .env` 대신 preflight 를 쓴다 (마스킹해서 보여준다).

### A5. preflight 통과

```powershell
cd $HOME\helth_training
.\.venv\Scripts\python.exe tests\preflight.py --net
```

이게 이 프로젝트의 **자가 진단 장치**다. 사람이나 외부 검토자를 부르기 전에 항상 먼저 돌린다.
검사 항목: 파이썬 버전 / 패키지 / 시간대 / SQLite 한글 / 한글 폰트 /
`.env`(BOM 포함) / 설정 로드 / 텔레그램 및 스톡 API 실전 호출.

- **종료 코드 0** = 봇이 뜰 수 있다 → A6 으로
- **종료 코드 1** = `FATAL` 이 있다. 출력에 원인과 조치가 한국어로 같이 나온다. 그걸 먼저 고친다.
- `WARN` 은 진행을 막지 않는다. 단 아래 하나는 예외다:
  - **`can_pin_messages` 없음** → `--pin` 이 실패한다. **사람만 고칠 수 있다**(§7).
    이게 뜨면 사람에게 요청하고, `--pin` 없이 진행한다.

같이 돌려두면 좋은 두 개(둘 다 네트워크 불필요, 몇 초):

```powershell
.\.venv\Scripts\python.exe tests\env_encoding.py
.\.venv\Scripts\python.exe tests\coach_smoke.py
```

### A6. 실제 발행 1회 검증 — **단계 C 의 전제조건**

preflight 가 통과했다고 발행이 되는 건 아니다. 눈으로 봐야 한다.

```powershell
cd $HOME\helth_training
.\.venv\Scripts\python.exe -m bot --once photo
```

그리고 **채널 `@helth_training` 을 직접 열어서 방금 그 글이 있는지 확인**한다.
없으면 단계 C 로 절대 가지 않는다. 이 검증 없이 Actions 를 끄면 채널이 죽는다.

브리핑도 확인한다 (아직 데이터가 없어서 0 이 정상이다):

```powershell
.\.venv\Scripts\python.exe -m bot --brief
```

### A7. 작업 스케줄러 등록 — `--serve` 로

**`--serve` 는 DM 만 받고 채널에 발행하지 않는다.** 그래서 Actions 가 켜져 있는
지금도 안전하게 같이 돌릴 수 있다. 이게 이 전환의 핵심 장치다.

| 모드 | DM 응답 | 채널 발행 | Actions 켜진 상태에서 |
|---|---|---|---|
| `-m bot --serve` | O | X | **안전** |
| `-m bot` | O | O | 중복 발행 — 금지 |

등록 (`docs/08-windows-setup.md` 7-4절과 동일):

```powershell
$BotDir = "$HOME\helth_training"
$Mode = 'serve'
$TaskName = 'helth-bot'

$pyw = Join-Path $BotDir '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pyw)) { $pyw = (Get-Command pythonw.exe).Source }
$botArgs = if ($Mode -eq 'serve') { '-m bot --serve' } else { '-m bot' }
$action  = New-ScheduledTaskAction -Execute $pyw -Argument $botArgs -WorkingDirectory $BotDir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 3
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "헬스봇 ($Mode)" | Out-Null
Start-ScheduledTask -TaskName $TaskName
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
```

확인:

```powershell
Get-Process pythonw -ErrorAction SilentlyContinue | Select-Object Id, StartTime
```

그리고 **텔레그램에서 헬스봇에게 DM 으로 `/streak`** 을 보낸다. 답이 오면 살아 있다.

> `409 Conflict` 가 로그에 보이면 `getUpdates` 를 두 프로세스가 동시에 폴링하는 것이다.
> 앞서 수동으로 띄운 봇이 남아 있는지 확인하고 하나만 남긴다.

**A 단계 끝. 사람에게 보고하고 B 로 간다.**

---

## 4. 단계 B — 코치 cron 등록

설정은 `secretary1` 저장소에 config-as-code 로 들어 있다.

### B1. secretary1 받기

```powershell
cd $HOME
if (Test-Path secretary1) { cd secretary1; git pull --ff-only origin main }
else { git clone https://github.com/para333311/secretary1.git; cd secretary1 }
```

읽어야 하는 문서:

| 파일 | 내용 |
|---|---|
| `openclaw/coach-persona.md` | 코치 말투, flags → 행동 표, 금지사항 7개 |
| `openclaw/jobs.md` | 잡 명세(기본 3개) + 헬스봇과 겹치지 않는 시간표 |
| `docs/architecture.md` | 왜 이렇게 만들었는지 + 버린 대안 |
| `docs/troubleshooting.md` | 사고 이력. **0번 항목부터** 읽는다 |

### B2. 기존 cron 백업 — **먼저**

DM 비서용 잡이 이미 돌고 있다. 그걸 건드리면 안 된다.

```powershell
cd $HOME\secretary1
openclaw cron list --all --json > "cron-backup-$(Get-Date -Format yyyyMMdd-HHmmss).json"
Get-ChildItem cron-backup-*.json
```

`--json` 이 없는 버전이면 그냥 `openclaw cron list --all > cron-backup-....txt` 로 남긴다.
백업 파일은 `.gitignore` 에 걸려 있어서 커밋되지 않는다.

### B3. 등록

```powershell
cd $HOME\secretary1\openclaw
.\register-cron.ps1 -BotDir "$HOME\helth_training" -DryRun   # 먼저 이것만. 실제로 안 건드린다
```

`-BotDir` 은 **생략할 수 없다.** 없으면 스크립트가 거부한다. 파이썬은 지정하지
않으면 `$BotDir\.venv\Scripts\python.exe` 를 자동으로 찾는다 — A3 에서 venv 를
제대로 만들었으면 그게 잡힌다.

`-DryRun` 출력이 기대와 맞는지 확인한다 — **기본 잡 3개**, 07:40 / 22:20 / 일 21:20,
`--session isolated`, `--tools exec,read`, `--no-deliver`, `--tz Asia/Seoul`.

> **`coach:condition`(19:00)은 기본으로 등록되지 않는다.** 원안은 컨디션을 채널에
> `--say`로 묻고 같은 cron 실행 안에서 `--record`로 저장하는 구조였는데, 이 채널은
> 구독자가 답장할 방법이 없는 방송 전용 비공개 채널이고, `--session isolated` cron은
> 사람이 답할 때까지 기다려주지 않는다. 즉 질문은 나가도 답을 받을 방법이 없다.
>
> 대신 헬스봇에 `/condition 1~5` DM 명령이 추가됐다 — 운영자가 스스로 기록하고,
> `--brief`의 `condition_stale`/`needs_rest`는 그 값을 그대로 읽는다. 나머지 코치
> 판단에는 지장이 없다. 원안대로 강행하려면 `-IncludeCondition`을 쓸 수 있지만,
> 위 이유로 등록해도 질문만 나가고 답을 받지 못하니 권하지 않는다.

> **주의:** 이 스크립트는 아직 **어디서도 실행된 적이 없다.** 정적 검토만 했다.
> `-DryRun` 에서 뭔가 이상하면 강행하지 말고 그 출력을 그대로 보고한다.
> OpenClaw 옵션명이 버전에 따라 다를 수 있다 — `openclaw cron add --help` 로 대조한다.
>
> Windows 특이사항: `sh` 가 없으므로 `--command <셸문자열>` 형태는 깨진다.
> 반드시 `--command-argv` 나 `--message` 를 쓴다.

이상 없으면 실제 등록 (`-DryRun` 만 뺀 같은 명령):

```powershell
.\register-cron.ps1 -BotDir "$HOME\helth_training"
.\register-cron.ps1 -List
```

`-List` / `-Disable` / `-Enable` / `-Remove` 는 `-BotDir` 없이 단독으로 쓴다
(별도 파라미터 세트다. 같이 주면 오류가 난다).

`-List` 에 `coach:morning`, `coach:night`, `coach:weekly` 3개가 보이고
(`-IncludeCondition` 을 안 썼다면 `coach:condition` 은 없는 게 정상이다)
**기존 비서 잡이 그대로 남아 있어야** 한다.

### B4. 즉시 실행 테스트

```powershell
openclaw cron list --all
openclaw cron run <coach:morning 의 jobId>
openclaw cron runs --id <jobId>
```

확인할 것:

- 채널에 코치 말투로 **한 번만** 떴는가 (두 번 뜨면 `--no-deliver` 가 안 걸린 것)
- 발행 주체가 헬스봇인가 (마키마 계정으로 뜨면 안 된다)
- DM 대화 맥락이 섞여 들어오지 않았는가 (섞이면 `--session isolated` 문제)
- `--brief` 를 실제로 읽은 흔적이 있는가 (D+n·스트릭 언급)

문제가 있으면 `.\register-cron.ps1 -Disable` 로 코치 4개만 끈다. 비서는 계속 돈다.

**B 단계 끝. 보고하고 C 로 간다.**

---

## 5. 단계 C — 발행 주체 교체 (가장 위험)

지금 채널에 매시 글을 올리는 건 **GitHub Actions** 다. 노트북이 아니다.
Actions 를 먼저 끄고 노트북이 준비 안 돼 있으면 채널이 조용해진다. 실제로 한 번 그랬다.

### C0. 전제조건 — 하나라도 X 면 멈춘다

- [ ] `$HOME\helth_training` 에 저장소가 있고 `.env` 에 토큰이 들어 있다
- [ ] `preflight.py --net` 이 종료 코드 0
- [ ] 작업 스케줄러에 등록돼 `pythonw.exe` 가 떠 있다
- [ ] **`--once photo` 로 올린 글을 채널에서 직접 눈으로 봤다** (A6)

### C1. Actions 끄기 — 사람만 가능

GitHub App 토큰으로는 워크플로 파일 수정도, Actions API 호출도 안 된다
(`403 Resource not accessible by integration`). 그래서 이건 **사람 몫**이다.

**사람에게 이렇게 요청한다:**

> 이제 노트북이 발행할 준비가 됐습니다. GitHub Actions 를 꺼주세요.
>
> 1. https://github.com/para333311/helth_training/actions 열기
> 2. **왼쪽 사이드바**의 워크플로 목록에서 `publish` 클릭
>    (오른쪽 위 `⋯` 아님 — 그건 개별 실행 메뉴입니다)
> 3. 목록 위쪽 오른편의 `⋯` → **Disable workflow**
> 4. 워크플로 이름 옆에 `Disabled` 배지가 생기면 완료. 스크린샷 주세요.
>
> ```
>  Actions
>  ┌──────────────┬─────────────────────────────────┐
>  │ All workflows│  publish            [⋯] ← 이거  │
>  │ ▸ publish ←② │  ─────────────────────────────  │
>  │              │  Scheduled  #123                │
>  └──────────────┴─────────────────────────────────┘
> ```
>
> `schedule:` 주석 처리가 아니라 이 UI 방식이어야 합니다. UI 설정은 저장소 설정에
> 남아서 `git pull`·머지에도 살아남습니다.

`Disabled` 배지를 확인하기 전에 C2 로 가지 않는다.
(끄기 전에 C2 를 하면 두 주체가 동시에 발행해서 모든 글이 두 번 나간다.)

### C2. 발행 모드로 재등록 — Actions 를 끈 **직후**

A7 과 같은 스크립트에서 `$Mode` 만 바꾼다.

```powershell
$BotDir = "$HOME\helth_training"
$Mode = 'full'        # ← 여기만 바뀐다
$TaskName = 'helth-bot'

$pyw = Join-Path $BotDir '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pyw)) { $pyw = (Get-Command pythonw.exe).Source }
$botArgs = if ($Mode -eq 'serve') { '-m bot --serve' } else { '-m bot' }
$action  = New-ScheduledTaskAction -Execute $pyw -Argument $botArgs -WorkingDirectory $BotDir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 3
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "헬스봇 ($Mode)" | Out-Null
Start-ScheduledTask -TaskName $TaskName
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
```

`--serve` 를 끄고 `-m bot` 으로 올리는 게 이 단계의 전부다.
**여기서 멈추면 발행 주체가 0개가 된다.** C1 과 C2 는 한 세션 안에서 연달아 한다.

### C3. 확인

다음 정시를 기다려서 채널에 자극이 **한 번만** 뜨는지 본다.

- 안 뜨면 → 발행 주체 0개. 진단은 `secretary1/docs/troubleshooting.md` **0번 항목**.
  급하면 사람에게 `Enable workflow` 를 요청해 즉시 복구하고, 그 다음에 원인을 찾는다.
- 두 번 뜨면 → 주체 2개. `Disabled` 배지를 다시 확인한다.

**참고:** Actions 가 쌓아둔 상태 DB(`actions/cache`)는 노트북으로 옮겨오지 않는다.
그런데 잃을 게 없다 — DM 명령(`/done`·사진·체중)은 Actions 에서 애초에 동작하지
않았으므로 스트릭·체중 데이터가 존재한 적이 없다. 노트북 전환이 곧 **기록의 시작**이다.

---

## 6. 단계 D — 하루 운영 검증 + 마무리

### D1. 하루치 관찰 체크리스트

| 시각 | 기대 | 주체 |
|---|---|---|
| 07:30 | 3단 미션 | 헬스봇 |
| 07:40 | 아침 한마디 | 마키마 → 헬스봇이 발행 |
| 매시 08~22 | 자극 드롭 (LLM 0회) | 헬스봇 |
| 12:30 | 귀찮음 응급처치 | 헬스봇 |
| 19:00 | 컨디션 체크 | 마키마 |
| 22:00 | 오운완 체크인 | 헬스봇 |
| 22:20 | 밤 마무리 | 마키마 |
| 23:00~06:00 | **아무것도 없음** | — |

### D2. 데이터가 실제로 쌓이는지

DM 으로 `/done` 을 보낸 뒤:

```powershell
.\.venv\Scripts\python.exe -m bot --brief
```

`streak` 이 올랐는지 본다. 안 오르면 `OWNER_USER_ID` 가 틀렸다 —
`--brief` 와 `--record` 는 이 값으로 "누구 기록인지"를 판단한다.

컨디션 답을 받았으면 **반드시** 저장한다:

```powershell
.\.venv\Scripts\python.exe -m bot --record condition=4
```

저장을 빼먹으면 내일 또 묻게 되고, 데이터가 안 쌓여서 코치가 영원히
"처음 만난 사람"처럼 말한다.

### D3. 자격증명 교체

토큰과 API 키가 과거 대화창에 노출됐다. `.env` 가 유일한 소비자가 된 지금이
교체 적기다. **사람에게 요청한다** (§7-3).

교체 후 `.env` 를 §A4 방식으로 다시 쓰고 `preflight.py --net` 을 다시 돌린다.

---

## 7. 사람만 할 수 있는 일 (이것만 요청한다)

너도, 외부 검토자도 못 하는 것들이다. 나머지는 전부 너가 한다.

### 7-1. 텔레그램 채널 — 메시지 고정 권한

현재 헬스봇에게 `can_post_messages` 는 있고 **`can_pin_messages` 는 없다.**
그래서 `--say --pin` 이 실패한다.

> 텔레그램 `@helth_training` 채널 → 관리자 → 헬스봇 → **메시지 고정** 을
> 켜주세요. 지금 이 권한이 없어서 코치가 중요한 글을 고정할 수 없습니다.

### 7-2. GitHub Actions 끄기 / 켜기

§C1 참조. Secrets·Variables 읽기도 사람만 가능하다(UI 에서도 값은 안 보인다).
그래서 설정값은 GitHub 이 아니라 `.env` 를 정본으로 삼는다.

### 7-3. 자격증명 재발급

> 다음을 새로 발급해서 보내주세요. 예전 값이 대화창에 노출된 적이 있습니다.
> 1. @BotFather → `/mybots` → 헬스봇 → API Token → **Revoke current token**
> 2. Unsplash Access Key — https://unsplash.com/oauth/applications
> 3. Pexels API Key — https://www.pexels.com/api/
>
> 새 토큰을 받으면 예전 토큰은 즉시 무효가 되니, 보내주신 직후에 `.env` 를
> 갱신하고 봇을 재시작하겠습니다. 그 사이 몇 분간 봇이 멈춥니다.

### 7-4. 헬스봇 이름 변경

BotFather 에서 하는 일이고, 사람이 원할 때 하면 된다. 너는 건드리지 않는다.
마키마는 계속 "마키마"다.

---

## 8. 자가 진단 — 사람·검토자를 부르기 전에

### 8-1. 순서

```powershell
cd $HOME\helth_training
.\.venv\Scripts\python.exe tests\preflight.py --net     # 1. 환경
.\.venv\Scripts\python.exe tests\env_encoding.py        # 2. BOM 회귀
.\.venv\Scripts\python.exe tests\coach_smoke.py         # 3. flags 로직 8케이스
.\.venv\Scripts\python.exe -m bot --check               # 4. 설정 로드
```

### 8-2. 증상 → 원인 대응표

| 증상 | 진짜 원인 | 조치 |
|---|---|---|
| `ZoneInfoNotFoundError: 'Asia/Seoul'` | `tzdata` 없음 | A2 → A3 |
| 토큰 넣었는데 "토큰이 없다" | `.env` BOM | A2 로 코드 갱신 + A4 방식으로 재작성 |
| `--pin` 실패 | `can_pin_messages` 없음 | 사람 (§7-1) |
| `409 Conflict` | 두 프로세스가 `getUpdates` 폴링 | 하나만 남긴다 |
| 채널에 아무것도 안 뜬다 | **발행 주체 0개** | troubleshooting.md 0번. 급하면 Enable workflow |
| 같은 글이 두 번 | 발행 주체 2개 | `Disabled` 배지 확인 |
| `--brief` 가 전부 0 | `OWNER_USER_ID` 불일치 | `.env` 수정 |
| D+1 에서 안 늘어남 | `SEASON_START` 가 비어 있다 | `2026-07-30` 로 채운다 |
| 카드 한글이 □□□ | 폰트 미검출 | preflight `[5]` 확인, `malgun.ttf` |
| `git pull` 거부 | 로컬 커밋 존재 | 밀지 말고 보고 (A2) |
| `--command` 가 Windows 에서 깨짐 | `sh` 없음 | `--command-argv` / `--message` |

### 8-3. 그래도 모르겠으면 — 검토자에게 넘기는 양식

사람에게 이 형식으로 정리해서 준다. 여기 없는 정보로는 원인 규명이 안 된다.

```
■ 무엇을 하려 했나 (단계 번호)
■ 실행한 명령 (그대로, 편집 없이)
■ 출력 전문 (토큰은 앞 4자만)
■ preflight --net 결과 (종료 코드 + FATAL/WARN 줄)
■ git log --oneline -3
■ .venv\Scripts\python.exe --version
■ 이미 시도해본 것과 결과
```

---

## 9. 코드를 고쳐야 할 때 — 최종 검토 핸드오프

문서만으로 안 되고 코드를 바꿔야 하는 상황이 온다. 그때 규약이다.

### 9-1. 작업 방식

1. 브랜치를 딴다. `main` 에 직접 커밋하지 않는다.
   ```powershell
   cd $HOME\helth_training
   git checkout -b makima/<짧은주제>
   ```
2. **작게** 고친다. 한 브랜치 = 한 문제.
3. 고칠 때마다 §8-1 네 개를 다 돌린다. 하나라도 깨지면 그걸 먼저 고친다.
4. 커밋 메시지는 한국어로, 무엇을 왜 고쳤는지.
   ```
   fix(store): 컨디션 중복 저장 시 UNIQUE 제약 위반

   같은 날 --record condition 을 두 번 하면 죽었다. UPSERT 로 바꿨다.
   ```

### 9-2. 검토 제출

가능하면 브랜치를 올린다 (검토자가 직접 읽을 수 있어서 가장 싸다):

```powershell
gh auth status
git push -u origin makima/<주제>
```

`gh` 인증이 안 되면 diff 를 파일로 뽑아 사람이 전달한다:

```powershell
git fetch origin main
git diff origin/main...HEAD > "$HOME\makima-review.diff"
Get-Content "$HOME\makima-review.diff" -Raw
```

**제출에 반드시 포함할 것:**

```
■ 문제: 어떤 증상이었나 (재현 명령 포함)
■ 원인: 왜 그랬나
■ 수정: 무엇을 바꿨나 + 왜 이 방법인가
■ 검증: 테스트 4개 결과 (출력 붙여넣기)
■ 부작용 가능성: 내가 걱정하는 부분
■ 브랜치명 또는 diff
```

"검증" 이 빠진 제출은 반송된다. 통과하는 것만 보고 통과 못 하는 걸 안 보면
고친 게 아니라 옮긴 거다.

### 9-3. 검토자를 부를 때 / 안 부를 때

| 상황 | 담당 |
|---|---|
| 설치·실행·시행착오·재시도 | **너** |
| 환경 진단 | **preflight.py** |
| 문서에 답이 있는 문제 | **너** (먼저 검색) |
| 아키텍처 변경, 새 기능 설계 | 검토자 |
| 원인 불명 버그, 8-2 표에 없는 증상 | 검토자 |
| 코드 최종 검토 | 검토자 |
| 워크플로 파일 / Actions API | **아무도 못 함** — 사람 (§7-2) |

크레딧이 유한하다. 3번 시도해서 안 되고 문서에도 없을 때 부른다.
반대로 **채널이 죽었거나 데이터가 날아갈 위험**이 있으면 즉시 부른다. 그건 아끼지 않는다.

---

## 10. 절대 하지 말 것

1. **발행 주체를 0개나 2개로 만들지 않는다.** A6 검증 없이 Actions 를 끄지 않고,
   Actions 가 켜진 채로 `-m bot`(발행 모드)을 띄우지 않는다.
2. **기존 DM 비서 cron 을 건드리지 않는다.** B2 백업 먼저. 코치 잡은 `coach:` 접두어로만.
3. **`.env`·토큰을 커밋하거나 출력하지 않는다.** 확인은 preflight 로.
4. **인스타그램 등에서 남의 운동 사진을 긁어오지 않는다.** 저작권 + 초상권.
   사진은 내가 보낸 것 → `content/photos/` → 스톡 API 순서로만.
5. **DM 인격을 바꾸지 않는다.** DM = 비서, 채널 = 코치. 기억은 공유, 역할은 장소로 분리.
6. **유료 API 를 붙이지 않는다.** 추가 과금 0원이 전제다.
7. **밤에 발행하지 않는다.** 23~06시는 조용. 뮤트당하면 전체가 무의미해진다.
8. **`git reset --hard` 로 로컬 변경을 밀지 않는다.** 보고하고 판단을 받는다.
9. **DM 과 채널에 같은 말을 두 번 하지 않는다.**
10. **밤 10시에 운동을 시키지 않는다.** `coach:night` 의 목적은 하루를 닫는 것이다.
11. **`Get-ChildItem C:\ -Recurse` 같은 전체 디스크 검색을 하지 않는다.**
    30분 낭비한 전례가 있다. 경로는 `$HOME\helth_training` 로 확정됐다.

---

## 11. 지금 당장 할 일

```powershell
cd $HOME\helth_training
git rev-parse --is-inside-work-tree
git remote -v
git pull --ff-only origin main
git log --oneline -3
```

이게 §A1 + §A2 다. 결과를 보고하고 A3 로 간다.
