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
    
    # 전체 지역 리스트 (메인 계산기 기준)
    ALL_REGIONS = [
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
    
    @staticmethod
    def round_down_to_hundred_thousand(amount: float) -> float:
        """
        100만 단위로 절삭 (10만 단위 이하 버림)
        예: 7550 -> 7500, 4850 -> 4800
        
        Args:
            amount: 금액 (만원 단위)
        
        Returns:
            100만 단위로 절삭된 금액
        """
        return (int(amount) // 100) * 100
    
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
        
        # 메인 계산기 전체 지역 리스트 기준 검증
        region_clean = region.replace(" ", "")
        is_valid_region = False
        for valid_region in self.ALL_REGIONS:
            if valid_region.replace(" ", "") == region_clean:
                is_valid_region = True
                break
        
        if not is_valid_region:
            print(f"DEBUG: BaseCalculator.calculate - Region {region} is not in ALL_REGIONS list, 취급 불가지역")
            return {
                "bank_name": self.bank_name,
                "results": [],
                "conditions": self.config.get("conditions", []),
                "errors": ["취급 불가지역"]
            }
        
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
                # 취급 불가지역인 경우 특별한 결과 반환
                return {
                    "bank_name": self.bank_name,
                    "results": [],
                    "conditions": self.config.get("conditions", []),
                    "errors": ["취급 불가지역"]
                }
        
        # 급지 확인
        grade = self.get_region_grade(region)
        print(f"DEBUG: BaseCalculator.calculate - region: {region}, grade: {grade}")
        if grade is None:
            print(f"DEBUG: BaseCalculator.calculate - grade is None for region: {region}, 취급 불가지역")
            # 급지가 없으면 취급 불가지역으로 처리
            return {
                "bank_name": self.bank_name,
                "results": [],
                "conditions": self.config.get("conditions", []),
                "errors": ["취급 불가지역"]
            }
        
        # 6급지인 경우 취급 불가지역으로 처리
        if grade == 6:
            print(f"DEBUG: BaseCalculator.calculate - grade 6 for region: {region}, 취급 불가지역")
            return {
                "bank_name": self.bank_name,
                "results": [],
                "conditions": self.config.get("conditions", []),
                "errors": ["취급 불가지역"]
            }
        
        # 기준 LTV 이하 지역 확인
        below_standard_ltv = self.get_below_standard_ltv(region)
        is_below_standard = below_standard_ltv is not None
        
        # 최대 LTV 확인 (1급지인 경우 A/B 그룹 구분)
        max_ltv = self.get_max_ltv_by_grade(grade, region)
        print(f"DEBUG: BaseCalculator.calculate - grade: {grade}, max_ltv: {max_ltv}, below_standard_ltv: {below_standard_ltv}")  # 추가
        if max_ltv is None or max_ltv == 0:
            print(f"DEBUG: BaseCalculator.calculate - max_ltv is None or 0 for grade {grade}, returning None")  # 추가
            return None
        
        # 기준 LTV 이하 지역인 경우 해당 LTV를 최대 LTV로 사용
        if is_below_standard:
            max_ltv = below_standard_ltv
            print(f"DEBUG: BaseCalculator.calculate - 기준 LTV 이하 지역: {region}, 적용 LTV: {max_ltv}%")
        
        # 기존 근저당권 총액 계산 (채권최고액 기준)
        mortgages = property_data.get("mortgages", [])
        
        # 대환할 근저당권 찾기 (여러 개 대비하여 누적합으로 처리)
        refinance_principal = 0.0  # 대환할 근저당권 원금 합계
        other_mortgages = []  # 나머지 근저당권들
        
        for mortgage in mortgages:
            if mortgage.get("is_refinance", False):
                mortgage_amount = float(mortgage.get("amount", 0) or 0)
                refinance_principal += mortgage_amount
                print(f"DEBUG: BaseCalculator.calculate - 대환할 근저당권 발견: priority={mortgage.get('priority')}, institution={mortgage.get('institution')}, principal={mortgage_amount}만원")
            else:
                other_mortgages.append(mortgage)
        
        # 나머지 근저당권의 채권최고액만 합산
        total_mortgage = self.calculate_total_mortgage(other_mortgages)
        print(f"DEBUG: BaseCalculator.calculate - mortgages: {mortgages}")  # 추가
        print(f"DEBUG: BaseCalculator.calculate - refinance_principal(대환 원금 합계): {refinance_principal}만원, total_mortgage(나머지 채권최고액): {total_mortgage}")  # 추가
        
        # 대환 여부 판단
        is_refinance = refinance_principal > 0
        
        # 신용점수/등급 확인
        credit_score = property_data.get("credit_score")
        credit_grade = self.credit_score_to_grade(credit_score)
        
        # 택시 관련 한도 제한 확인
        taxi_limit_config = self.config.get("taxi_limit", {})
        max_amount_limit = None
        if taxi_limit_config.get("enabled", False):
            special_notes = property_data.get("special_notes", "")
            if special_notes:
                keywords = taxi_limit_config.get("keywords", [])
                for keyword in keywords:
                    if keyword in special_notes:
                        max_amount_limit = taxi_limit_config.get("max_amount", 10000)  # 기본값 1억
                        print(f"DEBUG: BaseCalculator.calculate - 택시 관련 키워드 '{keyword}' 발견, 한도 제한: {max_amount_limit}만원")
                        break
        
        # 필요자금이 있으면 LTV별 계산을 건너뛰고 필요자금 기준으로 역산 계산
        required_amount = property_data.get("required_amount")
        results = []
        
        # 택시 한도 제한이 적용되면 1억을 받기 위해 필요한 LTV를 역산
        if max_amount_limit is not None and not required_amount:
            print(f"DEBUG: BaseCalculator.calculate - 택시 한도 제한 적용, 1억을 받기 위한 LTV 역산")
            
            # 근저당권 채권최고액 계산 (대환할 근저당권 제외한 나머지만)
            mortgage_max_amount = 0.0
            for mortgage in other_mortgages:
                # 채권최고액이 있으면 사용, 없으면 원금에 1.2를 곱해서 추정
                max_amount = mortgage.get("max_amount")
                if max_amount is not None and isinstance(max_amount, (int, float)):
                    mortgage_max_amount += max_amount
                else:
                    principal = mortgage.get("amount", 0)
                    if isinstance(principal, (int, float)):
                        mortgage_max_amount += principal * 1.2
            
            # 대환할 근저당권 원금 추가
            if is_refinance:
                mortgage_max_amount += refinance_principal
            
            # 1억(원금)을 받기 위한 LTV 역산 (채권최고액 기준)
            # 1억(원금)의 채권최고액 = 1억 * 1.2 = 1.2억
            limit_max_amount = max_amount_limit * 1.2
            
            # LTV 역산 (채권최고액 기준)
            required_total = limit_max_amount + mortgage_max_amount
            calculated_ltv = (required_total / kb_price) * 100
            
            print(f"DEBUG: BaseCalculator.calculate - 택시 한도 제한 LTV 역산: mortgage_max_amount(채권최고액)={mortgage_max_amount}만원, limit_max_amount={limit_max_amount}만원, required_total={required_total}만원, calculated_ltv={calculated_ltv:.2f}%")
            
            # 계산된 LTV가 max_ltv를 초과하면 불가능
            if calculated_ltv > max_ltv:
                print(f"DEBUG: BaseCalculator.calculate - 택시 한도 제한 LTV {calculated_ltv:.2f}% > max_ltv {max_ltv}%, not possible")
                results = []
            else:
                # 금리 조회를 위해 가장 가까운 ltv_steps 값 찾기
                ltv_steps = self.config.get("ltv_steps", [90, 85, 80, 75, 70, 65])
                closest_ltv_for_rate = None
                if ltv_steps:
                    closest_ltv_for_rate = min(ltv_steps, key=lambda x: abs(x - calculated_ltv))
                    print(f"DEBUG: BaseCalculator.calculate - 택시 한도 제한, using closest LTV {closest_ltv_for_rate}% for rate lookup (calculated: {calculated_ltv:.2f}%)")
                else:
                    closest_ltv_for_rate = int(round(calculated_ltv))
                
                # 금리 조회
                rate_info = self.get_interest_rate(credit_score, credit_grade, int(closest_ltv_for_rate), grade)
                
                # 결과 생성 (LTV는 정확히 계산된 값, 금액은 1억)
                # 100만 단위로 절삭
                rounded_amount = self.round_down_to_hundred_thousand(max_amount_limit)
                result = {
                    "ltv": round(calculated_ltv, 2),
                    "amount": rounded_amount,
                    "interest_rate": rate_info.get("interest_rate"),
                    "interest_rate_range": rate_info.get("interest_rate_range"),
                    "type": "대환" if is_refinance else "후순위",
                    "available_amount": rounded_amount,
                    "total_amount": rounded_amount,
                    "is_refinance": is_refinance,
                    "credit_grade": rate_info.get("credit_grade"),
                    "below_standard_ltv": is_below_standard,
                    "taxi_limit_applied": True  # 택시 한도 제한 적용 플래그
                }
                
                results = [result]  # 하나의 결과만 반환
                print(f"DEBUG: BaseCalculator.calculate - 택시 한도 제한 결과 생성: LTV {calculated_ltv:.2f}%, amount {max_amount_limit}만원")
        
        elif required_amount:
            print(f"DEBUG: BaseCalculator.calculate - required_amount: {required_amount}만원, calculating LTV from required amount (skipping LTV steps)")  # 추가
            
            # LTV 역산 공식 (채권최고액 기준):
            # 필요자금(원금)의 채권최고액 = 필요자금 * 1.2
            # 기존 근저당권 채권최고액 사용
            # LTV = (필요자금 채권최고액 + 기존 근저당권 채권최고액) / KB시세 * 100
            
            # 근저당권 채권최고액 계산 (대환할 근저당권 제외한 나머지만)
            mortgage_max_amount = 0.0
            for mortgage in other_mortgages:
                # 채권최고액이 있으면 사용, 없으면 원금에 1.2를 곱해서 추정
                max_amount = mortgage.get("max_amount")
                if max_amount is not None and isinstance(max_amount, (int, float)):
                    mortgage_max_amount += max_amount
                else:
                    principal = mortgage.get("amount", 0)
                    if isinstance(principal, (int, float)):
                        mortgage_max_amount += principal * 1.2
            
            # 대환할 근저당권 원금 추가
            if is_refinance:
                mortgage_max_amount += refinance_principal
            
            # 채권최고액 기준으로 계산
            # 필요자금의 채권최고액 = 필요자금(원금) * 1.2
            required_max_amount = required_amount * 1.2
            
            # LTV 역산 (채권최고액 기준)
            required_total = required_max_amount + mortgage_max_amount
            calculated_ltv = (required_total / kb_price) * 100
            
            print(f"DEBUG: BaseCalculator.calculate - mortgage_max_amount(채권최고액): {mortgage_max_amount}만원, required_max_amount(채권최고액): {required_max_amount}만원, required_total: {required_total}만원, calculated_ltv: {calculated_ltv:.2f}%")  # 추가
            
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
                
                # 택시 관련 한도 제한 적용
                final_amount = required_amount
                taxi_limit_applied = False
                if max_amount_limit is not None and final_amount > max_amount_limit:
                    final_amount = max_amount_limit
                    taxi_limit_applied = True
                    print(f"DEBUG: BaseCalculator.calculate - 택시 한도 제한 적용: {required_amount}만원 -> {final_amount}만원")
                
                # 대환인 경우 total_amount와 available_amount 구분
                if is_refinance:
                    # 전체 대출 금액 = 필요자금 + 대환 원금
                    total_amount = final_amount + refinance_principal
                    available_amount = final_amount
                else:
                    total_amount = final_amount
                    available_amount = final_amount
                
                # 100만 단위로 절삭
                rounded_amount = self.round_down_to_hundred_thousand(available_amount)
                rounded_total_amount = self.round_down_to_hundred_thousand(total_amount)
                
                # 결과 생성 (LTV는 정확히 계산된 값 사용, 금액은 정확히 필요자금으로)
                result = {
                    "ltv": round(calculated_ltv, 2),  # 소수점 2자리까지 표시
                    "amount": rounded_amount,
                    "interest_rate": rate_info.get("interest_rate"),
                    "interest_rate_range": rate_info.get("interest_rate_range"),
                    "type": "대환" if is_refinance else "후순위",
                    "available_amount": rounded_amount,
                    "total_amount": rounded_total_amount,
                    "is_refinance": is_refinance,
                    "credit_grade": rate_info.get("credit_grade"),
                    "below_standard_ltv": is_below_standard,  # 기준 LTV 이하 지역 여부
                    "taxi_limit_applied": taxi_limit_applied  # 택시 한도 제한 적용 플래그
                }
                
                results = [result]  # 하나의 결과만 반환
                print(f"DEBUG: BaseCalculator.calculate - created result with LTV {calculated_ltv:.2f}% and amount {final_amount}만원")  # 추가
        else:
            # 필요자금이 없고 택시 한도 제한도 없으면 기존대로 LTV별 한도 계산
            ltv_steps = self.config.get("ltv_steps", [90, 85, 80, 75, 70, 65])
            
            print(f"DEBUG: BaseCalculator.calculate - max_ltv: {max_ltv}, ltv_steps: {ltv_steps}")  # 추가
            
            for ltv in ltv_steps:
                # 최대 LTV를 초과하면 스킵
                if ltv > max_ltv:
                    print(f"DEBUG: LTV {ltv} > max_ltv {max_ltv}, skipping")  # 추가
                    continue
                
                # 가용 한도 계산
                amount_info = self.calculate_available_amount(
                    kb_price, ltv, total_mortgage, is_refinance, refinance_principal
                )
                
                print(f"DEBUG: LTV {ltv} - amount_info: {amount_info}")  # 추가
                
                # 가용 한도가 0 이하면 스킵
                if amount_info["available_amount"] <= 0:
                    print(f"DEBUG: LTV {ltv} - available_amount <= 0, skipping")  # 추가
                    continue
                
                # 금리 조회 (82% LTV의 경우 region_grade에 따라 다른 금리 적용)
                rate_info = self.get_interest_rate(credit_score, credit_grade, ltv, grade)
                
                # 택시 관련 한도 제한이 없으면 일반 계산
                # 100만 단위로 절삭
                final_amount = self.round_down_to_hundred_thousand(amount_info["available_amount"])
                final_total_amount = self.round_down_to_hundred_thousand(amount_info["total_amount"])
                
                result = {
                    "ltv": ltv,
                    "amount": final_amount,
                    "interest_rate": rate_info.get("interest_rate"),
                    "interest_rate_range": rate_info.get("interest_rate_range"),
                    "type": "대환" if is_refinance else "후순위",
                    "available_amount": final_amount,
                    "total_amount": final_total_amount,
                    "is_refinance": is_refinance,
                    "credit_grade": rate_info.get("credit_grade"),
                    "below_standard_ltv": is_below_standard  # 기준 LTV 이하 지역 여부
                }
                
                results.append(result)
        
        # 결과가 없으면 에러 메시지와 함께 반환 (가용 한도 부족 등)
        if not results:
            print(f"DEBUG: BaseCalculator.calculate - no results found for {self.bank_name}")
            # 최대 LTV로 계산했을 때 가용 한도 확인
            max_ltv_amount = kb_price * (max_ltv / 100)
            if total_mortgage > max_ltv_amount:
                shortage = total_mortgage - max_ltv_amount
                print(f"DEBUG: BaseCalculator.calculate - 기존 근저당권이 최대 LTV 한도를 초과: {shortage:.0f}만원 초과")
                return {
                    "bank_name": self.bank_name,
                    "results": [],
                    "conditions": self.config.get("conditions", []),
                    "errors": [f"기존 근저당권 채권최고액({total_mortgage:,.0f}만원)이 최대 한도({max_ltv_amount:,.0f}만원, LTV {max_ltv}%)를 초과하여 추가 대출 불가능"]
                }
            else:
                print(f"DEBUG: BaseCalculator.calculate - no results found for {self.bank_name}, returning None")
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
        region_grades에 명시된 지역만 처리 (fallback 없음)
        명시되지 않은 지역은 None 반환하여 취급 불가지역으로 처리
        """
        region_grades = self.config.get("region_grades", {})
        
        # 공백 제거 버전으로도 확인
        region_clean = region.replace(" ", "")
        
        # 1. 정확한 매칭 시도 (원본)
        if region in region_grades:
            grade = region_grades.get(region)
            # 광역 단위 키(서울, 경기 등)는 제외 (구체적인 지역만 처리)
            if grade is not None and not self._is_metropolitan_key(region):
                print(f"DEBUG: get_region_grade - exact match: {region} -> grade {grade}")
                return grade
        
        # 2. 공백 제거 버전으로 매칭 시도
        if region_clean in region_grades:
            grade = region_grades.get(region_clean)
            if grade is not None and not self._is_metropolitan_key(region_clean):
                print(f"DEBUG: get_region_grade - clean match: {region_clean} -> grade {grade}")
                return grade
        
        # 3. 키의 공백 제거 버전과 비교
        for key in region_grades.keys():
            if key.replace(" ", "") == region_clean:
                grade = region_grades.get(key)
                if grade is not None and not self._is_metropolitan_key(key):
                    print(f"DEBUG: get_region_grade - key clean match: {key} -> {region_clean} -> grade {grade}")
                    return grade
        
        print(f"DEBUG: get_region_grade - no match found for region: {region} (취급 불가지역)")
        return None
    
    def _is_metropolitan_key(self, key: str) -> bool:
        """
        광역 단위 키인지 확인 (서울, 경기, 인천, 부산 등)
        """
        metropolitan_keys = ["서울", "경기", "인천", "부산", "광주", "대전", "울산", "세종", 
                            "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주", "대구"]
        return key in metropolitan_keys
    
    def get_max_ltv_by_grade(self, grade: int, region: str = None) -> Optional[float]:
        """
        급지별 최대 LTV 조회
        1급지인 경우 A/B 그룹을 구분하여 반환
        
        Args:
            grade: 급지 번호 (1, 2, 3, 4)
            region: 지역명 (1급지 A/B 구분용)
        
        Returns:
            최대 LTV (float) 또는 None
        """
        max_ltv_by_grade = self.config.get("max_ltv_by_grade", {})
        print(f"DEBUG: get_max_ltv_by_grade - grade: {grade} (type: {type(grade)}), region: {region}, max_ltv_by_grade keys: {list(max_ltv_by_grade.keys())}")  # 추가
        
        # 1급지인 경우 A/B 그룹 구분
        if grade == 1 and region:
            region_clean = region.replace(" ", "")
            grade_1_group_a = self.config.get("grade_1_group_a", [])
            grade_1_group_b = self.config.get("grade_1_group_b", [])
            
            # A 그룹 확인
            for a_region in grade_1_group_a:
                if a_region.replace(" ", "") == region_clean:
                    result = max_ltv_by_grade.get("1")
                    print(f"DEBUG: get_max_ltv_by_grade - 1급지 A그룹: {region} -> LTV {result}%")
                    return result
            
            # B 그룹 확인
            for b_region in grade_1_group_b:
                if b_region.replace(" ", "") == region_clean:
                    result = max_ltv_by_grade.get("1_b")
                    print(f"DEBUG: get_max_ltv_by_grade - 1급지 B그룹: {region} -> LTV {result}%")
                    return result
            
            # 1급지이지만 A/B 그룹에 없으면 기본값 (A 그룹)
            result = max_ltv_by_grade.get("1")
            print(f"DEBUG: get_max_ltv_by_grade - 1급지 (기본값 A그룹): {region} -> LTV {result}%")
            return result
        
        # JSON 키는 문자열이므로 int를 문자열로 변환하여 조회
        result = max_ltv_by_grade.get(str(grade))
        print(f"DEBUG: get_max_ltv_by_grade - result: {result}")  # 추가
        return result
    
    def get_below_standard_ltv(self, region: str) -> Optional[float]:
        """
        기준 LTV 이하 지역인지 확인하고 해당 LTV 반환
        
        Args:
            region: 지역명
        
        Returns:
            기준 LTV 이하 지역인 경우 해당 LTV (float), 아니면 None
        """
        below_standard_ltv_regions = self.config.get("below_standard_ltv_regions", {})
        region_clean = region.replace(" ", "")
        
        # 정확한 매칭 시도
        if region in below_standard_ltv_regions:
            ltv = below_standard_ltv_regions[region]
            print(f"DEBUG: get_below_standard_ltv - exact match: {region} -> LTV {ltv}%")
            return ltv
        
        # 공백 제거 버전으로 매칭 시도
        if region_clean in below_standard_ltv_regions:
            ltv = below_standard_ltv_regions[region_clean]
            print(f"DEBUG: get_below_standard_ltv - clean match: {region_clean} -> LTV {ltv}%")
            return ltv
        
        # 키의 공백 제거 버전과 비교
        for key in below_standard_ltv_regions.keys():
            if key.replace(" ", "") == region_clean:
                ltv = below_standard_ltv_regions[key]
                print(f"DEBUG: get_below_standard_ltv - key clean match: {key} -> LTV {ltv}%")
                return ltv
        
        return None
    
    def calculate_total_mortgage(self, mortgages: List[Dict[str, Any]]) -> float:
        """
        기존 근저당권 총액 계산 (채권최고액 기준, 만원 단위)
        """
        total = 0.0
        for mortgage in mortgages:
            # 채권최고액이 있으면 사용, 없으면 원금에 1.2를 곱해서 추정
            max_amount = mortgage.get("max_amount")
            if max_amount is not None and isinstance(max_amount, (int, float)):
                total += max_amount
                print(f"DEBUG: calculate_total_mortgage - using max_amount(채권최고액): {max_amount}만원")
            else:
                # 채권최고액이 없으면 원금에 1.2를 곱해서 추정
                amount = mortgage.get("amount", 0)
                if isinstance(amount, (int, float)):
                    estimated_max = amount * 1.2
                    total += estimated_max
                    print(f"DEBUG: calculate_total_mortgage - estimated max_amount from amount: {amount}만원 -> {estimated_max}만원")
        return total
    
    def calculate_available_amount(
        self, 
        kb_price: float, 
        ltv: int, 
        total_mortgage: float,
        is_refinance: bool = False,
        refinance_principal: float = 0.0
    ) -> Dict[str, float]:
        """
        가용 한도 계산 (채권최고액 기준으로 차감)
        
        Args:
            kb_price: KB시세 (만원)
            ltv: LTV 비율 (예: 85) - 원금 기준
            total_mortgage: 기존 근저당권 총액 (채권최고액, 만원) - 대환할 근저당권 제외
            is_refinance: 대환 여부
            refinance_principal: 대환할 근저당권 원금 (만원)
        
        Returns:
            {
                "total_amount": 전체 대출 금액 (원금),
                "available_amount": 가용 한도 (원금)
            }
        """
        # LTV는 원금 기준이므로, 최대 대출 금액(원금) 계산
        max_amount_principal = kb_price * (ltv / 100)
        print(f"DEBUG: calculate_available_amount - kb_price: {kb_price}, ltv: {ltv}, total_mortgage(나머지 채권최고액): {total_mortgage}, is_refinance: {is_refinance}, refinance_principal(대환 원금): {refinance_principal}")  # 추가
        print(f"DEBUG: calculate_available_amount - max_amount_principal (kb_price * ltv/100): {max_amount_principal}")  # 추가
        
        if is_refinance:
            # 대환인 경우:
            # 추가로 받을 수 있는 금액(원금) = LTV 최대 금액 - 대환할 근저당권 원금 - 나머지 근저당권 채권최고액
            available_principal = max_amount_principal - refinance_principal - total_mortgage
            available_principal = max(0, available_principal)
            
            # 대환 총 실행금액(원금) = 대환원금 + 추가금
            total_refinance_amount = refinance_principal + available_principal
            
            result = {
                "total_amount": total_refinance_amount,
                "available_amount": available_principal
            }
            print(f"DEBUG: calculate_available_amount - 대환: available_principal={available_principal}, total_refinance_amount={total_refinance_amount}, result={result}")  # 추가
            return result
        else:
            # 후순위인 경우: 채권최고액 기준으로 차감
            # max_amount_principal(원금)에서 total_mortgage(채권최고액)을 차감
            available_principal = max_amount_principal - total_mortgage
            result = {
                "total_amount": max(0, available_principal),
                "available_amount": max(0, available_principal)
            }
            print(f"DEBUG: calculate_available_amount - 후순위: available_principal={available_principal}, result={result}")  # 추가
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
            계산 결과 리스트 (에러 메시지가 있는 경우도 포함)
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
                    # 취급 불가지역인 경우도 포함 (errors에 "취급 불가지역"이 있으면)
                    results.append(result)
            except Exception as e:
                print(f"계산기 {calculator.bank_name} 에러: {e}")
                continue
        
        return results

