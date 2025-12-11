# -*- coding: utf-8 -*-
"""
데이터 검증 유틸리티
"""


def validate_kb_price(kb_price):
    """
    KB시세 검증
    시세가 없으면 None 반환 (산출 불가)
    "일반 125,000만원" 형식도 처리
    """
    if kb_price is None or kb_price == "" or kb_price == "시세없음":
        print(f"DEBUG: validate_kb_price - None or empty: {kb_price}")
        return None
    
    try:
        # 문자열로 변환
        price_str = str(kb_price).strip()
        print(f"DEBUG: validate_kb_price - input: {price_str}")
        
        # "일반", "하한" 같은 키워드 제거
        price_str_clean = price_str.replace("일반", "").replace("하한", "").replace("상한", "").strip()
        
        # 숫자만 추출 (만원 단위)
        import re
        
        # 방법 1: 정규식으로 숫자 추출 (쉼표 포함)
        numbers = re.findall(r'[\d,]+', price_str_clean)
        if numbers:
            # 첫 번째 숫자 사용 (일반 가격)
            # "125,000" 형식에서 쉼표 제거
            price_str_num = numbers[0].replace(",", "").strip()
            if price_str_num:
                price = float(price_str_num)
                print(f"DEBUG: validate_kb_price - extracted price (method 1): {price}")
                return price
        
        # 방법 2: "만원" 또는 "만" 제거 후 숫자 추출
        price_str_clean2 = price_str_clean.replace("만원", "").replace("만", "").strip()
        numbers2 = re.findall(r'[\d,]+', price_str_clean2)
        if numbers2:
            price_str_num = numbers2[0].replace(",", "").strip()
            if price_str_num:
                price = float(price_str_num)
                print(f"DEBUG: validate_kb_price - extracted price (method 2): {price}")
                return price
        
        # 방법 3: 직접 변환 시도
        price_str_final = price_str_clean.replace(",", "").replace("만원", "").replace("만", "").strip()
        if price_str_final:
            price = float(price_str_final)
            print(f"DEBUG: validate_kb_price - extracted price (method 3): {price}")
            return price
        
        print(f"DEBUG: validate_kb_price - all methods failed, input: {kb_price}")
        return None
        
    except (ValueError, AttributeError, TypeError) as e:
        print(f"DEBUG: validate_kb_price - error: {e}, input: {kb_price}, type: {type(kb_price)}")
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

