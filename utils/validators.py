# -*- coding: utf-8 -*-
"""
데이터 검증 유틸리티
"""


def validate_kb_price(kb_price):
    """
    KB시세 검증
    시세가 없으면 None 반환 (산출 불가)
    """
    if kb_price is None or kb_price == "" or kb_price == "시세없음":
        return None
    
    try:
        # 숫자로 변환 시도 (만원 단위)
        price = float(str(kb_price).replace(",", "").replace("만원", "").strip())
        return price
    except (ValueError, AttributeError):
        return None


def validate_credit_score(credit_score):
    """
    신용점수 검증
    점수가 없거나 "X"인 경우 None 반환
    """
    if credit_score is None or credit_score == "" or str(credit_score).upper() == "X":
        return None
    
    try:
        score = int(str(credit_score).strip())
        if 0 <= score <= 1000:
            return score
        return None
    except (ValueError, TypeError):
        return None


def parse_amount(amount_str):
    """
    금액 문자열 파싱 (만원 단위로 변환)
    예: "27,000만원" -> 27000
    """
    if not amount_str:
        return None
    
    try:
        # 숫자만 추출
        amount = str(amount_str).replace(",", "").replace("만원", "").replace("만", "").strip()
        return float(amount)
    except (ValueError, AttributeError):
        return None

