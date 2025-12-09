# 담보대출 계산기

텔레그램 봇을 통한 주택담보대출 한도 및 금리 계산 시스템

## 프로젝트 구조

```
mortgage_calculator/
├── main.py                 # 텔레그램 봇 메인 진입점
├── config/
│   └── telegram_config.py  # 텔레그램 봇 설정
├── parsers/
│   └── message_parser.py   # 텔레그램 메시지 파싱
├── calculator/
│   └── base_calculator.py  # 금융사 계산기 (개별 계산 + 모든 금융사 계산 관리)
├── data/
│   └── banks/
│       └── bnk_config.json  # BNK 조건 설정 (급지, 금리, 조건 등 모든 정보 포함)
├── utils/
│   ├── formatter.py        # 결과 포맷팅
│   └── validators.py       # 데이터 검증
└── requirements.txt
```

## 설치 및 실행

```bash
pip install -r requirements.txt
python main.py
```

## 설정

### 📍 모든 설정은 `config/telegram_config.py` 파일에서 관리합니다

**상세 설정 가이드는 [`SETUP.md`](SETUP.md)를 참고하세요.**

### 빠른 설정

1. **텔레그램 봇 토큰 설정**
   - 예시 파일 복사:
     ```bash
     cp config/telegram_config.example.py config/telegram_config.py
     ```
   - `config/telegram_config.py` 파일 열기
   - `TELEGRAM_BOT_TOKEN`에 `@BotFather`에서 발급받은 토큰 입력
   - 또는 환경변수 `TELEGRAM_BOT_TOKEN` 설정
   
   ⚠️ **중요**: `config/telegram_config.py`는 `.gitignore`에 포함되어 있어 GitHub에 올라가지 않습니다.

2. **Vercel 배포 및 웹훅 설정**
   - Vercel에 배포 후 생성된 URL 확인
   - 텔레그램에 웹훅 등록:
     ```bash
     python scripts/set_webhook.py https://your-app.vercel.app/api/webhook
     ```
   - 상세 방법은 [`SETUP.md`](SETUP.md) 참고

### 금융사 설정 (선택사항)
- `data/banks/bnk_config.json`에서 금융사별 조건을 수정할 수 있습니다.
- 새 금융사를 추가하려면 `data/banks/새금융사_config.json` 파일을 추가하세요.

## 주요 기능

- ✅ 구/시/군 단위 행정구역 인식 (전국 모든 행정구역 지원)
- ✅ 금융사별 구/시/군 단위 급지 설정 가능
- ✅ JSON 파일만으로 금융사 추가/수정 가능
- ✅ 신용점수 없을 때 금리 범위 표시
- ✅ 대환/후순위 구분 계산

