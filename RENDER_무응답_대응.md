# Render 무응답 대응 가이드

Render에서 봇이 **가끔은 되다가 계속 응답이 없을 때** 확인할 항목과 대응 방법입니다.

---

## 원인 후보

### 1. 슬립(Spin-down)

Render 무료 플랜은 **약 15분 무활동** 후 프로세스를 종료합니다.

- 다음 **첫 요청**이 콜드 스타트(30초~1분)에 걸리면 Telegram 웹훅 타임아웃 → 사용자에게 회신 없음

### 2. 처리 중 예외

PDF 파싱, KB 시세, Telegram API 등에서 예외가 나면 로그에는 남지만 **사용자에게는 미회신**될 수 있습니다.

### 3. KB 스크래퍼 비활성

Render 웹훅 환경(`RENDER=true`)에서는 in-process Playwright를 쓰지 않습니다.

- `PLAYWRIGHT_SCRAPER_URL` 미설정 시: 세대수·사용승인일 등 **부가정보만 누락**, 본문 회신은 가능
- 스크래퍼 URL 설정: [render-playwright/README.md](render-playwright/README.md)

---

## 로그로 확인

Render 대시보드 → 서비스 → **Logs**

| 로그 패턴 | 의미 |
|-----------|------|
| `[WEBHOOK] Sending PDF result to user` | 전송 시도 |
| `PDF result sent successfully` | 정상 전송 |
| `Error in process() - reply NOT sent:` | 처리 중 예외 |
| `Thread error - reply NOT sent:` | 스레드 예외 |

traceback과 함께 `TELEGRAM_BOT_TOKEN`, `PLAYWRIGHT_SCRAPER_URL` 등 환경변수를 점검하세요.

---

## 권장 대응

### 슬립 방지 (가장 효과적)

[UptimeRobot](https://uptimerobot.com) 등에서 Render 서비스 URL을 **14분 간격**으로 GET 핑합니다.  
무활동 종료를 줄여 첫 요청 지연·타임아웃을 완화할 수 있습니다.

### Playwright 분리

세대수·사용승인일이 필요하면:

1. `render-playwright/` 서비스 별도 배포
2. 웹훅 서비스에 `PLAYWRIGHT_SCRAPER_URL` 설정

### 예외 처리

로그 traceback 기준으로:

- 토큰·네트워크·외부 API 오류 수정
- PDF 형식·KB 시세 실패 등 입력 데이터 문제 확인

---

## Vercel vs Render

| 항목 | Vercel | Render |
|------|--------|--------|
| Python Playwright | ❌ | 웹훅 프로세스에서 ❌ (분리 서비스 ✅) |
| Node Puppeteer | `api/kb-households.js` | 별도 구성 |
| 슬립 | Pro 플랜 외 주의 | 무료 15분 무활동 |

---

## 관련 문서

- [render-playwright/README.md](render-playwright/README.md)
- [KB_api/kbland_스크래핑_한계.md](KB_api/kbland_스크래핑_한계.md)
- [SETUP.md](SETUP.md)
