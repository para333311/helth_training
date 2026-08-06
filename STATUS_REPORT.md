# 상태 점검 리포트 — 2026-08-06

목적: Telegram 자료드랍/미션 봇이 밤~아침 사이(22:00 checkin, 06:30 mission)에
계속 빠지는 문제의 원인을 확인하고, Render sleep/crash와 무관하게 예정된 잡이
실행되도록 구조를 바꾼 기록. 실제 토큰/채널 ID 값은 이 문서 어디에도 없다 —
아래 모든 예시는 값이 아니라 **환경변수 이름**이다.

---

## 1. 현황 파악

### 코드 구조

- 발행 로직: `bot/jobs.py` (`Publisher` — mission/checkin/quickfix/hyrox/photo 등
  잡마다 별도 메서드로 분리돼 있음, 이미 잘 나뉘어 있어서 그대로 씀)
- 스케줄러: `bot/scheduler.py` (`Scheduler.tick()` — due 판정 + 실행)
- 스케줄 등록: `bot/main.py` `build_scheduler()` — mission 06:30, quickfix
  12:30/15:00, hyrox/quiz 18:00, checkin 22:00, weekly 21:00(일), reset_day
  20:00(격주 일)
- 잡 실행 기록: `bot/store.py` `job_runs` 테이블(`job` PK, `last_run`) — SQLite
  또는 Cloudflare D1(`bot/d1.py`, REST API를 sqlite3 커넥션처럼 감싼 어댑터)
- **스케줄러가 시작되는 곳은 딱 두 곳뿐:**
  1. `python -m bot` 상시 실행 루프 (`bot/main.py` 맨 아래 `while True`) —
     Render Web Service가 이 모드로 떠 있음
  2. `python -m bot --tick` — 스케줄을 한 번 확인하고 즉시 종료. **이미
     `.github/workflows/publish.yml`에 30분 간격 GitHub Actions cron으로
     구현돼 있었는데, Render로 옮기면서 8/2에 수동으로 꺼져 있었다**
     (workflow state: `disabled_manually`).
- Render 설정 파일(`render.yaml` 등)은 레포에 없음 — Render 대시보드에서
  수동 설정된 상태(Web Service, `python -m bot`, PORT 기반 헬스체크).

### 헬스체크

`bot/main.py`의 `_start_health_server()`가 `PORT` 환경변수가 있을 때만 뜨는
최소 HTTP 서버를 띄운다. 기존엔 모든 경로에 200만 응답 — Render의
Health Check Path가 뭘 가리키든 일단 응답은 갔다.

---

## 2. 원인 가설 검증

### A. Render sleep / in-memory scheduler 문제 — **확인됨 (핵심 원인)**

스케줄러는 `python -m bot`이 살아있는 동안 메모리 안의 `while True` 루프로만
돈다. Render 인스턴스가 자거나 죽으면 이 루프 자체가 멈추고, **그 순간이
06:30이든 22:00이든 그냥 통째로 빠진다.** 외부에서 깨워주기 전까지는 아무도
대신 실행해주지 않는다 — 이게 설계상 유일한 실행 경로였다.

D1 `job_runs` 실측 (요청 시점 기준):

| 잡 | 마지막 성공 |
|---|---|
| photo | 8/5 18:09 |
| hyrox | 8/5 18:00 |
| quickfix | 8/5 12:30 |
| checkin | 8/3 22:00 (그 뒤 계속 빠짐) |
| mission | D1 도입(8/3) 이후 기록 자체가 없음 |

낮 12:30~18:00대는 성공하고 22:00/06:30만 계속 빠지는 패턴 — 이건 "이 봇이
매번 밤 사이 죽고, 낮에야(수동으로 대시보드를 열거나 뭔가 트리거될 때) 겨우
살아난다"는 뜻이다. 죽는 시각이 항상 22:00 이전, 살아나는 시각이 항상 06:30
이후라서 이 두 개만 매번 걸린다.

