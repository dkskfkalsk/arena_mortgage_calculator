# Vercel Python Webhook 설정 가이드 (2025 최신 버전)

## 📋 목차
1. [프로젝트 구조](#1-프로젝트-구조)
2. [Python 서버리스 함수 작성](#2-python-서버리스-함수-작성)
3. [Vercel 설정](#3-vercel-설정)
4. [의존성 관리](#4-의존성-관리)
5. [배포 및 테스트](#5-배포-및-테스트)
6. [텔레그램 Webhook 설정](#6-텔레그램-webhook-설정)
7. [문제 해결](#7-문제-해결)

---

## 1. 프로젝트 구조

### 1.1 필수 디렉토리 구조
```
프로젝트 루트/
├── api/
│   └── webhook.py          # 서버리스 함수 파일
├── requirements.txt        # Python 의존성
├── vercel.json            # Vercel 설정 (선택사항)
└── .gitignore
```

### 1.2 중요 사항
- ✅ `api/` 폴더는 **프로젝트 루트**에 있어야 함
- ✅ Python 파일은 `api/` 폴더 안에 위치
- ✅ 파일명이 URL 경로가 됨 (`api/webhook.py` → `/api/webhook`)

---

## 2. Python 서버리스 함수 작성

### 2.1 기본 구조 (BaseHTTPRequestHandler 사용)

```python
# api/webhook.py
from http.server import BaseHTTPRequestHandler
import json

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """GET 요청 처리 (헬스체크)"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {"ok": True, "message": "Webhook endpoint is active"}
        self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def do_POST(self):
        """POST 요청 처리 (실제 webhook)"""
        try:
            # 요청 본문 읽기
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Empty body')
                return
            
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # 여기서 webhook 데이터 처리
            print(f"Received webhook: {data}")
            
            # 응답 전송
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {"ok": True, "message": "Webhook received"}
            self.wfile.write(json.dumps(response).encode('utf-8'))
            
        except Exception as e:
            print(f"Error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
```

### 2.2 텔레그램 봇용 예제 (현재 프로젝트 구조)

```python
# api/webhook.py
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import logging

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """헬스체크"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode('utf-8'))
    
    def do_POST(self):
        """텔레그램 webhook 처리"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # 텔레그램 update 처리
            if 'update_id' in data:
                logger.info(f"Received update: {data['update_id']}")
                # 여기서 텔레그램 봇 로직 처리
                
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode('utf-8'))
            
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
```

### 2.3 핵심 포인트
- ✅ 클래스명은 반드시 `handler` (소문자)
- ✅ `BaseHTTPRequestHandler` 상속 필수
- ✅ `do_GET()`, `do_POST()` 메서드로 HTTP 메서드 처리
- ✅ 응답은 `self.wfile.write()`로 전송
- ✅ 인코딩: 문자열은 `.encode('utf-8')` 필수

---

## 3. Vercel 설정

### 3.1 vercel.json (선택사항 - 2024년 기준)

**최신 버전에서는 vercel.json 없이도 자동 감지됩니다!**

```json
{
  "version": 2
}
```

**주의:** Python 런타임을 명시적으로 지정할 필요 없음 (자동 감지)

### 3.2 vercel.json이 필요한 경우

만약 특정 설정이 필요하다면:

```json
{
  "version": 2,
  "functions": {
    "api/webhook.py": {
      "maxDuration": 30,
      "memory": 1024
    }
  }
}
```

**설정 옵션:**
- `maxDuration`: 최대 실행 시간 (초 단위, 기본값: 10초, 최대: 300초)
- `memory`: 메모리 할당량 (MB 단위, 기본값: 1024MB)

### 3.3 2025년 신규 기능: In-Function Concurrency

**Pro/Enterprise 플랜에서 사용 가능:**
- 단일 함수 인스턴스가 여러 요청을 동시에 처리
- 외부 API 호출이나 데이터베이스 쿼리 시 유용
- 리소스 효율성 향상 및 비용 절감

**활성화 방법:**
- Vercel 대시보드 → 프로젝트 → Settings → Functions
- "In-Function Concurrency" 옵션 활성화

---

## 4. 의존성 관리

### 4.1 requirements.txt 작성 (권장)

프로젝트 루트에 `requirements.txt` 파일 생성:

```
python-telegram-bot==20.7
requests==2.31.0
```

### 4.2 pyproject.toml 지원 (2025년 신규)

Python 3.12와 함께 `pyproject.toml`도 지원됩니다:

```toml
[tool.poetry.dependencies]
python = "^3.12"
python-telegram-bot = "^20.7"
requests = "^2.31.0"
```

### 4.3 Python 버전 (2025년 기준)

- ✅ **Python 3.12** 고정 (변경 불가)
- ✅ Vercel이 자동으로 Python 3.12 사용
- ✅ `requirements.txt` 또는 `pyproject.toml` 사용 가능

### 4.4 중요 사항
- ✅ 파일은 프로젝트 **루트**에 위치
- ✅ Vercel이 자동으로 설치 및 캐싱
- ✅ 버전 명시 권장 (호환성 보장)
- ✅ 의존성은 자동으로 캐시되어 빌드 시간 단축

---

## 5. 배포 및 테스트

### 5.1 Vercel CLI로 배포

```bash
# 1. Vercel CLI 설치 (전역)
npm install -g vercel

# 2. 프로젝트 디렉토리에서 로그인
vercel login

# 3. 배포
vercel

# 4. 프로덕션 배포
vercel --prod
```

### 5.2 GitHub 연동 배포 (권장)

1. **GitHub 저장소에 코드 푸시**
   ```bash
   git add .
   git commit -m "Add webhook endpoint"
   git push origin main
   ```

2. **Vercel 대시보드에서 연동**
   - Vercel 대시보드 → **Add New Project**
   - GitHub 저장소 선택
   - 자동 배포 설정

3. **자동 배포 확인**
   - `git push` 할 때마다 자동 배포
   - Vercel 대시보드에서 배포 상태 확인

### 5.3 배포 후 URL 확인

배포 완료 후:
- **개발 환경**: `https://your-project.vercel.app/api/webhook`
- **프로덕션**: `https://your-project.vercel.app/api/webhook`

### 5.4 테스트

#### GET 요청 테스트 (헬스체크)
```bash
curl https://your-project.vercel.app/api/webhook
```

**예상 응답:**
```json
{"ok": true, "message": "Webhook endpoint is active"}
```

#### POST 요청 테스트
```bash
curl -X POST https://your-project.vercel.app/api/webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

---

## 6. 텔레그램 Webhook 설정

### 6.1 환경 변수 설정

**Vercel 대시보드에서:**
1. 프로젝트 → **Settings** → **Environment Variables**
2. 다음 변수 추가:
   - `TELEGRAM_BOT_TOKEN`: 봇 토큰
   - `ALLOWED_CHAT_IDS`: 허용된 채팅방 ID (선택사항)

### 6.2 Webhook URL 등록

#### 방법 1: 스크립트 사용 (권장)

```bash
# 로컬에서 실행
python scripts/set_webhook.py https://your-project.vercel.app/api/webhook
```

#### 방법 2: 텔레그램 API 직접 호출

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-project.vercel.app/api/webhook"}'
```

#### 방법 3: Python 코드로 설정

```python
from telegram import Bot

bot = Bot(token="YOUR_BOT_TOKEN")
result = bot.set_webhook(url="https://your-project.vercel.app/api/webhook")
print(result)  # True면 성공
```

### 6.3 Webhook 확인

```bash
# 스크립트 사용
python scripts/set_webhook.py --check

# 또는 API 직접 호출
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

---

## 7. 문제 해결

### 7.1 함수가 404 에러를 반환하는 경우

**원인:**
- 파일 위치가 잘못됨
- 파일명 오타
- `handler` 클래스명 오타

**해결:**
- ✅ `api/webhook.py` 경로 확인
- ✅ 클래스명이 정확히 `handler`인지 확인
- ✅ `BaseHTTPRequestHandler` 상속 확인

### 7.2 로그가 안 보이는 경우

**확인 사항:**
1. Vercel 대시보드 → **Functions** → `api/webhook.py` → **Logs**
2. 또는 상단 **Logs** 메뉴 → **Runtime Logs**
3. 시간 필터 확인 (Last 24 hours)
4. 로그 레벨 필터 확인

**로깅 코드:**
```python
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

# 사용
logger.info("This will appear in Vercel logs")
```

### 7.3 의존성 설치 실패

**원인:**
- `requirements.txt` 파일 위치 오류
- 호환되지 않는 패키지 버전

**해결:**
- ✅ `requirements.txt`가 프로젝트 루트에 있는지 확인
- ✅ 패키지 버전 명시
- ✅ Vercel 배포 로그에서 에러 확인

### 7.4 타임아웃 에러

**원인:**
- 함수 실행 시간이 10초 초과 (기본값)

**해결:**
```json
// vercel.json
{
  "functions": {
    "api/webhook.py": {
      "maxDuration": 30
    }
  }
}
```

### 7.6 함수 크기 제한 (250MB)

**원인:**
- 압축 해제 후 함수 크기가 250MB 초과

**해결 방법:**
1. **큰 라이브러리 제거 또는 교체**
   - 불필요한 패키지 제거
   - 경량 대체 라이브러리 사용

2. **파일 제외 설정**
   ```json
   // vercel.json
   {
     "functions": {
       "api/webhook.py": {
         "excludeFiles": "tests/**"
       }
     }
   }
   ```

3. **애플리케이션 분할**
   - 큰 기능을 여러 API 라우트로 분리
   - 공통 코드는 별도 모듈로 분리

### 7.5 환경 변수가 로드되지 않는 경우

**확인:**
1. Vercel 대시보드 → **Settings** → **Environment Variables**
2. 환경 변수가 올바른 환경에 설정되어 있는지 확인
3. 환경 변수 추가/수정 후 **재배포** 필요

**코드에서 확인:**
```python
import os

token = os.getenv("TELEGRAM_BOT_TOKEN")
if not token:
    print("ERROR: TELEGRAM_BOT_TOKEN not found")
```

---

## 8. 최신 베스트 프랙티스 (2025)

### 8.1 로깅
- ✅ `logging` 모듈 사용 (print 대신)
- ✅ `sys.stderr`로 출력
- ✅ 적절한 로그 레벨 사용 (INFO, WARNING, ERROR)
- ✅ 로그 메시지는 간결하게 (Vercel이 긴 메시지를 자를 수 있음)

### 8.2 에러 처리
- ✅ try-except로 모든 예외 처리
- ✅ 적절한 HTTP 상태 코드 반환
- ✅ 에러 로그 기록
- ✅ URL 디코딩 직접 처리 (Vercel이 자동 디코딩하지 않음)

### 8.3 성능
- ✅ 전역 변수로 싱글톤 패턴 사용 (애플리케이션 인스턴스 등)
- ✅ 불필요한 초기화 반복 방지
- ✅ 적절한 타임아웃 설정
- ✅ In-Function Concurrency 활용 (Pro/Enterprise 플랜)

### 8.4 보안
- ✅ 환경 변수로 민감한 정보 관리
- ✅ Webhook 서명 검증 (선택사항)
- ✅ 허용된 채팅방 ID 필터링

### 8.5 의존성 관리 (2025)
- ✅ `requirements.txt` 또는 `pyproject.toml` 사용
- ✅ 패키지 버전 명시 (정확한 버전 권장)
- ✅ Vercel의 자동 캐싱 활용
- ✅ 불필요한 패키지 제거 (250MB 제한 고려)

### 8.6 로컬 개발 (2025)
- ✅ `vercel dev` 사용 시 일부 기능 제한 가능
- ✅ 프로덕션 환경과 다를 수 있으므로 주의
- ✅ 가능하면 프로덕션 환경에서도 테스트

---

## 9. 체크리스트

배포 전 확인:

- [ ] `api/webhook.py` 파일이 올바른 위치에 있음
- [ ] `handler` 클래스가 `BaseHTTPRequestHandler` 상속
- [ ] `requirements.txt`에 필요한 패키지 명시
- [ ] 환경 변수가 Vercel에 설정됨
- [ ] `vercel.json`이 올바른 형식 (선택사항)
- [ ] 로컬에서 테스트 완료
- [ ] 배포 후 GET 요청 테스트 성공
- [ ] 텔레그램 Webhook URL 등록 완료
- [ ] 실제 메시지로 테스트 완료

---

## 10. 참고 자료

- [Vercel Python Functions 공식 문서](https://vercel.com/docs/functions/runtimes/python)
- [Vercel Serverless Functions 가이드](https://vercel.com/docs/functions)
- [Python-telegram-bot 문서](https://python-telegram-bot.org/)

---

## 📝 요약 (2025년 기준)

1. **파일 위치**: `api/webhook.py` (프로젝트 루트의 `api/` 폴더)
2. **클래스명**: `handler` (소문자, 필수)
3. **상속**: `BaseHTTPRequestHandler`
4. **Python 버전**: 3.12 (고정, 변경 불가)
5. **의존성**: `requirements.txt` 또는 `pyproject.toml` (프로젝트 루트)
6. **설정**: `vercel.json` (선택사항, 자동 감지)
7. **배포**: GitHub 연동 또는 `vercel` CLI
8. **로깅**: `logging` 모듈 + `sys.stderr`
9. **환경 변수**: Vercel 대시보드에서 설정 후 재배포
10. **제한사항**: 함수 크기 250MB, 기본 타임아웃 10초

### 2025년 주요 변경사항
- ✅ Python 3.12 지원
- ✅ `pyproject.toml` 지원 추가
- ✅ In-Function Concurrency (Pro/Enterprise)
- ✅ Streaming responses 지원
- ✅ 의존성 자동 캐싱

이 가이드를 따라하면 Vercel에서 Python webhook을 성공적으로 설정할 수 있습니다!
