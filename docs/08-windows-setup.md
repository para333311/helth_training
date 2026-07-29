# 08. Windows 노트북으로 상시 실행

라즈베리파이를 사지 않고, 이미 켜져 있는 Windows 노트북에 봇을 얹는 방법이다.
DM 명령(`/done`, `/streak`, 사진 제출)을 쓰려면 이 방식이든 07번 문서든 **뭔가는 24시간 켜져 있어야 한다.**

이미 그 노트북에서 다른 텔레그램 봇(예: 개인 비서)이 돌고 있어도 상관없다.
**서로 다른 BotFather 토큰을 쓰는 완전히 별개의 프로그램이라 충돌하지 않는다.**

---

## GitHub Actions 와의 관계

이 방식을 쓰면 **Actions 워크플로는 꺼두는 게 좋다.** 둘 다 켜두면 같은 시간에 미션이 두 번 발행된다.

레포 → Actions 탭 → 왼쪽 "채널 발행" → 우측 상단 **"..." → Disable workflow**

노트북을 끄는 날이 있을 걸 대비해서 Actions 는 비활성화만 해두고 삭제하지 않는 걸 권장한다.
노트북을 오래 못 켤 상황이면 다시 켜면 된다 (그동안은 발행이 비지만, 04번 문서의 "리셋 데이" 철학대로 며칠 비어도 괜찮다).

---

## 1. Python 설치 확인

이미 설치돼 있으면 건너뛴다.

```powershell
python --version
```

`Python 3.11` 이상이 안 뜨면 https://www.python.org/downloads/ 에서 설치.
설치 중 **"Add python.exe to PATH"** 체크박스를 반드시 켠다.

## 2. Git 설치 확인

```powershell
git --version
```

없으면 https://git-scm.com/download/win 에서 설치.

---

## 3. 레포 클론

PowerShell 을 열고:

```powershell
cd $HOME
git clone https://github.com/para333311/helth_training.git
cd helth_training
```

이미 클론했다면:

```powershell
cd $HOME\helth_training
git pull
```

---

## 4. 가상환경 + 의존성 설치

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`Activate.ps1` 실행이 막히면 (실행 정책 오류) PowerShell을 관리자 권한으로 열고:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

한 번만 하면 된다.

**한글 폰트는 따로 설치할 필요 없다.** Windows 는 기본으로 맑은 고딕이 깔려 있고, 봇이 자동으로 찾는다.

---

## 5. .env 설정

```powershell
copy .env.example .env
notepad .env
```

GitHub Actions Secrets 에 넣었던 값을 그대로 옮긴다.