### B. health check 오해 — **맞음, 그대로 유지**

`/healthz`는 "프로세스가 응답하는지"만 본다. Render가 이걸로 자동 재시작은
해주지만(연속 실패 60초 이상 시), **재시작된 프로세스가 다시 살아 있는
동안에만 스케줄러가 돈다** — sleep 자체를 막는 것도, 늦게 도착한 잡을 대신
실행해주는 것도 아니다. 그래서 3번에서 외부 cron 트리거를 별도로 둔다.

### C. crash / OOM 가능성 — **정황 증거 있음, 확정은 못 함**

지난 점검(8/3)에서 Render 로그에 다음이 실제로 찍혀 있었다:

```
requests.exceptions.ReadTimeout: HTTPSConnectionPool(host='api.cloudflare.com',
port=443): Read timed out. (read timeout=20)
```

`scheduler.tick()`이 이 실패를 개별 잡 단위로 격리하지 못하고 있었다(이전
점검에서 이미 수정 — `bot/scheduler.py`의 각 잡을 개별 try/except로 감쌈,
d1.py 타임아웃을 20초→(5,10)초+재시도로 단축). 이걸로 D1 지연이 스케줄러
전체를 막는 경로는 막았지만, **Render 자체가 얼어붙거나 OOM으로 죽는 경우는
코드로 막을 수 있는 범위 밖이다.** 그래서 이번엔 "안에서 고치기"가 아니라
"밖에서 대신 실행해주는 경로 추가"로 접근한다.

### D. timezone 문제 — **없음, 확인 완료**

`bot/config.py`가 `ZoneInfo(os.environ.get("TZ", "Asia/Seoul"))`로 명시적
tzinfo 객체를 만들고, 모든 `datetime.now(cfg.tz)` 호출이 이걸 쓴다. OS의
`TZ` 환경변수를 완전히 비운 상태로 실측해도(GitHub Actions 러너 기본값인 UTC
시뮬레이션) `cfg.tz`는 여전히 정확히 `Asia/Seoul`로 해석됐다 — OS 로캘에
의존하지 않는 구조. `.github/workflows/publish.yml`의 cron(`0,30 * * * *`)은
GitHub 사양상 항상 UTC로 해석되는데, 서울이 UTC+9로 정시 오프셋이라 30분
단위 정렬이 깨지지 않는다. **버그 없음.**

---

## 3~4. 구조 수정 — 왜 HTTP 엔드포인트 대신 기존 `--tick`/GitHub Actions를 썼는가

원래 요청은 `POST /internal/cron/tick` 같은 인증된 HTTP 엔드포인트를 새로
만드는 것이었다. 하지만 이 레포를 까보니 **기능적으로 동일한 경로가 이미
구현되어 있었다** — `python -m bot --tick` (CLI, 인증 불필요 — 애초에 GitHub
Actions Secrets 안에서만 실행되므로 별도 bearer 토큰이 필요 없음)과
`.github/workflows/publish.yml`(30분 cron)이 그것이다. 이건 그냥 꺼져 있었을
뿐이다.

**"최소 변경으로 복구 우선"** 원칙에 따라, 새 HTTP 인증 엔드포인트를 얹는
대신 기존 경로를 고쳐서 쓰기로 했다. 이 방식이 오히려 요청보다 더 안전하다:
HTTP 엔드포인트 방식은 여전히 Render 프로세스가 요청을 받을 수 있어야
동작하는데, `--tick`은 GitHub Actions 러너 안에서 레포를 통째로 새로
체크아웃해서 돌기 때문에 **Render가 죽어 있어도 완전히 무관하게 동작한다.**
이게 진짜 "앱 내부 스케줄러만 믿지 않는 구조"다.

다만 기존 방식엔 없던 문제가 하나 생긴다: Render(상시)와 GitHub
Actions(30분 cron)를 **동시에** 켜두면 같은 잡을 둘 다 due로 보고 둘 다
발행할 수 있다. 이건 4번(중복 방지)에서 해결했다.

