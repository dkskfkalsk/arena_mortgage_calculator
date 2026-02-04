# kbland.kr 사용승인일·재건축 스크래핑 현황

## 검증 결과

### 1. kbland.kr 기술 스택
- **Vue.js SPA** (Next.js 아님)
- 초기 HTML: `<div id="app"></div>` + JS 번들 로드
- **사용승인일·재건축 정보**는 JS 실행 후 API 호출로 로드됨

### 2. 적용 불가 방식
| 방식 | 이유 |
|------|------|
| _next/data JSON | kbland는 Next.js가 아님 |
| 단순 HTTP + HTML 파싱 | 초기 HTML에 데이터 없음 (SPA) |
| api.kbland.kr 단지 API | `/land-complex/complex/info`에 사용승인일 필드 없음 |

### 3. 현재 동작
| 환경 | 방식 | 상태 |
|------|------|------|
| **로컬** | Playwright 스크래핑 | ✅ 정상 (사용승인일, 년차, 세대수 추출됨) |
| **Vercel** | Node Puppeteer (/api/kb-households) | ❌ Chromium libnss3.so 오류 |

### 4. Vercel에서의 대안
1. **외부 브라우저 서비스**: Browserless, ScrapingBee 등
2. **공공데이터 API**: 건축물대장 등 사용승인일 제공 API (별도 연동)
3. **로컬/별도 서버**: Playwright 실행 가능한 환경에서 스크래핑 후 API 제공
