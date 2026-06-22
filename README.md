# 담보대출 계산기

텔레그램 봇으로 담보물건 정보를 입력받아, 여러 금융사의 **주택담보대출 한도·금리**를 자동 산출하는 시스템입니다.

등기부 PDF 파싱, KB 시세 조회, 공공데이터 실거래가 보조, 세대수·사용승인일 스크래핑까지 한 흐름으로 처리할 수 있습니다.

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 다중 금융사 산출 | JSON 조견만 추가·수정하면 금융사별 한도/금리 계산 |
| 메시지 파싱 | 담보물건 양식, 근저당 설정, 요청사항(대환·부족자금 등) 자동 해석 |
| 대환/후순위 | 순위·기관명·범위(1–3순위) 기반 대환 조건 반영 |
| KB 시세 | 주소·면적 기반 KB 부동산 시세 자동 조회 |
| PDF 처리 | 등기부 PDF 업로드 → 파싱 → 시세·부가정보 회신 |
| 채널별 동작 | 금융사 산출 / 대출상품 / PDF 전용 등 채팅방별 분기 |

---

## 프로젝트 구조

```
2512_mortgage_calculator/
├── main.py                      # 로컬 Polling 봇 (개발·테스트용)
├── local_pdf_bot.py             # 로컬 PDF 전용 Polling 봇
├── api/
│   ├── webhook.py               # Vercel/Render 웹훅 (메인 서비스)
│   └── kb-households.js         # Vercel Node: 세대수·동수 스크래핑
├── config/
│   └── telegram_config.example.py
├── parsers/
│   ├── message_parser.py        # 텍스트 메시지 파싱
│   └── registry_parser.py       # 등기부 PDF 파싱
├── calculator/
│   └── base_calculator.py       # 금융사별 한도·금리 계산 엔진
├── data/
│   ├── banks/                   # 금융사 조견 JSON
│   └── loan/                    # 대출상품 설정
├── utils/
│   ├── formatter.py             # 결과 포맷
│   ├── validators.py            # KB시세·금액 검증
│   ├── mortgage_calculator.py   # 원금·금융기관 분류
│   └── real_transaction_api.py  # 공공데이터 실거래가
├── KB_api/                      # KB 시세·법정동·스크래퍼
├── kb-price-node/               # Node.js KB 시세 (HTTP API 전용)
├── render-playwright/           # Render Playwright 스크래퍼 서비스
├── scripts/                     # 웹훅·빌드·점검 스크립트
├── requirements.txt
├── package.json                 # Vercel Node 의존성
└── vercel.json
```

### 등록된 금융사 (`data/banks/`)

| 파일 | 금융사 |
|------|--------|
| `1_MGcapital.json` | MG캐피탈 |
| `2_hantosavingbank.json` | 한토저축은행 |
| `3_JBwooricapital_himortage.json` | JB우리캐피탈 하이론 |
| `4_bnk_config.json` | BNK캐피탈 |
| `5_acuoncapital.json` | 애큐온캐피탈 |
| `5_acuonsavingbank.json` | 애큐온저축은행 |
| `5_kiwoomretail.json` | 키움저축은행 |
| `6_peppersavingbank.json` | 페퍼저축은행 |
| `7_ok_config.json` | OK저축은행 |

공통 참조: `refinanceable_institutions.json`, `korean_savings_and_capital_institutions.json`

---

## 빠른 시작

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

PDF·스크래핑 기능까지 쓸 경우:

```bash
pip install playwright python-dotenv
playwright install chromium
```

Vercel Node API용:

```bash
npm install
```

### 2. 설정

```bash
# Windows
copy config\telegram_config.example.py config\telegram_config.py

# Mac/Linux
cp config/telegram_config.example.py config/telegram_config.py
```

`TELEGRAM_BOT_TOKEN`을 입력하거나 환경변수로 설정합니다.  
상세 내용은 [SETUP.md](SETUP.md)를 참고하세요.

### 3. 로컬 실행

```bash
python main.py
```

### 4. Vercel 배포 (운영)

1. GitHub 연동 후 Vercel 배포
2. 환경변수 설정 (`TELEGRAM_BOT_TOKEN` 등)
3. 웹훅 등록:

```bash
python scripts/set_webhook.py https://your-app.vercel.app/api/webhook
```

---

## 실행 환경별 역할

| 환경 | 용도 | 진입점 |
|------|------|--------|
| **Vercel** | 운영 웹훅, KB Node API | `api/webhook.py`, `api/kb-households.js` |
| **Render** | 웹훅 + Playwright 분리 배포 | `run_webhook_render.py`, `render-playwright/` |
| **로컬 Polling** | 개발·PDF 전용 봇 | `main.py`, `local_pdf_bot.py` |

---

## 문서 목록

| 문서 | 내용 |
|------|------|
| [SETUP.md](SETUP.md) | 토큰, 환경변수, 웹훅, BotFather 설정 |
| [USAGE.md](USAGE.md) | 메시지 형식, 금융사 조견 수정, 기능 사용법 |
| [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) | 아키텍처·계산 로직·모듈 상세 |
| [README_LOCAL_BOT.md](README_LOCAL_BOT.md) | 로컬 PDF 봇 설치·실행 |
| [RENDER_무응답_대응.md](RENDER_무응답_대응.md) | Render 무응답 트러블슈팅 |
| [KB_api/README.md](KB_api/README.md) | KB 시세 API 사용법 |
| [kb-price-node/README.md](kb-price-node/README.md) | Node.js KB 시세 모듈 |
| [render-playwright/README.md](render-playwright/README.md) | Render Playwright 서비스 |
| [docs/공공데이터_실거래가_설정_가이드.md](docs/공공데이터_실거래가_설정_가이드.md) | 실거래가 API 설정 |
| [docs/CONFIG_UNIFICATION_PLAN.md](docs/CONFIG_UNIFICATION_PLAN.md) | 조견 JSON 통합 계획 (내부) |

---

## 부족자금 산출

기본적으로 **가용한도가 마이너스**인 LTV 단계는 결과에서 제외됩니다.  
요청사항에 **「부족자금」**을 포함하면 마이너스 한도도 표시되어 추가 필요 자금을 확인할 수 있습니다.

```
요청사항: *2순위 대환조건 확인 부탁드립니다. 부족자금
```

---

## KB 세대수·동수 (Vercel)

Vercel Python 런타임에서는 Playwright를 쓸 수 없어, **Node.js + Puppeteer** (`api/kb-households.js`)로 kbland.kr 단지 페이지를 스크래핑합니다.

- **엔드포인트**: `GET /api/kb-households?complex_id=15385`
- **응답**: `{ households, buildings, error }`
- **로컬 테스트**: `vercel dev` 또는 배포 URL로 curl 호출

세부 한계·대안은 [KB_api/kbland_스크래핑_한계.md](KB_api/kbland_스크래핑_한계.md) 참고.

---

## 보안

- `config/telegram_config.py`, `.env`, `.env.local`은 Git에 포함하지 않습니다.
- API 토큰·인증키는 환경변수로 관리하는 것을 권장합니다.
