# -*- coding: utf-8 -*-
"""
KB /c/ 단지 페이지 스크래퍼
- kbland.kr/c/{단지기본일련번호} 에서 재건축 단계(조합설립인가 등) + 세대수·동수 추출
- Playwright 사용 (JS 렌더링 SPA 대응)
- Vercel 등에서는 Playwright 대신 requests로 HTML만 가져와 파싱 시도 (폴백)
"""

import os
import re
import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Vercel 등 Playwright 미지원 환경
if os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV"):
    _SCRAPER_DISABLED = True
else:
    _SCRAPER_DISABLED = False

_BASE_URL = "https://kbland.kr/c/"

# requests 폴백용 헤더 (브라우저처럼 보이게)
_REQUESTS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://kbland.kr/",
}
# Next.js 데이터 JSON 요청용
_NEXT_DATA_HEADERS = {
    **_REQUESTS_HEADERS,
    "Accept": "application/json",
}
_NEXT_DATA_BASE = "https://kbland.kr/_next/data"


def _empty_result(complex_id: Any, error: Optional[str] = None) -> Dict[str, Any]:
    return {
        "redevelop_stages": [],
        "households": None,
        "buildings": None,
        "redevelop_yn": False,
        "complex_name": None,
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

    # 세대: 여러 패턴 시도 (쉼표/공백/전각 포함)
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


def _parse_redevelop_stages_from_text(text: str) -> List[Dict[str, Any]]:
    """'N단계 단계명 YYYY.MM.DD' 패턴 추출."""
    stages = []
    # 예: "5단계 조합설립인가 2017.06.01", "6단계 사업시행인가 2019.03.15"
    for m in re.finditer(r"(\d+)단계\s*([가-힣]+)\s*(\d{4}\.\d{2}\.\d{2})", text):
        stages.append({
            "step": int(m.group(1)),
            "name": m.group(2),
            "date": m.group(3),
        })
    return stages


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
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                # SPA 렌더링 대기 (세대수 등 기본정보가 늦게 뜨는 경우 대비)
                try:
                    page.wait_for_timeout(3000)
                except Exception:
                    pass
                body_text = page.inner_text("body") or ""

                # 1) 재건축 단계
                stages = _parse_redevelop_stages_from_text(body_text)
                out["redevelop_stages"] = stages
                out["redevelop_yn"] = len(stages) > 0

                # 2) 세대수·동수 (기본정보 블록)
                households, buildings = _parse_households_buildings(body_text)
                out["households"] = households
                out["buildings"] = buildings

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


def _find_num_in_obj(obj: Any, target_keys: List[str], max_val: int = 100000) -> Optional[int]:
    """중첩 dict/list에서 target_keys 중 하나에 해당하는 숫자 값 추출."""
    seen: set = set()

    def _find(o: Any) -> Optional[int]:
        if o is None or id(o) in seen:
            return None
        seen.add(id(o))
        if isinstance(o, dict):
            for k, v in o.items():
                if k in target_keys and v is not None:
                    try:
                        n = int(v) if isinstance(v, (int, float)) else int(str(v).replace(",", ""))
                        if 1 <= n <= max_val:
                            return n
                    except (ValueError, TypeError):
                        pass
                if isinstance(v, (dict, list)):
                    r = _find(v)
                    if r is not None:
                        return r
        elif isinstance(o, list):
            for item in o:
                r = _find(item)
                if r is not None:
                    return r
        return None

    return _find(obj)


def _get_next_build_id(session: Any, complex_id: Optional[str] = None) -> Optional[str]:
    """Next.js buildId 추출: 메인 페이지 또는 /c/ 페이지 HTML에서 __NEXT_DATA__.buildId."""
    import json
    urls = ["https://kbland.kr/"]
    if complex_id:
        urls.append(f"https://kbland.kr/c/{complex_id}")
    for url in urls:
        try:
            r = session.get(url, headers=_REQUESTS_HEADERS, timeout=10)
            r.raise_for_status()
            text = r.text or ""
            m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>([^<]+)</script>', text)
            if not m:
                m = re.search(r'<script[^>]*type=["\']application/json["\'][^>]*id=["\']__NEXT_DATA__["\'][^>]*>([^<]+)</script>', text)
            if m:
                data = json.loads(m.group(1))
                bid = data.get("buildId")
                if isinstance(bid, str) and len(bid) > 0:
                    return bid
        except Exception as e:
            logger.debug("buildId 추출 실패 %s: %s", url, e)
    return None


def _fetch_next_data_json(session: Any, build_id: str, complex_id: str) -> Optional[Dict[str, Any]]:
    """Next.js 데이터 URL: /_next/data/{buildId}/c/{complex_id}.json → pageProps 포함 (브라우저에서 보이는 세대수 등)."""
    url = f"{_NEXT_DATA_BASE}/{build_id}/c/{complex_id}.json"
    try:
        r = session.get(url, headers=_NEXT_DATA_HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug("_next/data JSON 요청 실패: %s", e)
    return None


def _fetch_with_requests(complex_id: int | str) -> Dict[str, Any]:
    """
    Vercel 등 Playwright 불가 환경에서 requests로 세대수·동수 추출.
    1) Next.js _next/data/{buildId}/c/{id}.json 호출 (브라우저와 동일한 데이터)
    2) 실패 시 /c/ 페이지 HTML에서 __NEXT_DATA__ 또는 정규식 파싱
    """
    out = _empty_result(complex_id, error=None)
    out["source_url"] = f"{_BASE_URL}{complex_id}" if complex_id else None
    if not complex_id or str(complex_id).strip() == "":
        out["error"] = "complex_id 필요"
        return out
    try:
        import requests
        import json
        cid = str(complex_id).strip()
        session = requests.Session()

        # 1) Next.js 데이터 URL 시도 (kbland.kr/c/15385 에서 보이는 세대수와 동일한 소스)
        build_id = _get_next_build_id(session, cid)
        if build_id:
            next_data = _fetch_next_data_json(session, build_id, cid)
            if next_data:
                h_keys = ["세대수", "households", "totHshldCnt", "hshldCnt", "총세대수", "totalHouseholdCnt"]
                b_keys = ["동수", "buildings", "bldgCnt", "totBldgCnt", "총동수"]
                households = _find_num_in_obj(next_data, h_keys, 100000)
                buildings = _find_num_in_obj(next_data, b_keys, 1000)
                if households is not None:
                    out["households"] = households
                    logger.info("requests 폴백(_next/data): 세대수 %s 추출", households)
                if buildings is not None:
                    out["buildings"] = buildings
                    logger.info("requests 폴백(_next/data): 동수 %s 추출", buildings)

        # 2) 아직 없으면 /c/ 페이지 HTML에서 __NEXT_DATA__ 또는 텍스트 파싱
        if out["households"] is None or out["buildings"] is None:
            url = f"{_BASE_URL}{cid}"
            r = session.get(url, headers=_REQUESTS_HEADERS, timeout=15)
            r.raise_for_status()
            text = r.text or ""
            households = out.get("households")
            buildings = out.get("buildings")
            if households is None or buildings is None:
                h_b_from_html = _parse_households_buildings(text)
                if households is None:
                    households = h_b_from_html[0]
                if buildings is None:
                    buildings = h_b_from_html[1]
            if households is None and "__NEXT_DATA__" in text:
                m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>([^<]+)</script>', text)
                if not m:
                    m = re.search(r'<script[^>]*type=["\']application/json["\'][^>]*id=["\']__NEXT_DATA__["\'][^>]*>([^<]+)</script>', text)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        h_keys = ["세대수", "households", "totHshldCnt", "hshldCnt", "총세대수"]
                        b_keys = ["동수", "buildings", "bldgCnt", "totBldgCnt"]
                        if households is None:
                            households = _find_num_in_obj(data, h_keys, 100000)
                        if buildings is None:
                            buildings = _find_num_in_obj(data, b_keys, 1000)
                    except Exception:
                        pass
            if households is None:
                for pattern in [
                    r'"세대수"\s*:\s*["\']?(\d+)',
                    r'"households"\s*:\s*["\']?(\d+)',
                    r'"totHshldCnt"\s*:\s*(\d+)',
                    r'"hshldCnt"\s*:\s*(\d+)',
                ]:
                    m = re.search(pattern, text, re.I)
                    if m:
                        val = int(m.group(1))
                        if 1 <= val <= 100000:
                            households = val
                            break
            if households is not None and out.get("households") is None:
                out["households"] = households
                logger.info("requests 폴백(HTML): 세대수 %s 추출", households)
            if buildings is not None and out.get("buildings") is None:
                out["buildings"] = buildings
                logger.info("requests 폴백(HTML): 동수 %s 추출", buildings)
            if not out["households"] and not out["buildings"]:
                out["error"] = "HTML에서 세대수/동수 미발견 (SPA는 JS 렌더링 필요)"
    except Exception as e:
        out["error"] = str(e)
        logger.warning("requests 폴백 실패: %s", e)
    return out


def get_complex_extra_info(complex_id: int | str) -> Dict[str, Any]:
    """
    단지기본일련번호로 /c/ 스크래핑 후 재건축·세대수·동수 반환.

    Args:
        complex_id: 단지기본일련번호 (get_complex_list / get_kb_price 의 단지 항목과 동일)

    Returns:
        {
            "redevelop_stages": [{"step":5,"name":"조합설립인가","date":"2017.06.01"}, ...],
            "households": 1584,
            "buildings": 24,
            "redevelop_yn": True,
            "complex_name": "시범",
            "source_url": "https://kbland.kr/c/2171",
            "error": None,
        }
    """
    if _SCRAPER_DISABLED:
        return _fetch_with_requests(complex_id)
    s = KBComplexScraper()
    return s.scrape(complex_id)
