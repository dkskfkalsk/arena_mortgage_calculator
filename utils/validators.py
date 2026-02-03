# -*- coding: utf-8 -*-
"""
데이터 검증 유틸리티
"""


def validate_kb_price(kb_price):
    """
    KB시세 검증
    시세가 없으면 None 반환 (산출 불가)
    "일반 125,000만원" 형식도 처리
    URL(참고 링크)이 넘어오면 시세로 사용하지 않음
    """
    import re
    if kb_price is None or kb_price == "" or kb_price == "시세없음":
        print(f"DEBUG: validate_kb_price - None or empty: {kb_price}")
        return None
    
    try:
        # 문자열로 변환
        price_str = str(kb_price).strip()
        print(f"DEBUG: validate_kb_price - input: {price_str}")
        
        # URL이 넘어온 경우 시세로 사용하지 않음 (참고 링크 등에서 숫자 추출 방지)
        if price_str and (
            price_str.lower().startswith("http://")
            or price_str.lower().startswith("https://")
            or "kbland.kr" in price_str.lower()
            or (re.match(r"^[\d./]+$", price_str) and "/" in price_str)  # /c/35317 같은 경로만 있는 경우
        ):
            print(f"DEBUG: validate_kb_price - URL/경로로 판단, 시세로 사용 안 함: {price_str[:50]}")
            return None
        
        # "일반", "하한" 같은 키워드 제거 (공백 포함)
        price_str_clean = re.sub(r'\s*(일반|하한|상한)\s*', ' ', price_str, flags=re.IGNORECASE).strip()
        # 여러 공백을 하나로
        price_str_clean = re.sub(r'\s+', ' ', price_str_clean)
        
        # "억" 단위 처리 (먼저 처리)
        # "20억" -> 200,000만원으로 변환
        eok_match = re.search(r'([\d,]+)\s*억', price_str_clean, re.IGNORECASE)
        if eok_match:
            eok_value = float(eok_match.group(1).replace(',', ''))
            price = eok_value * 10000  # 1억 = 10,000만원
            print(f"DEBUG: validate_kb_price - extracted price from 억: {price}만원")
            return price
        
        # 숫자만 추출 (만원 단위)
        # 방법 1: 정규식으로 숫자 추출 (쉼표 포함) - 첫 번째 큰 숫자 사용
        numbers = re.findall(r'[\d,]+', price_str_clean)
        if numbers:
            # 가장 큰 숫자 사용 (일반 가격이 보통 더 큼)
            number_values = []
            for num in numbers:
                num_clean = num.replace(",", "").strip()
                if num_clean and len(num_clean) >= 3:
                    try:
                        number_values.append(float(num_clean))
                    except ValueError:
                        continue
            if number_values:
                price = max(number_values)
                print(f"DEBUG: validate_kb_price - extracted price (method 1): {price}")
                return price
        
        # 방법 2: "만원" 또는 "만" 제거 후 숫자 추출
        price_str_clean2 = price_str_clean.replace("만원", "").replace("만", "").strip()
        numbers2 = re.findall(r'[\d,]+', price_str_clean2)
        if numbers2:
            price_str_num = numbers2[0].replace(",", "").strip()
            if price_str_num and len(price_str_num) >= 3:
                price = float(price_str_num)
                print(f"DEBUG: validate_kb_price - extracted price (method 2): {price}")
                return price
        
        # 방법 3: 직접 변환 시도
        price_str_final = price_str_clean.replace(",", "").replace("만원", "").replace("만", "").strip()
        # 숫자만 남기기
        price_str_final = re.sub(r'[^\d]', '', price_str_final)
        if price_str_final and len(price_str_final) >= 3:
            price = float(price_str_final)
            print(f"DEBUG: validate_kb_price - extracted price (method 3): {price}")
            return price
        
        print(f"DEBUG: validate_kb_price - all methods failed, input: {kb_price}")
        return None
        
    except (ValueError, AttributeError, TypeError) as e:
        print(f"DEBUG: validate_kb_price - error: {e}, input: {kb_price}, type: {type(kb_price)}")
        import traceback
        traceback.print_exc()
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


def extract_lower_bound_price(kb_price):
    """
    KB시세에서 하한가 추출
    "일반 175,000만원 하한 171,000만원" 형식에서 하한가 추출
    """
    if kb_price is None or kb_price == "" or kb_price == "시세없음":
        return None
    
    try:
        import re
        price_str = str(kb_price).strip()
        
        # "하한" 키워드가 포함된 부분 찾기
        lower_match = re.search(r'(?:하한|하)\s*[:\s]*([\d,]+)', price_str, re.IGNORECASE)
        if lower_match:
            price_str_num = lower_match.group(1).replace(",", "").strip()
            if price_str_num and len(price_str_num) >= 3:
                price = float(price_str_num)
                print(f"DEBUG: extract_lower_bound_price - extracted lower bound price: {price}")
                return price
        
        print(f"DEBUG: extract_lower_bound_price - no lower bound price found")
        return None
        
    except (ValueError, AttributeError, TypeError) as e:
        print(f"DEBUG: extract_lower_bound_price - error: {e}, input: {kb_price}")
        return None


