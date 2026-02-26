# -*- coding: utf-8 -*-
"""
JB하이론 한도 산출 예시 실행
- 경기도 오산시(1급지), 신용 X, KB시세 48,000만원
- 1순위 농협 42,900만원(유지), 2순위 드림앤캐쉬 2,000만원(대환)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calculator.base_calculator import BaseCalculator
from utils.formatter import format_result

# 예시 property_data
property_data = {
    "kb_price": 48000,
    "region": "경기도오산시",
    "credit_score": None,
    "credit_grade": None,
    "mortgages": [
        {
            "priority": 1,
            "institution": "농협",
            "amount": 39000,  # 원금 (채권최고액 42900 기준 110% 역산 근사)
            "max_amount": 42900,  # 채권최고액 (유지)
            "is_refinance": False,
        },
        {
            "priority": 2,
            "institution": "드림앤캐쉬",
            "amount": 2000,  # 대환 원금
            "max_amount": 2600,  # 채권최고액 (캐피탈 130% 가정)
            "is_refinance": True,
        },
    ],
    "requests": "2순위 대환조건",
}

# JB하이론 설정만 로드
config_path = os.path.join(
    os.path.dirname(__file__), "data", "banks", "3_JBwooricapital_himortage.json"
)
calculator = BaseCalculator(config_path)

# 계산 실행
result = calculator.calculate(property_data, product_type="business")

if result:
    print("=" * 50)
    print("JB하이론 한도 산출 결과")
    print("=" * 50)
    print(format_result(result))
    print()
    print("--- 상세 결과 ---")
    for r in result.get("results", []):
        print(r)
else:
    print("산출 불가")
