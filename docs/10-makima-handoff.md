# 10. 마키마 연동 — 인수인계서 (전체 런북)

`secretary1` 레포(`openclaw/`, `docs/handoff.md`)가 이 문서를 정본으로 가리킨다.
단계 A~D 전부를 여기서 다룬다.

---

## 배경

이 채널은 원래 헬스봇(고정 템플릿, LLM 안 씀)만으로 운영하도록 설계됐다 (01~08번 문서).
운영자가 이미 24시간 켜둔 노트북에서 **마키마**(개인 비서, OpenClaw 기반, `secretary1` 레포)가
돌고 있어서, 별도 기기를 사는 대신 **마키마에게 코치 역할을 하나 더 준다**는 결정을 했다.

같은 마키마가 DM에서는 비서, 운동 채널에서는 코치 — 하나의 인격, 다른 역할.
엄마 역할과 아내 역할이 다른 것과 같다는 비유로 합의됐다.

**원칙: 매시간 나가는 자극(사진/명언카드/유튜브)은 절대 LLM을 쓰지 않는다.**
템플릿 기반 헬스봇이 그대로 담당한다. 마키마는 하루 4번, **판단이 필요한 순간에만** 나선다.
이 경계가 무너지면 LLM 호출량이 하루 16회 × 84일로 불어나 비용을 감당 못 한다.

---

## 단계 A — 헬스봇을 노트북에 올리기 (이 레포)

08번 문서(Windows) 또는 07번 문서(라즈베리파이, 미사용 결정)를 따라간다.

**완료 판정 기준:** `python -m bot --once photo` 로 올린 글을 채널에서 눈으로 봤다.

이후 **GitHub Actions 워크플로는 비활성화한다** (레포 → Actions → "채널 발행" → Disable).
노트북과 Actions 가 동시에 돌면 같은 미션이 두 번 올라간다.

---

## 단계 B — 코치 연동에 필요한 헬스봇 인터페이스 (이번에 구현 완료)

`secretary1`의 `register-cron.ps1`과 `coach-persona.md`가 이 셋을 전제로 설계돼 있었는데,
처음 작성 시점에는 헬스봇에 실제로 없었다. **이번에 추가해서 인터페이스를 맞췄다.**

### `python -m bot --brief [--json]`

로컬 DB만 읽는다. 네트워크 호출 없음. `OWNER_USER_ID` 필수.

```json
{
  "date": "2026-07-30",
  "day_index": 30,
  "season_days": 84,
  "theme": "유산소",
  "streak": 3,
  "best_streak": 5,
  "week": 4,
  "total": 22,
  "condition_today": null,
  "weight_today": null,
  "flags": ["condition_stale", "no_media_source"],
  "published_today": ["mission", "photo"]
}
```

`flags` 계산 규칙 (전부 `bot/brief.py`):

| flag | 조건 |
|---|---|
| `streak_at_risk` | 정확히 어제 하루만 빠짐 (2일차 시즌부터) |
| `slipping` | 3일 이상 연속으로 안 함 |
| `on_fire` | 현재 연속 5일 이상 |
| `needs_rest` | 최근 3일 컨디션이 전부 2 이하로 기록됨 |
| `condition_stale` | 오늘 컨디션 기록 없음 |
| `weight_stale` | 마지막 체중 기록이 8일 이상 전 (또는 아예 없음) |
| `weight_stalled` | 최근 두 체중 기록 차이가 0.3kg 미만 |
| `done_today` | 오늘 이미 오운완 기록됨 |
| `no_media_source` | 사진·영상 소스가 하나도 없음 |
| `season_over` | 시즌 84일을 넘김 |

### `python -m bot --say "본문" --by 마키마`

**채널**에 발행한다. 본문 끝에 자동으로 `\n\n— {by}` 서명이 붙는다 (직접 쓰지 말 것).
줄바꿈은 실제 개행으로 넣는다 (`\n` 이라는 글자를 그대로 쓰면 안 된다 — 셸/JSON 이스케이프 주의).

### `python -m bot --notify "본문"` ← 이번에 새로 추가, `coach-persona.md`엔 없음

`OWNER_USER_ID`에게 **DM**으로 직접 보낸다. **아래 "열린 문제"에서 왜 이게 필요한지 설명한다.**

### `python -m bot --record KEY=VALUE`

```
python -m bot --record condition=3      # 1~5
python -m bot --record weight=62.4
python -m bot --record done=green       # green | yellow | red
```

범위를 벗어나면 종료 코드 1과 함께 에러를 표준에러로 출력한다.

---

## 컨디션 질문·응답 경로 — 해결됨 (②안 채택)

