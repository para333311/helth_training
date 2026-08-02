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
있다.**

- 감수할 만하면(개인 습관 기록이라 크게 아쉽지 않다면) 그대로 진행해도
  된다 — 04번 문서의 "리셋 데이" 철학대로, 기록이 끊겨도 채널 자체는
  계속된다.
- 기록을 지키고 싶으면 Render 유료 플랜(Starter, $7/월~)의 **Disk**
  애드온을 추가하거나, 07·08번 문서의 방식(진짜 영구 디스크)을 쓰는 걸
  권장한다.

---

## GitHub Actions 와의 관계

Render 를 쓰기로 하면 **Actions 워크플로("채널 발행")는 꺼야 한다.**
둘 다 발행하면 같은 시간에 미션이 두 번 올라간다.

레포 → Actions 탭 → 왼쪽 "채널 발행" → 우측 상단 **"..." → Disable workflow**

Render 쪽이 실제로 발행하는 걸 로그로 확인한 뒤에 끄는 걸 권장한다
(발행 주체가 0개가 되는 공백을 피하려면).

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
OWNER_USER_ID=1423971696
SOLO_MODE=true
SEASON_START=2026-07-30
PHOTO_INTERVAL_MINUTES=30
PHOTO_START_HOUR=7
PHOTO_END_HOUR=22
UNSPLASH_ACCESS_KEY=...
PEXELS_API_KEY=...
TZ=Asia/Seoul
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
