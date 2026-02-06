# -*- coding: utf-8 -*-
"""
KB /c/ 단지 페이지 스크래퍼
- kbland.kr/c/{단지기본일련번호} 에서 재건축 단계(조합설립인가 등) + 세대수·동수 추출
- Playwright 사용 (JS 렌더링 SPA 대응)
- Vercel에서는 Playwright 대신 Node Puppeteer API(/api/kb-households)로 세대수·동수 조회
"""

import os
import re
import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Vercel·Render 등 Playwright 미지원/미사용 환경 → 외부 API(PLAYWRIGHT_SCRAPER_URL/VERCEL_URL)만 사용
# Render에서 웹훅이 돌 때 in-process Playwright를 쓰면 실패·타임아웃으로 한도 회신이 안 나갈 수 있음
if os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV") or os.getenv("RENDER") == "true":
    _SCRAPER_DISABLED = True
else:
    _SCRAPER_DISABLED = False

_BASE_URL = "https://kbland.kr/c/"


def _empty_result(complex_id: Any, error: Optional[str] = None) -> Dict[str, Any]:
    return {
        "redevelop_stages": [],
        "households": None,
        "buildings": None,
        "approval_date": None,       # 사용승인일 YYYY.MM.DD
        "years_since_completion": None,  # N년차 (숫자)
        "redevelop_yn": False,
        "complex_name": None,
        "complex_type": None,  # 주상복합, 아파트, 오피스텔 등
        "source_url": f"{_BASE_URL}{complex_id}" if complex_id is not None else None,
        "error": error,
    }


def _parse_households_buildings(text: str) -> Tuple[Optional[int], Optional[int]]:
    """기본정보 텍스트에서 (세대수, 동수) 추출. 예: '아파트1,268세대08.04' → 1268."""
    households, buildings = None, None

    def _parse_number(s: str) -> Optional[int]:
        if not s:
            return None
        s = s.replace(",", "").replace("，", "").replace(" ", "").replace("\u00a0", "")
        try:
            return int(s)
        except ValueError:
            return None

    # 세대: "783세대(임대165)" 형식(총 세대수 명시) 우선 → 기본정보에서 총 세대수(임대 포함) 확보
    m = re.search(r"(\d{1,5})\s*세대\s*\(\s*임대\s*\d+", text)
    if m:
        val = _parse_number(m.group(1))
        if val is not None and 1 <= val <= 100000:
            households = val
    # 그 외: 여러 패턴 시도 (쉼표/공백/전각 포함)
    if households is None:
        for pattern in [
            r"([\d,，\s]+)\s*세대",   # 1,268세대 / 1 268 세대
            r"(\d{1,3}(?:[,，\s]\d{3})*)\s*세대",
            r"세대\s*[수:：]*\s*([\d,，]+)",
        ]:
            m = re.search(pattern, text)
            if m:
                val = _parse_number(m.group(1))
                if val is not None and 1 <= val <= 100000:
                    households = val
                    break

    m = re.search(r"(\d+)\s*개동", text)
    if m:
        try:
            buildings = int(m.group(1))
        except ValueError:
            pass
    return households, buildings


def _parse_approval_date(text: str) -> Tuple[Optional[str], Optional[int]]:
    """기본정보에서 사용승인일 추출. 예: '사용승인일 2015.05.21(12년차)' → ('2015.05.21', 12)."""
    approval_date, years_since = None, None
    # 사용승인일 YYYY.MM.DD(N년차) 또는 사용승인일 YYYY.MM.DD
    m = re.search(r"사용\s*승인\s*일\s*(\d{4}\.\d{2}\.\d{2})\s*(?:\(\s*(\d+)\s*년\s*차\s*\))?", text)
    if m:
        approval_date = m.group(1)  # 2015.05.21
        if m.lastindex >= 2 and m.group(2):
            try:
                years_since = int(m.group(2))
            except ValueError:
                pass
    return approval_date, years_since


