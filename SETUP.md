# 설정 가이드

모든 환경변수와 설정값은 **`config/telegram_config.py`** 파일에서 관리합니다.

## 📍 설정 파일 위치

```
config/telegram_config.py
```

이 파일 하나에 모든 설정값을 관리합니다.

## 🔑 텔레그램 봇 API 토큰 설정

### 방법 1: 환경변수 사용 (권장)

#### 로컬 실행 시
```bash
# Windows (PowerShell)
$env:TELEGRAM_BOT_TOKEN="your_token_here"

# Windows (CMD)
set TELEGRAM_BOT_TOKEN=your_token_here

# Mac/Linux
export TELEGRAM_BOT_TOKEN="your_token_here"
```

또는 `.env` 파일 생성:
```env
TELEGRAM_BOT_TOKEN=your_token_here
```

#### Vercel 배포 시
1. Vercel 대시보드 접속: https://vercel.com
2. 프로젝트 선택
3. **Settings** 탭 클릭
4. **Environment Variables** 섹션으로 이동
5. **Add New** 버튼 클릭
6. 다음 정보 입력:
   - **Key**: `TELEGRAM_BOT_TOKEN`
   - **Value**: `@BotFather`에서 발급받은 토큰
   - **Environment**: Production, Preview, Development 모두 선택
7. **Save** 클릭

### 방법 2: 파일에 직접 입력

1. **예시 파일 복사** (처음 한 번만):
   ```bash
   # Windows
   copy config\telegram_config.example.py config\telegram_config.py
   
   # Mac/Linux
   cp config/telegram_config.example.py config/telegram_config.py
   ```

2. `config/telegram_config.py` 파일 열기

3. 토큰 입력:
   ```python
   TELEGRAM_BOT_TOKEN = "실제_토큰_입력"
   ```

⚠️ **중요**: 
- `config/telegram_config.py`는 `.gitignore`에 포함되어 있어 **GitHub에 올라가지 않습니다**
- 실제 토큰을 입력해도 안전하게 Git에 커밋되지 않습니다
- Vercel 배포 시에는 환경변수 사용을 권장합니다

## 🌐 텔레그램 웹훅 설정 (Vercel 배포 시 필수)

### 1단계: Vercel에 배포
1. GitHub에 프로젝트 업로드
2. Vercel에 프로젝트 연결
3. 배포 완료 후 URL 확인 (예: `https://your-app.vercel.app`)

### 2단계: 웹훅 URL 확인
배포 후 생성되는 웹훅 URL:
```
https://your-app.vercel.app/api/webhook
```

### 3단계: 텔레그램에 웹훅 등록

**방법 1: 스크립트 사용 (권장)**
```bash
python scripts/set_webhook.py https://your-app.vercel.app/api/webhook
```

**방법 2: 수동으로 등록**
1. 브라우저에서 다음 URL 접속 (YOUR_BOT_TOKEN과 YOUR_WEBHOOK_URL을 실제 값으로 변경):
```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=<YOUR_WEBHOOK_URL>
```

예시:
```
https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz/setWebhook?url=https://your-app.vercel.app/api/webhook
```

**방법 3: curl 명령어 사용**
```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://your-app.vercel.app/api/webhook"
```

### 웹훅 확인
```bash
# 현재 웹훅 정보 확인
python scripts/set_webhook.py --check

# 웹훅 삭제 (로컬 Polling으로 전환 시)
python scripts/set_webhook.py --delete
```

### 웹훅 설정 확인
웹훅이 제대로 설정되었는지 확인:
```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo
```

성공 시 응답:
```json
{
  "ok": true,
  "result": {
    "url": "https://your-app.vercel.app/api/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}
```

## 📝 토큰 발급 방법

1. 텔레그램에서 `@BotFather` 검색
2. `/newbot` 명령어 입력
3. 봇 이름과 사용자명 설정
4. 발급받은 토큰을 복사
5. 위의 방법 중 하나로 설정

## ✅ 설정 확인

### 로컬 실행 확인
```bash
python main.py
```

토큰이 제대로 설정되었으면:
```
🤖 텔레그램 봇이 시작되었습니다...
```

토큰이 없으면:
```
⚠️  텔레그램 봇 토큰을 설정해주세요!
config/telegram_config.py 파일을 열어서 TELEGRAM_BOT_TOKEN을 입력하세요.
```

### Vercel 배포 확인
1. Vercel에 배포
2. 환경변수가 제대로 설정되었는지 확인
3. Webhook URL을 텔레그램에 등록

## 🔒 보안 주의사항

- ⚠️ **절대** `config/telegram_config.py` 파일을 Git에 커밋하지 마세요
- ⚠️ 토큰을 공개 저장소에 올리지 마세요
- ✅ 환경변수 사용을 권장합니다
- ✅ `.gitignore`에 `config/telegram_config.py`가 포함되어 있습니다

