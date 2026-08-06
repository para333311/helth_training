# 09. Render 로 상시 실행 (노트북·VPS 없이)

07번(라즈베리파이), 08번(Windows 노트북) 대신, 이미 갖고 있는 하드웨어 없이
**Render 무료 플랜 + 외부 핑 서비스** 조합으로 24시간 실행하는 방법이다.
DM 명령(`/done`, `/streak`, 사진 제출)을 쓰려면 이 방식이든 07·08번이든
**뭔가는 24시간 켜져 있어야 한다.**

---

## 원리

Render 무료 **Web Service**는 인바운드 HTTP 요청이 15분 이상 없으면
슬립한다. 이 봇은 원래 텔레그램 서버에 계속 요청을 보내는(long polling)
프로그램이라 HTTP 요청을 받을 일이 없는데, 그러면 Render가 "죽은
서비스"로 보고 재워버린다.

그래서 `bot/main.py` 에 최소한의 헬스체크 엔드포인트를 추가했다
(`PORT` 환경변수가 있을 때만 켜짐 — Render 가 자동으로 이 값을 주므로
노트북·VPS 실행에는 영향이 없다). 외부에서 그 주소를 5~10분마다
두드려주면 슬립하지 않는다.

```
텔레그램 폴링 루프 (기존 로직, 변화 없음)
        +
헬스체크용 포트 하나 열어둠 (Render 가 "Web Service"로 인식하게)
        ↑
외부 무료 핑 서비스가 5~10분마다 그 주소를 요청 → 계속 깨어있음
```

---

## ⚠️ 진행 전에 반드시 알아야 할 것 — 데이터 유실 위험

**Render 무료 플랜은 영구 디스크를 지원하지 않는다.** 재배포하거나
컨테이너가 재시작되면(코드 푸시, 플랫폼 점검, 크래시 등) 파일시스템이
초기화된다. 이 봇은 스트릭·사진·컨디션 기록을 `data/helth.db`
(SQLite 파일)에 저장하므로, **재시작 한 번에 그 기록이 전부 날아갈 수
있다.** (증상: 제출한 사진이 순환 안 되고 계속 같은 것만 나오거나, 스트릭이
갑자기 1일로 리셋되는 식으로 나타난다.)

세 가지 중 하나를 고른다:

- **감수한다** — 개인 습관 기록이라 크게 아쉽지 않다면 그대로 진행해도
  된다. 04번 문서의 "리셋 데이" 철학대로, 기록이 끊겨도 채널 자체는
  계속된다.
- **Render 유료 Disk** — 유료 플랜(Starter, $7/월~)의 **Disk** 애드온을
  추가한다. 코드 변경 없이 바로 해결된다.
- **Cloudflare D1 (무료, 아래 방법)** — Render 무료 플랜을 유지하면서
  기록만 재시작에도 살아남는 원격 DB로 옮긴다. 07·08번 문서의 방식(진짜
  영구 디스크가 있는 내 하드웨어)도 대안이다.

### Cloudflare D1로 기록 지키기 (무료)

