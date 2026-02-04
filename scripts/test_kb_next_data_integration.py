# -*- coding: utf-8 -*-
"""kb_next_data 통합 테스트 - Vercel 환경 시뮬레이션"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Vercel 환경 시뮬레이션 (Playwright 비활성화, _next/data 사용)
os.environ["VERCEL"] = "1"


def main():
    from KB_api.kb_complex_scraper import get_complex_extra_info

    print("=== kb_next_data 통합 테스트 (complex_id=4024, 진흥아파트) ===\n")
    result = get_complex_extra_info("4024")
    print("결과:")
    print(f"  approval_date: {result.get('approval_date')}")
    print(f"  years_since_completion: {result.get('years_since_completion')}")
    print(f"  redevelop_stages: {result.get('redevelop_stages')}")
    print(f"  households: {result.get('households')}")
    print(f"  buildings: {result.get('buildings')}")
    print(f"  error: {result.get('error')}")

    if result.get("approval_date"):
        print("\n성공: 사용승인일 추출됨")
    else:
        print("\n실패: 사용승인일 없음")


if __name__ == "__main__":
    main()
