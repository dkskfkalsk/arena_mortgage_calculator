# -*- coding: utf-8 -*-
"""권현주 250819.pdf 파싱 및 KB 시세 조회 테스트"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.registry_parser import analyze_pdf
from KB_api.kb_price_api import get_kb_price_from_registry

pdf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pdf_Parsing_example", "권현주 250819.pdf")
if not os.path.exists(pdf_path):
    print("PDF not found:", pdf_path)
    sys.exit(1)

doc = analyze_pdf(pdf_path)
print("=== 등기부 파싱 결과 ===")
print("부동산_주소:", repr(doc.부동산_주소))
print("면적:", repr(doc.면적))
print("층수정보:", repr(doc.층수정보))
print()

addr = doc.부동산_주소 or ""
area_str = doc.면적 or ""
if addr and area_str:
    print("=== KB 시세 조회 ===")
    result = get_kb_price_from_registry(addr, area_str)
    if result:
        print("KB 시세 조회 성공:", result.get("kb_price"), "만원")
    else:
        print("KB 시세 조회 실패 (None)")
else:
    print("주소 또는 면적 없음 - KB 조회 스킵")