def _parse_redevelop_stages_from_text(text: str) -> List[Dict[str, Any]]:
    """'N단계 단계명 YYYY.MM.DD' 패턴 추출.
    지원 형식: "5단계 조합설립인가 2017.06.01", "4단계추진위원회승인\n'2025.08.18"
    """
    stages = []
    seen_steps = set()
    
    logger.info(f"[DEBUG] 재건축 파싱 시작, text 길이: {len(text)}")
    
    # 패턴: "N단계한글이름\n'YYYY.MM.DD" (개행 뒤 아무 문자 1자 + 날짜)
    # . = 개행 제외 1글자 (straight/curly apostrophe 등 모두 매칭)
    pattern = r"(\d+)단계([가-힣]+)\n.(\d{4}\.\d{2}\.\d{2})"
    for m in re.finditer(pattern, text):
        step = int(m.group(1))
        name = m.group(2)
        date = m.group(3)
        logger.info(f"[DEBUG] 재건축 매칭: {step}단계{name} '{date}")
        if step not in seen_steps:
            seen_steps.add(step)
            stages.append({"step": step, "name": name, "date": date})
    
    logger.info(f"[DEBUG] 재건축 파싱 완료: {len(stages)}개 단계 추출")
    stages.sort(key=lambda x: x["step"])
    return stages


def _parse_complex_type(text: str) -> Optional[str]:
    """단지 유형 추출: 주상복합, 아파트, 오피스텔 등"""
    # 우선순위: 주상복합 > 오피스텔 > 아파트
    if re.search(r"주상\s*복합", text):
        return "주상복합"
    if re.search(r"오피스\s*텔", text):
        return "오피스텔"
    if re.search(r"아파트", text):
        return "아파트"
    return None


class KBComplexScraper:
    """kbland.kr/c/{id} 스크래핑."""

    def __init__(self, headless: bool = True, timeout_ms: int = 15000):
        self.headless = headless
        self.timeout_ms = timeout_ms

    def scrape(self, complex_id: int | str) -> Dict[str, Any]:
        """
        /c/{complex_id} 페이지를 열고 재건축 단계 + 세대수·동수 파싱.

        Returns:
            redevelop_stages, households, buildings, redevelop_yn, complex_name, source_url, error
        """
        if complex_id is None or str(complex_id).strip() == "":
            return _empty_result(complex_id, error="complex_id 필요")

        if _SCRAPER_DISABLED:
            return _empty_result(
                complex_id,
                error="Vercel 등 현재 환경에서는 스크래핑 비동작 (Playwright 미지원)",
            )

        url = f"{_BASE_URL}{complex_id}"
        out = _empty_result(complex_id, error=None)
        out["source_url"] = url

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return _empty_result(complex_id, error="playwright 미설치: pip install playwright && playwright install chromium")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                page = browser.new_page(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                )
                # 로컬: 충분한 대기 시간으로 모든 탭 로딩 보장
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Vue SPA API 호출·렌더링 대기 (재건축 정보 탭 로드 포함)
                page.wait_for_timeout(5000)
                # 페이지 스크롤로 추가 컨텐츠 로드 유도 (재건축 정보 등)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)
                # 다시 맨 위로 (전체 컨텐츠 확보)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(2000)
                body_text = page.inner_text("body") or ""
                
                # 디버그: body_text 샘플 및 재건축 텍스트 확인
                logger.info(f"[LOCAL] body_text 길이: {len(body_text)}, 샘플: {body_text[:200] if body_text else '(empty)'}")
                if "4단계" in body_text:
                    idx = body_text.find("4단계")
                    sample = body_text[max(0, idx-30):idx+100]
                    logger.info(f"[LOCAL] '4단계' 발견! 주변: ...{sample}...")
                    # 디버그: 재건축 부분을 파일로 저장
                    try:
                        with open("debug_redevelop_text.txt", "w", encoding="utf-8") as f:
                            f.write(f"전체 길이: {len(body_text)}\n")
                            f.write(f"4단계 위치: {idx}\n")
                            f.write(f"샘플 (repr): {repr(sample)}\n\n")
                            f.write(f"전체 텍스트:\n{body_text}")
                        logger.info(f"[LOCAL] 디버그 텍스트 저장: debug_redevelop_text.txt")
                    except Exception as e:
                        logger.warning(f"[LOCAL] 디버그 파일 저장 실패: {e}")

                # 1) 재건축 단계
                stages = _parse_redevelop_stages_from_text(body_text)
                out["redevelop_stages"] = stages
                out["redevelop_yn"] = len(stages) > 0

                # 2) 세대수·동수 (기본정보 블록)
                households, buildings = _parse_households_buildings(body_text)
                out["households"] = households
                out["buildings"] = buildings

                # 2-1) 사용승인일 (기본정보)
                approval_date, years_since = _parse_approval_date(body_text)
                out["approval_date"] = approval_date
                out["years_since_completion"] = years_since

                # 2-2) 단지유형 (주상복합, 아파트, 오피스텔 등)
                complex_type = _parse_complex_type(body_text)
                out["complex_type"] = complex_type

                # 3) 단지명 (선택: 페이지 제목 등에서 추출 시도)
                title = page.title() or ""
                if "|" in title:
                    out["complex_name"] = title.split("|")[0].strip().strip("'\" ")
                else:
                    out["complex_name"] = None

                browser.close()
        except Exception as e:
            out["error"] = str(e)
            logger.warning("kb_complex_scraper scrape fail: %s", e)

        return out


