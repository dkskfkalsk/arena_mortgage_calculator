# -*- coding: utf-8 -*-
"""
Render용 Playwright 스크래핑 API
kbland.kr/c/{complex_id} 에서 사용승인일·재건축·세대수 추출
"""
import os
import re
import logging
import time
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

# 메모리 캐시 (complex_id -> (결과, 캐시 시간))
_CACHE = {}
_CACHE_TTL = 3600  # 1시간


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
    """로컬 kb_complex_scraper와 동일: 'N단계 단계명 YYYY.MM.DD' 패턴 (개행+1자+날짜)."""
    stages = []
    seen_steps = set()
    # 로컬과 동일: "N단계한글이름\n'YYYY.MM.DD" (개행 뒤 아무 문자 1자 + 날짜)
    pattern = r"(\d+)단계([가-힣]+)\n.(\d{4}\.\d{2}\.\d{2})"
    for m in re.finditer(pattern, text):
        step = int(m.group(1))
        name = m.group(2)
        date = m.group(3)
        if step not in seen_steps:
            seen_steps.add(step)
            stages.append({"step": step, "name": name, "date": date})
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


def _scrape(complex_id: str) -> Dict[str, Any]:
    # 캐시 확인
    if complex_id in _CACHE:
        cached_data, cached_time = _CACHE[complex_id]
        if time.time() - cached_time < _CACHE_TTL:
            logger.info(f"✅ 캐시 히트: {complex_id} (나이: {int(time.time() - cached_time)}초)")
            return cached_data.copy()
    
    out = {
        "households": None,
        "buildings": None,
        "approval_date": None,
        "years_since_completion": None,
        "redevelop_stages": [],
        "redevelop_yn": False,
        "complex_type": None,  # 주상복합, 아파트, 오피스텔 등
        "complex_name": None,
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
            page = browser.new_page(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            )
            # 로컬과 동일: kbland.kr/c/{id} 접속 후 대기·스크롤로 기본정보 로드
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Vue SPA API 호출·렌더링 대기 (재건축 정보 탭 로드 포함) - 로컬과 동일 5초
            page.wait_for_timeout(5000)
            # 페이지 스크롤로 추가 컨텐츠 로드 유도 (재건축 정보 등)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(3000)
            # 다시 맨 위로 (전체 컨텐츠 확보)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(2000)
            body_text = page.inner_text("body") or ""

            logger.info("body_text 길이: %d, 샘플: %s", len(body_text), body_text[:200] if body_text else "(empty)")

            # 1) 재건축 단계 (로컬과 동일 순서)
            stages = _parse_redevelop_stages(body_text)
            out["redevelop_stages"] = stages
            out["redevelop_yn"] = len(stages) > 0
            if stages:
                logger.info("재건축 단계 발견: %s", stages)

            # 2) 세대수·동수 (기본정보 블록)
            households, buildings = _parse_households_buildings(body_text)
            out["households"] = households
            out["buildings"] = buildings

            # 2-1) 사용승인일 (기본정보)
            approval_date, years_since = _parse_approval_date(body_text)
            out["approval_date"] = approval_date
            out["years_since_completion"] = years_since

            # 2-2) 단지유형
            complex_type = _parse_complex_type(body_text)
            out["complex_type"] = complex_type
            if complex_type:
                logger.info("단지유형 발견: %s", complex_type)

            # 3) 단지명 (페이지 제목에서 추출 - 로컬과 동일)
            title = page.title() or ""
            if "|" in title:
                out["complex_name"] = title.split("|")[0].strip().strip("'\" ")
            else:
                out["complex_name"] = None

            browser.close()
        logger.info("scrape ok: complex_id=%s approval=%s households=%s redevelop=%s type=%s", complex_id, out["approval_date"], out["households"], len(stages), out["complex_type"])
        
        # 캐시 저장 (에러가 없고 최소한의 데이터가 있을 때만)
        if not out["error"] and (out["approval_date"] or out["households"]):
            _CACHE[complex_id] = (out.copy(), time.time())
            logger.info(f"💾 캐시 저장: {complex_id}")
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
