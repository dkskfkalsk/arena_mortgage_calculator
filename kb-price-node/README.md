# KB 시세 조회 (Node.js)

HTTP API만 사용하는 KB 시세 조회 모듈. **브라우저/Playwright 불필요**하며, Vercel 등 Node 18+ 서버리스 환경에서 사용 가능.

## 요구사항

- Node.js **18+** (native `fetch` 사용)
- 프로젝트 루트의 `KB_api/전국_dongcode_data.json` (법정동코드 데이터)

## 사용법

### CLI

```bash
node kb-price-node/index.js "<주소>" "<면적>"
# 예: node kb-price-node/index.js "경상남도 진주시 이현동 1180 이현하이클래스웰가 제105동 제23층 제2303호" "148.01"
```

출력: JSON 한 줄  
`{ "ok": true, "kb_price": 45500, "kb_price_min": 42500, "complex_id": "15385", "households": 1268, ... }`  
실패 시 `{ "ok": false, "error": "..." }`  

`households`: fastPriceInfo·get_complex_info API에 있으면 사용, 없으면 kbland.kr/c/{id} fetch 시도. 서버 요청에서 `__NEXT_DATA__` 미제공 시 often `null`.  
**정확한 세대수**(예: 이현하이클래스웰가 1,268세대)는 **Python + Playwright** 로컬 스크래핑(`run_scraper_local --pdf` 등)에서 보장됨.

### 모듈

```js
const { getKbPriceFromRegistry } = require("./kb-api");

const result = await getKbPriceFromRegistry(
  "경상남도 진주시 이현동 1180 이현하이클래스웰가 제105동 제23층 제2303호",
  "148.01"
);
// { kb_price, kb_price_min, complex_id, complex_name, ... } or null
```

## 로컬 테스트 (PDF 파싱 → Node 시세)

```bash
python scripts/test_kb_node_pdf.py
```

`pdf_Parsing_example/권현주 250819.pdf`를 파싱한 뒤 Node로 KB 시세를 조회하고 결과를 출력한다.
