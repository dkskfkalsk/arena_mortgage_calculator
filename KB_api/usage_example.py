# -*- coding: utf-8 -*-
"""
KB 시세 API 사용 예제

이 모듈은 등기부 파서와 독립적으로 작동하며,
등기부에서 추출한 주소와 면적을 받아서 KB 시세를 조회합니다.
"""

import sys
import os

# 프로젝트 루트를 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from KB_api.kb_price_api import KBPriceAPI, get_kb_price_from_registry


# 예제 1: 기본 사용법
def example_basic_usage():
    """기본 사용법 예제"""
    print("=== 예제 1: 기본 사용법 ===\n")
    
    # KBPriceAPI 인스턴스 생성
    api = KBPriceAPI()
    
    # 주소와 면적으로 KB 시세 조회
    result = api.get_kb_price(
        address="서울특별시 강남구 대치동",
        area=84.93  # m² 단위
    )
    
    if result:
        print(f"단지명: {result['complex_name']}")
        print(f"KB시세: {result['kb_price_raw']} ({result['kb_price']}만원)")
        print(f"면적: {result['area']}m²")
        print(f"평수: {result['pyeong']}평")
        print(f"타입: {result['type']}")
    else:
        print("KB 시세를 찾을 수 없습니다.")


# 예제 2: 등기부 파서와 연동
def example_with_registry_parser():
    """등기부 파서와 연동 예제"""
    print("\n=== 예제 2: 등기부 파서와 연동 ===\n")
    
    # 등기부 파서에서 추출한 정보 (가정)
    registry_address = "서울특별시 강남구 대치동 123"
    registry_area = "84.93㎡"  # 등기부에서 추출한 형식 그대로 사용 가능
    
    # 편의 함수 사용
    result = get_kb_price_from_registry(registry_address, registry_area)
    
    if result:
        print(f"등기부 주소: {registry_address}")
        print(f"등기부 면적: {registry_area}")
        print()
        print(f"✅ KB 시세 조회 성공:")
        print(f"   단지명: {result['complex_name']}")
        print(f"   KB시세: {result['kb_price_raw']}")
        print(f"   면적: {result['area']}m²")
    else:
        print("KB 시세를 찾을 수 없습니다.")


# 예제 3: 단지명이 있는 경우 (더 정확한 매칭)
def example_with_complex_name():
    """단지명이 있는 경우 예제"""
    print("\n=== 예제 3: 단지명이 있는 경우 ===\n")
    
    api = KBPriceAPI()
    
    # 등기부나 다른 소스에서 단지명도 알 수 있는 경우
    result = api.get_kb_price(
        address="서울특별시 강남구 대치동",
        area=84.93,
        complex_name="대치아이파크"  # 단지명이 있으면 더 정확한 매칭
    )
    
    if result:
        print(f"단지명: {result['complex_name']}")
        print(f"KB시세: {result['kb_price_raw']}")
    else:
        print("KB 시세를 찾을 수 없습니다.")


# 예제 4: 등기부 파서 결과를 직접 사용
def example_with_registry_document():
    """등기부 파서 결과를 직접 사용하는 예제"""
    print("\n=== 예제 4: 등기부 파서 결과 직접 사용 ===\n")
    
    # 등기부 파서 사용 (실제 사용 시)
    # from parsers.registry_parser import RegistryParser
    # parser = RegistryParser()
    # doc = parser.parse("등기부.pdf")
    
    # 가정: 등기부 파서 결과
    doc_address = "서울특별시 강남구 대치동 123"
    doc_area = "84.93㎡"
    
    # KB 시세 조회
    api = KBPriceAPI()
    
    # 면적에서 숫자만 추출
    import re
    area_match = re.search(r'([\d.]+)', doc_area)
    area_float = float(area_match.group(1)) if area_match else 0
    
    if area_float > 0:
        result = api.get_kb_price(
            address=doc_address,
            area=area_float
        )
        
        if result:
            print(f"등기부 주소: {doc_address}")
            print(f"등기부 면적: {doc_area}")
            print()
            print(f"✅ KB 시세: {result['kb_price_raw']}")
            print(f"   단지명: {result['complex_name']}")
            
            # 이제 이 결과를 다른 곳에서 사용할 수 있습니다
            kb_price_manwon = result['kb_price']  # 만원 단위
            print(f"\n💡 사용 예: KB시세 = {kb_price_manwon:,.0f}만원")
        else:
            print("KB 시세를 찾을 수 없습니다.")
    else:
        print("면적 정보가 올바르지 않습니다.")


if __name__ == "__main__":
    example_basic_usage()
    example_with_registry_parser()
    example_with_complex_name()
    example_with_registry_document()
