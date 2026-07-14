# KB 시세 API 모듈

등기부·메시지에서 추출한 **주소·면적**으로 KB 부동산 시세를 조회하는 Python 모듈입니다.  
`KB_api/`는 다른 모듈과 독립적으로 import해 사용할 수 있습니다.

---

## 설치

```bash
pip install requests
# 스크래핑(세대수·사용승인일) 사용 시
pip install playwright
playwright install chromium
```

또는 `pip install -r requirements.txt`

---

## 기본 사용

### 편의 함수

```python
from KB_api.kb_price_api import get_kb_price_from_registry

result = get_kb_price_from_registry(
    "서울특별시 강남구 대치동 123",
    "84.93㎡"
)

if result:
    print(result["kb_price_raw"])   # "125,000만원"
    print(result["complex_name"])
    print(result["area"])           # m²
```

### 클래스

```python
from KB_api.kb_price_api import KBPriceAPI

api = KBPriceAPI()
result = api.get_kb_price(
    address="서울특별시 강남구 대치동",
    area=84.93,
    complex_name="대치아이파크"  # 선택
)
```

---

## 등기부 연동

```python
from parsers.registry_parser import RegistryParser
from KB_api.kb_price_api import get_kb_price_from_registry

doc = RegistryParser().parse("등기부.pdf")
if doc.부동산_주소 and doc.면적:
    result = get_kb_price_from_registry(doc.부동산_주소, doc.면적)
```

---

## 반환값

```python
{
    "kb_price": 125000,            # 만원 (숫자)
    "kb_price_raw": "125,000만원",
    "kb_price_min": 120000,        # 하한 (있을 때)
    "complex_name": "대치아이파크",
    "complex_id": "15385",
    "area": 84.93,
    "pyeong": "25.7",
    "type": "84A형"
}
```

실패 시 `None`.

---

## 처리 흐름

1. **주소 파싱** — 시/도, 구/군, 동/읍/면, 단지명 추출
2. **법정동코드** — `전국_dongcode_data.json` 매칭 (도로명은 JUSO API)
3. **단지 목록** — KB API로 해당 지역 단지 조회
4. **면적 매칭** — 전용면적 기준 (허용 오차 약 5m²)
5. **시세** — 일반가·하한가 등

---

## 환경별 스크래핑

| 환경 | 세대수·사용승인일 | 방식 |
|------|-------------------|------|
| 로컬 | ✅ | `kb_complex_scraper.py` + Playwright |
| Vercel | 세대수 | `api/kb-households.js` (Node Puppeteer) |
| Render | ✅ (분리) | `PLAYWRIGHT_SCRAPER_URL` → render-playwright |
| Vercel/Render (미연동) | ❌ | HTTP API만, 부가정보 null 가능 |

한계: [kbland_스크래핑_한계.md](kbland_스크래핑_한계.md)

---

## Node 대안 (`kb-price-node/`)

Vercel 등에서 Python Playwright 없이 HTTP만으로 시세 조회:

```bash
node kb-price-node/index.js "<주소>" "<면적>"
```

상세: [../kb-price-node/README.md](../kb-price-node/README.md)

---

## 로컬 스크래핑 테스트

```bash
# 단지 ID
python scripts/run_scraper_local.py 15385

# PDF → 시세 → 세대수 일괄
python scripts/run_scraper_local.py --pdf "path/to/file.pdf"
```

---

## 환경변수

| 변수 | 용도 |
|------|------|
| `JUSO_API_KEY` / `JUSO_CONFM_KEY` | 도로명 → 법정동코드 |
| `REAL_ESTATE_API_KEY` | KB 실패 시 실거래가 ([../docs/공공데이터_실거래가_설정_가이드.md](../docs/공공데이터_실거래가_설정_가이드.md)) |
| `PLAYWRIGHT_SCRAPER_URL` | Render 외부 스크래퍼 |

---

## 데이터 파일

| 파일 | 설명 |
|------|------|
| `전국_dongcode_data.json` | 법정동코드 (필수) |
| `kb_complex_id_cache.json` | 단지 ID 캐시 |

업데이트: [법정동코드_데이터_출처.md](법정동코드_데이터_출처.md)

---

## 로그·디버깅

- 로컬: `kb_price_api_debug.log` (프로젝트 루트)
- Vercel: 대시보드 Logs, `vercel logs`
- 상세: [로그_확인_가이드.md](로그_확인_가이드.md)

---

## 파일 구조

```
KB_api/
├── kb_price_api.py           # 메인 시세 API
├── kb_complex_scraper.py     # Playwright 스크래퍼
├── kb_next_data.py           # kbland 데이터 파싱 보조
├── generate_dongcode_json.py # 법정동 JSON 생성
├── 전국_dongcode_data.json
├── README.md
├── 로그_확인_가이드.md
├── kbland_스크래핑_한계.md
└── 법정동코드_데이터_출처.md
```

---

## 문제 해결

| 문제 | 확인 |
|------|------|
| 법정동코드 없음 | 주소 형식, `전국_dongcode_data.json`, JUSO API 키 |
| 단지 매칭 실패 | 단지명·동/호수 제거 후 재시도, 로그의 단지 목록 |
| 면적 불일치 | 전용 vs 공급면적, 로그의 사용 가능 면적 목록 |
| API 실패 | 네트워크, KB 서버 상태, Vercel 타임아웃 |
