# -*- coding: utf-8 -*-
"""
Render용 Playwright 스크래핑 API
kbland.kr/c/{complex_id} 에서 사용승인일·재건축·세대수 추출
"""
import os
import re
import logging
from pathlib import Path

# Render: 빌드 시 프로젝트 내 ./browsers 에 설치. 배포 시 경로 지정
if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
    _browsers_dir = Path(__file__).parent / "browsers"
    if _browsers_dir.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_browsers_dir.resolve())
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Header, HTTPException, Query

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="KB 단지 스크래퍼 API", version="1.0")

_BASE_URL = "https://kbland.kr/c/"


def _parse_households_buildings(text: str) -> Tuple[Optional[int], Optional[int]]:
    households, buildings = None, None

    def _parse_number(s: str) -> Optional[int]:
        if not s:
            return None
        s = s.replace(",", "").replace("，", "").replace(" ", "").replace("\u00a0", "")
        try:
            return int(s)
        except ValueError:
            return None

    m = re.search(r"(\d{1,5})\s*세대\s*\(\s*임대\s*\d+", text)
    if m:
        val = _parse_number(m.group(1))
        if val is not None and 1 <= val <= 100000:
            households = val
    if households is None:
        for pattern in [
            r"([\d,，\s]+)\s*세대",
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
    approval_date, years_since = None, None
    m = re.search(r"사용\s*승인\s*일\s*(\d{4}\.\d{2}\.\d{2})\s*(?:\(\s*(\d+)\s*년\s*차\s*\))?", text)
    if m:
        approval_date = m.group(1)
        if m.lastindex >= 2 and m.group(2):
            try:
                years_since = int(m.group(2))
            except ValueError:
                pass
    return approval_date, years_since


def _parse_redevelop_stages(text: str) -> List[Dict[str, Any]]:
    stages = []
    seen_steps = set()
    for m in re.finditer(r"(\d+)단계\s*([가-힣]+)['\s]*(\d{4}\.\d{2}\.\d{2})", text):
        step = int(m.group(1))
        if step not in seen_steps:
            seen_steps.add(step)
            stages.append({"step": step, "name": m.group(2), "date": m.group(3)})
    stages.sort(key=lambda x: x["step"])
    return stages


def _scrape(complex_id: str) -> Dict[str, Any]:
    out = {
        "households": None,
        "buildings": None,
        "approval_date": None,
        "years_since_completion": None,
        "redevelop_stages": [],
        "redevelop_yn": False,
        "error": None,
    }
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        out["error"] = "playwright 미설치"
        return out

    url = f"{_BASE_URL}{complex_id}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=20000)
            # Vue SPA 렌더링 대기 (사용승인일 등 기본정보 노출)
            page.wait_for_timeout(5000)
            body_text = page.inner_text("body") or ""

            households, buildings = _parse_households_buildings(body_text)
            out["households"] = households
            out["buildings"] = buildings

            approval_date, years_since = _parse_approval_date(body_text)
            out["approval_date"] = approval_date
            out["years_since_completion"] = years_since

            stages = _parse_redevelop_stages(body_text)
            out["redevelop_stages"] = stages
            out["redevelop_yn"] = len(stages) > 0

            browser.close()
        logger.info("scrape ok: complex_id=%s approval=%s households=%s", complex_id, out["approval_date"], out["households"])
    except Exception as e:
        out["error"] = str(e)
        logger.warning("scrape fail: %s", e)
    return out


@app.get("/")
def root():
    return {"status": "ok", "service": "kb-playwright-scraper"}


@app.get("/scrape")
def scrape(
    complex_id: str = Query(..., description="단지기본일련번호"),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
):
    token = os.environ.get("PLAYWRIGHT_SCRAPER_TOKEN", "").strip()
    if token:
        incoming = (x_internal_token or "").strip()
        if incoming != token:
            raise HTTPException(status_code=401, detail="X-Internal-Token 불일치")

    if not complex_id or not str(complex_id).strip():
        raise HTTPException(status_code=400, detail="complex_id 필요")

    result = _scrape(str(complex_id).strip())
    return result


@app.get("/health")
def health():
    return {"status": "ok"}
