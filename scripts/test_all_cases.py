# -*- coding: utf-8 -*-
"""
모든 케이스 테스트 (district 파싱 개선 후)
"""
import sys
sys.path.insert(0, '.')

from parsers.registry_parser import analyze_pdf
from KB_api.kb_price_api import get_kb_price_from_registry

test_cases = [
    ("권현주 250819.pdf", "15385"),  # 경기 김포시 양촌읍
    ("진석태 등기 1 (2).pdf", "14094"),  # 부산 동래구 온천동
    ("김경연 251230.pdf", "871"),  # 서울 구로구 오류동
]

print("=" * 70)
print("전체 케이스 테스트 (district 파싱 개선)")
print("=" * 70)

for pdf_name, expected_id in test_cases:
    print(f"\n[TEST] {pdf_name}")
    print("-" * 70)
    
    try:
        r = analyze_pdf(f'pdf_Parsing_example/{pdf_name}')
        print(f"Address: {r.부동산_주소}")
        print(f"Area: {r.면적}")
        
        kb = get_kb_price_from_registry(r.부동산_주소, r.면적)
        if kb:
            actual_id = str(kb.get('complex_id', ''))
            status = "OK" if actual_id == expected_id else "FAIL"
            print(f"KB price: {kb.get('kb_price')} man-won")
            print(f"Complex ID: {actual_id} (expected: {expected_id}) [{status}]")
            print(f"Complex name: {kb.get('complex_name')}")
        else:
            print(f"NO KB PRICE FOUND (expected ID: {expected_id}) [FAIL]")
    except Exception as e:
        print(f"ERROR: {e}")

print("\n" + "=" * 70)
print("Test completed")
print("=" * 70)
