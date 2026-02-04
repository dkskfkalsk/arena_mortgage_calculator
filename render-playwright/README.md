# Render Playwright 스크래퍼

## Render Build Command (필수)

```
pip install -r requirements.txt && playwright install-deps && playwright install chromium
```

`playwright install-deps` 는 Chromium에 필요한 시스템 라이브러리를 설치합니다.

## Start Command

```
uvicorn main:app --host 0.0.0.0 --port $PORT
```
