# 설정 가이드

봇 토큰, 배포 환경변수, 웹훅, BotFather 설정을 다룹니다.

---

## 설정 파일 위치

| 파일 | 용도 |
|------|------|
| `config/telegram_config.py` | 로컬 실행용 (예시: `telegram_config.example.py` 복사) |
| `.env` / `.env.local` | 로컬 PDF 봇·API 키 |
| Vercel/Render 환경변수 | 운영 배포 |

`config/telegram_config.py`는 `.gitignore`에 포함되어 Git에 올라가지 않습니다.

---

## 1. 텔레그램 봇 토큰

### BotFather에서 발급

1. 텔레그램에서 `@BotFather` 검색
2. `/newbot` → 봇 이름·사용자명 설정
3. 발급된 토큰 복사

### 방법 A: 환경변수 (권장)

**Windows PowerShell (현재 세션)**

```powershell
$env:TELEGRAM_BOT_TOKEN="your_token_here"
```

**Mac/Linux**

```bash
export TELEGRAM_BOT_TOKEN="your_token_here"
```

**`.env` 파일 (프로젝트 루트)**

```env
TELEGRAM_BOT_TOKEN=your_token_here
```

### 방법 B: 설정 파일에 직접 입력

```bash
# Windows
copy config\telegram_config.example.py config\telegram_config.py

# Mac/Linux
cp config/telegram_config.example.py config/telegram_config.py
```

```python
TELEGRAM_BOT_TOKEN = "실제_토큰_입력"
```

---

## 2. Vercel 환경변수

Vercel 대시보드 → **Settings** → **Environment Variables**

| Key | 필수 | 설명 |
|-----|------|------|
| `TELEGRAM_BOT_TOKEN` | ✅ | 메인 봇 토큰 |
| `ALLOWED_CHAT_IDS_BANKS` | 선택 | 금융사 산출 채널 ID (쉼표 구분) |
| `ALLOWED_CHAT_IDS_BANKS_2` | 선택 | 금융사 산출 2번 채널 |
| `ALLOWED_CHAT_IDS_LOAN` | 선택 | 대출상품 채널 |
| `ALLOWED_CHAT_IDS_PDF_ONLY` | 선택 | PDF 파싱만 수행하는 채널 |
| `JUSO_API_KEY` 또는 `JUSO_CONFM_KEY` | 선택 | 도로명주소 → 법정동코드 API |
| `REAL_ESTATE_API_KEY` | 선택 | 공공데이터 실거래가 API |
| `WEBHOOK_URL` | 선택 | 웹훅 URL (스크립트 대신 사용 시) |

채팅방 ID를 비우면 해당 분기 제한 없이 동작합니다.

---

## 3. 로컬 PDF 봇 (별도 토큰)

로컬 PDF 전용 봇은 `.env.local`에 별도 토큰을 둡니다.

```env
TELEGRAM_PDF_BOT_TOKEN=your_pdf_bot_token_here
```

설치·실행: [README_LOCAL_BOT.md](README_LOCAL_BOT.md)

---

## 4. 웹훅 설정 (Vercel 배포)

### 1단계: 배포

GitHub 연동 → Vercel 배포 → URL 확인 (예: `https://your-app.vercel.app`)

### 2단계: 웹훅 URL

```
https://your-app.vercel.app/api/webhook
```

### 3단계: 등록

**스크립트 (권장)**

```bash
python scripts/set_webhook.py https://your-app.vercel.app/api/webhook
```

**브라우저**

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://your-app.vercel.app/api/webhook
```

**curl**

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://your-app.vercel.app/api/webhook"
```

### 웹훅 확인·삭제

```bash
python scripts/set_webhook.py --check
python scripts/set_webhook.py --delete   # Polling 전환 시
```

Telegram API로 확인:

```
https://api.telegram.org/bot<TOKEN>/getWebhookInfo
```

---

## 5. BotFather 추가 설정 (권장)

### 명령어 목록

```
/setcommands
@your_bot_username
start - 봇 시작 및 도움말
help - 도움말
```

### 설명·약식 설명

```
/setdescription
@your_bot_username
여러 금융사의 담보대출 한도와 금리를 계산해드립니다.

/setabouttext
@your_bot_username
담보대출 계산기
```

---

## 6. 선택 API 키

### 도로명주소 API (JUSO)

동/읍/면이 없는 도로명 주소에서 KB 시세 조회 시 필요합니다.

- 신청: [juso.go.kr Open API](https://www.juso.go.kr/addrlink/openApi/apiReqst.do)
- 환경변수: `JUSO_API_KEY` 또는 `JUSO_CONFM_KEY`

### 공공데이터 실거래가

KB 일반가가 없을 때 보조 시세로 사용합니다.

- 설정: [docs/공공데이터_실거래가_설정_가이드.md](docs/공공데이터_실거래가_설정_가이드.md)
- 환경변수: `REAL_ESTATE_API_KEY`

### Render Playwright 스크래퍼

Render 웹훅에서 세대수·사용승인일 등 브라우저 스크래핑이 필요할 때:

- 환경변수: `PLAYWRIGHT_SCRAPER_URL` (별도 Render 서비스 URL)
- 설정: [render-playwright/README.md](render-playwright/README.md)

---

## 7. 설정 확인

### 로컬 Polling

```bash
python main.py
```

정상 시: `🤖 텔레그램 봇이 시작되었습니다...`

토큰 미설정 시: `⚠️ 텔레그램 봇 토큰을 설정해주세요!`

### Vercel

1. 환경변수 저장 후 재배포
2. 웹훅 등록
3. 테스트 채팅방에서 메시지 전송
4. Vercel **Logs** 탭에서 `api/webhook` 로그 확인

---

## 보안 주의사항

- 토큰·API 키를 공개 저장소에 커밋하지 마세요.
- 운영 환경에서는 환경변수 사용을 권장합니다.
- `config/telegram_config.py`, `.env`, `.env.local`은 Git 추적 대상이 아닙니다.
