# -*- coding: utf-8 -*-
"""
김경연 PDF KB시세 조회 디버깅
"""
import sys
sys.path.insert(0, '.')

from parsers.registry_parser import analyze_pdf
from KB_api.kb_price_api import get_kb_price_from_registry, KBPriceAPI

print("=" * 60)
print("김경연 251230.pdf KB시세 조회 테스트")
print("=" * 60)

# 1. PDF 파싱
result = analyze_pdf('pdf_Parsing_example/김경연 251230.pdf')
print(f"\n[1단계] PDF 파싱 결과:")
print(f"  주소: {result.부동산_주소}")
print(f"  면적: {result.면적}")

# 2. 주소 확인
address = result.부동산_주소
print(f"\n[2단계] 주소:")
print(f"  원본 주소: {address}")

# 3. KB API로 법정동코드 조회 (내부에서 자동 파싱됨)
print(f"\n[3단계] KB API 조회 중...")
dongcode = None

# 4. 직접 단지 조회 (c/871)
api = KBPriceAPI()
print(f"\n[4단계] kbland.kr/c/871 단지 정보 조회:")
complex_info = api.get_complex_info('871')
if complex_info:
    print(f"  단지명: {complex_info.get('단지명')}")
    print(f"  주소: {complex_info.get('법정동주소명')}")
    print(f"  법정동코드: {complex_info.get('법정동코드')}")
    dongcode = complex_info.get('법정동코드')

# 5. KB 시세 조회
print(f"\n[5단계] KB 시세 조회:")
kb_result = get_kb_price_from_registry(address, result.면적)

if kb_result:
    print(f"  KB시세: {kb_result.get('kb_price')}만원")
    print(f"  단지명: {kb_result.get('complex_name')}")
    print(f"  단지ID: {kb_result.get('complex_id')}")
    print(f"  면적: {kb_result.get('area')}㎡")
else:
    print(f"  ❌ KB시세를 찾을 수 없음")

# 6. 해당 법정동코드의 단지 목록 확인
if dongcode:
    print(f"\n[6단계] 법정동코드 {dongcode}의 단지 목록:")
    complexes = api.get_complex_list(dongcode)
    
    if complexes:
        print(f"  총 {len(complexes)}개 단지 발견")
        print(f"\n  단지명에 '한신' 또는 '플러스타운' 포함된 단지:")
        for c in complexes:
            complex_name = c.get('단지명', '')
            if '한신' in complex_name or '플러스타운' in complex_name:
                print(f"    - {complex_name} (ID: {c.get('단지기본일련번호')})")
                print(f"      주소: {c.get('법정동주소명', '')}")
