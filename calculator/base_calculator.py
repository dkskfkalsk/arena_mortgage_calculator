# -*- coding: utf-8 -*-
"""
금융사 계산기 클래스
개별 금융사 계산 및 모든 금융사 계산 관리
"""

import json
import os
from typing import Dict, List, Optional, Any, Union
from utils.validators import validate_kb_price


class BaseCalculator:
    """
    금융사 계산기 베이스 클래스
    """
    
    def __init__(self, config: Union[Dict[str, Any], str]):
        """
        Args:
            config: 금융사별 설정 딕셔너리 또는 JSON 설정 파일 경로
        """
        # JSON 파일 경로인 경우 로드
        if isinstance(config, str):
            with open(config, "r", encoding="utf-8") as f:
                config = json.load(f)
        
        self.config = config
        self.bank_name = config.get("bank_name", "Unknown")
    
    def calculate(self, property_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        담보대출 한도 및 금리 계산 (범용 구현)
        
        Args:
            property_data: 파싱된 담보물건 정보
                - kb_price: KB시세 (만원)
                - region: 지역 (예: "서울", "부산")
                - mortgages: 근저당권 설정 내역 리스트
                - credit_score: 신용점수 (없으면 None)
                - etc...
        
        Returns:
            계산 결과 딕셔너리 또는 None (산출 불가 시)
            {
                "bank_name": "BNK캐피탈",
                "results": [
                    {
                        "ltv": 80,
                        "amount": 49300,
                        "interest_rate": 7.60,
                        "interest_rate_range": None,  # 신용점수 없을 때만 사용
                        "type": "후순위",
                        "available_amount": 49300,  # 대환 시 가용한도
                        "total_amount": 49300,  # 대환 시 전체 금액
                        "is_refinance": False
                    },
                    ...
                ],
                "conditions": ["조건1", "조건2"],
                "errors": []
            }
        """
        # KB시세 검증
        kb_price_raw = property_data.get("kb_price")
        print(f"DEBUG: BaseCalculator.calculate - kb_price_raw: {kb_price_raw}, type: {type(kb_price_raw)}")
        kb_price = self.validate_kb_price(kb_price_raw)
        print(f"DEBUG: BaseCalculator.calculate - kb_price after validation: {kb_price}")
        if kb_price is None:
            print(f"DEBUG: BaseCalculator.calculate - KB price is None, returning None")
            return None  # 시세 없으면 산출 불가
        
        # 지역 확인
        region = property_data.get("region", "")
        if not region:
            print(f"DEBUG: BaseCalculator.calculate - region is empty")
            return None
        
        # 대상 지역 확인 (광역 단위로 체크)
        target_regions = self.config.get("target_regions", [])
        if target_regions:
            is_target_region = False
            for target in target_regions:
                if target in region:  # "서울" in "서울특별시광진구"
                    is_target_region = True
                    break
            if not is_target_region:
                print(f"DEBUG: BaseCalculator.calculate - Region {region} is not in target regions: {target_regions}")
                return None
        
        # 급지 확인
        grade = self.get_region_grade(region)
        print(f"DEBUG: BaseCalculator.calculate - region: {region}, grade: {grade}")
        if grade is None:
            print(f"DEBUG: BaseCalculator.calculate - grade is None for region: {region}")
            return None
        
        # 최대 LTV 확인
        max_ltv = self.get_max_ltv_by_grade(grade)
        print(f"DEBUG: BaseCalculator.calculate - grade: {grade}, max_ltv: {max_ltv}")  # 추가
        if max_ltv is None:
            print(f"DEBUG: BaseCalculator.calculate - max_ltv is None for grade {grade}, returning None")  # 추가
            return None
        
        # 기존 근저당권 총액 계산
        mortgages = property_data.get("mortgages", [])
        total_mortgage = self.calculate_total_mortgage(mortgages)
        print(f"DEBUG: BaseCalculator.calculate - mortgages: {mortgages}")  # 추가
        print(f"DEBUG: BaseCalculator.calculate - total_mortgage: {total_mortgage}")  # 추가
        
        # 신용점수/등급 확인
        credit_score = property_data.get("credit_score")
        credit_grade = self.credit_score_to_grade(credit_score)
        
        # 대환 여부 판단
        is_refinance = property_data.get("is_refinance", False)
        
        # 필요자금이 있으면 LTV별 계산을 건너뛰고 필요자금 기준으로 역산 계산
        required_amount = property_data.get("required_amount")
        results = []
        
        if required_amount:
            print(f"DEBUG: BaseCalculator.calculate - required_amount: {required_amount}만원, calculating LTV from required amount (skipping LTV steps)")  # 추가
            
            # LTV 역산 공식: 필요자금 = KB시세 * LTV/100 - 기존 근저당권(원금)
            # LTV = (필요자금 + 기존 근저당권 원금) / KB시세 * 100
            # 근저당권에서 원금만 사용 (괄호 안의 금액)
            
            # 근저당권 원금 계산 (괄호 안의 금액)
            mortgage_principal = 0.0
            for mortgage in mortgages:
                # amount가 원금 (괄호 안의 금액)
                principal = mortgage.get("amount", 0)
                if isinstance(principal, (int, float)):
                    mortgage_principal += principal
            
            # LTV 역산
            required_total = required_amount + mortgage_principal
            calculated_ltv = (required_total / kb_price) * 100
            
            print(f"DEBUG: BaseCalculator.calculate - mortgage_principal: {mortgage_principal}만원, required_total: {required_total}만원, calculated_ltv: {calculated_ltv:.2f}%")  # 추가
            
            # 계산된 LTV가 max_ltv를 초과하면 불가능
            if calculated_ltv > max_ltv:
                print(f"DEBUG: BaseCalculator.calculate - calculated_ltv {calculated_ltv:.2f}% > max_ltv {max_ltv}%, not possible")  # 추가
                results = []
            else:
                # 계산된 정확한 LTV 사용 (ltv_steps에 없어도 됨)
                # 금리 조회를 위해 가장 가까운 ltv_steps 값 찾기
                ltv_steps = self.config.get("ltv_steps", [90, 85, 80, 75, 70, 65])
                closest_ltv_for_rate = None
                if ltv_steps:
                    # 계산된 LTV에 가장 가까운 ltv_steps 값 찾기
                    closest_ltv_for_rate = min(ltv_steps, key=lambda x: abs(x - calculated_ltv))
                    print(f"DEBUG: BaseCalculator.calculate - using closest LTV {closest_ltv_for_rate}% for rate lookup (calculated: {calculated_ltv:.2f}%)")  # 추가
                else:
                    closest_ltv_for_rate = int(round(calculated_ltv))
                
                # 금리 조회 (가장 가까운 ltv_steps 값 사용)
                rate_info = self.get_interest_rate(credit_score, credit_grade, int(closest_ltv_for_rate), grade)
                
                # 결과 생성 (LTV는 정확히 계산된 값 사용, 금액은 정확히 필요자금으로)
                result = {
                    "ltv": round(calculated_ltv, 2),  # 소수점 2자리까지 표시
                    "amount": required_amount,
                    "interest_rate": rate_info.get("interest_rate"),
                    "interest_rate_range": rate_info.get("interest_rate_range"),
                    "type": "대환" if is_refinance else "후순위",
                    "available_amount": required_amount,
                    "total_amount": required_amount,
                    "is_refinance": is_refinance,
                    "credit_grade": rate_info.get("credit_grade")
                }
                
                results = [result]  # 하나의 결과만 반환
                print(f"DEBUG: BaseCalculator.calculate - created result with LTV {calculated_ltv:.2f}% and amount {required_amount}만원")  # 추가
        else:
            # 필요자금이 없으면 기존대로 LTV별 한도 계산
            ltv_steps = self.config.get("ltv_steps", [90, 85, 80, 75, 70, 65])
            
            print(f"DEBUG: BaseCalculator.calculate - max_ltv: {max_ltv}, ltv_steps: {ltv_steps}")  # 추가
            
            for ltv in ltv_steps:
                # 최대 LTV를 초과하면 스킵
                if ltv > max_ltv:
                    print(f"DEBUG: LTV {ltv} > max_ltv {max_ltv}, skipping")  # 추가
                    continue
                
                # 가용 한도 계산
                amount_info = self.calculate_available_amount(
                    kb_price, ltv, total_mortgage, is_refinance
                )
                
                print(f"DEBUG: LTV {ltv} - amount_info: {amount_info}")  # 추가
                
                # 가용 한도가 0 이하면 스킵
                if amount_info["available_amount"] <= 0:
                    print(f"DEBUG: LTV {ltv} - available_amount <= 0, skipping")  # 추가
                    continue
                
                # 금리 조회 (82% LTV의 경우 region_grade에 따라 다른 금리 적용)
                rate_info = self.get_interest_rate(credit_score, credit_grade, ltv, grade)
                
                result = {
                    "ltv": ltv,
                    "amount": round(amount_info["available_amount"]),
                    "interest_rate": rate_info.get("interest_rate"),
                    "interest_rate_range": rate_info.get("interest_rate_range"),
                    "type": "대환" if is_refinance else "후순위",
                    "available_amount": round(amount_info["available_amount"]),
                    "total_amount": round(amount_info["total_amount"]),
                    "is_refinance": is_refinance,
                    "credit_grade": rate_info.get("credit_grade")
                }
                
                results.append(result)
        
        # 결과가 없으면 None 반환
        if not results:
            print(f"DEBUG: BaseCalculator.calculate - no results found for {self.bank_name}, returning None")  # 추가
            return None
        
        print(f"DEBUG: BaseCalculator.calculate - {self.bank_name} found {len(results)} results")  # 추가
        return {
            "bank_name": self.bank_name,
            "results": results,
            "conditions": self.config.get("conditions", []),
            "errors": []
        }
    
    def credit_score_to_grade(self, credit_score: Optional[int]) -> Optional[int]:
        """
        신용점수를 등급으로 변환
        금융사별 설정 파일의 credit_score_to_grade를 사용하고,
        없으면 전역 설정을 fallback으로 사용
        """
        print(f"DEBUG: credit_score_to_grade - credit_score: {credit_score}")  # 추가
        if credit_score is None:
            print(f"DEBUG: credit_score_to_grade - credit_score is None, returning None")  # 추가
            return None
        
        # 금융사별 설정 파일의 매핑 확인
        score_map = self.config.get("credit_score_to_grade", {})
        print(f"DEBUG: credit_score_to_grade - score_map: {score_map}")  # 추가
        if score_map:
            for range_str, grade in score_map.items():
                # "920-1000" 형식을 파싱
                parts = range_str.split("-")
                if len(parts) == 2:
                    try:
                        min_score = int(parts[0])
                        max_score = int(parts[1])
                        print(f"DEBUG: credit_score_to_grade - checking range {range_str}: {min_score} <= {credit_score} <= {max_score}")  # 추가
                        if min_score <= credit_score <= max_score:
                            print(f"DEBUG: credit_score_to_grade - matched! returning grade: {grade}")  # 추가
                            return grade
                    except ValueError:
                        continue
        
        print(f"DEBUG: credit_score_to_grade - no match found, returning None")  # 추가
        return None
    
    def validate_kb_price(self, kb_price: Any) -> Optional[float]:
        """
        KB시세 검증 및 변환
        시세가 없으면 None 반환 (산출 불가)
        """
        print(f"DEBUG: BaseCalculator.validate_kb_price - input: {kb_price}, type: {type(kb_price)}")
        result = validate_kb_price(kb_price)
        print(f"DEBUG: BaseCalculator.validate_kb_price - output: {result}")
        return result
    
    def get_region_grade(self, region: str) -> Optional[int]:
        """
        지역별 급지 조회
        구/시 단위 매핑이 있으면 우선 사용, 없으면 광역 단위로 fallback
        """
        region_grades = self.config.get("region_grades", {})
        
        # 공백 제거 버전으로도 확인
        region_clean = region.replace(" ", "")
        
        # 1. 정확한 매칭 시도 (원본)
        if region in region_grades:
            print(f"DEBUG: get_region_grade - exact match: {region}")
            return region_grades.get(region)
        
        # 2. 공백 제거 버전으로 매칭 시도
        if region_clean in region_grades:
            print(f"DEBUG: get_region_grade - clean match: {region_clean}")
            return region_grades.get(region_clean)
        
        # 3. 키의 공백 제거 버전과 비교
        for key in region_grades.keys():
            if key.replace(" ", "") == region_clean:
                print(f"DEBUG: get_region_grade - key clean match: {key} -> {region_clean}")
                return region_grades.get(key)
        
        # 4. 광역 단위로 fallback
        fallback_map = {
            "서울": ["서울"],
            "경기": ["경기"],
            "인천": ["인천"],
            "부산": ["부산"],
            "대구": ["대구"],
            "광주": ["광주"],
            "대전": ["대전"],
            "울산": ["울산"],
            "세종": ["세종"],
            "강원": ["강원"],
            "충북": ["충북", "청주", "충주", "제천"],
            "충남": ["충남", "천안", "아산", "공주", "보령", "서산", "논산", "계룡", "당진"],
            "전북": ["전북", "전주", "군산", "익산", "정읍", "남원", "김제"],
            "전남": ["전남", "목포", "순천", "여수", "나주", "광양"],
            "경북": ["경북", "포항", "구미", "경산", "경주", "김천", "안동", "영주", "영천", "상주", "문경"],
            "경남": ["경남", "창원", "진주", "김해", "양산", "거제", "통영", "사천", "밀양"],
            "제주": ["제주"]
        }
        
        for fallback_key, keywords in fallback_map.items():
            for keyword in keywords:
                if keyword in region:
                    fallback_grade = region_grades.get(fallback_key)
                    if fallback_grade is not None:
                        print(f"DEBUG: get_region_grade - fallback match: {keyword} -> {fallback_key} (grade: {fallback_grade})")
                        return fallback_grade
        
        print(f"DEBUG: get_region_grade - no match found for region: {region}")
        return None
    
    def get_max_ltv_by_grade(self, grade: int) -> Optional[int]:
        """
        급지별 최대 LTV 조회
        """
        max_ltv_by_grade = self.config.get("max_ltv_by_grade", {})
        print(f"DEBUG: get_max_ltv_by_grade - grade: {grade} (type: {type(grade)}), max_ltv_by_grade keys: {list(max_ltv_by_grade.keys())}")  # 추가
        # JSON 키는 문자열이므로 int를 문자열로 변환하여 조회
        result = max_ltv_by_grade.get(str(grade))
        print(f"DEBUG: get_max_ltv_by_grade - result: {result}")  # 추가
        return result
    
    def calculate_total_mortgage(self, mortgages: List[Dict[str, Any]]) -> float:
        """
        기존 근저당권 총액 계산 (만원 단위)
        """
        total = 0.0
        for mortgage in mortgages:
            amount = mortgage.get("amount", 0)
            if isinstance(amount, (int, float)):
                total += amount
        return total
    
    def calculate_available_amount(
        self, 
        kb_price: float, 
        ltv: int, 
        total_mortgage: float,
        is_refinance: bool = False
    ) -> Dict[str, float]:
        """
        가용 한도 계산
        
        Args:
            kb_price: KB시세 (만원)
            ltv: LTV 비율 (예: 87)
            total_mortgage: 기존 근저당권 총액 (만원)
            is_refinance: 대환 여부
        
        Returns:
            {
                "total_amount": 전체 대출 금액,
                "available_amount": 가용 한도
            }
        """
        max_amount = kb_price * (ltv / 100)
        print(f"DEBUG: calculate_available_amount - kb_price: {kb_price}, ltv: {ltv}, total_mortgage: {total_mortgage}, is_refinance: {is_refinance}")  # 추가
        print(f"DEBUG: calculate_available_amount - max_amount (kb_price * ltv/100): {max_amount}")  # 추가
        
        if is_refinance:
            # 대환인 경우: 전체 금액과 가용한도 구분
            available = max_amount - total_mortgage
            result = {
                "total_amount": max_amount,
                "available_amount": max(0, available)
            }
            print(f"DEBUG: calculate_available_amount - 대환: available={available}, result={result}")  # 추가
            return result
        else:
            # 후순위인 경우
            available = max_amount - total_mortgage
            result = {
                "total_amount": max(0, available),
                "available_amount": max(0, available)
            }
            print(f"DEBUG: calculate_available_amount - 후순위: available={available}, result={result}")  # 추가
            return result
    
    def get_interest_rate(
        self, 
        credit_score: Optional[int], 
        credit_grade: Optional[int],
        ltv: int,
        region_grade: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        신용등급별 금리 조회
        
        Args:
            credit_score: 신용점수 (없으면 None)
            credit_grade: 신용등급 (1-7)
            ltv: LTV 비율
            region_grade: 지역 급지 (1 또는 2, 82% LTV의 경우 2급지 금리 적용)
        
        Returns:
            {
                "interest_rate": 금리 (신용점수 있을 때),
                "interest_rate_range": (최저, 최고) 튜플 (신용점수 없을 때),
                "credit_grade": 신용등급
            }
        """
        ltv_rates = self.config.get("interest_rates_by_ltv", {})
        
        # 82% LTV이고 2급지인 경우 특별 처리
        if ltv == 82 and region_grade == 2:
            ltv_key = "82_2"
            print(f"DEBUG: get_interest_rate - 82% LTV with region_grade 2, using key: {ltv_key}")  # 추가
        else:
            ltv_key = str(ltv)
        
        print(f"DEBUG: get_interest_rate - ltv: {ltv}, credit_score: {credit_score}, credit_grade: {credit_grade}, region_grade: {region_grade}")  # 추가
        print(f"DEBUG: get_interest_rate - ltv_key: {ltv_key}, available ltv_keys: {list(ltv_rates.keys())}")  # 추가
        
        if ltv_key not in ltv_rates:
            print(f"DEBUG: get_interest_rate - LTV {ltv_key} not found in interest_rates_by_ltv")  # 추가
            return {
                "interest_rate": None,
                "interest_rate_range": None,
                "credit_grade": credit_grade
            }
        
        grade_rates = ltv_rates[ltv_key]
        print(f"DEBUG: get_interest_rate - grade_rates for LTV {ltv_key}: {grade_rates}")  # 추가
        
        if credit_grade is not None:
            # 신용등급이 있으면 해당 등급의 금리 반환
            grade_key = str(credit_grade)
            print(f"DEBUG: get_interest_rate - looking for grade_key: {grade_key}")  # 추가
            if grade_key in grade_rates:
                rate = grade_rates[grade_key]
                print(f"DEBUG: get_interest_rate - found rate: {rate} for grade {credit_grade}")  # 추가
                return {
                    "interest_rate": rate,
                    "interest_rate_range": None,
                    "credit_grade": credit_grade
                }
            else:
                print(f"DEBUG: get_interest_rate - grade_key {grade_key} not found in grade_rates")  # 추가
        
        # 신용점수/등급이 없으면 최저~최고 금리 범위 반환
        all_rates = [v for v in grade_rates.values() if isinstance(v, (int, float))]
        if all_rates:
            min_rate = min(all_rates)
            max_rate = max(all_rates)
            print(f"DEBUG: get_interest_rate - no credit_grade, returning range: {min_rate}~{max_rate}")  # 추가
            return {
                "interest_rate": None,
                "interest_rate_range": (min_rate, max_rate),
                "credit_grade": None
            }
        
        print(f"DEBUG: get_interest_rate - no rates found, returning None")  # 추가
        return {
            "interest_rate": None,
            "interest_rate_range": None,
            "credit_grade": credit_grade
        }
    
    @classmethod
    def calculate_all_banks(cls, property_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        모든 금융사에 대해 계산 수행
        
        Args:
            property_data: 파싱된 담보물건 정보
        
        Returns:
            계산 결과 리스트 (산출 불가한 금융사는 제외)
        """
        # data/banks 폴더 경로
        current_dir = os.path.dirname(os.path.abspath(__file__))
        banks_dir = os.path.join(current_dir, "..", "data", "banks")
        
        if not os.path.exists(banks_dir):
            return []
        
        calculators = []
        
        # 모든 JSON 파일 찾기 및 계산기 생성
        for filename in os.listdir(banks_dir):
            if filename.endswith("_config.json") or filename.endswith(".json"):
                config_path = os.path.join(banks_dir, filename)
                try:
                    calculator = cls(config_path)
                    calculators.append(calculator)
                except Exception as e:
                    print(f"⚠️  계산기 로드 실패 ({filename}): {e}")
                    continue
        
        # 모든 계산기 실행
        results = []
        for calculator in calculators:
            try:
                result = calculator.calculate(property_data)
                if result is not None:
                    results.append(result)
            except Exception as e:
                print(f"계산기 {calculator.bank_name} 에러: {e}")
                continue
        
        return results

