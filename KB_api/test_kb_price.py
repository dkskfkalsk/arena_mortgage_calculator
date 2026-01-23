# -*- coding: utf-8 -*-
"""
KB 시세 조회 테스트 스크립트
"""

from KB_api.kb_price_api import KBPriceAPI
import urllib.parse

def test_kb_price():
    """KB 시세 조회 테스트"""
    
    # 테스트 주소
    address = "경기도 부천시 원미구 중동 1180-1 미리내마을 제939동 제2층 제203호"
    area = 64.08  # m²
    
    print("=" * 60)
    print("KB 시세 조회 테스트")
    print("=" * 60)
    print(f"주소: {address}")
    print(f"면적: {area}m²")
    print()
    
    # KB API 인스턴스 생성
    api = KBPriceAPI()
    
    # 1. 법정동코드 찾기
    print("1단계: 법정동코드 찾기")
    dongcode = api.find_dongcode(address)
    
    if not dongcode:
        print("❌ 법정동코드를 찾을 수 없습니다.")
        return
    
    print(f"✅ 법정동코드: {dongcode}")
    print()
    
    # 2. API URL 생성
    print("2단계: API URL 생성")
    base_url = "https://api.kbland.kr/land-price/price/fastPriceInfo"
    params = {
        "법정동코드": dongcode,
        "유형": "1",  # 아파트
        "거래유형": "0"  # 매매
    }
    
    query_string = urllib.parse.urlencode(params, encoding='utf-8')
    api_url = f"{base_url}?{query_string}"
    
    print(f"API URL:")
    print(f"  {api_url}")
    print()
    print("=" * 60)
    print("💡 위 URL을 브라우저에 붙여넣어서 직접 확인하세요!")
    print("=" * 60)
    print()
    
    # 3. KB 시세 조회
    print("3단계: KB 시세 조회")
    result = api.get_kb_price(address, area)
    
    if result:
        print()
        print("✅ KB 시세 조회 성공!")
        print(f"  단지명: {result.get('complex_name')}")
        print(f"  일반 매매가: {result.get('kb_price_raw')}")
        if result.get('kb_price_min_raw'):
            print(f"  하한 매매가: {result.get('kb_price_min_raw')}")
        print(f"  면적: {result.get('area')}m²")
        print(f"  평수: {result.get('pyeong')}평")
        print(f"  타입: {result.get('type')}")
    else:
        print()
        print("❌ KB 시세 조회 실패")
        print("   로그 파일(kb_price_api_debug.log)을 확인하세요.")


if __name__ == "__main__":
    test_kb_price()
