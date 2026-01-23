# -*- coding: utf-8 -*-
"""
KB API 직접 호출 URL 생성 스크립트
주소를 입력하면 브라우저에서 바로 테스트할 수 있는 API URL을 생성합니다.
"""

from KB_api.kb_price_api import KBPriceAPI
import urllib.parse

def generate_api_url(address: str):
    """
    주소로부터 KB API 호출 URL 생성
    
    Args:
        address: 부동산 주소 (예: "경기도 수원시 권선구 곡반정동 654")
    
    Returns:
        API 호출 URL 문자열
    """
    print(f"\n🔍 주소 분석: {address}")
    
    api = KBPriceAPI()
    
    # 법정동코드 찾기
    dongcode = api.find_dongcode(address)
    
    if not dongcode:
        print("❌ 법정동코드를 찾을 수 없어 API URL을 생성할 수 없습니다.")
        print("\n💡 가능한 원인:")
        print("   1. 주소 형식이 올바르지 않음")
        print("   2. 법정동코드 데이터에 해당 동이 없음")
        print("   3. '제217동', '제1105호' 같은 상세 주소가 포함되어 있음")
        return None
    
    # API URL 생성
    base_url = "https://api.kbland.kr/land-price/price/fastPriceInfo"
    params = {
        "법정동코드": dongcode,
        "유형": "1",  # 아파트
        "거래유형": "0"  # 매매
    }
    
    # URL 인코딩
    query_string = urllib.parse.urlencode(params, encoding='utf-8')
    full_url = f"{base_url}?{query_string}"
    
    print(f"\n✅ API 호출 URL:")
    print(f"   {full_url}")
    print(f"\n📋 복사해서 브라우저 주소창에 붙여넣으세요!")
    
    return full_url


if __name__ == "__main__":
    import sys
    
    # 명령줄 인자로 주소 받기
    if len(sys.argv) > 1:
        test_address = " ".join(sys.argv[1:])
    else:
        # 기본 테스트 주소
        test_address = "경기도 수원시 권선구 곡반정동 654"
    
    print("=" * 60)
    print("KB 시세 API 직접 호출 URL 생성기")
    print("=" * 60)
    
    url = generate_api_url(test_address)
    
    if url:
        print("\n" + "=" * 60)
        print("💡 사용법:")
        print("   1. 위 URL을 복사")
        print("   2. 브라우저 주소창에 붙여넣기")
        print("   3. JSON 응답 확인")
        print("\n📝 다른 주소로 테스트:")
        print(f"   python {__file__} \"경기도 수원시 권선구 곡반정동 654\"")
        print("=" * 60)
    else:
        print("\n💡 수동으로 법정동코드를 찾아서 URL 생성:")
        print("   https://api.kbland.kr/land-price/price/fastPriceInfo?법정동코드=4111314100&유형=1&거래유형=0")
        print("\n   (위 URL은 권선구 예시입니다. 곡반정동의 정확한 법정동코드를 찾아야 합니다)")
