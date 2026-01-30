# -*- coding: utf-8 -*-
"""
양도로 주소 파싱 테스트 - 왜 fallback이 필요한지 확인
"""
import sys
sys.path.insert(0, '.')

test_address = "경기도 김포시 양도로 161-1 양도마을서해아파트 제16동 제1607호"

print("=" * 70)
print("양도로 주소 파싱 테스트")
print("=" * 70)
print(f"\n테스트 주소: {test_address}")

# 1. parse_address로 파싱 시도
from KB_api.kb_price_api import KBPriceAPI

api = KBPriceAPI()
parsed = api.parse_address(test_address)

print(f"\n[파싱 결과]")
print(f"  region: {parsed.get('region')}")
print(f"  district: {parsed.get('district')}")
print(f"  dong: {parsed.get('dong')}")
print(f"  detail: {parsed.get('detail')}")

# 2. 법정동코드 조회
dongcode = api.find_dongcode(test_address)
print(f"\n[법정동코드 조회]")
print(f"  법정동코드: {dongcode}")

# 3. 문제 설명
print("\n" + "=" * 70)
print("문제 분석")
print("=" * 70)
print("""
1. "양도로"는 **도로명 주소**입니다.
   - 법정동명(동/읍/면)이 아니라 "로"로 끝나는 도로명입니다.

2. parse_address의 dong_patterns는 다음만 찾습니다:
   - [가-힣]+동, [가-힣]+읍, [가-힣]+면
   - "양도로"는 "로"로 끝나서 매칭되지 않습니다.

3. 법정동명 vs 도로명:
   - 법정동명: "양촌읍", "오류동", "온천동" (동/읍/면으로 끝남)
   - 도로명: "양도로", "고척로", "테헤란로" (로/길로 끝남)

4. 해결 방법:
   - 옵션1: 도로명주소 API 연동 (복잡, 외부 API 필요)
   - 옵션2: 자주 나오는 도로명 주소만 fallback 매핑 (간단, 현재 방식)
   
5. 현재 fallback:
   - "양도로" → 양촌읍 (법정동코드: 4157025600)
   - 이는 실제 "양도로"가 김포시 양촌읍에 속하기 때문입니다.
""")

print("=" * 70)
print("결론: 도로명 주소는 동/읍/면 파싱이 불가능하므로")
print("     자주 나오는 케이스만 fallback 매핑이 필요합니다.")
print("=" * 70)
