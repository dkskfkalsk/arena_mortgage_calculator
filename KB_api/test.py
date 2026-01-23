# -*- coding: utf-8 -*-
"""
KB 시세 API 테스트 스크립트
"""

import os
import sys

# 프로젝트 루트를 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from KB_api.kb_price_api import KBPriceAPI, get_kb_price_from_registry


def test_address_parsing():
    """주소 파싱 테스트"""
    print("=== 주소 파싱 테스트 ===\n")
    
    api = KBPriceAPI()
    
    test_addresses = [
        "서울특별시 강남구 대치동 123",
        "서울 강남구 역삼동 456",
        "경기도 성남시 분당구 정자동 789",
        "서울특별시 서초구 반포동 101",
    ]
    
    for addr in test_addresses:
        parsed = api.parse_address(addr)
        dongcode = api.find_dongcode(addr)
        print(f"주소: {addr}")
        print(f"파싱 결과: {parsed}")
        print(f"법정동코드: {dongcode}")
        print()


def test_kb_price_lookup():
    """KB 시세 조회 테스트"""
    print("=== KB 시세 조회 테스트 ===\n")
    
    api = KBPriceAPI()
    
    # 테스트 케이스
    test_cases = [
        {
            "address": "서울특별시 강남구 대치동",
            "area": 84.93,
            "complex_name": None
        },
        {
            "address": "서울특별시 서초구 반포동",
            "area": 114.93,
            "complex_name": None
        },
    ]
    
    for case in test_cases:
        print(f"주소: {case['address']}")
        print(f"면적: {case['area']}m²")
        print()
        
        result = api.get_kb_price(
            address=case["address"],
            area=case["area"],
            complex_name=case.get("complex_name")
        )
        
        if result:
            print("✅ 조회 성공:")
            print(f"   단지명: {result['complex_name']}")
            print(f"   KB시세: {result['kb_price_raw']}")
            print(f"   면적: {result['area']}m²")
            print(f"   평수: {result['pyeong']}평")
            print(f"   타입: {result['type']}")
        else:
            print("❌ 조회 실패")
        
        print("\n" + "="*50 + "\n")


def test_from_registry():
    """등기부 정보로 KB 시세 조회 테스트"""
    print("=== 등기부 정보로 KB 시세 조회 테스트 ===\n")
    
    test_cases = [
        {
            "address": "서울특별시 강남구 대치동 123",
            "area": "84.93㎡"
        },
        {
            "address": "서울특별시 서초구 반포동 456",
            "area": "114.93㎡"
        },
    ]
    
    for case in test_cases:
        print(f"주소: {case['address']}")
        print(f"면적: {case['area']}")
        print()
        
        result = get_kb_price_from_registry(case["address"], case["area"])
        
        if result:
            print("✅ 조회 성공:")
            print(f"   단지명: {result['complex_name']}")
            print(f"   KB시세: {result['kb_price_raw']}")
            print(f"   면적: {result['area']}m²")
        else:
            print("❌ 조회 실패")
        
        print("\n" + "="*50 + "\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="KB 시세 API 테스트")
    parser.add_argument("--test", choices=["parse", "lookup", "registry", "all"], 
                       default="all", help="테스트 종류 선택")
    
    args = parser.parse_args()
    
    if args.test == "parse" or args.test == "all":
        test_address_parsing()
    
    if args.test == "lookup" or args.test == "all":
        test_kb_price_lookup()
    
    if args.test == "registry" or args.test == "all":
        test_from_registry()
