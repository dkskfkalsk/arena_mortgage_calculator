# kbland.kr 스크래핑 한계

KB 부동산(kbland.kr)에서 **브라우저 없이** 가져올 수 없는 정보와, 환경별 대안을 정리합니다.

---

## kbland 기술 구조

- **Vue.js SPA** (Next.js 아님)
- 초기 HTML: `<div id="app"></div>` + JS 번들
- 사용승인일·재건축·일부 단지 정보는 **JS 실행 후 API/렌더**로 로드

---

## 불가능한 방식

| 방식 | 이유 |
|------|------|
| `_next/data` JSON | Next.js가 아님 |
| 단순 HTTP + HTML 파싱 | 초기 HTML에 데이터 없음 |
| `api.kbland.kr` 단지 info만 | 사용승인일 필드 없음 |

---

## 환경별 현황

| 환경 | 방식 | 세대수 | 사용승인일·재건축 |
|------|------|--------|-------------------|
| **로컬** | Python Playwright | ✅ | ✅ |
| **Vercel** | Node Puppeteer (`api/kb-households.js`) | ⚠️ 환경 의존 | ❌ |
| **Render** | 분리 Playwright (`PLAYWRIGHT_SCRAPER_URL`) | ✅ | ✅ |

Vercel Node Puppeteer는 Chromium 네이티브 라이브러리(`libnss3.so` 등) 이슈로 **실패할 수 있음**.  
이 경우 세대수는 `null`, 시세·산출 본문은 정상일 수 있습니다.

---

## 대안

1. **로컬 PDF 봇** — Playwright 로컬 실행 ([README_LOCAL_BOT.md](../README_LOCAL_BOT.md))
2. **Render Playwright 서비스** — [render-playwright/README.md](../render-playwright/README.md)
3. **공공데이터** — 건축물대장 등 사용승인일 API (별도 연동)
4. **외부 브라우저 서비스** — Browserless, ScrapingBee 등

---

## HTTP API만으로 가능한 것

`kb-price-node/`, `KB_api/kb_price_api.py` HTTP 경로:

- 법정동코드 → 단지 목록 → **KB 일반가·하한가**
- `complex_id` (fastPriceInfo 등에서)

**보장되지 않는 것**: 정확한 세대수(예: 1,268세대), 사용승인일, 재건축 여부

---

## Vercel 세대수 API 점검

```bash
curl "https://<배포URL>/api/kb-households?complex_id=15385"
```

기대: `{ "households": ..., "buildings": ..., "error": null }`

Vercel Logs에서:

- `Node kb-households API 호출`
- `Node API 응답`
- `Node kb-households API HTTP 에러`

---

## 관련 문서

- [README.md](README.md)
- [../kb-price-node/README.md](../kb-price-node/README.md)
- [로그_확인_가이드.md](로그_확인_가이드.md)