`jobs.md`의 원안(`coach:condition`)은 `--say`(채널 발행)로 컨디션을 묻고,
같은 cron 실행 안에서 `--record`로 저장하는 것처럼 설계돼 있었다. **이 흐름은 그대로 두면 동작하지 않는다.**

**이유 둘:**

1. 이 채널은 구독자가 운영자 혼자인 비공개 채널이고, **댓글 그룹이 없다.**
   텔레그램 채널은 방송 전용이라 구독자가 채널 글에 답장할 방법이 원천적으로 없다.
2. `--say`로 질문을 올린 cron 세션은 그 자리에서 끝난다(`--session isolated`).
   사람이 답하는 데 걸리는 시간(몇 분~몇 시간) 동안 세션이 기다려주지 않는다.

세 가지 대안 중 **"마키마(비서)는 절대 안 건드린다"는 원칙을 지키는 ②안으로 확정했다:**
자동으로 묻는 대신, 헬스봇에 `/condition` DM 명령을 추가해서 **운영자가 스스로 기록**한다.

```
/condition 3        (1~5, DM 에서 헬스봇에게)
```

`coach:condition` cron(19:00 자동 질문)은 **등록하지 않는다.** 나머지 3개
(`coach:morning`, `coach:night`, `coach:weekly`)만 등록한다 — `--brief`의 `condition_today`,
`needs_rest` 는 `/condition`으로 쌓인 값을 그대로 읽으므로 코치 판단에는 지장이 없다.
다만 운영자가 컨디션을 입력하지 않는 날은 `condition_stale`이 계속 뜬다 — 이건 못 물어서가
아니라 원래 입력을 안 했다는 뜻이므로 정상 동작이다.

`--notify`(DM 전용 발송)는 구현은 해뒀지만 ②안 채택으로 현재는 안 쓴다. 나중에 ①안으로
바꾸고 싶어지면(마키마가 먼저 물어보게 하고 싶다면) 이 명령을 그대로 재사용할 수 있다.

---

## 단계 C — GitHub Actions 끄고 코치 cron 등록

```powershell
# 헬스봇 폴더에서 먼저 인터페이스 점검
cd $HOME\helth_training
.venv\Scripts\python.exe -m bot --brief
# "flags:" 로 시작하는 줄이 보이면 정상

cd $HOME
git clone https://github.com/para333311/secretary1.git   # 또는 git pull
cd secretary1\openclaw
.\register-cron.ps1 -BotDir "$HOME\helth_training" -DryRun
.\register-cron.ps1 -BotDir "$HOME\helth_training"
```

`register-cron.ps1`은 등록 전에 자체적으로 `bot --brief`를 호출해서 인터페이스가 맞는지
확인한다. 실패하면 `.env`의 `TELEGRAM_BOT_TOKEN` / `OWNER_USER_ID`를 다시 확인하라고 안내한다.

**등록 직후 위 "열린 문제"의 컨디션 cron만 비활성화할 것:**

```powershell
openclaw cron list --all          # coach:condition 의 id 확인
openclaw cron disable <jobId>
```

나머지 3개(`coach:morning`, `coach:night`, `coach:weekly`)는 컨디션 데이터가 없어도
동작한다 (없으면 그냥 그 flag를 안 쓸 뿐).

---

## 단계 D — 검증

```powershell
openclaw cron list --all
openclaw cron run <coach:morning 의 id>
```

채널에 헬스봇 미션 밑에 마키마 서명(`— 마키마`)이 붙은 글이 하나 더 뜨면 성공이다.

**회귀 확인 — 비서 기능이 그대로인지:**
마키마와의 평소 DM 대화가 이전과 똑같이 동작하는지 확인한다. 코치 cron은
`--session isolated`라 DM 대화 맥락과 분리돼 있어야 하고, 섞이면 즉시 보고할 것.

---

## 킬 스위치

```powershell
cd secretary1\openclaw
.\register-cron.ps1 -Disable    # 코치 4개 전부 끄기 (비서는 영향 없음)
.\register-cron.ps1 -Remove     # 완전 삭제
```

---

## 아직 검증 못 한 것

- **OpenClaw CLI 실제 사양.** `cron add --session isolated --tools exec,read --no-deliver`,
  정시 잡 최대 5분 흩뿌림 등은 그록이 작성한 명세이고, 이 세션은 OpenClaw 문서에
  접근할 수 없어 검증하지 못했다. 노트북에서 `openclaw cron add --help`로 실제 플래그를
  먼저 확인하고, 다르면 `register-cron.ps1`을 그에 맞게 고쳐야 한다.
- **`--say`/`--notify`의 실제 텔레그램 발송.** 이 개발 환경은 `api.telegram.org`가
  프록시에 막혀 있어 코드 경로까지만 확인했다. 노트북에서의 첫 실행이 실제 검증이다.
