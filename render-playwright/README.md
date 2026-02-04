# Render Playwright 스크래퍼

## Render 설정

- **Build Command**: `bash build.sh`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

build.sh가 Chromium을 프로젝트 내 `browsers/` 폴더에 설치해 배포에 포함시킵니다.
