# 로컬 PDF 분석 봇 사용 가이드

## 개요

등기부등본 PDF를 로컬 컴퓨터에서 빠르게 처리하는 텔레그램 봇입니다.

**장점:**
- ✅ 매우 빠른 스크래핑 (2-3초)
- ✅ 로컬에서 실행되어 안정적
- ✅ ngrok 불필요
- ✅ 간단한 실행 (더블클릭)

---

## 🔧 최초 설치 (한 번만)

### 1단계: Python 설치 확인

**Python이 설치되어 있는지 확인:**

```bash
python --version
```

- Python 3.9 이상이 표시되면 OK
- 오류가 나면 Python 설치 필요

**Python 설치 (필요한 경우):**

1. https://www.python.org/downloads/ 접속
2. "Download Python 3.12" 클릭
3. 설치 시 **"Add Python to PATH" 체크 필수!** ⚠️
4. 설치 완료 후 컴퓨터 재시작

### 2단계: 필요한 패키지 설치

**방법 A: 명령 프롬프트 (추천)**

```bash
python -m pip install python-dotenv python-telegram-bot
```

**방법 B: 배치 파일**

```
install_bot_packages.bat 더블클릭
```

### 3단계: Playwright 브라우저 설치

```bash
python -m playwright install chromium
```

**설치 완료!** 이제 매일 아침 `start_pdf_bot.bat`만 실행하면 됩니다.

---

## 매일 아침 실행 방법

### 방법 1: 배치 파일 더블클릭 (추천) ⭐

```
start_pdf_bot.bat 더블클릭
```

끝! 봇이 실행됩니다.

### 방법 2: 명령 프롬프트

```bash
cd c:\Users\박성호\Desktop\아레나홀딩스\01_프로젝트\2512_mortgage_calculator
python local_pdf_bot.py
```

---

## 사용 방법

1. **봇 시작**
   - `start_pdf_bot.bat` 더블클릭
   - 콘솔 창이 열리면서 "봇이 실행되었습니다!" 메시지 표시

2. **텔레그램에서 PDF 전송**
   - 새 봇과 1:1 채팅 또는 그룹 채팅
   - 등기부등본 PDF 파일 전송

3. **자동 처리**
   - 봇이 자동으로 PDF 분석
   - KB 시세 조회 (로컬 Playwright - 빠름!)
   - 결과 회신

4. **봇 종료**
   - 콘솔 창에서 `Ctrl+C`
   - 또는 콘솔 창 닫기

---

## 봇 정보

**봇 토큰:** `7829144358:AAF0zZy-cEM0bYZX03X9-oigqWB3DTEoBO4`

**처리 기능:**
- PDF 파싱
- KB 시세 자동 조회
- 세대수, 동수 추출
- 사용승인일 추출
- 재건축 정보 추출
- 주상복합 자동 구분

---

## 주의사항

⚠️ **컴퓨터를 켜두어야 합니다**
- 봇이 실행 중이어야 PDF 처리 가능
- 컴퓨터 꺼지면 봇 중단

⚠️ **다른 채팅방은 영향 없음**
- 기존 Vercel webhook 봇은 계속 동작
- 대부중개, 대출 계산 채팅방은 정상 작동

---

## 트러블슈팅

### "pip is not recognized" 오류

```bash
# pip 대신 이렇게:
python -m pip install python-dotenv python-telegram-bot
```

### "python is not recognized" 오류

Python이 PATH에 없습니다:
1. Python 재설치 ("Add Python to PATH" 체크)
2. 또는 컴퓨터 재시작

### "ModuleNotFoundError: No module named 'dotenv'" 오류

패키지 설치 필요:

```bash
python -m pip install python-dotenv python-telegram-bot
python -m playwright install chromium
```

### 봇이 응답하지 않음

1. 콘솔 창 확인 - 오류 메시지 확인
2. 인터넷 연결 확인
3. 봇 재시작

### PDF 처리 실패

1. PDF 파일이 등기부등본인지 확인
2. PDF 파일 크기 확인 (너무 크지 않은지)
3. 콘솔 로그 확인

### 로그 파일

문제 발생 시 `pdf_bot.log` 파일 확인

---

## 자동 시작 (선택사항)

**Windows 시작 프로그램 등록:**

1. `Win + R` → `shell:startup`
2. `start_pdf_bot.bat` 바로가기 복사
3. 컴퓨터 재시작 시 자동 실행

---

## 연락처

문제 발생 시 개발자에게 문의하세요.
