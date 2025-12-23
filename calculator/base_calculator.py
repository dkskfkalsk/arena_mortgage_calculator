# -*- coding: utf-8 -*-
"""
금융사 계산기 클래스
개별 금융사 계산 및 모든 금융사 계산 관리
"""

import json
import os
import sys
import logging
from typing import Dict, List, Optional, Any, Union
from utils.validators import validate_kb_price, extract_lower_bound_price

# 로깅 설정 (Vercel에서 로그가 보이도록)
logger = logging.getLogger(__name__)

# 원본 print 함수 저장
_original_print = print

# print 함수를 래핑하여 버퍼 플러시 및 stderr 출력
def log_print(*args, **kwargs):
    """로그 출력 헬퍼 (버퍼 플러시 및 stderr 출력)"""
    message = ' '.join(str(arg) for arg in args)
    # stderr로 출력 (버퍼링 없음)
    _original_print(message, file=sys.stderr, flush=True, **kwargs)
    # stdout도 출력 (호환성)
    _original_print(message, file=sys.stdout, flush=True, **kwargs)

# print 함수를 래핑하여 모든 print 호출이 자동으로 버퍼 플러시되도록 함
def _wrapped_print(*args, **kwargs):
    """print 함수 래퍼 (버퍼 플러시 자동 적용)"""
    # flush가 명시되지 않았으면 True로 설정
    if 'flush' not in kwargs:
        kwargs['flush'] = True
    # stderr로도 출력 (Vercel 로그 캡처를 위해)
    _original_print(*args, file=sys.stderr, **kwargs)
    # 원래 의도한 출력 스트림으로도 출력
    _original_print(*args, **kwargs)

