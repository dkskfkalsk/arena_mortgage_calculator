# -*- coding: utf-8 -*-
"""
주소 파싱 테스트 스크립트
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from KB_api.kb_price_api import KBPriceAPI

def test_address():
    """부천시 원미구 중동 주소 파싱 테스트"""
    
    address = "경기도 부천시 원미구 중동 1180-1 미리내마을 제939동 제2층 제203호"
    
    print("=" * 60)
    print("주소 파싱 테스트")
    print("=" * 60)
    print(f"주소: {address}")
    print()
    
    api = KBPriceAPI()
    
    # 주소 파싱
    parsed = api.parse_address(address)
    print("파싱 결과:")
    print(f"  region: {parsed.get('region')}")
    print(f"  district: {parsed.get('district')}")
    print(f"  dong: {parsed.get('dong')}")
    print()
    
    # 법정동코드 찾기
    dongcode = api.find_dongcode(address)
    print(f"법정동코드: {dongcode}")
    print()
    
    # 올바른 법정동코드
    expected_code = "4119210800"
    if dongcode == expected_code:
        print(f"✅ 올바른 법정동코드: {dongcode}")
    else:
        print(f"❌ 잘못된 법정동코드!")
        print(f"   예상: {expected_code} (경기도 부천시 원미구 중동)")
        print(f"   실제: {dongcode}")

if __name__ == "__main__":
    test_address()