이 봇은 `CF_ACCOUNT_ID` / `CF_D1_DATABASE_ID` / `CF_API_TOKEN` 이 셋 다
설정돼 있으면 로컬 SQLite 대신 [Cloudflare D1](https://developers.cloudflare.com/d1/)
을 자동으로 쓴다 (`bot/d1.py`, `bot/store.py` 의 `Store(d1=...)`). D1은 REST API로
쓰는 원격 SQLite라 로컬 SQLite와 SQL이 거의 똑같이 호환되고, Render 컨테이너가
재시작돼도 데이터가 그대로 남는다. 셋 중 하나라도 비어 있으면 자동으로 기존
로컬 파일 방식으로 동작하므로, 라즈베리파이·Windows·로컬 개발 환경은 이 설정을
그냥 무시하면 된다.

1. Cloudflare 대시보드([dash.cloudflare.com](https://dash.cloudflare.com)) 로그인
   (계정이 없으면 무료 가입)
2. **Account ID** 복사 — 대시보드 아무 페이지나 오른쪽 사이드바 하단, 또는
   **Workers & Pages** 개요 페이지에 표시된다
3. D1 데이터베이스 준비 — **Workers & Pages → D1** 에서 **Create database**
   (이름은 자유, 예: `helth-training-db`). 생성 후 상세 페이지 URL이나
   목록에서 **Database ID** 를 복사한다
4. API 토큰 발급 — **오른쪽 위 프로필 아이콘 → My Profile → API Tokens →
   Create Token → Custom token** 으로 만들고, 권한은 **Account → D1 → Edit**
   하나만 준다 (그 이상 줄 필요 없음)
5. Render **Environment** 탭(또는 로컬 `.env`)에 세 값을 넣는다:
   ```
   CF_ACCOUNT_ID=<2번에서 복사한 값>
   CF_D1_DATABASE_ID=<3번에서 복사한 값>
   CF_API_TOKEN=<4번에서 발급한 토큰>
   ```
6. 재배포하면 `Store.__init__` 이 첫 실행 시 D1에 테이블을 자동으로 만든다
   (`python -m bot --check` 로 정상 연결 확인 가능)

> `content/photos/` 에 직접 넣는 로컬 이미지 파일은 D1과 무관하게 여전히
> Render 재시작마다 사라진다 (파일이지 DB 행이 아니라서). Render에서는
> DM으로 사진을 보내는 `/photos` 제출 방식(`submitted_photos` 테이블, D1로
> 보호됨)을 쓰는 걸 권장한다.

---

## GitHub Actions 와의 관계 — 이제는 **같이 켜두는 걸 권장한다**

예전엔 "Render 쓰면 Actions는 꺼라"고 안내했다. 이제는 반대다 — **Actions를
Render의 안전망으로 같이 켜두는 걸 권장한다.**

이유: Render 무료 플랜은 자거나 크래시되면 그 안의 스케줄러(메모리에서만
도는 `while True` 루프)도 같이 멈춘다. 그 순간이 06:30 미션이든 22:00
체크인이든 그냥 통째로 빠진다 — Health Check Path로 재시작은 되지만,
재시작되는 그 잠깐의 공백 자체는 막을 수 없다. `.github/workflows/publish.yml`
은 Render와 완전히 무관하게 30분마다 GitHub 자체 러너에서 새로 실행되므로,
Render가 죽어 있어도 예정된 잡을 대신 발행해준다.

**둘 다 켜둬도 중복 발행되지 않는다** — Render와 Actions가 CF_ACCOUNT_ID /
CF_D1_DATABASE_ID / CF_API_TOKEN 으로 **같은 D1**을 보게 설정하면(아래
"GitHub Actions Secrets 설정" 참고), 어느 쪽이 먼저 실행하든 D1에 "내가
방금 처리했다"를 원자적으로 남기고(`bot/store.py`의 `claim_run`), 뒤따라온
쪽은 조용히 스킵한다.

### GitHub Actions Secrets 설정

레포 → Settings → Secrets and variables → Actions → **New repository secret**
으로 아래 세 개를 Render에 넣은 값과 **똑같이** 추가한다:

| 이름 | 값 |
|---|---|
| `CF_ACCOUNT_ID` | Render 에 넣은 것과 동일 |
| `CF_D1_DATABASE_ID` | Render 에 넣은 것과 동일 |
| `CF_API_TOKEN` | Render 에 넣은 것과 동일 |

### 꺼져 있다면 다시 켜기

레포 → Actions 탭 → 왼쪽 "채널 발행" → 워크플로가 회색으로 비활성 표시면
우측 상단 **"..." → Enable workflow**.

DM 명령(`/done`, `/streak`, 사진 제출)은 여전히 Render(또는 07·08번 문서의
상시 실행)가 떠 있어야만 받을 수 있다 — Actions 는 발행만 대신해준다.

---

## 1. Render 계정 생성 + 레포 연결

1. https://render.com 가입 (GitHub 계정으로 로그인하면 편하다)
2. 대시보드 → **New +** → **Web Service**
3. 이 레포(`para333311/helth_training`)를 선택

## 2. 서비스 설정

| 항목 | 값 |
|---|---|
| Name | `helth-bot` (원하는 이름) |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt && mkdir -p .fonts && curl -sL -o .fonts/NanumGothic.ttf https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/NanumGothic-Regular.ttf` |
| Start Command | `python -m bot` |
| Instance Type | Free |

> Render 빌드 환경엔 `sudo`/`apt-get` 권한이 없다 (`dpkg lock ... are you
> root?` 로 실패한다). 그래서 패키지 설치 대신 한글 폰트 파일을 레포 안
> `.fonts/`로 직접 내려받는다. `bot/cards.py` 가 이 경로를 우선 확인하도록
> 되어 있다.

## 3. 환경변수 등록

**Environment** 탭에서 GitHub Actions Secrets 에 넣었던 값을 그대로 옮긴다.

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHANNEL_ID=@helth_training
TELEGRAM_BOT_USERNAME=helth_training_bot
OWNER_USER_ID=<내 텔레그램 user_id>
SOLO_MODE=true
SEASON_START=2026-07-30
PHOTO_INTERVAL_MINUTES=30
PHOTO_START_HOUR=6
PHOTO_END_HOUR=22
UNSPLASH_ACCESS_KEY=...
PEXELS_API_KEY=...
TZ=Asia/Seoul

# 기록을 재시작에도 지키고, GitHub Actions와 발행을 안전하게 나눠 갖고 싶으면
# (아래 "Cloudflare D1로 기록 지키기" 참고, 셋 다 있어야 적용된다)
CF_ACCOUNT_ID=...
CF_D1_DATABASE_ID=...
CF_API_TOKEN=...
```

`PORT` 는 Render 가 자동으로 넣어주므로 따로 등록할 필요 없다.

> **이 `data/helth.db` 는 GitHub Actions 에서 쌓인 기록과 별개로
> 새로 시작된다.** 위 데이터 유실 경고와 같은 이유다.

## 4. 배포 확인

**Logs** 탭에서 아래가 보이면 정상이다.

```
봇 @helth_training_bot 로 접속했습니다
발행 대상: 같이보는 오운완 (channel, id=-100...)
헬스체크 서버 시작 (포트 10000) — Web Service 슬립 방지용
시작합니다. Ctrl+C 로 종료.
```

서비스 상단에 뜨는 `https://helth-bot-xxxx.onrender.com` 주소를 하나
적어둔다. 브라우저로 열어서 `ok` 가 뜨면 헬스체크가 살아있는 것이다.

---

## 5. 슬립 방지 — 외부 핑 등록 (UptimeRobot, 무료)

1. https://uptimerobot.com 가입 (무료 플랜으로 충분)
2. **Add New Monitor**
   - Monitor Type: `HTTP(s)`
   - URL: 4번에서 확인한 Render 주소
   - Monitoring Interval: **5분**
3. 저장

이제 5분마다 UptimeRobot 이 그 주소를 요청하므로 15분 슬립 기준을
넘기지 않는다.

> cron-job.org 등 다른 무료 핑 서비스를 써도 동일하다. 중요한 건
> "15분보다 짧은 간격으로 계속 요청이 들어오는 것"뿐이다.

---

## 6. DM 기능 시험

텔레그램에서 `@helth_training_bot` 을 검색해 **1:1 대화**를 연다 (채널이 아니라 봇과의 대화창).

```
/start
/mission
/done
/streak
```

`/done` 에 "💪 오운완 기록됨" 과 연속 일수가 뜨면 정상이다. 사진을 그냥
보내면 "📷 사진 받았습니다" 응답이 오고, 시간당 자극 로테이션에
익명으로 섞여 들어간다.

---

## 업데이트하는 법

레포에 `git push` 하면 Render 가 자동으로 다시 빌드·배포한다
(Auto-Deploy 가 기본 켜져 있음). **이때도 디스크가 초기화된다** — 위의
데이터 유실 경고와 같은 이유다.

---

## 문제 해결

| 증상 | 확인 |
|---|---|
| 서비스가 자꾸 슬립함 | UptimeRobot 모니터 간격이 15분보다 짧은지, URL 이 정확한지 확인 |
| 명언 카드가 안 나옴 | Build Command 의 `curl` 로그가 `HTTP 200`인지, Build Command 를 통째로 정확히 붙여넣었는지 확인 |
| 빌드 로그에 `dpkg lock ... are you root?` | `apt-get`을 쓰던 옛 Build Command다. 위 2번 표의 `curl` 버전으로 교체 |
| 배포할 때마다 스트릭이 리셋됨 | 무료 플랜의 알려진 한계 (위 경고 참고). Disk 애드온 또는 07·08번 문서 방식 고려 |
| DM 명령이 안 먹음 | Actions 워크플로가 아직 켜져 있어 두 프로세스가 충돌하는지 확인 → Actions 비활성화 |
