# Render Playwright 스크래퍼 API

kbland.kr/c/{complex_id} 에서 사용승인일·재건축·세대수 추출

## Render 설정

- **Root Directory**: `render-playwright`
- **Build Command**: `pip install -r requirements.txt && playwright install chromium`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **환경변수**: `PLAYWRIGHT_SCRAPER_TOKEN` (Vercel 호출 시 인증용, 선택)

## API

- `GET /scrape?complex_id=4024`  
  - Header: `X-Internal-Token: <PLAYWRIGHT_SCRAPER_TOKEN>` (토큰 설정 시)
