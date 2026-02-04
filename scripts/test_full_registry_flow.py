# -*- coding: utf-8 -*-
"""
등기부 PDF 분석 + KB API 연동 전체 플로우 테스트
- 조경대 260203.pdf (진흥아파트)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Vercel 비활성화 (로컬 Playwright 사용)
os.environ.pop("VERCEL", None)
os.environ.pop("VERCEL_ENV", None)


def main():
    from parsers.registry_parser import analyze_pdf
    from KB_api.kb_price_api import get_kb_price_from_registry

    pdf_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "pdf_Parsing_example",
        "조경대 260203.pdf"
    )
    if not os.path.exists(pdf_path):
        print(f"PDF 없음: {pdf_path}")
        return

    print("=== 1. 등기부 PDF 파싱 ===\n")
    result = analyze_pdf(pdf_path)
    address = result.부동산_주소
    area = result.면적
    print(f"주소: {address}")
    print(f"면적: {area}")

    print("\n=== 2. KB API 호출 (시세 + 사용승인일 + 재건축) ===\n")
    kb_result = get_kb_price_from_registry(address, area)
    if kb_result:
        print(f"KB시세 일반: {kb_result.get('kb_price'):,}만원" if kb_result.get('kb_price') else "없음")
        print(f"KB시세 하한: {kb_result.get('kb_price_min'):,}만원" if kb_result.get('kb_price_min') else "없음")
        print(f"사용승인일: {kb_result.get('approval_date')}")
        print(f"년차: {kb_result.get('years_since_completion')}년차")
        print(f"재건축: {kb_result.get('redevelop_yn')}")
        print(f"재건축 단계: {kb_result.get('redevelop_stages')}")
        print(f"세대수: {kb_result.get('households')}")
        print(f"complex_id: {kb_result.get('complex_id')}")
    else:
        print("KB API 결과 없음")

    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