def _fetch_render_playwright(complex_id: str) -> Dict[str, Any]:
    """
    Vercel 전용. Render Playwright API 호출 (사용승인일·재건축·세대수).
    """
    import time
    import requests
    out = _empty_result(complex_id, error=None)
    out["source_url"] = f"{_BASE_URL}{complex_id}" if complex_id else None
    if not complex_id or str(complex_id).strip() == "":
        out["error"] = "complex_id 필요"
        return out

    base = (os.getenv("PLAYWRIGHT_SCRAPER_URL") or "").strip().rstrip("/")
    if not base:
        out["error"] = "PLAYWRIGHT_SCRAPER_URL 미설정"
        return out

    cid = str(complex_id).strip()
    url = f"{base}/scrape?complex_id={cid}"
    token = (os.getenv("PLAYWRIGHT_SCRAPER_TOKEN") or "").strip()
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Internal-Token"] = token

    for attempt in (1, 2):
        try:
            r = requests.get(url, headers=headers, timeout=50)
            r.raise_for_status()
            data = r.json()
            out["households"] = data.get("households")
            out["buildings"] = data.get("buildings")
            out["approval_date"] = data.get("approval_date")
            out["years_since_completion"] = data.get("years_since_completion")
            out["redevelop_stages"] = data.get("redevelop_stages") or []
            out["redevelop_yn"] = bool(out["redevelop_stages"])
            out["complex_type"] = data.get("complex_type")
            out["complex_name"] = data.get("complex_name")
            out["error"] = data.get("error")
            if out.get("approval_date") or out.get("households"):
                logger.info("✅ Render Playwright API 성공: approval=%s households=%s type=%s", out["approval_date"], out["households"], out["complex_type"])
                return out
            if out.get("error") and attempt == 1:
                logger.warning("Render API attempt 1 실패 (%s), 재시도...", out.get("error"))
                time.sleep(3)
                continue
        except Exception as e:
            out["error"] = str(e)
            logger.warning("Render Playwright API 실패 (attempt=%s): %s", attempt, e)
            if attempt == 1:
                time.sleep(3)
                continue
        break
    return out