# print 함수를 래핑된 버전으로 교체
import builtins
builtins.print = _wrapped_print


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
    
    def calculate(self, property_data: Dict[str, Any], product_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
        log_print(f"DEBUG: BaseCalculator.calculate - kb_price_raw: {kb_price_raw}, type: {type(kb_price_raw)}")
        logger.debug(f"BaseCalculator.calculate - kb_price_raw: {kb_price_raw}, type: {type(kb_price_raw)}")
        kb_price = self.validate_kb_price(kb_price_raw)
        log_print(f"DEBUG: BaseCalculator.calculate - kb_price after validation: {kb_price}")
        logger.debug(f"BaseCalculator.calculate - kb_price after validation: {kb_price}")
        if kb_price is None:
            log_print(f"DEBUG: BaseCalculator.calculate - KB price is None, returning None")
            logger.warning("BaseCalculator.calculate - KB price is None, returning None")
            return None  # 시세 없으면 산출 불가
        
        # KB시세 최소 금액 확인
        min_kb_price = self.config.get("min_kb_price")
        if min_kb_price is not None and kb_price < min_kb_price:
            log_print(f"DEBUG: BaseCalculator.calculate - KB price {kb_price}만원 < min_kb_price {min_kb_price}만원, 취급 불가")
            logger.warning(f"BaseCalculator.calculate - KB price {kb_price}만원 < min_kb_price {min_kb_price}만원, 취급 불가")
            return {
                "bank_name": self.bank_name,
                "results": [],
                "conditions": self.config.get("conditions", []),
                "errors": [f"KB시세 {kb_price:,.0f}만원은 최소 {min_kb_price:,.0f}만원 이상이어야 취급 가능합니다"],
                "min_amount": self.config.get("min_amount", 3000)
            }
        
        # 하한가 적용 조건 확인
        lower_bound_config = self.config.get("lower_bound_price", {})
        if lower_bound_config.get("enabled", False):
            # 하한가 적용 조건 확인
            property_type = property_data.get("property_type", "")
            address = property_data.get("address", "")
            
            # 아파트/주상복합 확인
            is_apartment_or_complex = property_type and ("아파트" in property_type or "주상복합" in property_type)
            
            # 1,2층 확인 (주소에서 층수 추출)
            floor = None
            if address:
                import re
                floor_match = re.search(r'(\d+)층', address)
                if floor_match:
                    floor = int(floor_match.group(1))
            
            # 하한가 적용 조건: 아파트/주상복합이고 1층 또는 2층
            if is_apartment_or_complex and floor in [1, 2]:
                lower_bound_price = extract_lower_bound_price(kb_price_raw)
                if lower_bound_price is not None:
                    log_print(f"DEBUG: BaseCalculator.calculate - 하한가 적용: 일반가 {kb_price}만원 -> 하한가 {lower_bound_price}만원 (아파트/주상복합 {floor}층)")
                    logger.info(f"BaseCalculator.calculate - 하한가 적용: 일반가 {kb_price}만원 -> 하한가 {lower_bound_price}만원 (아파트/주상복합 {floor}층)")
                    kb_price = lower_bound_price
                else:
                    log_print(f"DEBUG: BaseCalculator.calculate - 하한가 적용 조건 충족하지만 하한가 추출 실패")
                    logger.warning("BaseCalculator.calculate - 하한가 적용 조건 충족하지만 하한가 추출 실패")
        
        # 지역 확인
        region = property_data.get("region", "")
        if not region:
            log_print(f"DEBUG: BaseCalculator.calculate - region is empty")
            logger.warning("BaseCalculator.calculate - region is empty")
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
                "errors": ["취급 불가지역"],
                "min_amount": self.config.get("min_amount", 3000)
            }
        
        # 대상 지역 확인 (광역 단위로 체크)
        target_regions = self.config.get("target_regions", [])
        if target_regions:
            is_target_region = False
            # 약자 매핑 (target_regions의 약자를 실제 지역명으로 변환)
            region_abbreviation_map = {
                "경북": "경상북도",
                "경남": "경상남도",
                "충북": "충청북도",
                "충남": "충청남도",
                "전북": "전라북도",
                "전남": "전라남도",
                "강원": "강원특별자치도"
            }
            
            for target in target_regions:
                # 약자 매핑 적용
                target_full = region_abbreviation_map.get(target, target)
                if target_full in region or target in region:  # "서울" in "서울특별시광진구" 또는 "경상북도" in "경상북도구미시"
                    is_target_region = True
                    break
            if not is_target_region:
                print(f"DEBUG: BaseCalculator.calculate - Region {region} is not in target regions: {target_regions}")
                # 취급 불가지역인 경우 특별한 결과 반환
                return {
                    "bank_name": self.bank_name,
                    "results": [],
                    "conditions": self.config.get("conditions", []),
                    "errors": ["취급 불가지역"],
                    "min_amount": self.config.get("min_amount", 3000)
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
                "errors": ["취급 불가지역"],
                "min_amount": self.config.get("min_amount", 3000)
            }
        
        # 6급지인 경우 취급 불가지역으로 처리
        if grade == 6:
            print(f"DEBUG: BaseCalculator.calculate - grade 6 for region: {region}, 취급 불가지역")
            return {
                "bank_name": self.bank_name,
                "results": [],
                "conditions": self.config.get("conditions", []),
                "errors": ["취급 불가지역"],
                "min_amount": self.config.get("min_amount", 3000)
            }
        
        # 면적 제한 확인 (BNK캐피탈 등 특정 금융사만)
        area_limit_config = self.config.get("area_limit", {})
        if area_limit_config.get("enabled", False):
            area = property_data.get("area")
            if area is not None:
                max_area = area_limit_config.get("max_area", 135)
                excluded_regions = area_limit_config.get("excluded_regions", [])
                
                # 제외 지역(서울 등)이 아니고 면적이 제한을 초과하면 불가
                is_excluded_region = False
                for excluded in excluded_regions:
                    if excluded in region:
                        is_excluded_region = True
                        break
                
                if not is_excluded_region and area > max_area:
                    print(f"DEBUG: BaseCalculator.calculate - area {area}㎡ > max_area {max_area}㎡ for region {region}, 취급 불가")
                    return {
                        "bank_name": self.bank_name,
                        "results": [],
                        "conditions": self.config.get("conditions", []),
                        "errors": [f"면적 {area}㎡는 서울지역 이외에서는 135㎡ 초과로 취급 불가"],
                        "min_amount": self.config.get("min_amount", 3000)
                    }
        
        # 기준 LTV 이하 지역 확인
        below_standard_ltv = self.get_below_standard_ltv(region)
        is_below_standard = below_standard_ltv is not None
        
        # OK저축은행 가계자금인 경우 확인 (최대 LTV 계산 전에 먼저 확인)
        is_ok_bank = self.bank_name == "OK저축은행" or "OK저축은행" in self.bank_name or "오케이저축은행" in self.bank_name
        is_household_for_ok = False
        if is_ok_bank:
            # product_type이 "household"이면 가계자금
            is_household_for_ok = product_type == "household"
        
        # 최대 LTV 확인 (1급지인 경우 A/B 그룹 구분)
        # OK저축은행인 경우 면적과 신용점수 등급을 고려
        # property_data에 product_type 정보 추가 (get_max_ltv_by_grade에서 사용)
        if is_household_for_ok:
            property_data_with_type = property_data.copy()
            property_data_with_type["_product_type"] = "household"
            max_ltv = self.get_max_ltv_by_grade(grade, region, property_data_with_type)
        else:
            property_data_with_type = property_data.copy()
            property_data_with_type["_product_type"] = "business"
            max_ltv = self.get_max_ltv_by_grade(grade, region, property_data_with_type)
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
        refinance_institutions = []  # 대환하는 금융사 이름 리스트 (가계자금용)
        other_mortgages = []  # 나머지 근저당권들
        
        # 가계자금인 경우: 물상담보 제외, business_product_names에 없는 것만 대환 가능
        if is_household_for_ok:
            business_product_names = self.config.get("business_product_names", [])
            requests = property_data.get("requests", "")
            household_refinance_requested = "가계자금" in requests or "가계" in requests
            
            for mortgage in mortgages:
                institution = mortgage.get("institution", "")
                # 물상담보 체크
                if "물상" in institution or "물상담보" in institution:
                    print(f"DEBUG: BaseCalculator.calculate - 가계자금: 물상담보는 대환 불가 - {institution}")
                    other_mortgages.append(mortgage)
                    continue
                
                # business_product_names에 있는지 확인
                is_business_product = False
                institution_clean = institution.replace(" ", "")
                for product_name in business_product_names:
                    product_name_clean = product_name.replace(" ", "")
                    if product_name_clean in institution_clean:
                        is_business_product = True
                        break
                
                # business_product_names에 없으면 가계자금으로 대환 가능
                if not is_business_product:
                    # 요청사항에 가계자금 대환 요청이 있고, 해당 근저당권이 대환 요청된 경우만 대환
                    if household_refinance_requested and mortgage.get("is_refinance", False):
                        mortgage_amount = float(mortgage.get("amount", 0) or 0)
                        refinance_principal += mortgage_amount
                        refinance_institutions.append(institution)
                        print(f"DEBUG: BaseCalculator.calculate - 가계자금 대환: priority={mortgage.get('priority')}, institution={institution}, principal={mortgage_amount}만원")
                    else:
                        # 대환 요청이 없으면 후순위로 처리
                        other_mortgages.append(mortgage)
                else:
                    # business_product_names에 있으면 사업자금이므로 후순위로 처리
                    other_mortgages.append(mortgage)
        else:
            # 일반 처리
            for mortgage in mortgages:
                if mortgage.get("is_refinance", False):
                    mortgage_amount = float(mortgage.get("amount", 0) or 0)
                    refinance_principal += mortgage_amount
                    print(f"DEBUG: BaseCalculator.calculate - 대환할 근저당권 발견: priority={mortgage.get('priority')}, institution={mortgage.get('institution')}, principal={mortgage_amount}만원")
                else:
                    other_mortgages.append(mortgage)
        
        # 나머지 근저당권의 채권최고액만 합산
        total_mortgage = self.calculate_total_mortgage(other_mortgages)
        
        # OK저축은행인 경우 원금 기준으로 차감하는지 확인
        is_ok_bank = self.bank_name == "OK저축은행" or "OK저축은행" in self.bank_name or "오케이저축은행" in self.bank_name
        use_principal_for_ok = self.config.get("use_principal_for_calculation", False)  # 원금 기준 계산 여부
        
        if is_ok_bank and use_principal_for_ok:
            # OK저축은행이고 원금 기준 계산이 설정된 경우: 원금 합계 사용
            total_mortgage_principal = sum(float(m.get("amount", 0) or 0) for m in other_mortgages)
            print(f"DEBUG: BaseCalculator.calculate - OK저축은행 원금 기준 계산: total_mortgage_principal={total_mortgage_principal}만원 (기존 채권최고액: {total_mortgage}만원)")
            total_mortgage = total_mortgage_principal
        
        print(f"DEBUG: BaseCalculator.calculate - mortgages: {mortgages}")  # 추가
        print(f"DEBUG: BaseCalculator.calculate - refinance_principal(대환 원금 합계): {refinance_principal}만원, total_mortgage(차감할 금액): {total_mortgage}")  # 추가
        
        # 대환 여부 판단
        is_refinance = refinance_principal > 0
        
        # 가계자금인 경우: 대환 요청된 금융사가 가계자금으로 대환 가능한 경우에만 산출
        if is_household_for_ok:
            # 대환 요청된 근저당권 중 가계자금으로 대환 가능한 것이 있는지 확인
            # (refinance_institutions에 추가된 것들이 가계자금으로 대환 가능한 근저당권)
            has_household_refinance = len(refinance_institutions) > 0
            
            # 가계자금으로 대환 가능한 근저당권이 없으면 가계자금 산출하지 않음 (None 반환하여 아무것도 표시하지 않음)
            if not has_household_refinance:
                print(f"DEBUG: BaseCalculator.calculate - 가계자금: 대환 요청된 금융사 중 가계자금으로 대환 가능한 것이 없어서 산출하지 않음")
                return None
            
            # 가계자금으로 대환 가능한 근저당권이 있으면 산출 진행
            if is_refinance:
                print(f"DEBUG: BaseCalculator.calculate - 가계자금: 대환 요청 있음, 대환으로 진행 (대환 금융사: {refinance_institutions})")
            else:
                print(f"DEBUG: BaseCalculator.calculate - 가계자금: 대환할 근저당권 없음, 후순위로 산출")
        
        # OK 저축은행 사업자/가계 상품 구분
        is_ok_bank = self.bank_name == "OK저축은행" or "OK저축은행" in self.bank_name or "오케이저축은행" in self.bank_name
        is_business_product = False
        is_household_product = False
        
        if is_ok_bank:
            # product_type 파라미터가 있으면 그것을 우선 사용
            if product_type == "household":
                is_household_product = True
                is_household_for_ok = True
            elif product_type == "business":
                is_business_product = True
                is_household_for_ok = False
            else:
                # bank_name이 사업자 상품명 리스트에 있는지 확인
                business_product_names = self.config.get("business_product_names", [])
                bank_name_clean = self.bank_name.replace(" ", "")
                
                # 사업자 상품명 확인 (현대캐피탈 가계/가계자금 제외)
                for product_name in business_product_names:
                    product_name_clean = product_name.replace(" ", "")
                    if product_name_clean in bank_name_clean:
                        # "가계" 또는 "가계자금"이 포함되어 있으면 가계 상품
                        if "가계" in bank_name_clean or "가계자금" in bank_name_clean:
                            is_household_product = True
                        else:
                            is_business_product = True
                        break
                
                # OK저축은행이지만 사업자 상품명 리스트에 없으면 가계 상품으로 간주
                if not is_business_product and not is_household_product:
                    is_household_product = True
            
            # 사업자 상품인 경우: business_product_names에 있는 기관만 대환 가능
            if is_business_product and is_refinance:
                # 대환할 근저당권이 business_product_names에 있는지 확인
                business_product_names = self.config.get("business_product_names", [])
                can_refinance = False
                refinance_institutions = []
                
                for mortgage in mortgages:
                    if mortgage.get("is_refinance", False):
                        institution = mortgage.get("institution", "")
                        institution_clean = institution.replace(" ", "")
                        for product_name in business_product_names:
                            product_name_clean = product_name.replace(" ", "")
                            if product_name_clean in institution_clean:
                                can_refinance = True
                                refinance_institutions.append(institution)
                                break
                
                if not can_refinance:
                    print(f"DEBUG: BaseCalculator.calculate - OK 저축은행 사업자 상품: 대환 요청된 기관이 사업자 상품이 아님")
                    return {
                        "bank_name": self.bank_name,
                        "results": [],
                        "conditions": self.config.get("conditions", []),
                        "errors": ["사업자 상품은 사업자금 기관만 대환 가능"],
                        "min_amount": self.config.get("min_amount", 3000)
                    }
        
        # 사업자/가계 상품 정보를 인스턴스 변수로 저장 (get_interest_rate에서 사용)
        self._is_business_product = is_business_product
        self._is_household_product = is_household_product
        self._is_subordinate = len(other_mortgages) > 0  # 후순위 여부
        self._current_property_data = property_data
        
        # 가계 상품: 빌라인 경우 선순위만 산출
        if is_household_product:
            property_type = property_data.get("property_type", "")
            if property_type and "빌라" in property_type:
                # 선순위만 산출 (기존 근저당권이 없어야 함)
                if len(other_mortgages) > 0:
                    print(f"DEBUG: BaseCalculator.calculate - OK 저축은행 가계 상품, 빌라인 경우 선순위만 산출 가능")
                    return {
                        "bank_name": self.bank_name,
                        "results": [],
                        "conditions": self.config.get("conditions", []),
                        "errors": ["빌라인 경우 선순위만 산출 가능"],
                        "min_amount": self.config.get("min_amount", 3000)
                    }
        
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
        
        # 가계 상품: 서울 수도권 한도 제한 (1억)
        if is_household_product:
            household_limit_regions = self.config.get("household_limit_regions", ["서울", "경기", "인천"])
            household_limit_amount = self.config.get("household_limit_amount", 10000)  # 1억
            
            is_limit_region = False
            for limit_region in household_limit_regions:
                if limit_region in region:
                    is_limit_region = True
                    break
            
            if is_limit_region:
                # 기존 한도 제한이 없거나 더 큰 경우에만 적용
                if max_amount_limit is None or max_amount_limit > household_limit_amount:
                    max_amount_limit = household_limit_amount
                    print(f"DEBUG: BaseCalculator.calculate - OK 저축은행 가계 상품, 서울 수도권 한도 제한: {max_amount_limit}만원")
        
        # 가계자금인 경우 LTV 70% 고정
        if is_household_for_ok:
            max_ltv = 70
            print(f"DEBUG: BaseCalculator.calculate - 가계자금: LTV 70% 고정")
        
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
                    "taxi_limit_applied": True,  # 택시 한도 제한 적용 플래그
                    "refinance_institutions": refinance_institutions if is_household_for_ok and is_refinance else None  # 가계자금 대환 시 대환하는 금융사 이름
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
                    "taxi_limit_applied": taxi_limit_applied,  # 택시 한도 제한 적용 플래그
                    "fixed_rate_comment": rate_info.get("fixed_rate_comment"),  # 고정금리 코멘트
                    "refinance_institutions": refinance_institutions if is_household_for_ok and is_refinance else None  # 가계자금 대환 시 대환하는 금융사 이름
                }
                
                results = [result]  # 하나의 결과만 반환
                print(f"DEBUG: BaseCalculator.calculate - created result with LTV {calculated_ltv:.2f}% and amount {final_amount}만원")  # 추가
        else:
            # 필요자금이 없고 택시 한도 제한도 없으면 기존대로 LTV별 한도 계산
            # 가계자금인 경우 LTV 70%만 계산
            if is_household_for_ok:
                ltv_steps = [70]
            else:
                # 사업자금인 경우 max_ltv_by_area_grade_credit에서 가능한 LTV만 사용
                if is_ok_bank and is_business_product:
                    # 사업자금은 max_ltv_by_area_grade_credit에서 가능한 LTV만 사용
                    # max_ltv는 이미 get_max_ltv_by_grade에서 계산됨
                    # ltv_steps에서 max_ltv 이하만 사용
                    all_ltv_steps = self.config.get("ltv_steps", [90, 85, 80, 75, 70, 65])
                    ltv_steps = [ltv for ltv in all_ltv_steps if ltv <= max_ltv]
                    print(f"DEBUG: BaseCalculator.calculate - 사업자금: max_ltv={max_ltv}, filtered ltv_steps={ltv_steps}")
                else:
                    ltv_steps = self.config.get("ltv_steps", [90, 85, 80, 75, 70, 65])
            
            print(f"DEBUG: BaseCalculator.calculate - max_ltv: {max_ltv}, ltv_steps: {ltv_steps}")  # 추가
            
            for ltv in ltv_steps:
                # 최대 LTV를 초과하면 스킵
                if ltv > max_ltv:
                    print(f"DEBUG: LTV {ltv} > max_ltv {max_ltv}, skipping")  # 추가
                    continue
                
                # 가용 한도 계산
                # OK저축은행인 경우 특별한 계산 방식 적용
                if is_ok_bank and not is_refinance:
                    # OK저축은행 후순위: 현재 LTV 한도에서 기존 근저당권이 차지하는 LTV 수준의 한도를 차감
                    # 기존 근저당권이 차지하는 LTV = total_mortgage / kb_price * 100
                    existing_ltv = (total_mortgage / kb_price) * 100 if kb_price > 0 else 0
                    # 기존 근저당권 LTV 수준의 한도 계산
                    existing_ltv_limit = kb_price * (existing_ltv / 100)
                    # 현재 LTV 한도에서 기존 근저당권 LTV 수준 한도를 차감
                    max_amount_principal = kb_price * (ltv / 100)
                    available_principal = max_amount_principal - existing_ltv_limit
                    amount_info = {
                        "total_amount": max(0, available_principal),
                        "available_amount": max(0, available_principal)
                    }
                    print(f"DEBUG: BaseCalculator.calculate - OK저축은행 특별 계산: ltv={ltv}%, existing_ltv={existing_ltv:.2f}%, max_amount={max_amount_principal}, existing_limit={existing_ltv_limit}, available={available_principal}")
                else:
                    # 일반 계산 방식
                    amount_info = self.calculate_available_amount(
                        kb_price, ltv, total_mortgage, is_refinance, refinance_principal
                    )
                
                print(f"DEBUG: LTV {ltv} - amount_info: {amount_info}")  # 추가
                
                # 가용 한도가 0 이하면 스킵 (대환인 경우는 마이너스여도 산출)
                if not is_refinance and amount_info["available_amount"] <= 0:
                    print(f"DEBUG: LTV {ltv} - available_amount <= 0, skipping")  # 추가
                    continue
                
                # 금리 조회 (82% LTV의 경우 region_grade에 따라 다른 금리 적용)
                rate_info = self.get_interest_rate(credit_score, credit_grade, ltv, grade)
                
                # 가계 상품 한도 제한 적용
                final_amount = amount_info["available_amount"]
                if max_amount_limit is not None and final_amount > max_amount_limit:
                    final_amount = max_amount_limit
                    print(f"DEBUG: BaseCalculator.calculate - 가계 상품 한도 제한 적용: {amount_info['available_amount']}만원 -> {final_amount}만원")
                
                # 100만 단위로 절삭
                final_amount = self.round_down_to_hundred_thousand(final_amount)
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
                    "below_standard_ltv": is_below_standard,  # 기준 LTV 이하 지역 여부
                    "fixed_rate_comment": rate_info.get("fixed_rate_comment"),  # 고정금리 코멘트
                    "refinance_institutions": refinance_institutions if is_household_for_ok and is_refinance else None  # 가계자금 대환 시 대환하는 금융사 이름
                }
                
                results.append(result)
        
        # 결과가 없으면 에러 메시지와 함께 반환 (가용 한도 부족 등)
        if not results:
            print(f"DEBUG: BaseCalculator.calculate - no results found for {self.bank_name}")
            # 최대 LTV로 계산했을 때 가용 한도 확인
            max_ltv_amount = kb_price * (max_ltv / 100)
            
            # 대환인 경우: 대환할 근저당권의 원금 + 나머지 근저당권의 채권최고액을 합산하여 체크
            # 대환이 아닌 경우: 기존 근저당권의 채권최고액만 체크
            if is_refinance:
                # 대환할 근저당권의 원금을 채권최고액으로 추정 (원금 × 1.2)
                refinance_max_amount = refinance_principal * 1.2
                # 대환할 근저당권의 채권최고액 + 나머지 근저당권의 채권최고액
                total_mortgage_for_check = refinance_max_amount + total_mortgage
                print(f"DEBUG: BaseCalculator.calculate - 대환인 경우: refinance_principal={refinance_principal}만원, refinance_max_amount={refinance_max_amount}만원, total_mortgage={total_mortgage}만원, total_mortgage_for_check={total_mortgage_for_check}만원")
                
                if total_mortgage_for_check > max_ltv_amount:
                    shortage = total_mortgage_for_check - max_ltv_amount
                    print(f"DEBUG: BaseCalculator.calculate - 대환 시 기존 근저당권이 최대 LTV 한도를 초과: {shortage:.0f}만원 초과")
                    return {
                        "bank_name": self.bank_name,
                        "results": [],
                        "conditions": self.config.get("conditions", []),
                        "errors": [f"기존 근저당권 채권최고액({total_mortgage_for_check:,.0f}만원)이 최대 한도({max_ltv_amount:,.0f}만원, LTV {max_ltv}%)를 초과하여 추가 대출 불가능"],
                        "min_amount": self.config.get("min_amount", 3000)
                    }
            else:
                # 대환이 아닌 경우: 기존 로직 유지
                if total_mortgage > max_ltv_amount:
                    shortage = total_mortgage - max_ltv_amount
                    print(f"DEBUG: BaseCalculator.calculate - 기존 근저당권이 최대 LTV 한도를 초과: {shortage:.0f}만원 초과")
                    return {
                        "bank_name": self.bank_name,
                        "results": [],
                        "conditions": self.config.get("conditions", []),
                        "errors": [f"기존 근저당권 채권최고액({total_mortgage:,.0f}만원)이 최대 한도({max_ltv_amount:,.0f}만원, LTV {max_ltv}%)를 초과하여 추가 대출 불가능"],
                        "min_amount": self.config.get("min_amount", 3000)
                    }
            
            print(f"DEBUG: BaseCalculator.calculate - no results found for {self.bank_name}, returning None")
            return None
        
        print(f"DEBUG: BaseCalculator.calculate - {self.bank_name} found {len(results)} results")  # 추가
        return {
            "bank_name": self.bank_name,
            "results": results,
            "conditions": self.config.get("conditions", []),
            "errors": [],
            "min_amount": self.config.get("min_amount", 3000)  # 기본값 3000만원
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
    
    def get_max_ltv_by_grade(self, grade: Union[int, str], region: str = None, property_data: Dict[str, Any] = None) -> Optional[float]:
        """
        급지별 최대 LTV 조회
        1급지인 경우 A/B 그룹을 구분하여 반환
        문자 급지(A, B, C, D)도 지원
        OK저축은행인 경우 면적과 신용점수 등급을 고려
        
        Args:
            grade: 급지 번호 (1, 2, 3, 4) 또는 문자 급지 (A, B, C, D)
            region: 지역명 (1급지 A/B 구분용)
            property_data: 담보물건 정보 (면적, 신용점수 등)
        
        Returns:
            최대 LTV (float) 또는 None
        """
        # OK저축은행인 경우 면적과 신용점수 등급을 고려한 LTV 계산 (사업자금만)
        is_ok_bank = self.bank_name == "OK저축은행" or "OK저축은행" in self.bank_name or "오케이저축은행" in self.bank_name
        # product_type이 "household"이면 가계자금이므로 이 로직을 사용하지 않음
        is_household_for_ok = False
        if is_ok_bank and property_data is not None:
            # product_type 파라미터 확인 (calculate 메서드에서 전달)
            # 가계자금인 경우 이 로직을 사용하지 않음
            is_household_for_ok = property_data.get("_product_type") == "household"
        
        if is_ok_bank and property_data is not None and not is_household_for_ok:
            area = property_data.get("area")
            credit_score = property_data.get("credit_score")
            print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 체크: area={area}, credit_score={credit_score}")
            
            if area is not None:
                # 신용점수가 있는 경우
                if credit_score is not None:
                    # 신용점수 범위 문자열을 등급 번호로 변환
                    credit_grade_number = self._get_ok_credit_grade_number(credit_score)
                    print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 credit_grade_number: {credit_grade_number}")
                    if credit_grade_number is not None:
                        # 면적별 급지별 LTV 조회
                        max_ltv = self._get_ok_max_ltv_by_area_grade_credit(area, grade, credit_grade_number)
                        print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 _get_ok_max_ltv_by_area_grade_credit 결과: {max_ltv}")
                        if max_ltv is not None:
                            print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 면적별 LTV: area={area}㎡, grade={grade}, credit_grade={credit_grade_number}등급 -> LTV {max_ltv}%")
                            return max_ltv
                else:
                    # 신용점수가 없는 경우: 해당 급지의 최대 LTV 사용 (면적과 급지만 고려)
                    print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 신용점수 없음, 면적과 급지만으로 최대 LTV 계산")
                    max_ltv = self._get_ok_max_ltv_by_area_grade(area, grade)
                    if max_ltv is not None:
                        print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 면적별 LTV (신용점수 없음): area={area}㎡, grade={grade} -> LTV {max_ltv}%")
                        return max_ltv
        
        max_ltv_by_grade = self.config.get("max_ltv_by_grade", {})
        print(f"DEBUG: get_max_ltv_by_grade - grade: {grade} (type: {type(grade)}), region: {region}, max_ltv_by_grade keys: {list(max_ltv_by_grade.keys())}")  # 추가
        
        # 문자 급지인 경우 (OK 저축은행 등)
        if isinstance(grade, str):
            result = max_ltv_by_grade.get(grade)
            print(f"DEBUG: get_max_ltv_by_grade - 문자 급지: {grade} -> LTV {result}%")
            return result
        
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
    
    def _get_ok_credit_grade_number(self, credit_score: int) -> Optional[int]:
        """
        OK저축은행: 신용점수를 등급 번호(1~8)로 변환
        
        Args:
            credit_score: 신용점수
        
        Returns:
            등급 번호 (1~8) 또는 None
        """
        score_range_to_grade = self.config.get("credit_score_range_to_grade_number", {})
        if not score_range_to_grade:
            return None
        
        for range_str, grade_number in score_range_to_grade.items():
            parts = range_str.split("-")
            if len(parts) == 2:
                try:
                    score1 = int(parts[0])
                    score2 = int(parts[1])
                    # 범위가 내림차순인 경우 (예: 1000-915)와 오름차순인 경우 모두 처리
                    min_score = min(score1, score2)
                    max_score = max(score1, score2)
                    if min_score <= credit_score <= max_score:
                        print(f"DEBUG: _get_ok_credit_grade_number - credit_score: {credit_score}, range: {range_str} -> grade: {grade_number}")
                        return grade_number
                except ValueError:
                    continue
        
        print(f"DEBUG: _get_ok_credit_grade_number - credit_score: {credit_score}, no match found")
        return None
    
    def _get_ok_max_ltv_by_area_grade_credit(self, area: float, region_grade: Union[int, str], credit_grade_number: int) -> Optional[float]:
        """
        OK저축은행: 면적, 급지, 신용등급을 기반으로 최대 LTV 조회
        
        Args:
            area: 면적 (㎡)
            region_grade: 급지 번호 (1, 2, 3, 4)
            credit_grade_number: 신용등급 번호 (1~8)
        
        Returns:
            최대 LTV (float) 또는 None
        """
        max_ltv_config = self.config.get("max_ltv_by_area_grade_credit", {})
        if not max_ltv_config:
            return None
        
        # 면적 구분 (110㎡ 이하/초과)
        area_key = "area_110_below" if area <= 110 else "area_110_over"
        area_config = max_ltv_config.get(area_key, {})
        if not area_config:
            return None
        
        # 급지별 설정 조회
        grade_key = str(region_grade)
        grade_config = area_config.get(grade_key, {})
        if not grade_config:
            return None
        
        # 4급지는 등급 상관없이 모두 동일한 LTV
        if grade_key == "4" and "all" in grade_config:
            result = grade_config["all"]
            print(f"DEBUG: _get_ok_max_ltv_by_area_grade_credit - area: {area}㎡, grade: {grade_key}, credit_grade: {credit_grade_number}등급 -> LTV {result}% (4급지 전체)")
            return result
        
        # 등급 범위별 LTV 조회
        for grade_range, ltv in grade_config.items():
            if grade_range == "all":
                continue
            
            # "1-3", "4-6", "7-8" 형식 파싱
            parts = grade_range.split("-")
            if len(parts) == 2:
                try:
                    min_grade = int(parts[0])
                    max_grade = int(parts[1])
                    if min_grade <= credit_grade_number <= max_grade:
                        print(f"DEBUG: _get_ok_max_ltv_by_area_grade_credit - area: {area}㎡, grade: {grade_key}, credit_grade: {credit_grade_number}등급, range: {grade_range} -> LTV {ltv}%")
                        return ltv
                except ValueError:
                    continue
        
        print(f"DEBUG: _get_ok_max_ltv_by_area_grade_credit - area: {area}㎡, grade: {grade_key}, credit_grade: {credit_grade_number}등급, no match found")
        return None
    
    def _get_ok_max_ltv_by_area_grade(self, area: float, region_grade: Union[int, str]) -> Optional[float]:
        """
        OK저축은행: 면적과 급지만으로 최대 LTV 조회 (신용점수 없을 때 사용)
        해당 급지의 신용등급 범위 중 가장 높은 LTV를 반환
        
        Args:
            area: 면적 (㎡)
            region_grade: 급지 번호 (1, 2, 3, 4)
        
        Returns:
            최대 LTV (float) 또는 None
        """
        max_ltv_config = self.config.get("max_ltv_by_area_grade_credit", {})
        if not max_ltv_config:
            return None
        
        # 면적 구분 (110㎡ 이하/초과)
        area_key = "area_110_below" if area <= 110 else "area_110_over"
        area_config = max_ltv_config.get(area_key, {})
        if not area_config:
            return None
        
        # 급지별 설정 조회
        grade_key = str(region_grade)
        grade_config = area_config.get(grade_key, {})
        if not grade_config:
            return None
        
        # 4급지는 등급 상관없이 모두 동일한 LTV
        if grade_key == "4" and "all" in grade_config:
            result = grade_config["all"]
            print(f"DEBUG: _get_ok_max_ltv_by_area_grade - area: {area}㎡, grade: {grade_key} -> LTV {result}% (4급지 전체)")
            return result
        
        # 신용등급 범위별 LTV 중 최대값 찾기
        max_ltv = None
        for grade_range, ltv in grade_config.items():
            if grade_range == "all":
                continue
            if max_ltv is None or ltv > max_ltv:
                max_ltv = ltv
        
        if max_ltv is not None:
            print(f"DEBUG: _get_ok_max_ltv_by_area_grade - area: {area}㎡, grade: {grade_key} -> 최대 LTV {max_ltv}% (신용점수 없음)")
        else:
            print(f"DEBUG: _get_ok_max_ltv_by_area_grade - area: {area}㎡, grade: {grade_key}, no match found")
        
        return max_ltv
    
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
            # 마이너스도 허용 (대환 한도 부족해도 산출)
            available_principal = max_amount_principal - refinance_principal - total_mortgage
            
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
        region_grade: Optional[Union[int, str]] = None
    ) -> Dict[str, Any]:
        """
        신용등급별 금리 조회
        OK 저축은행의 경우 신용점수 범위별 스프레드 + CoFix + 급지별 가산금리 방식 지원
        
        Args:
            credit_score: 신용점수 (없으면 None)
            credit_grade: 신용등급 (1-7) 또는 신용점수 범위 문자열 (OK 저축은행)
            ltv: LTV 비율
            region_grade: 지역 급지 (1, 2, 3, 4 또는 A, B, C, D)
        
        Returns:
            {
                "interest_rate": 금리 (신용점수 있을 때),
                "interest_rate_range": (최저, 최고) 튜플 (신용점수 없을 때),
                "credit_grade": 신용등급
            }
        """
        # OK 저축은행인지 확인 (cofix_rate가 있으면 OK 저축은행)
        cofix_rate = self.config.get("cofix_rate")
        if cofix_rate is not None:
            # 사업자/가계 상품 구분 (property_data에서 확인)
            is_business_product = getattr(self, '_is_business_product', False)
            is_household_product = getattr(self, '_is_household_product', False)
            is_subordinate = getattr(self, '_is_subordinate', False)
            property_data = getattr(self, '_current_property_data', None)
            return self._get_ok_interest_rate(
                credit_score, ltv, region_grade, cofix_rate,
                is_business_product, is_household_product, is_subordinate, property_data
            )
        
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
    
    def _get_ok_interest_rate(
        self,
        credit_score: Optional[int],
        ltv: int,
        region_grade: Optional[Union[int, str]],
        cofix_rate: float,
        is_business_product: bool = False,
        is_household_product: bool = False,
        is_subordinate: bool = False,
        property_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        OK 저축은행 금리 계산
        사업자 상품: 스프레드 금리 + CoFix + 급지별 가산금리
        가계 상품: 스프레드 금리 + CoFix + 조정금리(거치식/원리금분할상환, 6개월 변동금리, 후순위)
        
        Args:
            credit_score: 신용점수
            ltv: LTV 비율
            region_grade: 지역 급지 (1, 2, 3, 4) - 숫자로 통일됨
            cofix_rate: CoFix 금리
            is_business_product: 사업자 상품 여부
            is_household_product: 가계 상품 여부
            is_subordinate: 후순위 여부
            property_data: 담보물건 정보 (가계 상품 조정금리 확인용)
        
        Returns:
            {
                "interest_rate": 최종 금리,
                "interest_rate_range": (최저, 최고) 튜플 (신용점수 없을 때),
                "credit_grade": 신용점수 범위 문자열,
                "fixed_rate_comment": 고정금리 코멘트 (사업자 상품)
            }
        """
        # 사업자/가계 상품에 따라 다른 금리 테이블 사용
        if is_business_product:
            ltv_rates = self.config.get("business_interest_rates_by_ltv", {})
            grade_additional_rates = self.config.get("business_grade_additional_rates", {})
        elif is_household_product:
            ltv_rates = self.config.get("household_interest_rates_by_ltv", {})
            grade_additional_rates = {}  # 가계 상품은 급지별 가산금리 없음
        else:
            # 기본값 (기존 호환성)
            ltv_rates = self.config.get("interest_rates_by_ltv", {})
            grade_additional_rates = self.config.get("grade_additional_rates", {})
        
        credit_score_to_grade = self.config.get("credit_score_to_grade", {})
        
        ltv_key = str(ltv)
        
        # 사업자 상품: 70% 이하일 경우 70% 금리 사용
        if is_business_product and ltv_key not in ltv_rates and ltv <= 70:
            ltv_key = "70"
            print(f"DEBUG: _get_ok_interest_rate - 사업자 상품, LTV {ltv}%는 70% 금리 적용")
        
        if ltv_key not in ltv_rates:
            return {
                "interest_rate": None,
                "interest_rate_range": None,
                "credit_grade": None,
                "fixed_rate_comment": None
            }
        
        score_rates = ltv_rates[ltv_key]
        
        # 급지별 가산금리 (사업자 상품만)
        additional_rate = 0.0
        if is_business_product:
            if isinstance(region_grade, int):
                grade_key = str(region_grade)
                additional_rate = grade_additional_rates.get(grade_key, 0.0)
            elif isinstance(region_grade, str):
                additional_rate = grade_additional_rates.get(region_grade, 0.0)
        
        # 가계 상품 조정금리
        household_adjustment = 0.0
        if is_household_product and property_data:
            household_adjustment_rates = self.config.get("household_adjustment_rates", {})
            special_notes = property_data.get("special_notes", "") or ""
            requests = property_data.get("requests", "") or ""
            combined_text = special_notes + " " + requests
            
            # 거치식 원금/원리금분할상환 선택시 +0.2%
            if "거치식" in combined_text or "원리금분할상환" in combined_text:
                household_adjustment += household_adjustment_rates.get("installment_repayment", 0.2)
            
            # 6개월 변동금리 적용시 +0.2%
            if "6개월" in combined_text and "변동금리" in combined_text:
                household_adjustment += household_adjustment_rates.get("6month_variable_rate", 0.2)
            
            # 후순위 취급시 +0.4% (선순위가 아닌 후순위로 들어갈 경우 무조건)
            if is_subordinate:
                household_adjustment += household_adjustment_rates.get("subordinate_loan", 0.4)
        
        # 신용점수가 있으면 해당 범위의 스프레드 금리 사용
        if credit_score is not None:
            # 신용점수 범위 찾기
            score_range = None
            for range_str in credit_score_to_grade.keys():
                parts = range_str.split("-")
                if len(parts) == 2:
                    try:
                        min_score = int(parts[0])
                        max_score = int(parts[1])
                        if min_score <= credit_score <= max_score:
                            score_range = range_str
                            break
                    except ValueError:
                        continue
            
            if score_range and score_range in score_rates:
                spread_rate = score_rates[score_range]
                final_rate = spread_rate + cofix_rate + additional_rate + household_adjustment
                print(f"DEBUG: _get_ok_interest_rate - credit_score: {credit_score}, score_range: {score_range}, spread: {spread_rate}, cofix: {cofix_rate}, additional: {additional_rate}, household_adjustment: {household_adjustment}, final: {final_rate}")
                
                # 사업자 상품 고정금리 코멘트
                fixed_rate_comment = None
                if is_business_product:
                    fixed_rate_comment = "고정금리 선택시 -0.3%"
                
                return {
                    "interest_rate": round(final_rate, 2),
                    "interest_rate_range": None,
                    "credit_grade": score_range,
                    "fixed_rate_comment": fixed_rate_comment
                }
        
        # 신용점수가 없으면 최저~최고 금리 범위 반환
        all_rates = [v + cofix_rate + additional_rate + household_adjustment for v in score_rates.values() if isinstance(v, (int, float))]
        if all_rates:
            min_rate = min(all_rates)
            max_rate = max(all_rates)
            print(f"DEBUG: _get_ok_interest_rate - no credit_score, returning range: {min_rate:.2f}~{max_rate:.2f}")
            
            # 사업자 상품 고정금리 코멘트
            fixed_rate_comment = None
            if is_business_product:
                fixed_rate_comment = "고정금리 선택시 -0.3%"
            
            return {
                "interest_rate": None,
                "interest_rate_range": (round(min_rate, 2), round(max_rate, 2)),
                "credit_grade": None,
                "fixed_rate_comment": fixed_rate_comment
            }
        
        return {
            "interest_rate": None,
            "interest_rate_range": None,
            "credit_grade": None,
            "fixed_rate_comment": None
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
                # OK저축은행인 경우 가계자금과 사업자금을 각각 계산
                is_ok_bank = calculator.bank_name == "OK저축은행" or "OK저축은행" in calculator.bank_name or "오케이저축은행" in calculator.bank_name
                
                if is_ok_bank:
                    # 가계자금 계산
                    household_result = calculator.calculate(property_data, product_type="household")
                    if household_result is not None:
                        household_result["bank_name"] = "OK저축은행 가계자금"
                        results.append(household_result)
                    
                    # 사업자금 계산
                    business_result = calculator.calculate(property_data, product_type="business")
                    if business_result is not None:
                        business_result["bank_name"] = "OK저축은행 사업자금"
                        results.append(business_result)
                else:
                    # 일반 금융사는 기존대로 계산
                    result = calculator.calculate(property_data)
                    if result is not None:
                        # 취급 불가지역인 경우도 포함 (errors에 "취급 불가지역"이 있으면)
                        results.append(result)
            except Exception as e:
                print(f"계산기 {calculator.bank_name} 에러: {e}")
                continue
        
        return results

