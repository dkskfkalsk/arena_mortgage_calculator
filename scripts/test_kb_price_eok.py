# -*- coding: utf-8 -*-
"""KB시세 억 단위 테스트"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.validators import validate_kb_price
from parsers.message_parser import MessageParser

def test_validate_kb_price():
    """validate_kb_price 테스트"""
    print("=== validate_kb_price 테스트 ===\n")
    
    test_cases = [
        "20억",
        "KB시세 20억",
        "KB시세 : 일반 20억",
        "KB시세 : 일반 125,000만원",
        "KB시세 : 일반 20억 하한 19억",
    ]
    
    for test_case in test_cases:
        result = validate_kb_price(test_case)
        print(f"Input: {test_case}")
        print(f"Output: {result}만원")
        print()

def test_message_parser():
    """MessageParser 테스트"""
    print("\n=== MessageParser 테스트 ===\n")
    
    test_messages = [
        "KB시세 20억\n사업자\n신용점수 890점",
        "KB시세 : 일반 20억\n하한 19억",
    ]
    
    parser = MessageParser()
    for msg in test_messages:
        print(f"Input:\n{msg}\n")
        result = parser.parse(msg)
        print(f"KB시세: {result.get('kb_price')}")
        print()

if __name__ == "__main__":
    test_validate_kb_price()
    test_message_parser()
