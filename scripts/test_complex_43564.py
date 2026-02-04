# -*- coding: utf-8 -*-
"""complex_id=43564 스크래핑 테스트"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from KB_api.kb_complex_scraper import get_complex_extra_info

if __name__ == "__main__":
    print("\n=== complex_id=43564 스크래핑 테스트 ===")
    result = get_complex_extra_info("43564")
    print(f"approval_date: {result.get('approval_date')}")
    print(f"households: {result.get('households')}")
    print(f"buildings: {result.get('buildings')}")
    print(f"complex_type: {result.get('complex_type')}")
    print(f"redevelop_yn: {result.get('redevelop_yn')}")
    print(f"redevelop_stages: {result.get('redevelop_stages')}")
    print(f"error: {result.get('error')}")
    
    print("\n=== complex_id=4024 스크래핑 테스트 (조경대) ===")
    result2 = get_complex_extra_info("4024")
    print(f"approval_date: {result2.get('approval_date')}")
    print(f"households: {result2.get('households')}")
    print(f"complex_type: {result2.get('complex_type')}")
    print(f"redevelop_yn: {result2.get('redevelop_yn')}")
    print(f"redevelop_stages: {result2.get('redevelop_stages')}")
    print(f"error: {result2.get('error')}")
