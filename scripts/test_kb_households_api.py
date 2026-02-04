# -*- coding: utf-8 -*-
"""
1) 로컬 Playwright로 get_complex_extra_info(98) 직접 테스트
2) (선택) 배포된 /api/kb-households 호출 테스트
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Vercel 비활성화 → 로컬 Playwright 사용
os.environ.pop("VERCEL", None)
os.environ.pop("VERCEL_ENV", None)


def test_local_playwright():
    """로컬 Playwright 스크래핑 테스트"""
    print("=== 1. 로컬 Playwright (get_complex_extra_info) 테스트 ===\n")
    from KB_api.kb_complex_scraper import get_complex_extra_info

    for cid in [98, 4024]:  # complex_id 98 (401 발생), 4024 (진흥아파트)
        print(f"complex_id={cid}:")
        result = get_complex_extra_info(cid)
        print(f"  approval_date: {result.get('approval_date')}")
        print(f"  years_since: {result.get('years_since_completion')}")
        print(f"  redevelop_stages: {result.get('redevelop_stages')}")
        print(f"  households: {result.get('households')}")
        print(f"  error: {result.get('error')}")
        print()


def test_deployed_api(base_url: str):
    """배포된 /api/kb-households 호출 테스트"""
    import requests

    print("=== 2. 배포 API (/api/kb-households) 호출 테스트 ===\n")
    url = f"{base_url.rstrip('/')}/api/kb-households?complex_id=98"
    print(f"URL: {url}\n")

    try:
        r = requests.get(
            url,
            headers={"User-Agent": "python-requests/2.32.5", "Accept": "application/json"},
            timeout=30,
        )
        print(f"Status: {r.status_code}")
        print(f"Headers: {dict(r.headers)}")
        print(f"Body: {r.text[:500]}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test_local_playwright()
    # 배포 URL이 있으면 API 호출도 테스트
    base = os.getenv("VERCEL_DEPLOYMENT_URL", "https://arena-mortgage-calculator-pkuxsa.vercel.app")
    test_deployed_api(base)
