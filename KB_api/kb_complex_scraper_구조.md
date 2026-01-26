# KB /c/ 단지 페이지 스크래퍼 구조

> **목적**: `kbland.kr/c/{단지기본일련번호}` 페이지를 스크래핑해 **재건축 단계(조합설립인가 등)** 와 **세대수·동수**를 한 번에 추출한다.

---

## 1. 전체 구조

```
KB_api/
├── kb_price_api.py           # 기존: 시세 API (fastPriceInfo, typInfo 등)
├── kb_complex_scraper.py     # 신규: /c/ 페이지 스크래퍼
├── 전국_dongcode_data.json
└── ...
```

- **입력**: `단지기본일련번호` (int 또는 str) — `get_complex_list`/`get_kb_price` 등에서 이미 사용하는 ID와 동일.
- **출력**: 재건축 단계 리스트 + 세대수 + 동수(+ 선택 필드).

---

## 2. `kb_complex_scraper.py` 역할

| 기능 | 설명 |
|------|------|
| **재건축 단계** | "5단계 조합설립인가 2017.06.01" 형태를 파싱해 리스트로 반환 |
| **세대수** | 기본정보의 "○,○○○세대" 에서 숫자 추출 |
| **동수** | 기본정보의 "△개동" 에서 숫자 추출 (있을 때만) |

---

## 3. 출력 스키마 (반환 dict)

```python
{
    # 재건축 단계 (해당 블록이 있을 때만)
    "redevelop_stages": [
        {"step": 5, "name": "조합설립인가", "date": "2017.06.01"},
        {"step": 6, "name": "사업시행인가", "date": "2019.03.15"},
        # ...
    ],
    "households": 1584,        # 세대수 (없으면 None)
    "buildings": 24,           # 동수 (없으면 None)
    "redevelop_yn": True,      # 재건축 관련 블록 존재 여부
    "complex_name": "시범",     # 페이지 제목 등에서 추출 (선택)
    "source_url": "https://kbland.kr/c/2171",
    "error": None,             # 파싱/요청 실패 시 메시지
}
```

---

## 4. 클래스·함수 설계

```python
# kb_complex_scraper.py

class KBComplexScraper:
    """kbland.kr/c/{id} 스크래핑 전용."""

    def __init__(self, headless: bool = True, timeout_ms: int = 15000):
        """
        headless: 브라우저 창 숨김 여부
        timeout_ms: 페이지 로드·선택자 대기 타임아웃
        """

    def scrape(self, complex_id: int | str) -> dict:
        """
        /c/{complex_id} 페이지를 열고 재건축 단계 + 세대수·동수 파싱.
        Returns: 위 출력 스키마 형태의 dict.
        """

    def _parse_redevelop_stages(self, page) -> list:
        """재건축 단계 블록에서 N단계 / 단계명 / 일자 추출."""

    def _parse_basic_info(self, page) -> tuple[int|None, int|None]:
        """기본정보에서 (세대수, 동수) 추출."""


# 편의 함수 (기존 kb_price_api 스타일에 맞춤)
def get_complex_extra_info(complex_id: int | str) -> dict:
    """단지기본일련번호로 /c/ 스크래핑 후 재건축·세대수·동수 반환."""
    scraper = KBComplexScraper()
    return scraper.scrape(complex_id)
```

---

## 5. 파싱 전략 (정규·DOM)

### 5.1 재건축 단계

- **위치**: /c/ 페이지 내 "재건축" / "정비" / "사업 단계" 등으로 보이는 블록.
- **예시 문자열**: `"5단계 조합설립인가 2017.06.01"`, `"6단계 사업시행인가 2019.03.15"`.
- **정규 예시**:
  - `r'(\d+)단계\s*([가-힣]+)\s*(\d{4}\.\d{2}\.\d{2})'` → (step, name, date).
  - `r'(\d{4})\.(\d{2})\.(\d{2})'` 만 있고 "단계" 표현이 다르면, 블록 안 텍스트를 잘라서 유연하게 처리.

### 5.2 세대수·동수

- **위치**: 기본정보 영역.
- **예시**: `"1,584세대 / 24개동"`, `"496세대 / 13개동"`.
- **정규**:
  - 세대수: `r'([\d,]+)\s*세대'` → 숫자만 남기기 (쉼표 제거).
  - 동수: `r'(\d+)\s*개동'`.

---

## 6. 의존성 및 설치

```text
# requirements.txt 에 주석 해제 후 추가
playwright>=1.40.0
```

```bash
pip install -r requirements.txt
playwright install chromium   # 최초 1회
```