def _fetch_node_households(complex_id: str) -> Dict[str, Any]:
    """
    Vercel 전용. /api/kb-households (Node Puppeteer) 호출로 세대수·동수만 조회.
    """
    import time
    import requests
    out = _empty_result(complex_id, error=None)
    out["source_url"] = f"{_BASE_URL}{complex_id}" if complex_id else None
    if not complex_id or str(complex_id).strip() == "":
        out["error"] = "complex_id 필요"
        return out
    base = os.getenv("VERCEL_URL", "").strip()
    if not base:
        out["error"] = "VERCEL_URL 없음 (Node API 미호출)"
        logger.warning("Node API 미호출: VERCEL_URL 없음")
        return out
    cid = str(complex_id).strip()
    url = f"https://{base.rstrip('/')}/api/kb-households?complex_id={cid}"
    logger.info("Node kb-households API 호출: complex_id=%s", cid)
    for attempt in (1, 2):
        try:
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=35)
            logger.info("Node API 응답 (attempt=%s): status=%s", attempt, r.status_code)
            r.raise_for_status()
            data = r.json()
            h = data.get("households")
            b = data.get("buildings")
            approval_date = data.get("approval_date")
            years_since = data.get("years_since_completion")
            err = data.get("error")
            if h is not None:
                out["households"] = int(h)
                logger.info("✅ Node Puppeteer API에서 세대수 추출: %s", out["households"])
            if b is not None:
                out["buildings"] = int(b)
                logger.info("✅ Node Puppeteer API에서 동수 추출: %s", out["buildings"])
            if approval_date is not None:
                out["approval_date"] = approval_date
                logger.info("✅ Node Puppeteer API에서 사용승인일 추출: %s", approval_date)
            if years_since is not None:
                out["years_since_completion"] = years_since
                logger.info("✅ Node Puppeteer API에서 년차 추출: %s년차", years_since)
            redevelop_stages = data.get("redevelop_stages") or []
            if redevelop_stages:
                out["redevelop_stages"] = redevelop_stages
                out["redevelop_yn"] = True
                logger.info("✅ Node Puppeteer API에서 재건축 단계 추출: %s", redevelop_stages)
            if out.get("households") is not None or out.get("buildings") is not None or out.get("approval_date") is not None or out.get("redevelop_stages"):
                out["error"] = None
            elif err:
                out["error"] = err
                logger.warning("Node API 세대수/동수 없음: %s", err)
            else:
                logger.warning("Node API 응답에 households/buildings 없음: %s", list(data.keys()))
            return out
        except requests.exceptions.HTTPError as e:
            try:
                body = (e.response.text or "")[:500]
                logger.warning("Node kb-households API HTTP 에러 (attempt=%s): %s, body=%s", attempt, e, body)
            except Exception:
                logger.warning("Node kb-households API HTTP 에러 (attempt=%s): %s", attempt, e)
            out["error"] = str(e)
            if attempt == 1 and e.response is not None and e.response.status_code >= 500:
                time.sleep(2)
                continue
            return out
        except Exception as e:
            logger.warning("Node kb-households API 호출 실패 (attempt=%s): %s", attempt, e)
            out["error"] = str(e)
            if attempt == 1:
                time.sleep(2)
                continue
            return out
    return out


def get_complex_extra_info(complex_id: int | str) -> Dict[str, Any]:
    """
    단지기본일련번호로 /c/ 스크래핑 후 재건축·세대수·동수·사용승인일 반환.

    - 로컬: Playwright 사용
    - Vercel/Render: PLAYWRIGHT_SCRAPER_URL 있으면 해당 API, Vercel일 때만 VERCEL_URL(Node API) fallback

    Returns:
        { redevelop_stages, households, buildings, approval_date, ... }
    """
    if _SCRAPER_DISABLED:
        cid = str(complex_id).strip() if complex_id else ""
        if os.getenv("PLAYWRIGHT_SCRAPER_URL"):
            return _fetch_render_playwright(cid)
        if os.getenv("VERCEL_URL"):
            return _fetch_node_households(cid)
        return _empty_result(complex_id, error="PLAYWRIGHT_SCRAPER_URL 또는 VERCEL_URL 없음")
    s = KBComplexScraper()
    return s.scrape(complex_id)
