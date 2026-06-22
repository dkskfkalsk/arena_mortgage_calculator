# Render Playwright 스크래퍼

Render에서 **별도 마이크로서비스**로 Playwright(Chromium)를 실행해, 웹훅 본 서비스에서 세대수·사용승인일·재건축 정보를 가져올 때 사용합니다.

---

## 역할

- kbland.kr 단지 페이지 등 **브라우저가 필요한** 정보 수집
- 메인 웹훅(`run_webhook_render.py`)은 `PLAYWRIGHT_SCRAPER_URL`로 이 서비스 호출
- `RENDER=true`인 웹훅 프로세스에서는 in-process Playwright 비활성

---

## Render 배포 설정

| 항목 | 값 |
|------|-----|
| **Root Directory** | `render-playwright` (또는 해당 폴더 기준 배포) |
| **Build Command** | `bash build.sh` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |

`build.sh`가 Chromium을 프로젝트 `browsers/` 폴더에 설치해 배포에 포함합니다.

---

## 웹훅 연동

메인 Render 웹훅 서비스 환경변수:

```env
PLAYWRIGHT_SCRAPER_URL=https://your-playwright-service.onrender.com
```

배포 URL 끝에 `/` 없이 설정합니다.

---

## API

FastAPI(`main.py`)로 스크래핑 엔드포인트를 제공합니다.  
웹훅 쪽 `KB_api/kb_complex_scraper.py`가 이 URL을 호출합니다.

---

## 트러블슈팅

| 증상 | 확인 |
|------|------|
| 세대수만 비어 있음 | `PLAYWRIGHT_SCRAPER_URL` 설정·스크래퍼 서비스 기동 여부 |
| 스크래퍼 콜드 스타트 | UptimeRobot 등으로 14분 간격 핑 ([RENDER_무응답_대응.md](../RENDER_무응답_대응.md)) |
| Chromium 빌드 실패 | Render 로그에서 `build.sh` 출력 확인 |

---

## 관련 문서

- [RENDER_무응답_대응.md](../RENDER_무응답_대응.md)
- [KB_api/kbland_스크래핑_한계.md](../KB_api/kbland_스크래핑_한계.md)
- [KB_api/README.md](../KB_api/README.md)