- **Selenium 대신 Playwright**: SPA(/c/가 JS로 로딩) 대응, API가 단순하고 헤드리스 안정적.
- **Vercel**: Playwright/Chromium은 서버리스에서 부적합하므로, `kb_complex_scraper`는 Vercel에서 자동 비활성화됨. 스크래핑이 필요하면 로컬·별도 서버에서만 사용.

---

## 7. 기존 흐름과의 연동

### 7.1 `단지기본일련번호` 얻기

- `get_complex_list`(fastPriceInfo) → `selected_complex["단지기본일련번호"]`
- `get_kb_price` 내부에서 `selected_complex` 확보 후 `complex_id = selected_complex.get("단지기본일련번호")` 사용.

### 7.2 호출 위치 (선택)

| 방식 | 설명 |
|------|------|
| **A. 시세 조회 바로 다음** | `get_kb_price` 반환 후, `complex_id`를 인자로 `get_complex_extra_info(complex_id)` 호출. 시세 dict에 `redevelop_stages`, `households`, `buildings` 등을 merge. |
| **B. 재건축여부=1일 때만** | `info` 또는 `hscmList`에서 `재건축여부=="1"`인 경우에만 `get_complex_extra_info` 호출. 트래픽 절감. |
| **C. 별도 API/함수** | `get_kb_price_with_complex_info(address, area, complex_name)` 형태로, 내부에서 `get_kb_price` + `get_complex_extra_info` 호출 후 하나의 dict로 합쳐 반환. |

- 초기 구현은 **B** 또는 **C**로 두고, `get_kb_price` 본체는 그대로 두는 쪽을 권장.

### 7.3 반환 확장 예 (get_kb_price 쪽에 merge 시)

```python
# get_kb_price 반환에 merge 할 수 있는 키
{
    "kb_price": 272500,
    "kb_price_min": 36500,
    "complex_name": "시범",
    # ... 기존 필드 ...

    # 스크래퍼에서 확장 (스크래퍼 호출 시에만 존재)
    "households": 1584,
    "buildings": 24,
    "redevelop_stages": [{"step": 5, "name": "조합설립인가", "date": "2017.06.01"}],
    "redevelop_yn": True,
}
```

---

## 8. Vercel·서버리스 고려

- Playwright/Chromium은 바이너리·메모리 요구가 커서 **Vercel 기본 서버리스에서는 실행이 어려움**.
- **권장**:
  - 스크래퍼는 **로컬, 또는 Playwright를 지원하는 별도 서버/컨테이너**에서만 실행.
  - Vercel 람다에서는:
    - `get_complex_extra_info`를 **호출하지 않거나**,
    - `VERCEL=1` 등 환경을 보고 `get_complex_extra_info` 내부에서 **즉시 `{"redevelop_stages":[], "households":None, "buildings":None, "redevelop_yn":False, "error":"스크래핑 미지원(Vercel)"}` 같은 구조를 반환**하고, 스크래핑 로직은 수행하지 않음.

```python
# kb_complex_scraper.py 상단 예시
if os.getenv("VERCEL") == "1":
    def get_complex_extra_info(complex_id):
        return {"redevelop_stages": [], "households": None, "buildings": None,
                "redevelop_yn": False, "error": "Vercel 환경에서는 스크래핑 비동작"}
```

- 스크래핑이 필요한 기능은 **별도 API 서버·크론·로컬 스크립트**에서 `get_complex_extra_info`를 호출하도록 두는 것이 안전함.

---

## 9. 에러·예외

| 상황 | 처리 |
|------|------|
| `complex_id` 없음/None | `{"error": "complex_id 필요", "redevelop_stages": [], "households": None, "buildings": None}` |
| /c/ 404 또는 로드 실패 | `{"error": "페이지 로드 실패", ...}` |
| 재건축 블록 없음 | `redevelop_stages=[]`, `redevelop_yn=False` |
| 기본정보에 세대/동 없음 | `households=None`, `buildings=None` |
| Playwright 미설치/미사용 환경 | `error` 메시지로 원인 기록, 나머지 필드는 None/빈 리스트 |

---

## 10. 요약

- **대상 URL**: `https://kbland.kr/c/{단지기본일련번호}`
- **추출**: 재건축 단계(조합설립인가 등), 세대수, 동수.
- **구현**: `KB_api/kb_complex_scraper.py` 에 `KBComplexScraper`, `get_complex_extra_info` 추가.
- **의존성**: `playwright` + `playwright install chromium`.
- **연동**: `get_kb_price` 등에서 `단지기본일련번호` 확보 후 `get_complex_extra_info(id)` 호출, 결과를 시세 dict에 merge (또는 재건축여부=1일 때만).
- **Vercel**: `/c/` 스크래퍼는 Vercel 기본 환경에서 비활성화하고, 스크래핑이 필요한 경로는 로컬/별도 서버에서만 호출.
