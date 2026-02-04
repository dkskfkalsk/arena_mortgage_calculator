# -*- coding: utf-8 -*-
"""
스크래핑 전체 흐름 테스트
1) 로컬 Playwright  2) Render API
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COMPLEX_ID = "4024"  # 진흥아파트

def test_local():
    """로컬 Playwright (VERCEL 없음)"""
    for k in ("VERCEL", "VERCEL_ENV"):
        os.environ.pop(k, None)
    from KB_api.kb_complex_scraper import get_complex_extra_info
    r = get_complex_extra_info(COMPLEX_ID)
    print("[1] 로컬 Playwright:")
    print(f"    approval_date: {r.get('approval_date')}")
    print(f"    years_since: {r.get('years_since_completion')}")
    print(f"    households: {r.get('households')}")
    print(f"    redevelop_stages: {r.get('redevelop_stages')}")
    print(f"    error: {r.get('error')}")
    ok = r.get("approval_date") or r.get("households")
    print(f"    => {'OK' if ok else 'FAIL'}")
    return bool(ok)

def test_render():
    """Render API 직접 호출"""
    import requests
    url = os.environ.get("PLAYWRIGHT_SCRAPER_URL", "https://arena-mortgage-calculator.onrender.com").rstrip("/")
    token = os.environ.get("PLAYWRIGHT_SCRAPER_TOKEN", "3a617a13e9ee165aed1205690421f11b")
    req_url = f"{url}/scrape?complex_id={COMPLEX_ID}"
    headers = {"Accept": "application/json", "X-Internal-Token": token}
    print(f"\n[2] Render API ({url}):")
    try:
        r = requests.get(req_url, headers=headers, timeout=60)
        data = r.json()
        print(f"    status: {r.status_code}")
        print(f"    approval_date: {data.get('approval_date')}")
        print(f"    years_since: {data.get('years_since_completion')}")
        print(f"    households: {data.get('households')}")
        print(f"    redevelop_stages: {data.get('redevelop_stages')}")
        print(f"    error: {data.get('error')}")
        ok = data.get("approval_date") or data.get("households")
        print(f"    => {'OK' if ok else 'FAIL'}")
        return bool(ok)
    except Exception as e:
        print(f"    => FAIL: {e}")
        return False

def test_vercel_flow():
    """Vercel 환경 시뮬레이션 (Render API 사용)"""
    os.environ["VERCEL"] = "1"
    os.environ["PLAYWRIGHT_SCRAPER_URL"] = os.environ.get("PLAYWRIGHT_SCRAPER_URL", "https://arena-mortgage-calculator.onrender.com")
    os.environ["PLAYWRIGHT_SCRAPER_TOKEN"] = os.environ.get("PLAYWRIGHT_SCRAPER_TOKEN", "3a617a13e9ee165aed1205690421f11b")
    from KB_api.kb_complex_scraper import get_complex_extra_info
    r = get_complex_extra_info(COMPLEX_ID)
    print("\n[3] Vercel 시뮬레이션 (get_complex_extra_info -> Render):")
    print(f"    approval_date: {r.get('approval_date')}")
    print(f"    households: {r.get('households')}")
    print(f"    redevelop_stages: {r.get('redevelop_stages')}")
    print(f"    error: {r.get('error')}")
    ok = r.get("approval_date") or r.get("households")
    print(f"    => {'OK' if ok else 'FAIL'}")
    return bool(ok)

if __name__ == "__main__":
    print("=== 스크래핑 흐름 테스트 (complex_id=4024) ===\n")
    t1 = test_local()
    t2 = test_render()
    t3 = test_vercel_flow()
    print("\n=== 요약 ===")
    print(f"  로컬 Playwright: {'OK' if t1 else 'FAIL'}")
    print(f"  Render API:      {'OK' if t2 else 'FAIL'}")
    print(f"  Vercel 흐름:     {'OK' if t3 else 'FAIL'}")
