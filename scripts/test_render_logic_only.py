# -*- coding: utf-8 -*-
"""Render 스크래핑 로직 (FastAPI 없이) 로컬 테스트"""
import re
from typing import Any, Dict, List, Optional, Tuple

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
        for pattern in [r"([\d,，\s]+)\s*세대", r"(\d{1,3}(?:[,，\s]\d{3})*)\s*세대", r"세대\s*[수:：]*\s*([\d,，]+)"]:
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

def test_scrape(complex_id: str):
    from playwright.sync_api import sync_playwright
    url = f"https://kbland.kr/c/{complex_id}"
    out = {"approval_date": None, "years_since_completion": None, "households": None, "buildings": None, "redevelop_stages": [], "error": None}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            )
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(10000)
            body_text = page.inner_text("body") or ""
            
            households, buildings = _parse_households_buildings(body_text)
            out["households"] = households
            out["buildings"] = buildings
            
            approval_date, years_since = _parse_approval_date(body_text)
            out["approval_date"] = approval_date
            out["years_since_completion"] = years_since
            
            stages = _parse_redevelop_stages(body_text)
            out["redevelop_stages"] = stages
            
            browser.close()
            print(f"body_text 샘플 (첫 500자):\n{body_text[:500]}\n")
    except Exception as e:
        out["error"] = str(e)
    return out

if __name__ == "__main__":
    result = test_scrape("4024")
    print("=== 로컬 테스트 결과 ===")
    print(f"approval_date: {result.get('approval_date')}")
    print(f"years_since: {result.get('years_since_completion')}")
    print(f"households: {result.get('households')}")
    print(f"redevelop_stages: {result.get('redevelop_stages')}")
    print(f"error: {result.get('error')}")
    print(f"\n=> {'✅ OK' if result.get('approval_date') else '❌ FAIL'}")
