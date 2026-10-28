# Render Playwright 스크래퍼 (보조)

Render에 **별도 마이크로서비스**로 띄운 Playwright(Chromium) 스크래퍼입니다.  
kbland.kr `/c/{단지기본일련번호}` 페이지에서 세대수·동수·사용승인일·단지유형·재건축 단계를 읽어 옵니다.

**KB API가 실패했을 때만 쓰는 보조 경로**입니다. 평소에는 호출되지 않습니다.  
경위는 [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md#kb-단지-부가정보-조회-이력)를 참고하세요.

---

## 호출 흐름

```
Vercel 웹훅 (api/webhook.py)
  → KB_api/kb_price_api.py  get_complex_extra_via_api()   ← 1차: KB API (complexMain, rcnsInfo)
      세대수 또는 사용승인일이 비어 있을 때만
  → KB_api/kb_complex_scraper.py  get_complex_extra_info()
      PLAYWRIGHT_SCRAPER_URL 있음 → 이 서비스 (GET /scrape)
      없음                          → api/kb-households.js (Vercel Node Puppeteer)
```

- 메인 웹훅은 Vercel에서만 돌고, Render에는 이 스크래퍼만 배포합니다.
- 스크래퍼 결과는 KB API가 채우지 못한 항목에만 덮어씁니다.

---

## Render 배포 설정

| 항목 | 값 |
|------|-----|
| **Root Directory** | `render-playwright` |
| **Build Command** | `bash build.sh` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |

`build.sh`가 Chromium을 프로젝트 `browsers/` 폴더에 설치해 배포에 포함합니다.

| Render 환경변수 | 설명 |
|-----------------|------|
| `PLAYWRIGHT_SCRAPER_TOKEN` | 설정 시 요청 헤더 `X-Internal-Token`과 일치해야 응답 |

---

## Vercel 연동

Vercel 프로젝트(`arena-mortgage-calculator`) 환경변수:

```env
PLAYWRIGHT_SCRAPER_URL=https://your-playwright-service.onrender.com
PLAYWRIGHT_SCRAPER_TOKEN=<Render와 같은 값>
```

- URL 끝에 `/` 없이 설정합니다.
- `PLAYWRIGHT_SCRAPER_URL`을 지우면 보조 경로가 `api/kb-households.js`로 바뀝니다.

---

## API

| 경로 | 설명 |
|------|------|
| `GET /scrape?complex_id={id}` | 단지 정보 스크래핑 (1시간 메모리 캐시) |
| `GET /health` | 상태 확인 (슬립 방지 핑용) |
| `GET /` | 서비스 이름 |

---

## 콜드 스타트 주의

Render 무료 플랜은 약 15분 무활동 후 서비스를 내립니다. 다시 뜨는 데 30초~1분이 걸리는데,
Vercel 쪽 호출은 60초 제한 안에 끝내려고 **10초 타임아웃 × 2회**만 시도합니다.

보조 경로라 평소 호출이 거의 없어 대부분 잠든 상태입니다. 그대로 두면 KB API가 실패했을 때
스크래퍼도 타임아웃으로 실패해 세대수·사용승인일이 비어 나올 수 있습니다.

보조 경로가 실제로 동작해야 하면 [UptimeRobot](https://uptimerobot.com) 등에서
`https://<서비스>.onrender.com/health`를 **14분 간격**으로 GET 핑하세요.

---

## 트러블슈팅

| 증상 | 확인 |
|------|------|
| 세대수·사용승인일이 비어 있음 | Vercel 로그에서 `KB API로 단지정보 부족` → `Render Playwright API 실패` 순서인지 확인. 먼저 KB API(`complexMain`) 실패 원인 점검 |
| `Render Playwright API 실패` (timeout) | 콜드 스타트. 위 슬립 방지 핑 설정 |
| `401` / `X-Internal-Token 불일치` | Vercel·Render의 `PLAYWRIGHT_SCRAPER_TOKEN` 값 일치 여부 |
| Chromium 빌드 실패 | Render 로그에서 `build.sh` 출력 확인 |

---

## 관련 문서

- [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md) — 프로젝트 구조, 부가정보 조회 이력
- [KB_api/kbland_스크래핑_한계.md](../KB_api/kbland_스크래핑_한계.md)
- [KB_api/README_KB_api.md](../KB_api/README_KB_api.md)
