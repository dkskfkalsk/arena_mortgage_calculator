# KB 시세 조회 (Node.js)

**HTTP API만** 사용하는 KB 시세 모듈입니다. Playwright 없이 Vercel 등 Node 18+ 환경에서 동작합니다.

---

## 요구사항

- Node.js **18+** (native `fetch`)
- `KB_api/전국_dongcode_data.json`

---

## CLI

```bash
node kb-price-node/index.js "<주소>" "<면적>"
```

예:

```bash
node kb-price-node/index.js "경상남도 진주시 이현동 1180 이현하이클래스웰가 제105동 제23층 제2303호" "148.01"
```

### 출력 (JSON 한 줄)

성공:

```json
{ "ok": true, "kb_price": 45500, "kb_price_min": 42500, "complex_id": "15385", "households": 1268, ... }
```

실패:

```json
{ "ok": false, "error": "..." }
```

`households`: API·페이지 fetch에 있으면 채움, 없으면 `null`.  
**정확한 세대수**가 필요하면 로컬 Playwright([KB_api/README.md](../KB_api/README.md)) 사용.

---

## 모듈

```javascript
const { getKbPriceFromRegistry } = require("./kb-api");

const result = await getKbPriceFromRegistry(
  "경상남도 진주시 이현동 1180 ...",
  "148.01"
);
// { kb_price, kb_price_min, complex_id, complex_name, ... } or null
```

---

## Vercel 연동

- Python 웹훅은 주로 `KB_api/kb_price_api.py` 사용
- 세대수 전용: `api/kb-households.js` (Puppeteer)
- Node 시세 단독 테스트: `scripts/test_kb_node_pdf.py`

---

## 로컬 PDF → Node 시세 테스트

```bash
python scripts/test_kb_node_pdf.py
```

`pdf_Parsing_example/` PDF 파싱 후 Node로 KB 시세 조회.

---

## 관련 문서

- [KB_api/README.md](../KB_api/README.md)
- [KB_api/kbland_스크래핑_한계.md](../KB_api/kbland_스크래핑_한계.md)
