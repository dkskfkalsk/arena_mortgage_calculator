# 로컬 PDF 분석 봇

등기부 PDF를 **로컬 PC**에서 빠르게 처리하는 텔레그램 Polling 봇입니다.  
Vercel 웹훅과 **독립**으로 동작하며, Playwright로 KB 시세·세대수 조회가 가능합니다.

---

## 특징

| 항목 | 설명 |
|------|------|
| 속도 | 로컬 Playwright 기준 약 2~3초 |
| 안정성 | ngrok·외부 스크래퍼 불필요 |
| 실행 | 배치 파일 더블클릭으로 시작 |
| 분리 | 운영 웹훅 봇과 토큰·프로세스 분리 |

---

## 최초 설치 (1회)

### 1. Python 확인

```bash
python --version
```

Python **3.9 이상** 필요. 미설치 시 [python.org](https://www.python.org/downloads/)에서 설치하고 **Add Python to PATH** 체크.

### 2. 패키지 설치

```bash
python -m pip install python-dotenv python-telegram-bot playwright
python -m playwright install chromium
```

또는 `install_bot_packages.bat` 실행 후 Playwright만 추가 설치.

### 3. 토큰 설정

프로젝트 루트에 `.env.local` 생성:

```env
TELEGRAM_PDF_BOT_TOKEN=BotFather에서_발급한_토큰
```

⚠️ 토큰을 문서·Git에 올리지 마세요.

---

## 매일 실행

### 방법 1: 배치 파일 (권장)

```
start_pdf_bot.bat 더블클릭
```

### 방법 2: 터미널

```bash
cd 프로젝트_루트
python local_pdf_bot.py
```

콘솔에 봇 시작 메시지가 보이면 텔레그램에서 PDF를 보낼 수 있습니다.

종료: `Ctrl+C` 또는 콘솔 창 닫기.

---

## 사용 방법

1. 봇 실행 (`start_pdf_bot.bat`)
2. 텔레그램에서 PDF 봇과 1:1 또는 그룹 채팅
3. 등기부 PDF 파일 전송
4. 자동 처리 후 결과 수신

### 처리 내용

- PDF 파싱 (주소, 면적, 근저당 등)
- KB 시세 조회 (로컬 Playwright)
- 세대수·동수
- 사용승인일·재건축 정보
- 주상복합 구분

---

## 주의사항

- **PC가 켜져 있고 봇이 실행 중**이어야 PDF 처리 가능
- Vercel/Render 웹훅 봇은 별도로 동작 — 이 봇을 끄면 웹훅 채널에는 영향 없음
- PDF 봇 전용 토큰(`TELEGRAM_PDF_BOT_TOKEN`) 사용 — 메인 봇과 분리

---

## 트러블슈팅

| 증상 | 해결 |
|------|------|
| `pip is not recognized` | `python -m pip install ...` 사용 |
| `python is not recognized` | Python 재설치 + PATH, PC 재시작 |
| `ModuleNotFoundError: dotenv` | `python -m pip install python-dotenv python-telegram-bot` |
| 봇 무응답 | 콘솔 오류 확인, 인터넷·토큰 확인, 재시작 |
| PDF 실패 | 등기부 PDF 여부·파일 크기 확인, `pdf_bot.log` 확인 |

### 로그

문제 발생 시 프로젝트 루트 `pdf_bot.log` 확인.

---

## Windows 시작 프로그램 등록 (선택)

1. `Win + R` → `shell:startup`
2. `start_pdf_bot.bat` 바로가기 복사
3. 로그인 시 자동 실행

---

## 관련 문서

- [SETUP.md](SETUP.md) — 환경변수·토큰 관리
- [KB_api/README.md](KB_api/README.md) — KB 시세·스크래핑
- [README.md](README.md) — 전체 프로젝트 개요