def extract_kb_ai_price_from_special_notes(special_notes):
    """
    특이사항에서 KB AI시세 추출
    "KB AI시세: 25,000만원" 또는 "KB AI시세 25,000만원" 형식 처리
    """
    if not special_notes:
        return None
    
    try:
        import re
        notes_str = str(special_notes).strip()
        
        # "KB AI시세" 또는 "KB AI 시세" 패턴 찾기
        # 다양한 형식 지원: "KB AI시세: 25,000만원", "KB AI시세 25,000만원", "KB AI 시세 25,000만원" 등
        patterns = [
            r'KB\s*AI\s*시세\s*[:\s]*([\d,]+(?:\s*만원)?)',
            r'KB\s*AI시세\s*[:\s]*([\d,]+(?:\s*만원)?)',
            r'KB\s*AI\s*시세\s*[:\s]*([\d,]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, notes_str, re.IGNORECASE)
            if match:
                price_str = match.group(1).strip()
                # "만원" 제거 후 숫자만 추출
                price_str_clean = price_str.replace("만원", "").replace("만", "").replace(",", "").strip()
                if price_str_clean and len(price_str_clean) >= 3:
                    price = float(price_str_clean)
                    print(f"DEBUG: extract_kb_ai_price_from_special_notes - extracted KB AI price: {price}만원")
                    return price
        
        print(f"DEBUG: extract_kb_ai_price_from_special_notes - no KB AI price found in special_notes")
        return None
        
    except (ValueError, AttributeError, TypeError) as e:
        print(f"DEBUG: extract_kb_ai_price_from_special_notes - error: {e}, input: {special_notes}")
        return None


def extract_bank_appraisal_price_from_special_notes(special_notes):
    """
    특이사항에서 탁감가(은행감정가) 추출
    "은행감정가 8억", "감정가 80,000만원", "감정가 60,000만", "탁감 80,000" 형식 처리
    """
    if not special_notes:
        return None
    
    try:
        import re
        notes_str = str(special_notes).strip()
        
        print(f"DEBUG: extract_bank_appraisal_price_from_special_notes - input: {notes_str}")
        
        # "은행감정가", "감정가", "탁감" 패턴 찾기
        # "8억" -> 80000, "80,000만원" -> 80000, "60,000만" -> 60000 등 처리
        # 더 명확하고 간단한 패턴들
        
        # 먼저 "억" 단위가 있는지 확인
        eok_pattern = r'(?:은행\s*감정가|감정가|탁감)\s*[:\s]*([\d,]+)\s*억'
        eok_match = re.search(eok_pattern, notes_str, re.IGNORECASE)
        if eok_match:
            price_str = eok_match.group(1).strip().replace(",", "")
            if price_str:
                try:
                    price = float(price_str) * 10000
                    print(f"DEBUG: extract_bank_appraisal_price_from_special_notes - ✅ extracted bank appraisal price (억): {price}만원")
                    return price
                except ValueError:
                    pass
        
        # "만원" 또는 "만" 단위가 있는 경우
        man_patterns = [
            r'(?:은행\s*감정가|감정가|탁감)\s*[:\s]*([\d,]+)\s*만원',  # "감정가 60,000만원" 형식
            r'(?:은행\s*감정가|감정가|탁감)\s*[:\s]*([\d,]+)\s*만',  # "감정가 60,000만" 형식
        ]
        
        for pattern in man_patterns:
            match = re.search(pattern, notes_str, re.IGNORECASE)
            if match:
                price_str = match.group(1).strip().replace(",", "")
                print(f"DEBUG: extract_bank_appraisal_price_from_special_notes - matched price_str: {price_str}")
                if price_str and len(price_str) >= 2:
                    try:
                        price = float(price_str)
                        print(f"DEBUG: extract_bank_appraisal_price_from_special_notes - ✅ extracted bank appraisal price: {price}만원")
                        return price
                    except ValueError:
                        continue
        
        # 단위가 없는 경우 (숫자만)
        no_unit_pattern = r'(?:은행\s*감정가|감정가|탁감)\s*[:\s]*([\d,]+)'
        no_unit_match = re.search(no_unit_pattern, notes_str, re.IGNORECASE)
        if no_unit_match:
            price_str = no_unit_match.group(1).strip().replace(",", "")
            print(f"DEBUG: extract_bank_appraisal_price_from_special_notes - matched price_str (no unit): {price_str}")
            if price_str and len(price_str) >= 2:
                try:
                    price = float(price_str)
                    print(f"DEBUG: extract_bank_appraisal_price_from_special_notes - ✅ extracted bank appraisal price (no unit): {price}만원")
                    return price
                except ValueError:
                    pass
        
        print(f"DEBUG: extract_bank_appraisal_price_from_special_notes - ❌ no bank appraisal price found in special_notes: {notes_str}")
        return None
        
    except (ValueError, AttributeError, TypeError) as e:
        print(f"DEBUG: extract_bank_appraisal_price_from_special_notes - error: {e}, input: {special_notes}")
        import traceback
        traceback.print_exc()
        return None


def extract_realestatetech_price_from_special_notes(special_notes):
    """
    특이사항에서 부동산테크 시세 추출
    "부동산테크 시세: 25,000만원" 또는 "부동산테크 25,000" 형식 처리
    """
    if not special_notes:
        return None
    
    try:
        import re
        notes_str = str(special_notes).strip()
        
        # "부동산테크" 패턴 찾기
        patterns = [
            r'부동산\s*테크\s*(?:시세)?\s*[:\s]*([\d,]+(?:\s*만원)?)',
            r'부동산테크\s*(?:시세)?\s*[:\s]*([\d,]+(?:\s*만원)?)',
            r'부동산\s*테크\s*[:\s]*([\d,]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, notes_str, re.IGNORECASE)
            if match:
                price_str = match.group(1).strip()
                # "만원" 제거 후 숫자만 추출
                price_str_clean = price_str.replace("만원", "").replace("만", "").replace(",", "").strip()
                if price_str_clean and len(price_str_clean) >= 3:
                    price = float(price_str_clean)
                    print(f"DEBUG: extract_realestatetech_price_from_special_notes - extracted realestatetech price: {price}만원")
                    return price
        
        print(f"DEBUG: extract_realestatetech_price_from_special_notes - no realestatetech price found in special_notes")
        return None
        
    except (ValueError, AttributeError, TypeError) as e:
        print(f"DEBUG: extract_realestatetech_price_from_special_notes - error: {e}, input: {special_notes}")
        return None


def extract_korea_realestate_price_from_special_notes(special_notes):
    """
    특이사항에서 한국부동산원 시세 추출
    "한국부동산원 시세: 25,000만원" 또는 "한부원 25,000" 형식 처리
    """
    if not special_notes:
        return None
    
    try:
        import re
        notes_str = str(special_notes).strip()
        
        # "한국부동산원", "한부원" 패턴 찾기
        patterns = [
            r'한국\s*부동산원\s*(?:시세)?\s*[:\s]*([\d,]+(?:\s*만원)?)',
            r'한부원\s*(?:시세)?\s*[:\s]*([\d,]+(?:\s*만원)?)',
            r'한국\s*부동산원\s*[:\s]*([\d,]+)',
            r'한부원\s*[:\s]*([\d,]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, notes_str, re.IGNORECASE)
            if match:
                price_str = match.group(1).strip()
                # "만원" 제거 후 숫자만 추출
                price_str_clean = price_str.replace("만원", "").replace("만", "").replace(",", "").strip()
                if price_str_clean and len(price_str_clean) >= 3:
                    price = float(price_str_clean)
                    print(f"DEBUG: extract_korea_realestate_price_from_special_notes - extracted korea realestate price: {price}만원")
                    return price
        
        print(f"DEBUG: extract_korea_realestate_price_from_special_notes - no korea realestate price found in special_notes")
        return None
        
    except (ValueError, AttributeError, TypeError) as e:
        print(f"DEBUG: extract_korea_realestate_price_from_special_notes - error: {e}, input: {special_notes}")
        return None


def extract_housematch_price_from_special_notes(special_notes):
    """
    특이사항에서 하우스머치 시세 추출
    "하우스머치 시세: 25,000만원" 또는 "하우스머치 25,000" 형식 처리
    """
    if not special_notes:
        return None
    
    try:
        import re
        notes_str = str(special_notes).strip()
        
        # "하우스머치" 패턴 찾기
        patterns = [
            r'하우스\s*머치\s*(?:시세)?\s*[:\s]*([\d,]+(?:\s*만원)?)',
            r'하우스머치\s*(?:시세)?\s*[:\s]*([\d,]+(?:\s*만원)?)',
            r'하우스\s*머치\s*[:\s]*([\d,]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, notes_str, re.IGNORECASE)
            if match:
                price_str = match.group(1).strip()
                # "만원" 제거 후 숫자만 추출
                price_str_clean = price_str.replace("만원", "").replace("만", "").replace(",", "").strip()
                if price_str_clean and len(price_str_clean) >= 3:
                    price = float(price_str_clean)
                    print(f"DEBUG: extract_housematch_price_from_special_notes - extracted housematch price: {price}만원")
                    return price
        
        print(f"DEBUG: extract_housematch_price_from_special_notes - no housematch price found in special_notes")
        return None
        
    except (ValueError, AttributeError, TypeError) as e:
        print(f"DEBUG: extract_housematch_price_from_special_notes - error: {e}, input: {special_notes}")
        return None

