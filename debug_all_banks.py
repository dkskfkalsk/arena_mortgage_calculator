# -*- coding: utf-8 -*-
"""모든 금융사 계산 디버그 - 왜 JB만 나오는지 확인"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parsers.message_parser import MessageParser
from calculator.base_calculator import BaseCalculator

MESSAGE = """성   명 : 방태식 (30)
직   업 : 사업자
신용점수 : X
거주여부 : 거주
소유현황 : 단독소유
주   소 : 경기도오산시서동641더샵오산엘리포레103동 27층 2704호
총층수 : 29층
면   적 : 75.54㎡
세대수 : 927세대 (1개동 이상)
구   분 : 아파트
KB시세 : 일반 48,000만원
            하한 45,000만원
=========설정내역=========
1순위 : 농협은행
           42,900 (39,000)만원
2순위 : 드림앤캐쉬대부(사업자금)
           2,600 (2,000)만원
94.79% / 85.42%
========================
특이사항 : *실사업자
요청사항 : *2순위 드림앤캐쉬 대부 대환조건 확인 부탁드립니다."""

parser = MessageParser()
property_data = parser.parse(MESSAGE)

print("=== 파싱 결과 ===")
print(f"region: {property_data.get('region')}")
print(f"kb_price: {property_data.get('kb_price')}")
print(f"property_type: {property_data.get('property_type')}")
print(f"household_count: {property_data.get('household_count')}")
print(f"mortgages: {property_data.get('mortgages')}")
print()

# 각 금융사별로 계산 시도
banks_dir = os.path.join(os.path.dirname(__file__), "data", "banks")
for filename in sorted(os.listdir(banks_dir)):
    if not filename.endswith(".json"):
        continue
    config_path = os.path.join(banks_dir, filename)
    try:
        calc = BaseCalculator(config_path)
        result = calc.calculate(property_data)
        bank_name = calc.bank_name
        if result is None:
            print(f"❌ {bank_name}: None 반환")
        elif not result.get("results"):
            errs = result.get("errors", [])
            print(f"⚠️ {bank_name}: results 비어있음, errors={errs}")
        else:
            n = len(result["results"])
            print(f"✅ {bank_name}: {n}건 산출")
    except Exception as e:
        print(f"❌ {filename}: 예외 - {e}")
