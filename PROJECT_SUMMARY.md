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
| `api/webhook.py` | Vercel 서버리스 웹훅 (운영) |
| `main.py` | 로컬 Polling 비활성 가드 (Vercel 웹훅만 사용) |

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
| `KB_api/kb_price_api.py` | Python KB 시세 (법정동코드 → 단지 → 면적 매칭), 단지 부가정보 KB API 조회 |
| `KB_api/kb_complex_scraper.py` | 단지 부가정보 스크래핑 (KB API 실패 시 보조) |
| `kb-price-node/` | Node HTTP API 전용 (Vercel 호환) |
| `api/kb-households.js` | Vercel Node Puppeteer 스크래퍼 (보조, Render 미설정 시) |
| `render-playwright/` | Render Playwright 스크래퍼 (보조) |

법정동코드: `KB_api/전국_dongcode_data.json`  
도로명 주소: `JUSO_API_KEY` 환경변수로 실시간 조회

### 단지 부가정보 조회 순서

세대수·동수·사용승인일·단지유형·재건축 단계는 아래 순서로 채웁니다.

```
1차  KB API  kb_price_api.get_complex_extra_via_api()
     complexMain(세대수·동수·준공일·유형) + rcnsInfo(재건축 단계)
       │  세대수 또는 사용승인일이 비어 있을 때만
       ▼
보조  kb_complex_scraper.get_complex_extra_info()
     로컬   → Python Playwright
     Vercel → PLAYWRIGHT_SCRAPER_URL 있으면 Render 스크래퍼 (현재 설정됨)
              없으면 api/kb-households.js (Node Puppeteer)
```

보조 결과는 KB API가 채우지 못한 항목에만 덮어씁니다.

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
- Python Playwright 불가 → 보조 스크래핑은 Render 스크래퍼 또는 Node 사용

### Render (보조 스크래퍼만)

- `render-playwright/`만 배포. 웹훅은 Render에서 돌리지 않음
- Vercel 환경변수 `PLAYWRIGHT_SCRAPER_URL`, `PLAYWRIGHT_SCRAPER_TOKEN`으로 연동
- 무료 플랜 슬립(15분) → 보조 경로가 필요하면 `/health` 14분 간격 핑
- 상세: [render-playwright/README_render-playwright.md](render-playwright/README_render-playwright.md)

---

## KB 단지 부가정보 조회 이력

세대수·사용승인일 등을 어디서 가져오는지가 여러 번 바뀌었습니다. Render가 왜 남아 있는지 이해하려면 이 흐름을 보면 됩니다.

### 1. 로컬 Playwright (2026.01)

- kbland.kr은 Vue SPA라 초기 HTML에 데이터가 없음 → `/c/{단지ID}` 페이지를 브라우저로 띄워 본문 텍스트를 파싱
- 당시 알던 API(`complex/info`)에는 세대수·사용승인일이 없었음
- 로컬에서는 잘 되지만 Vercel 서버리스에서는 Python Playwright(Chromium) 실행 불가

### 2. Vercel Node Puppeteer (2026.01.30)

- `api/kb-households.js` 추가: `puppeteer-core` + `@sparticuz/chromium`으로 Vercel 안에서 스크래핑
- Chromium 네이티브 라이브러리 문제·시간 제한으로 실패가 잦음

### 3. Render 분리 (2026.02)

- `render-playwright/`: Render에 Playwright 전용 서비스를 따로 배포하고 Vercel이 `PLAYWRIGHT_SCRAPER_URL`로 호출
- 같은 시기 웹훅 자체를 Render에서 돌리는 구성(`run_webhook_render.py`)도 시도
  - 무료 플랜 슬립·콜드 스타트로 무응답이 잦아 "일어나" 명령, UptimeRobot 핑 등으로 대응
  - 이후 웹훅은 Vercel로 일원화 → `run_webhook_render.py`, `RENDER_무응답_대응.md`, `RENDER=true` 분기 삭제 (2026.10)

### 4. KB API 우선 (2026.08 ~ 현재)

- `complexMain`(세대수·동수·준공일·유형)과 `rcnsInfo`(재건축 단계)에 같은 값이 있다는 것을 확인
- `kb_price_api.get_complex_extra_via_api()`가 1차로 조회. 0.3~0.7초 (브라우저 11~19초)
- 스크래퍼는 KB API로 세대수·사용승인일을 못 얻은 경우에만 보조로 호출
- 상세: [KB_api/kbland_스크래핑_한계.md](KB_api/kbland_스크래핑_한계.md)

### 현재 상태 (2026.10)

| 구성 | 상태 |
|------|------|
| KB API (`get_complex_extra_via_api`) | 1차, 정상 상황에서는 이것만 사용 |
| Render 스크래퍼 (`render-playwright/`) | 보조. Vercel에 `PLAYWRIGHT_SCRAPER_URL` 설정되어 있어 이쪽이 먼저 쓰임 |
| Node 스크래퍼 (`api/kb-households.js`) | 보조의 대체. `PLAYWRIGHT_SCRAPER_URL`을 지우면 사용 |
| Render 웹훅 | 삭제 |

Render를 완전히 걷어내려면 Vercel에서 `PLAYWRIGHT_SCRAPER_URL`을 지우고 KB API 실패 시 Node 스크래퍼가 잘 도는지 확인한 뒤, `render-playwright/`와 `_fetch_render_playwright`를 삭제하고 Render 서비스를 내리면 됩니다.

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
- [KB_api/README_KB_api.md](KB_api/README_KB_api.md) — KB API 상세
- [render-playwright/README_render-playwright.md](render-playwright/README_render-playwright.md) — Render 보조 스크래퍼