### 중복 발송 방지 — `claim_run()`

`bot/store.py`에 원자적 선점 메서드를 추가했다:

```sql
INSERT INTO job_runs (job, last_run) VALUES (?, ?)
ON CONFLICT(job) DO UPDATE SET last_run = excluded.last_run
WHERE job_runs.last_run < ?   -- now - 5분
```

SQLite/D1 양쪽 다 이 문장 전체가 원자적으로 실행된다. 이미 5분 이내에 다른
프로세스가 이 잡을 선점했으면 이 UPDATE는 조용히 아무 것도 안 바꾸고,
`rowcount == 0`으로 그걸 구분해서 "내가 안 이겼다"를 알 수 있다.

`bot/scheduler.py`의 `tick()`을 "실행 후 표시"에서 **"선점 성공해야만
실행"**으로 바꿨다 — 실행 전에 슬롯을 잠그므로 두 트리거가 몇 초~몇 분
간격으로 겹쳐 들어와도 실제 발행은 한 번만 나간다.

**검증:** 같은 SQLite 파일을 보는 두 개의 독립된 `Scheduler`/`Store` 인스턴스
(Render 프로세스 하나 + GitHub Actions 프로세스 하나를 흉내)가 15초 간격으로
`tick()`을 불러도 실제 잡 실행은 1회만 일어나는 것을 직접 실행해서 확인했다
(아래 검증 결과 참고).

---

## 5. mission/checkin 누락 복구 — catch-up window

`DailyJob.due()`가 이미 `GRACE` 기간 안에서 "예정 시각을 지났지만 아직 안
했으면 지금 실행"을 구현하고 있었다 (요청하신 "06:25~07:30이면 실행 가능"과
동일한 메커니즘). `JOB_GRACE_MINUTES` 기본값을 40→**60분**으로 늘려서
06:30/22:00 같은 정시 발행이 GitHub의 예약 지연이나 Render/Actions가 번갈아
도는 타이밍에도 안전하게 걸리도록 여유를 더 줬다. GRACE를 넘겨서 발견되면
그 슬롯은 늦게라도 보내지 않고 다음 정시까지 조용히 skip된다(기존 동작 그대로,
"의도치 않은 늦은 밤 발송 금지" 요구사항과 일치).

---

## 6. Telegram 전송 안정화

`bot/tg.py`의 `call()`은 이미 다음을 갖추고 있었다:
- `timeout=30`
- 429는 `retry_after` 존중, 네트워크 오류는 지수 백오프 재시도(최대 4회)
- 4xx(429 제외)는 재시도 없이 즉시 실패 처리(설정/권한 오류로 분류)

**이번에 고친 것 — 시크릿 마스킹 구멍:** 봇 토큰이 요청 URL 경로의 일부라서,
네트워크 예외(`requests.ConnectionError` 등)의 문자열 표현에 토큰이 포함된
URL이 그대로 들어있을 수 있었다. 이게 로그로 나가면 토큰이 노출된다.
`Telegram._redact()`를 추가해서 모든 예외 메시지에서 토큰을 `***`로 치환한
뒤에만 로그/예외 메시지로 내보내도록 고쳤다 (`call()`의 네트워크 오류
경로, `download_file_bytes()`의 파일 다운로드 실패 경로 둘 다).

`await` 관련 항목은 이 프로젝트가 동기(`requests` 기반) Python이라 해당 없음.

---

## 최종 결론

**확정 원인:** 스케줄러가 Render 프로세스 메모리 안에서만 돌아서, Render가
자거나 죽는 동안(주로 22:00 이후~06:30 이전)은 아무도 대신 실행해주지
않았다. 이미 만들어져 있던 GitHub Actions 백업 트리거가 Render 이전 과정에서
꺼진 채로 남아 있었던 게 직접 원인이다. D1 타임아웃(8/3 확인)은 증상을
악화시켰을 수 있는 정황 증거이나, 지난 점검에서 이미 방어 처리됨.
