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

# Vercel 등 Playwright 미지원 환경
if os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV"):
    _SCRAPER_DISABLED = True
else:
    _SCRAPER_DISABLED = False

_BASE_URL = "https://kbland.kr/c/"


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
            err = data.get("error")
            if h is not None:
                out["households"] = int(h)
                logger.info("✅ Node Puppeteer API에서 세대수 추출: %s", out["households"])
            if b is not None:
                out["buildings"] = int(b)
                logger.info("✅ Node Puppeteer API에서 동수 추출: %s", out["buildings"])
            if out.get("households") is not None or out.get("buildings") is not None:
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
        if os.getenv("VERCEL_URL"):
            return _fetch_node_households(str(complex_id).strip())
        return _empty_result(complex_id, error="VERCEL_URL 없음 (Node API 미호출)")
    s = KBComplexScraper()
    return s.scrape(complex_id)
