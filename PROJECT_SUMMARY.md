# 프로젝트 기술 요약

담보대출 계산기의 아키텍처, 모듈 역할, 계산 흐름을 정리한 문서입니다.

---

## 개요

텔레그램 메시지 또는 등기부 PDF로 담보물건 정보를 받아, `data/banks/` JSON 조견에 따라 여러 금융사의 LTV·한도·금리를 산출합니다.

```
입력 (텍스트/PDF)
  → 파서 (message_parser / registry_parser)
  → KB 시세·부가정보 (KB_api, kb-price-node, 스크래퍼)
  → 계산 엔진 (base_calculator)
  → 포맷터 (formatter)
  → 텔레그램 응답
```

---

## 진입점

| 파일 | 역할 |
|------|------|
| `main.py` | 로컬 Polling 봇 (개발·간단 테스트) |
| `api/webhook.py` | Vercel/Render 서버리스 웹훅 (운영) |
| `local_pdf_bot.py` | 로컬 PDF 전용 Polling 봇 |
| `run_webhook_render.py` | Render 웹훅 실행 |

---

## 파서 (`parsers/`)

### `message_parser.py`

- 담보물건 텍스트 양식 파싱
- 근저당 설정내역 (순위, 기관, 원금, 채권최고액)
- 요청사항: 대환 순위·범위, 부족자금, 지분조건 등
- 대환 판단: `N순위 대환`, `전체 대환`, `선순위`, `N-M순위 대환`, 기관명 매칭

### `registry_parser.py`

- 등기부 PDF → 구조화 데이터
- 주소, 면적, 근저당, 소유자 등 추출

---

## 계산기 (`calculator/base_calculator.py`)

- `data/banks/*.json` 자동 로드 (`enabled: true`만)
- 금융사별 분기: LTV 급지, 선/후순위, 대환, 지역·등급 조합 등
- `calculate_all_banks(property_data)` — 전 금융사 일괄 산출
- 대환 마스터: `refinanceable_institutions.json` + 금융사별 `business_product_names`

### 계산 단계

1. KB시세·보조가 검증 (`utils/validators.py`)
2. 주소 → 행정구역 → `region_grades` 급지
3. 급지별 max LTV, `ltv_steps` 순회
4. 기존 근저당 차감 → 가용한도
5. 신용등급 → `interest_rates_by_ltv` 금리
6. `conditions` 등 특이 조건 부가

---

## 유틸 (`utils/`)

| 모듈 | 역할 |
|------|------|
| `formatter.py` | 금융사별 결과 통합 포맷 |
| `validators.py` | KB시세, 특이사항 보조가, 금액 파싱 |
| `mortgage_calculator.py` | 원금 계산, 금융기관 분류 |
| `real_transaction_api.py` | 공공데이터 실거래가 |
| `tenant_extractor.py` | 세입자·임차 정보 |

---

## KB 시세 (`KB_api/`, `kb-price-node/`)

| 구성 | 설명 |
|------|------|
| `KB_api/kb_price_api.py` | Python KB 시세 (법정동코드 → 단지 → 면적 매칭) |
| `KB_api/kb_complex_scraper.py` | Playwright: 세대수·사용승인일·재건축 |
| `kb-price-node/` | Node HTTP API 전용 (Vercel 호환) |
| `api/kb-households.js` | Vercel Node Puppeteer 세대수 API |
| `render-playwright/` | Render 전용 Playwright 마이크로서비스 |

법정동코드: `KB_api/전국_dongcode_data.json`  
도로명 주소: `JUSO_API_KEY` 환경변수로 실시간 조회

---

## 데이터 (`data/`)

### `data/banks/`

금융사별 조견 JSON. 파일 추가만으로 계산기 확장.

현재 등록: MG캐피탈, 한토저축, JB우리캐피탈, BNK, 애큐온(캐·저), 키움저축, 페퍼저축, OK저축

### `data/loan/`

대출상품·팀별 설정 (`FSS/`, `Local/`)

---

## 웹훅 채널 분기 (`api/webhook.py`)

환경변수로 채팅방별 동작을 나눕니다.

| 변수 | 용도 |
|------|------|
| `ALLOWED_CHAT_IDS_BANKS` | 금융사 한도 산출 |
| `ALLOWED_CHAT_IDS_BANKS_2` | 금융사 산출 (2번 채널) |
| `ALLOWED_CHAT_IDS_LOAN` | 대출상품 안내 |
| `ALLOWED_CHAT_IDS_PDF_ONLY` | PDF 파싱만 (산출 없음) |

---

## 배포

### Vercel

- `api/webhook.py` — maxDuration 60s
- `api/kb-households.js` — Node Puppeteer, memory 1024MB
- Python Playwright 불가 → Node 또는 외부 스크래퍼 사용

### Render

- 무료 플랜 슬립 이슈 → UptimeRobot 등 핑 권장
- `RENDER=true` 시 in-process Playwright 비활성 → `PLAYWRIGHT_SCRAPER_URL` 연동
- 상세: [RENDER_무응답_대응.md](RENDER_무응답_대응.md)

---

## 결과 형식

```
* {금융사명} ({N}등급기준)
{대환|후순위} {LTV}% {한도}만 / {금리}%
- {conditions 항목}
```

대환 시 `가용 {금액}만` 추가. 신용점수 없으면 `{최저}%~{최고}%`.

---

## 향후 개선 (내부)

- 조견 JSON 스키마 통합 → [docs/CONFIG_UNIFICATION_PLAN.md](docs/CONFIG_UNIFICATION_PLAN.md)
- 금융사명 하드코딩 분기를 config 플래그로 대체

---

## 참고 문서

- [README.md](README.md) — 프로젝트 소개·빠른 시작
- [SETUP.md](SETUP.md) — 환경 설정
- [USAGE.md](USAGE.md) — 사용법
- [KB_api/README.md](KB_api/README.md) — KB API 상세
