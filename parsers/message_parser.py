# -*- coding: utf-8 -*-
"""
텔레그램 메시지 파서
담보물건 정보 텍스트를 구조화된 데이터로 변환
"""

import re
from typing import Dict, List, Optional, Any
from utils.validators import validate_kb_price, validate_credit_score, parse_amount


class MessageParser:
    """
    텔레그램 메시지 파서
    """
    
    def parse(self, message_text: str) -> Dict[str, Any]:
        """
        텔레그램 메시지를 파싱하여 구조화된 데이터로 변환
        
        Args:
            message_text: 텔레그램 메시지 텍스트
        
        Returns:
            파싱된 데이터 딕셔너리
        """
        lines = message_text.split("\n")
        
        data = {
            "name": None,
            "age": None,
            "occupation": None,
            "credit_score": None,
            "residence": None,
            "ownership": None,
            "address": None,
            "area": None,
            "household_count": None,
            "property_type": None,
            "kb_price": None,
            "mortgages": [],
            "special_notes": None,
            "requests": None,
            "region": None,
            "required_amount": None
        }
        
        # 먼저 전체 텍스트에서 KB시세를 직접 추출 (가장 확실한 방법)
        kb_price = self._extract_kb_price_from_text(message_text)
        if kb_price:
            data["kb_price"] = kb_price
            print(f"DEBUG: KB price extracted from full text: {kb_price}")
        
        current_section = None
        skip_next_line = False  # 다음 줄을 건너뛸지 여부
        
        i = 0
        while i < len(lines):
            # 이전 반복에서 이미 처리한 줄이면 건너뛰기
            if skip_next_line:
                skip_next_line = False
                i += 1
                continue
                
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            # 섹션 구분 (키:값 파싱보다 먼저 체크)
            if "설정내역" in line or "=========" in line:
                current_section = "mortgages"
                i += 1
                continue
            elif "특이사항" in line:
                current_section = "special_notes"
                # "특이사항 : 내용" 형식인 경우 즉시 내용 추가
                if ":" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2 and parts[1].strip():
                        data["special_notes"] = parts[1].strip()
                i += 1
                continue
            elif "요청사항" in line:
                current_section = "requests"
                # "요청사항 : 내용" 형식인 경우 즉시 내용 추가
                if ":" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2 and parts[1].strip():
                        data["requests"] = parts[1].strip()
                i += 1
                continue
            elif ":" in line and current_section != "mortgages":
                # 키:값 형식 파싱
                key, value = self._parse_key_value(line)
                if key and value:
                    # KB시세인 경우 특별 처리
                    if "kb시세" in key.lower() or ("시세" in key and "kb" in line.lower()):
                        # 다음 줄이 있으면 추가 (하한, 상한 등) - 최대 2줄까지 확인
                        for j in range(1, 3):  # 다음 1-2줄 확인
                            if i + j < len(lines):
                                next_line = lines[i + j].strip()
                                # 다음 줄이 숫자로 시작하거나 "하한", "상한" 같은 키워드가 있으면 추가
                                if next_line and (any(keyword in next_line for keyword in ["하한", "상한", "일반"]) or re.search(r'[\d,]+', next_line)):
                                    value += " " + next_line
                                    if j == 1:
                                        skip_next_line = True  # 첫 번째 다음 줄은 건너뛰기
                                else:
                                    # 숫자가 없으면 더 이상 확인하지 않음
                                    break
                        # KB시세 직접 설정 (더 강력한 파싱)
                        print(f"DEBUG: Setting KB price from key-value: {value}")
                        self._set_field(data, key, value)
                    else:
                        self._set_field(data, key, value)
            elif "kb시세" in line.lower() and current_section != "mortgages":
                # "KB시세"가 포함된 줄에서 직접 추출 (콜론이 없어도 처리)
                # 예: "KB시세 일반 125,000만원" 또는 "KB시세: 일반 125,000만원"
                kb_match = re.search(r'kb시세\s*:?\s*(.+)', line, re.IGNORECASE)
                if kb_match:
                    kb_value = kb_match.group(1).strip()
                    # 다음 줄도 확인 - 최대 2줄까지 확인
                    for j in range(1, 3):  # 다음 1-2줄 확인
                        if i + j < len(lines):
                            next_line = lines[i + j].strip()
                            if next_line and (any(keyword in next_line for keyword in ["하한", "상한", "일반"]) or re.search(r'[\d,]+', next_line)):
                                kb_value += " " + next_line
                                if j == 1:
                                    skip_next_line = True
                            else:
                                # 숫자가 없으면 더 이상 확인하지 않음
                                break
                    data["kb_price"] = kb_value
                    print(f"DEBUG: Direct KB price extraction - line: {line}, value: {kb_value}")
            
            # 설정 내역 파싱 (근저당권) - 여러 줄을 합쳐서 파싱
            if current_section == "mortgages":
                # "1순위 : 전세입자" 형태의 줄 찾기
                if "순위" in line and ":" in line:
                    # 현재 줄부터 다음 3줄까지 합쳐서 파싱 시도
                    combined_lines = line
                    for j in range(1, 4):
                        if i + j < len(lines):
                            next_line = lines[i + j].strip()
                            if next_line and not any(kw in next_line for kw in ["순위", "특이사항", "요청사항", "==="]):
                                combined_lines += " " + next_line
                            else:
                                break
                    
                    mortgage = self._parse_mortgage_line(combined_lines)
                    if mortgage:
                        data["mortgages"].append(mortgage)
                        print(f"DEBUG: Parsed mortgage - combined_lines: '{combined_lines}', result: {mortgage}")
            
            # 특이사항 파싱
            elif current_section == "special_notes":
                if data["special_notes"]:
                    data["special_notes"] += "\n" + line
                else:
                    data["special_notes"] = line
            
            # 요청사항 파싱
            elif current_section == "requests":
                if data["requests"]:
                    data["requests"] += "\n" + line
                else:
                    data["requests"] = line
            
            i += 1
        
        # 지역 추출 (주소에서)
        if data["address"]:
            data["region"] = self._extract_region(data["address"])
        
        # KB시세 검증 (전체 텍스트에서 추출한 것이 없으면 기존 방식 사용)
        if not data["kb_price"]:
            # 기존 방식으로 다시 시도
            for i, line in enumerate(lines):
                if "kb시세" in line.lower():
                    # KB시세 줄과 다음 줄 모두 포함
                    kb_value = line
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line:
                            kb_value += " " + next_line
                    # 콜론 뒤의 값만 추출
                    if ":" in kb_value:
                        kb_value = kb_value.split(":", 1)[1].strip()
                    else:
                        kb_value = re.sub(r'kb시세\s*', '', kb_value, flags=re.IGNORECASE).strip()
                    data["kb_price"] = kb_value
                    print(f"DEBUG: KB price from line parsing: {kb_value}")
                    break
        
        print(f"DEBUG: Before validation - kb_price: {data['kb_price']}")
        if data["kb_price"]:
            validated_price = validate_kb_price(data["kb_price"])
            data["kb_price"] = validated_price
            print(f"DEBUG: After validation - kb_price: {data['kb_price']}")
        else:
            print(f"DEBUG: No KB price found in parsed data")
            print(f"DEBUG: Full text sample: {message_text[:500]}")
        
        # 신용점수 검증
        if data["credit_score"]:
            validated_score = validate_credit_score(data["credit_score"])
            data["credit_score"] = validated_score
        
        # 필요자금 추출 (요청사항에서)
        if data["requests"]:
            print(f"DEBUG: Parsing required_amount from requests: {data['requests']}")
            
            # "필요자금 1억" 또는 "필요자금 10000만원" 패턴 찾기
            # 1. 억 단위 패턴
            required_match = re.search(r'필요자금[:\s]*(\d+(?:[.,]\d+)?)\s*억', data["requests"])
            if required_match:
                # 억 단위를 만원으로 변환
                amount_eok = float(required_match.group(1).replace(",", "").replace(".", ""))
                data["required_amount"] = amount_eok * 10000  # 1억 = 10,000만원
                print(f"DEBUG: Parsed required_amount from 억: {data['required_amount']}만원")
            else:
                # 2. 만원 단위 패턴
                required_match = re.search(r'필요자금[:\s]*(\d+(?:,\d+)*)\s*만', data["requests"])
                if required_match:
                    data["required_amount"] = float(required_match.group(1).replace(",", ""))
                    print(f"DEBUG: Parsed required_amount from 만원: {data['required_amount']}만원")
                else:
                    # 3. 단위 없이 숫자만 있는 경우 (만원으로 가정)
                    required_match = re.search(r'필요자금[:\s]*(\d+(?:,\d+)*)', data["requests"])
                    if required_match:
                        data["required_amount"] = float(required_match.group(1).replace(",", ""))
                        print(f"DEBUG: Parsed required_amount (no unit, assuming 만원): {data['required_amount']}만원")
        
        # 대환 정보 추출 (요청사항에서)
        if data["requests"] and "대환" in data["requests"]:
            print(f"DEBUG: Parsing refinance info from requests: {data['requests']}")
            
            # 먼저 모든 근저당권의 is_refinance를 False로 초기화 (명시적으로 지정된 것만 True로 설정)
            for mortgage in data["mortgages"]:
                mortgage["is_refinance"] = False
            
            # 패턴: "N순위 [기관명] 대환" 또는 "[기관명] 대환" 등
            # 1. "N순위 [기관명] 대환" 또는 "N순위 [기관명] 대환조건" 패턴
            # 정규식 개선: "대환" 전까지 모든 문자를 캡처 (non-greedy)
            # 예: "2순위 도원캐피탈대부 대환조건" -> priority=2, institution="도원캐피탈대부"
            refinance_match = re.search(r'(\d+)순위\s+([^대환]+?)\s*대환', data["requests"])
            if refinance_match:
                priority = int(refinance_match.group(1))
                institution_keyword = refinance_match.group(2).strip()
                # 공백 제거 (기관명에 공백이 있을 수 있으므로)
                institution_keyword = institution_keyword.replace(" ", "")
                print(f"DEBUG: Found refinance - priority: {priority}, institution_keyword: '{institution_keyword}'")
                
                # 해당 순위의 근저당권 찾기
                found = False
                for mortgage in data["mortgages"]:
                    if mortgage.get("priority") == priority:
                        institution = mortgage.get("institution", "")
                        # 기관명에 키워드가 포함되어 있는지 확인 (양방향 확인)
                        # "도원캐피탈대부"와 "도원캐피탈" 둘 다 매칭되도록
                        if institution_keyword in institution or institution in institution_keyword or \
                           any(keyword in institution for keyword in institution_keyword.split() if len(keyword) > 2):
                            mortgage["is_refinance"] = True
                            found = True
                            print(f"DEBUG: Set is_refinance=True for mortgage: priority={priority}, institution='{institution}', keyword='{institution_keyword}'")
                            break
                
                if not found:
                    print(f"DEBUG: Warning - Could not find matching mortgage for priority {priority} with keyword '{institution_keyword}'")
            else:
                # 2. "[기관명] 대환" 패턴 (순위 없이) - 기관명이 명시된 경우만
                refinance_match = re.search(r'([가-힣a-zA-Z0-9]+(?:[가-힣a-zA-Z0-9\s]+)?)\s*대환', data["requests"])
                if refinance_match:
                    institution_keyword = refinance_match.group(1).strip()
                    # "대환"이라는 단어 자체는 제외
                    if institution_keyword != "대환":
                        print(f"DEBUG: Found refinance (no priority) - institution_keyword: '{institution_keyword}'")
                        
                        # 기관명이 일치하는 근저당권 찾기
                        found = False
                        for mortgage in data["mortgages"]:
                            institution = mortgage.get("institution", "")
                            if institution_keyword in institution or institution in institution_keyword or \
                               any(keyword in institution for keyword in institution_keyword.split() if len(keyword) > 2):
                                mortgage["is_refinance"] = True
                                found = True
                                print(f"DEBUG: Set is_refinance=True for mortgage: priority={mortgage.get('priority')}, institution='{institution}', keyword='{institution_keyword}'")
                                break
                        
                        if not found:
                            print(f"DEBUG: Warning - Could not find matching mortgage with keyword '{institution_keyword}'")
        
        return data
    
    def _parse_key_value(self, line: str) -> tuple:
        """키:값 형식 파싱"""
        if ":" not in line:
            return None, None
        
        parts = line.split(":", 1)
        if len(parts) != 2:
            return None, None
        
        key = parts[0].strip()
        value = parts[1].strip()
        
        return key, value
    
    def _set_field(self, data: Dict[str, Any], key: str, value: str):
        """필드 설정"""
        # 키에서 공백 제거하여 비교 (더 안정적인 매칭)
        key_clean = key.replace(" ", "").lower()
        
        if "성명" in key_clean or "이름" in key_clean:
            # 성명에서 연령 추출 (예: "정종민 (68)")
            match = re.search(r"\((\d+)\)", value)
            if match:
                data["age"] = int(match.group(1))
                data["name"] = value.split("(")[0].strip()
            else:
                data["name"] = value
        
        elif "직업" in key_clean:
            data["occupation"] = value
        
        elif "신용점수" in key_clean or "신용" in key_clean:
            data["credit_score"] = value
        
        elif "거주여부" in key_clean:
            data["residence"] = value
        
        elif "소유현황" in key_clean:
            data["ownership"] = value
        
        elif "주소" in key_clean:  # 공백 제거된 키로 비교
            data["address"] = value
            print(f"DEBUG: Address set - key: '{key}', value: '{value}'")
        
        elif "면적" in key_clean:
            # 면적에서 숫자 추출 (예: "25.95㎡")
            match = re.search(r"([\d.]+)", value)
            if match:
                data["area"] = float(match.group(1))
        
        elif "세대수" in key_clean:
            # 세대수에서 숫자 추출 (예: "16세대 (1개동)")
            match = re.search(r"(\d+)", value)
            if match:
                data["household_count"] = int(match.group(1))
        
        elif "구분" in key_clean:
            data["property_type"] = value
        
        elif "kb시세" in key_clean or "시세" in key_clean:
            # KB시세는 여러 줄에 걸쳐 있을 수 있음 (일반, 하한 등)
            # 첫 번째 값만 저장 (일반 가격)
            data["kb_price"] = value
            print(f"DEBUG: Parsed KB price - key: {key}, value: {value}")
    
    def _parse_mortgage_line(self, line: str) -> Optional[Dict[str, Any]]:
        """근저당권 설정 내역 라인 파싱"""
        # 순위 추출
        priority_match = re.search(r"(\d+)순위", line)
        if not priority_match:
            return None
        
        priority = int(priority_match.group(1))
        print(f"DEBUG: _parse_mortgage_line - priority: {priority}, line: '{line}'")
        
        # 채권최고액과 원금 추출
        # 패턴: "44,200 (34,000)만원" 형식
        # 괄호 밖의 금액 = 채권최고액, 괄호 안의 금액 = 원금
        max_amount = None  # 채권최고액
        amount = None  # 원금
        
        # 괄호 안의 금액 (원금) 추출
        amount_match = re.search(r"\(([\d,]+)\)", line)
        if amount_match:
            amount_str = amount_match.group(1)
            amount = parse_amount(amount_str)
            print(f"DEBUG: _parse_mortgage_line - amount(원금) from parentheses: {amount_str} -> {amount}")
        
        # 괄호 밖의 금액 (채권최고액) 추출
        # "44,200 (34,000)만원" 형식에서 괄호 앞의 숫자 추출
        max_amount_match = re.search(r"(\d{2,}[,\d]*)\s*\([\d,]+\)", line)
        if max_amount_match:
            max_amount_str = max_amount_match.group(1)
            max_amount = parse_amount(max_amount_str)
            print(f"DEBUG: _parse_mortgage_line - max_amount(채권최고액) from pattern: {max_amount_str} -> {max_amount}")
        else:
            # 괄호가 없으면 첫 번째 큰 숫자를 채권최고액으로 사용
            amount_matches = re.findall(r"(\d{2,}[,\d]*)", line)
            if amount_matches:
                max_amount_str = amount_matches[0]
                max_amount = parse_amount(max_amount_str)
                print(f"DEBUG: _parse_mortgage_line - max_amount(채권최고액) from pattern (no parentheses): {max_amount_str} -> {max_amount}")
                # 원금이 없으면 채권최고액을 원금으로도 사용
                if amount is None:
                    amount = max_amount
        
        if amount is None:
            print(f"DEBUG: _parse_mortgage_line - no amount found in line: '{line}'")
            return None
        
        # 채권최고액이 없으면 원금에 1.2를 곱해서 추정 (기본값)
        if max_amount is None:
            max_amount = amount * 1.2
            print(f"DEBUG: _parse_mortgage_line - max_amount(채권최고액) estimated from amount: {max_amount}")
        
        # 기관명/유형 추출
        institution_match = re.search(r":\s*([^0-9\n]+?)(?=\s*\d|\s*$)", line)
        if institution_match:
            institution = institution_match.group(1).strip()
        else:
            institution = None
        
        print(f"DEBUG: _parse_mortgage_line - institution: {institution}, amount(원금): {amount}, max_amount(채권최고액): {max_amount}")
        
        is_refinance = False
        
        return {
            "priority": priority,
            "amount": amount,  # 원금 (기존 호환성 유지)
            "max_amount": max_amount,  # 채권최고액 (새로 추가)
            "institution": institution,
            "is_refinance": is_refinance
        }
    
    def _extract_kb_price_from_text(self, text: str) -> Optional[str]:
        """
        전체 텍스트에서 KB시세를 직접 추출
        "KB시세 : 일반 125,000만원" 형식 등 다양한 형식 처리
        """
        lines = text.split('\n')
        kb_value = None
        
        # KB시세가 포함된 줄 찾기
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if 'kb시세' in line_lower or ('kb' in line_lower and '시세' in line_lower):
                print(f"DEBUG: Found KB시세 line: {line}")
                # KB시세 줄에서 값 추출
                # "KB시세 : 일반 125,000만원" 형식
                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        kb_value = parts[1].strip()
                        print(f"DEBUG: Extracted from colon: {kb_value}")
                else:
                    # "KB시세 일반 125,000만원" 형식
                    kb_match = re.search(r'kb시세\s+(.+)', line, re.IGNORECASE)
                    if kb_match:
                        kb_value = kb_match.group(1).strip()
                        print(f"DEBUG: Extracted from regex: {kb_value}")
                
                # 다음 줄도 확인 (하한, 상한 정보) - 최대 2줄까지 확인
                for j in range(1, 3):  # 다음 1-2줄 확인
                    if i + j < len(lines):
                        next_line = lines[i + j].strip()
                        if next_line:
                            # 하한, 상한, 일반 키워드가 있거나 숫자가 있으면 추가
                            if any(kw in next_line for kw in ['하한', '상한', '일반']) or re.search(r'[\d,]+', next_line):
                                if kb_value:
                                    kb_value += " " + next_line
                                    print(f"DEBUG: Added next line {j}: {next_line}, kb_value now: {kb_value}")
                                else:
                                    kb_value = next_line
                                    print(f"DEBUG: Set kb_value from next line {j}: {kb_value}")
                            else:
                                # 숫자가 없으면 더 이상 확인하지 않음
                                break
                
                if kb_value:
                    print(f"DEBUG: KB price extracted - line: {line}, value: {kb_value}")
                    return kb_value
        
        # 패턴 매칭으로 재시도 (더 강력한 패턴)
        kb_patterns = [
            r'kb시세\s*:?\s*일반\s*([\d,]+)\s*만원',  # KB시세 : 일반 125,000만원
            r'kb시세\s*:?\s*([\d,]+)\s*만원',  # KB시세 : 125,000만원
            r'kb시세\s*:?\s*일반\s*([\d,]+)',  # KB시세 : 일반 125,000
            r'kb시세\s*:?\s*([\d,]+)',  # KB시세 : 125,000
            r'kb시세[^:]*:?\s*일반\s*([\d,]+)',  # KB시세 일반 125,000
            r'kb시세[^:]*:?\s*([\d,]+)',  # KB시세 125,000
        ]
        
        for pattern in kb_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                price_str = match.group(1).replace(",", "").strip()
                if price_str:
                    # 전체 컨텍스트를 찾아서 반환
                    kb_context = re.search(r'kb시세[^:]*:?\s*(.+?)(?=\n|$)', text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                    if kb_context:
                        kb_value = kb_context.group(1).strip()
                        # 다음 줄도 포함 (하한 정보 등)
                        for i, line in enumerate(lines):
                            if 'kb시세' in line.lower():
                                for j in range(1, 3):  # 다음 1-2줄 확인
                                    if i + j < len(lines):
                                        next_line = lines[i + j].strip()
                                        if next_line and (any(kw in next_line for kw in ['하한', '상한', '일반']) or re.search(r'[\d,]+', next_line)):
                                            kb_value += " " + next_line
                                break
                        print(f"DEBUG: KB price from pattern matching: {kb_value}")
                        return kb_value
        
        print(f"DEBUG: No KB price found in text")
        return None
    
    def _extract_region(self, address: str) -> Optional[str]:
        """주소에서 행정구역 추출 (구/시/군 단위까지)"""
        if not address:
            return None
        
        print(f"DEBUG: _extract_region - input address: '{address}'")
        
        # 행정구역 리스트 (구/시/군 단위) - 전체 지역 리스트 기준
        # 사용자가 제공한 전체 지역 리스트 (공백 제거 버전)
        regions = [
            "서울특별시종로구", "서울특별시중구", "서울특별시용산구", "서울특별시성동구",
            "서울특별시광진구", "서울특별시동대문구", "서울특별시중랑구", "서울특별시성북구",
            "서울특별시강북구", "서울특별시도봉구", "서울특별시노원구", "서울특별시은평구",
            "서울특별시서대문구", "서울특별시마포구", "서울특별시양천구", "서울특별시강서구",
            "서울특별시구로구", "서울특별시금천구", "서울특별시영등포구", "서울특별시동작구",
            "서울특별시관악구", "서울특별시서초구", "서울특별시강남구", "서울특별시송파구",
            "서울특별시강동구",
            "경기도성남시분당구", "경기도광명시", "경기도과천시", "경기도하남시",
            "경기도수원시장안구", "경기도수원시권선구", "경기도수원시팔달구", "경기도수원시영통구",
            "경기도성남시수정구", "경기도성남시중원구", "경기도안양시만안구", "경기도안양시동안구",
            "경기도부천시소사구", "경기도부천시오정구", "경기도부천시원미구", "경기도고양시덕양구",
            "경기도고양시일산동구", "경기도고양시일산서구", "인천광역시연수구", "인천광역시부평구",
            "경기도의정부시", "경기도안산시상록구", "경기도안산시단원구", "경기도구리시",
            "경기도남양주시", "경기도군포시", "경기도의왕시", "경기도용인시처인구",
            "경기도용인시기흥구", "경기도용인시수지구", "경기도김포시", "경기도화성시",
            "경기도평택시", "경기도동두천시", "경기도오산시", "경기도시흥시",
            "경기도파주시", "경기도안성시", "경기도광주시", "경기도양주시",
            "경기도이천시", "경기도포천시", "경기도여주시", "경기도연천군",
            "경기도가평군", "경기도양평군",
            "인천광역시중구", "인천광역시동구", "인천광역시남동구", "인천광역시계양구",
            "인천광역시서구", "인천광역시미추홀구", "인천광역시강화군", "인천광역시옹진군",
            "광주광역시동구", "광주광역시서구", "광주광역시남구", "광주광역시북구", "광주광역시광산구",
            "대전광역시동구", "대전광역시중구", "대전광역시서구", "대전광역시유성구", "대전광역시대덕구",
            "울산광역시중구", "울산광역시남구", "울산광역시동구", "울산광역시북구", "울산광역시울주군",
            "세종특별자치시세종시",
            "강원특별자치도춘천시", "강원특별자치도원주시", "강원특별자치도강릉시",
            "강원특별자치도동해시", "강원특별자치도태백시", "강원특별자치도속초시", "강원특별자치도삼척시",
            "강원특별자치도홍천군", "강원특별자치도횡성군", "강원특별자치도영월군", "강원특별자치도평창군",
            "강원특별자치도정선군", "강원특별자치도철원군", "강원특별자치도화천군", "강원특별자치도양구군",
            "강원특별자치도인제군", "강원특별자치도고성군", "강원특별자치도양양군",
            "충청북도충주시", "충청북도제천시", "충청북도청주시상당구", "충청북도청주시서원구",
            "충청북도청주시흥덕구", "충청북도청주시청원구", "충청북도보은군", "충청북도옥천군",
            "충청북도영동군", "충청북도진천군", "충청북도괴산군", "충청북도음성군",
            "충청북도단양군", "충청북도증평군",
            "충청남도천안시동남구", "충청남도천안시서북구", "충청남도공주시", "충청남도보령시",
            "충청남도아산시", "충청남도서산시", "충청남도논산시", "충청남도계룡시",
            "충청남도당진시", "충청남도금산군", "충청남도부여군", "충청남도서천군",
            "충청남도청양군", "충청남도홍성군", "충청남도예산군", "충청남도태안군",
            "전북특별자치도전주시완산구", "전북특별자치도전주시덕진구", "전북특별자치도군산시",
            "전북특별자치도익산시", "전북특별자치도정읍시", "전북특별자치도남원시", "전북특별자치도김제시",
            "전북특별자치도완주군", "전북특별자치도진안군", "전북특별자치도무주군", "전북특별자치도장수군",
            "전북특별자치도임실군", "전북특별자치도순창군", "전북특별자치도고창군", "전북특별자치도부안군",
            "전라남도목포시", "전라남도여수시", "전라남도순천시", "전라남도나주시",
            "전라남도광양시", "전라남도담양군", "전라남도곡성군", "전라남도구례군",
            "전라남도고흥군", "전라남도보성군", "전라남도화순군", "전라남도장흥군",
            "전라남도강진군", "전라남도해남군", "전라남도영암군", "전라남도무안군",
            "전라남도함평군", "전라남도영광군", "전라남도장성군", "전라남도완도군",
            "전라남도진도군", "전라남도신안군",
            "경상북도포항시남구", "경상북도포항시북구", "경상북도경주시", "경상북도김천시",
            "경상북도안동시", "경상북도구미시", "경상북도영주시", "경상북도영천시",
            "경상북도상주시", "경상북도문경시", "경상북도경산시", "경상북도의성군",
            "경상북도청송군", "경상북도영양군", "경상북도영덕군", "경상북도청도군",
            "경상북도고령군", "경상북도성주군", "경상북도칠곡군", "경상북도예천군",
            "경상북도봉화군", "경상북도울진군", "경상북도울릉군",
            "경상남도진주시", "경상남도통영시", "경상남도사천시", "경상남도김해시",
            "경상남도밀양시", "경상남도거제시", "경상남도양산시", "경상남도창원시의창구",
            "경상남도창원시성산구", "경상남도창원시마산합포구", "경상남도창원시마산회원구",
            "경상남도창원시진해구", "경상남도의령군", "경상남도함안군", "경상남도창녕군",
            "경상남도고성군", "경상남도남해군", "경상남도하동군", "경상남도산청군",
            "경상남도함양군", "경상남도거창군", "경상남도합천군",
            "제주특별자치도제주시", "제주특별자치도서귀포시",
            "부산광역시중구", "부산광역시서구", "부산광역시동구", "부산광역시영도구",
            "부산광역시부산진구", "부산광역시동래구", "부산광역시남구", "부산광역시북구",
            "부산광역시해운대구", "부산광역시사하구", "부산광역시금정구", "부산광역시강서구",
            "부산광역시연제구", "부산광역시수영구", "부산광역시사상구", "부산광역시기장군",
            "대구광역시중구", "대구광역시동구", "대구광역시서구", "대구광역시남구",
            "대구광역시북구", "대구광역시수성구", "대구광역시달서구", "대구광역시달성군",
            "대구광역시군위군"
        ]
        
        # 공백 제거 후 매칭
        address_clean = address.replace(" ", "")
        
        # 긴 행정구역부터 매칭 (더 구체적인 매칭 우선)
        for region in sorted(regions, key=len, reverse=True):
            region_clean = region.replace(" ", "")
            if region_clean in address_clean:
                # 원본 region 형식 반환 (공백 없는 버전)
                result = region.replace(" ", "")
                print(f"DEBUG: _extract_region - matched region: '{result}'")
                return result
        
        # 매칭 실패 시 광역 단위로 fallback
        fallback_regions = ["서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산",
                           "세종", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
        
        for region in fallback_regions:
            if region in address_clean:
                print(f"DEBUG: _extract_region - fallback matched: '{region}'")
                return region
        
        print(f"DEBUG: _extract_region - no match found")
        return None
    
    def _extract_required_amount(self, requests_text: str) -> Optional[float]:
        """
        요청사항에서 필요자금 추출
        예: "필요자금 1억" -> 10000.0 (만원 단위)
        예: "필요자금 5천만" -> 5000.0
        """
        if not requests_text:
            return None
        
        # "필요자금" 키워드 찾기
        if "필요자금" not in requests_text:
            return None
        
        # 필요자금 뒤의 숫자 추출
        # 패턴: "필요자금" + 공백 + 숫자 + (억/천만/만원 등)
        import re
        
        # 다양한 패턴 시도
        patterns = [
            r'필요자금\s*[:\s]*(\d+)\s*억',  # "필요자금 1억"
            r'필요자금\s*[:\s]*(\d+)\s*천만',  # "필요자금 5천만"
            r'필요자금\s*[:\s]*([\d,]+)\s*만원?',  # "필요자금 10,000만원"
            r'필요자금\s*[:\s]*([\d,]+)',  # "필요자금 10000"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, requests_text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(",", "").strip()
                try:
                    amount = float(amount_str)
                    # "억" 단위인 경우 만원으로 변환
                    if "억" in pattern:
                        amount = amount * 10000
                    # "천만" 단위인 경우 만원으로 변환
                    elif "천만" in pattern:
                        amount = amount * 1000
                    print(f"DEBUG: _extract_required_amount - found: {amount}만원 (from pattern: {pattern})")
                    return amount
                except ValueError:
                    continue
        
        print(f"DEBUG: _extract_required_amount - no amount found in: {requests_text}")
        return None