```
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

저장하고 메모장을 닫는다.

> **이 `data\helth.db` 는 GitHub Actions 에서 쌓인 기록과 별개다.**
> 여기서부터 스트릭이 새로 시작된다. Actions 쪽 기록을 옮기고 싶으면 알려달라.

---

## 6. 동작 확인

```powershell
python -m bot --check
```

```
발행 대상: 같이보는 오운완 (channel, id=-100...)
설정 정상입니다.
```

이게 뜨면 준비 끝. `Ctrl+C` 로 종료.

---

## 7. 상시 실행 등록 (작업 스케줄러)

PowerShell 창을 계속 띄워두는 방식은 창을 닫으면 봇도 죽는다.
**작업 스케줄러**에 등록하면 로그인 시 자동으로 백그라운드에서 켜지고, 죽으면 알아서 재시작한다.

### 7-1. 실행할 경로 확인

아래 두 경로를 메모해둔다 (사용자 이름에 맞게 실제 경로가 다를 수 있다).

```powershell
(Get-Item .venv\Scripts\pythonw.exe).FullName
(Get-Item .).FullName
```

`pythonw.exe` 는 콘솔 창 없이 백그라운드로 도는 버전이다 (`python.exe` 아님).

### 7-2. 작업 스케줄러 등록

1. `Win + R` → `taskschd.msc` → Enter
2. 오른쪽 **"작업 만들기..."** (기본 작업 만들기 말고 "작업 만들기")
3. **일반** 탭
   - 이름: `helth-bot`
   - **"사용자가 로그온했는지 여부에 관계없이 실행"** 선택
   - **"가장 높은 권한으로 실행"** 체크
4. **트리거** 탭 → 새로 만들기
   - 작업 시작: **"로그온할 때"**
   - (선택) 추가 트리거로 **"컴퓨터가 유휴 상태가 아닐 때마다 반복"** 은 필요 없음
5. **동작** 탭 → 새로 만들기
   - 프로그램/스크립트: 7-1 에서 확인한 `pythonw.exe` 전체 경로
   - 인수 추가: `-m bot`
   - 시작 위치: 7-1 에서 확인한 레포 폴더 전체 경로
6. **조건** 탭
   - "컴퓨터가 AC 전원을 사용할 때만 작업 시작" **체크 해제** (노트북 배터리로 돌 때도 실행)
7. **설정** 탭
   - **"작업이 실패하면 다시 시작 간격"** 체크 → `1분마다`, `3회`
   - "예약된 시작 시간을 놓치면 가능한 한 빨리 작업 시작" 체크
8. 확인 → 로그온 암호 입력 요구되면 Windows 로그인 암호 입력

### 7-3. 지금 바로 시작

작업 스케줄러 목록에서 `helth-bot` 우클릭 → **실행**.

작업 관리자(`Ctrl+Shift+Esc`) → 세부 정보 탭에서 `pythonw.exe` 가 보이면 동작 중이다.

---

## 8. 로그 확인

`pythonw.exe` 는 창이 없어서 출력이 안 보인다. 파일로 남기려면 동작을 아래처럼 바꾼다.

작업 스케줄러 → `helth-bot` → 속성 → 동작 탭 → 편집:

- 프로그램/스크립트: `cmd.exe`
- 인수 추가:
  ```
  /c ".venv\Scripts\python.exe -m bot >> logs\bot.log 2>&1"
  ```
- 시작 위치는 그대로 레포 폴더

레포 폴더에 `logs` 폴더를 미리 만들어둔다.

```powershell
mkdir logs
```

이후 로그 확인:

```powershell
Get-Content logs\bot.log -Tail 30 -Wait
```

---

## 9. 재부팅 테스트

```powershell
Restart-Computer
```

로그인 후 1분 뒤:

```powershell
Get-Process pythonw -ErrorAction SilentlyContinue
```

뭔가 뜨면 정상 동작 중이다.

---

## 10. DM 기능 시험

텔레그램에서 `@helth_training_bot` 을 검색해 **1:1 대화**를 연다 (마키마 말고, 이 새 봇).

```
/start
/mission
/done
/streak
```

`/done` 에 "💪 오운완 기록됨" 과 연속 일수가 뜨면 정상이다.

---

## 업데이트하는 법

```powershell
cd $HOME\helth_training
git pull
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

작업 스케줄러에서 `helth-bot` 우클릭 → **끝내기** → 다시 우클릭 → **실행**.

---

## 문제 해결

| 증상 | 확인 |
|---|---|
| 작업이 "실행되지 않음"으로 뜸 | 로그인 암호가 바뀌었을 수 있음 → 작업 속성에서 암호 재입력 |
| `pythonw.exe` 가 안 보임 | 경로 오타 → 7-1 의 `FullName` 값을 다시 정확히 붙여넣기 |
| DM 명령이 안 먹음 | Actions 워크플로가 아직 켜져 있어 두 프로세스가 충돌 → Actions 비활성화 |
| 노트북 절전모드로 자꾸 꺼짐 | 설정 → 시스템 → 전원 → "절전" 을 "안 함" 으로 (전원 연결 시) |
| 명언 카드가 안 나옴 | 거의 없는 문제 (Windows 기본 폰트 자동 인식). 로그에 "한글 폰트를 찾지 못했습니다" 있으면 알려달라 |
