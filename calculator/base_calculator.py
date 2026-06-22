# -*- coding: utf-8 -*-
"""
금융사 계산기 클래스
개별 금융사 계산 및 모든 금융사 계산 관리
"""

import json
import os
import re
import sys
import logging
from datetime import date
from typing import Dict, List, Optional, Any, Union, Set
from utils.validators import (
    validate_kb_price, extract_lower_bound_price, extract_kb_ai_price_from_special_notes,
    extract_bank_appraisal_price_from_special_notes, extract_realestatetech_price_from_special_notes,
    extract_korea_realestate_price_from_special_notes, extract_housematch_price_from_special_notes
)
from utils.mortgage_calculator import classify_financial_institution

# Vercel 로그 출력을 위한 강력한 헬퍼 함수
def log_print(*args, **kwargs):
    """Vercel에서 확실하게 로그가 보이도록 하는 헬퍼"""
    import time
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    message = ' '.join(str(arg) for arg in args)
    log_line = f"[{timestamp}] {message}\n"
    
    # stderr에 직접 쓰기 (가장 확실한 방법)
    try:
        sys.stderr.write(log_line)
        sys.stderr.flush()
    except:
        pass
    
    # stdout에도 쓰기
    try:
        sys.stdout.write(log_line)
        sys.stdout.flush()
    except:
        pass

# 로깅 설정 (Vercel에서는 INFO만 출력해 로그 256줄 제한 내 유지)
_is_vercel = os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV") is not None
logging.basicConfig(
    level=logging.INFO if _is_vercel else logging.DEBUG,
    format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)
logger = logging.getLogger(__name__)
if _is_vercel:
    logger.setLevel(logging.INFO)

# 원본 print 함수를 래핑하여 모든 print가 stderr로도 출력되도록
_original_print = print

def _wrapped_print(*args, **kwargs):
    """print 함수 래퍼 (stderr로도 출력)"""
    # flush가 명시되지 않았으면 True로 설정
    if 'flush' not in kwargs:
        kwargs['flush'] = True
    # stderr로도 출력 (Vercel 로그 캡처를 위해)
    try:
        _original_print(*args, file=sys.stderr, **kwargs)
    except:
        pass
    # 원래 의도한 출력 스트림으로도 출력
    _original_print(*args, **kwargs)

# print 함수를 래핑된 버전으로 교체
import builtins
builtins.print = _wrapped_print

# 대환 가능 금융기관 공통 목록 (저축은행+캐피탈) 캐시. 금융사별 config에 business_product_names 없을 때 사용.
_REFINANCE_MASTER_NAMES_CACHE: Optional[List[str]] = None


def _load_refinanceable_master_names() -> List[str]:
    """
    저축은행·리스·할부(캐피탈) 등 마스터 명단 로드 (한 번만).
    우선순위: data/banks/refinanceable_institutions.json → data/refinanceable_institutions.json(legacy)
    """
    global _REFINANCE_MASTER_NAMES_CACHE
    if _REFINANCE_MASTER_NAMES_CACHE is not None:
        return _REFINANCE_MASTER_NAMES_CACHE
    base = os.path.join(os.path.dirname(__file__), "..", "data")
    master_path = os.path.join(base, "banks", "refinanceable_institutions.json")
    try:
        with open(master_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        names = data.get("names")
        if names:
            _REFINANCE_MASTER_NAMES_CACHE = list(names)
        else:
            s = data.get("savings_banks") or []
            c = data.get("capital_lease_installment") or []
            _REFINANCE_MASTER_NAMES_CACHE = sorted(set(s + c))
        return _REFINANCE_MASTER_NAMES_CACHE
    except Exception as e:
        logger.warning("refinanceable_institutions.json(banks) 로드 실패: %s", e)
    legacy = os.path.join(base, "refinanceable_institutions.json")
    try:
        with open(legacy, "r", encoding="utf-8") as f:
            data = json.load(f)
        _REFINANCE_MASTER_NAMES_CACHE = data.get("names") or []
    except Exception as e:
        logger.warning("refinanceable_institutions.json 로드 실패: %s", e)
        _REFINANCE_MASTER_NAMES_CACHE = []
    return _REFINANCE_MASTER_NAMES_CACHE


def _parse_grade_range(credit_grade: str) -> Set[int]:
    """credit_grade 문자열(예: '1~2', '1~5', '5')을 등급 번호 집합으로 변환"""
    if not credit_grade:
        return set()
    s = str(credit_grade).strip()
    if "~" in s:
        parts = s.split("~", 1)
        try:
            start, end = int(parts[0]), int(parts[1])
            return set(range(start, end + 1))
        except (ValueError, IndexError):
            return set()
    try:
        return {int(s)}
    except ValueError:
        return set()


def _grades_fully_covered(credit_grade: str, grades_with_limit: Set[int]) -> bool:
    """해당 등급 구간의 모든 등급이 한도가 나온 등급에 포함되는지"""
    grades_in_range = _parse_grade_range(credit_grade)
    return bool(grades_in_range) and grades_in_range <= grades_with_limit


def get_property_type_key(property_type: str, special_notes: str = "") -> Optional[str]:
    """
    한글 물건유형·특이사항 → config 키(apartment, villa, …).
    property_type_conditions / household_property_types 등과 동일한 키 체계.
    """
    if not property_type:
        return None
    notes = special_notes or ""
    has_no_land_registry = "대지권" in notes and ("미등기" in notes or "미 등기" in notes)
    if "아파트" in property_type:
        return "apartment_no_land_registry" if has_no_land_registry else "apartment"
    if "주상복합" in property_type:
        return "residential_commercial"
    if "빌라" in property_type:
        return "villa"
    if "오피스텔" in property_type:
        return "officetel"
    if "단독주택" in property_type:
        return "detached_house"
    if "공동주택" in property_type:
        return "multi_family_house"
    return None


def has_tenant_in_property(property_data: Dict[str, Any]) -> bool:
    """
    거주 또는 특이사항에 세입자 관련 키워드가 있으면 True.
    키워드: 전세입자, 월세입자, 세입자, 전세세입자, 월세세입자
    """
    keywords = ("전세입자", "월세입자", "세입자", "전세세입자", "월세세입자")
    residence = (property_data.get("residence") or "") or ""
    notes = (property_data.get("special_notes") or "") or ""
    combined = f"{residence} {notes}"
    return any(kw in combined for kw in keywords)


def infer_fractional_ownership(property_data: Dict[str, Any]) -> Optional[bool]:
    """
    지분/공유지분 여부 추정.
    True: 지분·공동소유 등으로 취급 제한 대상으로 볼 수 있음.
    False: 단독소유 등 명확히 전체 지분.
    None: 정보 부족 (해당 config로 판단 보류)
    """
    explicit = property_data.get("is_fractional_share")
    if explicit is True:
        return True
    if explicit is False:
        return False
    ownership = (property_data.get("ownership") or "").strip()
    notes = (property_data.get("special_notes") or "") or ""
    if not ownership and not notes:
        return None
    o = ownership.replace(" ", "")
    n = notes.replace(" ", "")
    if o and ("단독소유" in o or o == "단독") and "분의" not in o:
        return False
    if "분의" in o or "분의" in n:
        return True
    if "공동소유" in o or "공동소유" in notes:
        return True
    if "지분" in o and "단독" not in o:
        return True
    return None


def fractional_share_condition_requested(property_data: Dict[str, Any]) -> bool:
    """
    요청사항에 「지분조건」이 있으면 True (공백·전각공백 무시).
    한도 산출 시 최대 LTV 50%로 제한·최소진행 1000만원 하한에 사용.
    """
    requests = (property_data.get("requests") or "").strip()
    normalized = requests.replace(" ", "").replace("\u3000", "")
    return "지분조건" in normalized


def has_bucuk_jageum_request(property_data: Dict[str, Any]) -> bool:
    """
    요청사항 또는 특이사항에 '부족자금'이 있으면 True.
    가용한도가 0 이하일 때도 한도를 산출(마이너스 표시)하는 데 사용.
    """
    req = str(property_data.get("requests") or "")
    notes = str(property_data.get("special_notes") or "")
    return "부족자금" in req or "부족자금" in notes


def extract_reconstruction_stage(
    property_data: Dict[str, Any],
    keyword: str = "재건축",
) -> Optional[int]:
    """
    특이사항/요청사항에서 재건축 단계 숫자 추출.
    예: "재건축 : 4단계추진위원회승인" -> 4
    여러 단계가 있으면 가장 높은 단계 반환.
    """
    if not property_data:
        return None

    texts = [
        str(property_data.get("special_notes") or ""),
        str(property_data.get("requests") or ""),
    ]
    stages: List[int] = []

    # 1) 라인 단위: 재건축 키워드가 있는 줄에서 N단계 추출
    for text in texts:
        for line in text.splitlines():
            if keyword not in line:
                continue
            for m in re.finditer(r"(\d+)\s*단계", line):
                try:
                    stages.append(int(m.group(1)))
                except (TypeError, ValueError):
                    continue

    # 2) 줄바꿈으로 키워드/단계가 분리된 경우까지 보완
    for text in texts:
        if keyword not in text:
            continue
        for m in re.finditer(rf"{re.escape(keyword)}[\s\S]*?(\d+)\s*단계", text):
            try:
                stages.append(int(m.group(1)))
            except (TypeError, ValueError):
                continue

    if not stages:
        return None
    return max(stages)


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
        "경기도수원시장안구", "경기도수원시권선구", "경기도수원시팔달구",
        "경기도수원시영통구이의동", "경기도수원시영통구원천동", "경기도수원시영통구하동",
        "경기도수원시영통구",
        "경기도성남시수정구창곡동", "경기도성남시수정구", "경기도성남시중원구",
        "경기도안양시만안구", "경기도안양시동안구",
        "경기도부천시소사구", "경기도부천시오정구", "경기도부천시원미구", "경기도고양시덕양구",
        "경기도고양시일산동구", "경기도고양시일산서구", "인천광역시연수구", "인천광역시부평구",
        "경기도의정부시", "경기도안산시상록구", "경기도안산시단원구", "경기도구리시",
        "경기도남양주시별내동", "경기도남양주시다산동", "경기도남양주시",
        "경기도군포시", "경기도의왕시", "경기도용인시처인구",
        "경기도용인시기흥구", "경기도용인시수지구", "경기도김포시",
        "경기도화성시동탄구", "경기도화성시만세구", "경기도화성시효행구", "경기도화성시병점구", "경기도화성시",
        "경기도평택시", "경기도동두천시", "경기도오산시", "경기도시흥시",
        "경기도파주시", "경기도안성시", "경기도광주시", "경기도양주시",
        "경기도이천시", "경기도포천시", "경기도여주시", "경기도연천군",
        "경기도가평군", "경기도양평군",
        "인천광역시중구", "인천광역시동구", "인천광역시남동구", "인천광역시계양구",
        "인천광역시서구청라동", "인천광역시서구가정동", "인천광역시서구신현동",
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

    def _refinance_self_alias_strings(self) -> List[str]:
        """이 계산기가 나타내는 금융사(자기) — 마스터 명단에서 제외할 때 사용."""
        raw = self.config.get("refinance_self_aliases")
        if raw:
            return list(raw)
        bn = (self.config.get("bank_name") or "").strip()
        for suf in ("-사업자", "-리테일", "-가계"):
            if bn.endswith(suf):
                bn = bn[: -len(suf)].strip()
        out: List[str] = [bn] if bn else []
        for x in self.config.get("self_refinance_excluded", []) or []:
            if x and x not in out:
                out.append(x)
        return out

    def _exclude_self_from_refinance_names(self, names: List[str]) -> List[str]:
        """마스터 명단에서 자기 금융사(별칭)에 해당하는 항목 제거."""
        aliases = self._refinance_self_alias_strings()
        if not aliases:
            return names
        alias_clean = [a.replace(" ", "") for a in aliases if a]
        result: List[str] = []
        for n in names:
            nc = n.replace(" ", "")
            drop = False
            for ac in alias_clean:
                if len(ac) < 3:
                    continue
                if ac in nc:
                    drop = True
                    break
            if not drop:
                result.append(n)
        return result

    def _get_business_product_names(self) -> List[str]:
        """대환 가능 금융기관 목록. config에 business_product_names가 있으면 사용, 없으면 마스터 명단(자기 제외)."""
        from_config = self.config.get("business_product_names")
        if from_config is not None and len(from_config) > 0:
            return from_config
        master = _load_refinanceable_master_names()
        return self._exclude_self_from_refinance_names(master)
    
    def round_down_to_hundred_thousand(self, amount: float) -> float:
        """
        설정된 단위(만원)로 절삭.
        기본값은 100(=100만원), 금융사별 amount_round_down_unit으로 오버라이드 가능.
        예: unit=100 -> 7550 -> 7500, unit=1000 -> 7550 -> 7000
        
        Args:
            amount: 금액 (만원 단위)
        
        Returns:
            설정 단위로 절삭된 금액
        """
        unit = self.config.get("amount_round_down_unit", 100)
        try:
            unit_int = int(unit)
        except (TypeError, ValueError):
            unit_int = 100
        if unit_int <= 0:
            unit_int = 100
        return (int(amount) // unit_int) * unit_int
    
    def _fractional_share_ltv_cap_applies(self, property_data: Dict[str, Any]) -> bool:
        """
        요청사항에 지분조건 + JSON fractional_share_request_enabled 가 true일 때만
        최대 LTV 50%·최소진행 1000만원 하한 적용.
        """
        if not self.config.get("fractional_share_request_enabled", False):
            return False
        return fractional_share_condition_requested(property_data)
    
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
        # 프로모션 플래그 초기화
        self._promotion_applied = False
        self._promotion_name = None
        self._promotion_rejection_reason = None
        self._gm_ltv_steps_override = None
        self._fractional_share_min_floor = None
        
        # config에 product_type이 있으면 product_type 파라미터가 없을 때 사용 (팀엑스대부 등)
        if product_type is None:
            product_type = self.config.get("product_type")
        
        # 모든 검증 오류를 수집
        validation_errors = []
        
        # KB시세 검증
        # 파서에서 kb_price_raw(원본 문자열)와 kb_price(숫자)를 분리해서 전달
        # kb_price_raw가 있으면 원본 문자열 사용, 없으면 kb_price를 원본으로 사용 (하위호환)
        kb_price_raw = property_data.get("kb_price_raw") or property_data.get("kb_price")
        log_print(f"DEBUG: BaseCalculator.calculate - kb_price_raw: {kb_price_raw}, type: {type(kb_price_raw)}")
        logger.debug(f"BaseCalculator.calculate - kb_price_raw: {kb_price_raw}, type: {type(kb_price_raw)}")
        kb_price = self.validate_kb_price(property_data.get("kb_price") if property_data.get("kb_price_raw") else kb_price_raw)
        log_print(f"DEBUG: BaseCalculator.calculate - kb_price after validation: {kb_price}")
        logger.debug(f"BaseCalculator.calculate - kb_price after validation: {kb_price}")
        
        # 탁감가 여부 확인 (kb_price가 설정되어 있어도 체크)
        price_sources = self.config.get("price_sources", {})
        is_tackgamga = False
        if kb_price_raw:
            kb_price_raw_str = str(kb_price_raw).lower()
            if "탁감가" in kb_price_raw_str or "감정가" in kb_price_raw_str or "은행감정가" in kb_price_raw_str:
                is_tackgamga = True
                log_print(f"DEBUG: BaseCalculator.calculate - 탁감가 감지됨 (kb_price_raw): {kb_price_raw}")
        
        # special_notes에서도 탁감가 확인
        if not is_tackgamga:
            special_notes = property_data.get("special_notes", "") or ""
            if special_notes:
                special_notes_str = str(special_notes).lower()
                if "탁감가" in special_notes_str or "감정가" in special_notes_str or "은행감정가" in special_notes_str:
                    is_tackgamga = True
                    log_print(f"DEBUG: BaseCalculator.calculate - 탁감가 감지됨 (special_notes): {special_notes}")
        
        # 탁감가가 입력되어 있고, 해당 금융사가 탁감가를 사용하지 않으면 즉시 반환
        if is_tackgamga and price_sources.get("bank_appraisal_price", 0) == 0:
            log_print(f"DEBUG: BaseCalculator.calculate - 탁감가 입력됨 but 금융사가 탁감가 미사용: {self.bank_name}")
            logger.warning(f"BaseCalculator.calculate - 탁감가 입력됨 but 금융사가 탁감가 미사용: {self.bank_name}")
            validation_errors.append("감정가·탁감가 적용 불가")
            return {
                "bank_name": self.bank_name,
                "results": [],
                "conditions": self.config.get("conditions", []),
                "errors": validation_errors,
                "min_amount": self.config.get("min_amount", 3000)
            }
        
        # KB AI시세만 있고 해당 금융사가 취급하지 않을 경우
        # (앞선 금융사 calculate가 kb_ai를 kb_price에 반영하면 property_data.kb_price가 채워져 오판됨 → 스냅샷 우선)
        _pin = property_data.get("_price_input_snapshot")
        if _pin is not None:
            _kb_in, _pt_in, _kai_in = _pin.get("kb_price"), _pin.get("price_type"), _pin.get("kb_ai_price")
        else:
            _kb_in = property_data.get("kb_price")
            _pt_in = property_data.get("price_type")
            _kai_in = property_data.get("kb_ai_price")
        is_kb_ai_only = (
            (_pt_in == "kb_ai" or _kai_in)
            and not _kb_in
        )
        if is_kb_ai_only and price_sources.get("kb_ai_price", 0) == 0:
            log_print(f"DEBUG: BaseCalculator.calculate - KB AI시세 입력됨 but 금융사가 KB AI시세 미사용: {self.bank_name}")
            logger.warning(f"BaseCalculator.calculate - KB AI시세 입력됨 but 금융사가 KB AI시세 미사용: {self.bank_name}")
            validation_errors.append("KB AI시세 적용 불가")
            return {
                "bank_name": self.bank_name,
                "results": [],
                "conditions": self.config.get("conditions", []),
                "errors": validation_errors,
                "min_amount": self.config.get("min_amount", 3000)
            }
        
        # 하우스머치 시세만 있고 해당 금융사가 취급하지 않을 경우
        is_housematch_only = (
            property_data.get("price_type") == "housematch" or property_data.get("housematch_price") is not None
        )
        if is_housematch_only and price_sources.get("housematch_price", 0) == 0:
            log_print(f"DEBUG: BaseCalculator.calculate - 하우스머치 시세 입력됨 but 금융사가 하우스머치 시세 미사용: {self.bank_name}")
            logger.warning(f"BaseCalculator.calculate - 하우스머치 시세 입력됨 but 금융사가 하우스머치 시세 미사용: {self.bank_name}")
            validation_errors.append("하우스머치 시세 적용 불가")
            return {
                "bank_name": self.bank_name,
                "results": [],
                "conditions": self.config.get("conditions", []),
                "errors": validation_errors,
                "min_amount": self.config.get("min_amount", 3000)
            }
        
        # price_sources 설정에 따라 시세 추출 시도 (KB시세가 없을 경우)
        if kb_price is None:
            price_sources = self.config.get("price_sources", {})
            special_notes = property_data.get("special_notes", "") or ""
            original_kb_price_raw = property_data.get("kb_price_raw", "") or ""
            
            log_print(f"DEBUG: BaseCalculator.calculate - KB시세 없음, 대체 시세 추출 시도")
            log_print(f"DEBUG: BaseCalculator.calculate - special_notes: {special_notes}")
            log_print(f"DEBUG: BaseCalculator.calculate - original_kb_price_raw: {original_kb_price_raw}")
            log_print(f"DEBUG: BaseCalculator.calculate - bank_appraisal_price 설정: {price_sources.get('bank_appraisal_price', 0)}")
            
            # 탁감가가 입력되어 있는지 먼저 확인
            bank_appraisal_price = None
            try:
                # special_notes에서 탁감가 추출 시도
                bank_appraisal_price = extract_bank_appraisal_price_from_special_notes(special_notes)
                log_print(f"DEBUG: BaseCalculator.calculate - special_notes에서 탁감가 추출 시도 결과: {bank_appraisal_price}")
            except Exception as e:
                log_print(f"DEBUG: BaseCalculator.calculate - special_notes에서 탁감가 추출 에러: {e}")
                logger.error(f"BaseCalculator.calculate - 탁감가 추출 에러: {e}")
            
            # kb_price_raw에서도 탁감가 추출 시도 (예: "감정가 60,000만" 형식)
            if bank_appraisal_price is None and original_kb_price_raw:
                try:
                    log_print(f"DEBUG: BaseCalculator.calculate - kb_price_raw에서 탁감가 추출 시도")
                    bank_appraisal_price = extract_bank_appraisal_price_from_special_notes(str(original_kb_price_raw))
                    log_print(f"DEBUG: BaseCalculator.calculate - kb_price_raw에서 탁감가 추출 결과: {bank_appraisal_price}")
                except Exception as e:
                    log_print(f"DEBUG: BaseCalculator.calculate - kb_price_raw에서 탁감가 추출 에러: {e}")
                    logger.error(f"BaseCalculator.calculate - kb_price_raw에서 탁감가 추출 에러: {e}")
            
            # 탁감가가 입력되어 있고, 해당 금융사가 탁감가를 사용하지 않으면 즉시 반환
            if bank_appraisal_price is not None and price_sources.get("bank_appraisal_price", 0) == 0:
                log_print(f"DEBUG: BaseCalculator.calculate - 탁감가 입력됨 ({bank_appraisal_price}만원) but 금융사가 탁감가 미사용")
                logger.warning(f"BaseCalculator.calculate - 탁감가 입력됨 but 금융사가 탁감가 미사용: {self.bank_name}")
                validation_errors.append("감정가·탁감가 적용 불가")
                return {
                    "bank_name": self.bank_name,
                    "results": [],
                    "conditions": self.config.get("conditions", []),
                    "errors": validation_errors,
                    "min_amount": self.config.get("min_amount", 3000)
                }
            
            # 우선순위에 따라 시세 추출 시도
            # kb_price는 이미 위에서 확인했으므로 제외
            if price_sources.get("kb_ai_price", 0) == 1:
                kb_ai_price = None
                if property_data.get("kb_ai_price"):
                    kb_ai_price = self.validate_kb_price(property_data.get("kb_ai_price"))
                if kb_ai_price is None:
                    kb_ai_price = extract_kb_ai_price_from_special_notes(special_notes)
                if kb_ai_price is not None:
                    log_print(f"DEBUG: BaseCalculator.calculate - KB AI시세 추출: {kb_ai_price}만원")
                    logger.info(f"BaseCalculator.calculate - KB AI시세 추출: {kb_ai_price}만원")
                    kb_price = kb_ai_price
                    kb_price_raw = f"KB AI시세: {kb_ai_price}만원"
                    property_data["kb_price_raw"] = kb_price_raw  # property_data 업데이트
                    property_data["kb_price"] = kb_price  # property_data 업데이트
            
            # 탁감가 사용 가능한 경우 (이미 위에서 추출한 bank_appraisal_price 사용)
            if kb_price is None and price_sources.get("bank_appraisal_price", 0) == 1 and bank_appraisal_price is not None:
                log_print(f"DEBUG: BaseCalculator.calculate - ✅ 탁감가 사용: {bank_appraisal_price}만원")
                logger.info(f"BaseCalculator.calculate - 탁감가 사용: {bank_appraisal_price}만원")
                kb_price = bank_appraisal_price
                kb_price_raw = f"탁감가: {bank_appraisal_price}만원"
                property_data["kb_price_raw"] = kb_price_raw  # property_data 업데이트
                property_data["kb_price"] = kb_price  # property_data 업데이트
                log_print(f"DEBUG: BaseCalculator.calculate - property_data 업데이트 완료: kb_price={kb_price}, kb_price_raw={kb_price_raw}")
            
            if kb_price is None and price_sources.get("realestatetech_price", 0) == 1:
                realestatetech_price = extract_realestatetech_price_from_special_notes(special_notes)
                if realestatetech_price is not None:
                    log_print(f"DEBUG: BaseCalculator.calculate - 부동산테크 시세 추출: {realestatetech_price}만원")
                    logger.info(f"BaseCalculator.calculate - 부동산테크 시세 추출: {realestatetech_price}만원")
                    kb_price = realestatetech_price
                    kb_price_raw = f"부동산테크 시세: {realestatetech_price}만원"
                    property_data["kb_price_raw"] = kb_price_raw  # property_data 업데이트
                    property_data["kb_price"] = kb_price  # property_data 업데이트
            
            if kb_price is None and price_sources.get("korea_realestate_price", 0) == 1:
                korea_realestate_price = extract_korea_realestate_price_from_special_notes(special_notes)
                if korea_realestate_price is not None:
                    log_print(f"DEBUG: BaseCalculator.calculate - 한국부동산원 시세 추출: {korea_realestate_price}만원")
                    logger.info(f"BaseCalculator.calculate - 한국부동산원 시세 추출: {korea_realestate_price}만원")
                    kb_price = korea_realestate_price
                    kb_price_raw = f"한국부동산원 시세: {korea_realestate_price}만원"
                    property_data["kb_price_raw"] = kb_price_raw  # property_data 업데이트
                    property_data["kb_price"] = kb_price  # property_data 업데이트
            
            if kb_price is None and price_sources.get("housematch_price", 0) == 1:
                housematch_price = property_data.get("housematch_price") or extract_housematch_price_from_special_notes(special_notes)
                if housematch_price is not None:
                    log_print(f"DEBUG: BaseCalculator.calculate - 하우스머치 시세 추출: {housematch_price}만원")
                    logger.info(f"BaseCalculator.calculate - 하우스머치 시세 추출: {housematch_price}만원")
                    kb_price = housematch_price
                    kb_price_raw = f"하우스머치 시세: {housematch_price}만원"
                    property_data["kb_price_raw"] = kb_price_raw  # property_data 업데이트
                    property_data["kb_price"] = kb_price  # property_data 업데이트
        
        if kb_price is None:
            log_print(f"DEBUG: BaseCalculator.calculate - KB price is None, returning None")
            logger.warning("BaseCalculator.calculate - KB price is None, returning None")
            
            # property_data에서 탁감가 정보가 있는지 확인 (실제 입력된 시세 정보 확인)
            kb_price_raw = property_data.get("kb_price_raw", "") or ""
            special_notes = property_data.get("special_notes", "") or ""
            
            # 탁감가/감정가 정보가 있는지 확인 (여러 소스에서 확인)
            has_appraisal_price = False
            
            # 1. kb_price_raw에서 확인
            if kb_price_raw:
                kb_price_raw_str = str(kb_price_raw).lower()
                if "탁감가" in kb_price_raw_str or "감정가" in kb_price_raw_str or "은행감정가" in kb_price_raw_str:
                    has_appraisal_price = True
                    log_print(f"DEBUG: 탁감가 감지됨 (kb_price_raw): {kb_price_raw}")
            
            # 2. special_notes에서 확인
            if not has_appraisal_price and special_notes:
                special_notes_str = str(special_notes).lower()
                if "탁감가" in special_notes_str or "감정가" in special_notes_str or "은행감정가" in special_notes_str:
                    has_appraisal_price = True
                    log_print(f"DEBUG: 탁감가 감지됨 (special_notes): {special_notes}")
                else:
                    # special_notes에서 탁감가 추출 시도 (이미 상단에서 import됨)
                    appraisal_price = extract_bank_appraisal_price_from_special_notes(special_notes)
                    if appraisal_price is not None:
                        has_appraisal_price = True
                        log_print(f"DEBUG: 탁감가 추출됨 (special_notes): {appraisal_price}만원")
            
            # 감정가·탁감가(동일) 정보가 있으면 "감정가·탁감가 취급 불가", 하우스머치만 있으면 "하우스머치 시세 적용 불가", 없으면 "KB시세 정보가 없어 취급 불가합니다"
            if has_appraisal_price:
                validation_errors.append("감정가·탁감가 취급 불가")
                log_print(f"DEBUG: 감정가·탁감가 취급 불가 메시지 추가")
            else:
                # special_notes에 하우스머치 시세만 있는 경우 (금융사가 housematch 미사용 시)
                housematch_in_notes = extract_housematch_price_from_special_notes(special_notes)
                if housematch_in_notes is not None and price_sources.get("housematch_price", 0) == 0:
                    validation_errors.append("하우스머치 시세 적용 불가")
                    log_print(f"DEBUG: 하우스머치 시세 적용 불가 메시지 추가 (special_notes에서 추출)")
                else:
                    validation_errors.append("KB시세 정보가 없어 취급 불가합니다")
                    log_print(f"DEBUG: KB시세 정보 없음 메시지 추가")
            
            return {
                "bank_name": self.bank_name,
                "results": [],
                "conditions": self.config.get("conditions", []),
                "errors": validation_errors,
                "min_amount": self.config.get("min_amount", 3000)
            }
        
        # property_types 설정에 따른 취급 물건 타입 체크
        property_type = property_data.get("property_type", "")
        special_notes = property_data.get("special_notes", "") or ""
        
        # OK저축은행인 경우 사업자/가계 상품에 따라 다른 설정 사용
        is_ok_bank = self.bank_name == "OK저축은행" or "OK저축은행" in self.bank_name or "오케이저축은행" in self.bank_name
        if is_ok_bank:
            # OK저축은행: product_type에 따라 적절한 설정 선택
            if product_type == "household":
                property_types_config = self.config.get("household_property_types", {})
            elif product_type == "business":
                property_types_config = self.config.get("business_property_types", {})
            else:
                # product_type이 없으면 기본적으로 가계자금 설정 사용
                property_types_config = self.config.get("household_property_types", self.config.get("property_types", {}))
        else:
            # 일반 금융사: product_type에 따라 설정 선택 (팀엑스대부 등)
            if product_type == "household":
                property_types_config = self.config.get("household_property_types", self.config.get("property_types", {}))
            elif product_type == "business":
                property_types_config = self.config.get("business_property_types", self.config.get("property_types", {}))
            else:
                property_types_config = self.config.get("property_types", {})
        
        # 한글 물건유형 → apartment 등 config 키 (물건취급·세대수 조건 공통)
        ptype_key = get_property_type_key(property_type, special_notes)
        
        if property_type and property_types_config and ptype_key:
            is_allowed = property_types_config.get(ptype_key, 1) == 1
            if not is_allowed:
                log_print(f"DEBUG: BaseCalculator.calculate - 취급 불가 물건 타입: {property_type} (key: {ptype_key})")
                logger.warning(f"BaseCalculator.calculate - 취급 불가 물건 타입: {property_type}")
                validation_errors.append(f"{property_type}은(는) 취급 불가 물건 타입입니다")
                return {
                    "bank_name": self.bank_name,
                    "results": [],
                    "conditions": self.config.get("conditions", []),
                    "errors": validation_errors,
                    "min_amount": self.config.get("min_amount", 3000)
                }
        
        # property_type_conditions 체크 (부동산 타입별 조건 — 키는 apartment 등 영문, bank/loan JSON과 동일)
        property_type_conditions = self.config.get("property_type_conditions", {})
        if property_type_conditions and ptype_key:
            conditions_for_ptype = property_type_conditions.get(ptype_key)
            if conditions_for_ptype:
                prop_label = property_type or ptype_key
                min_household_count = conditions_for_ptype.get("min_household_count")
                if min_household_count is not None:
                    household_count = property_data.get("household_count")
                    if household_count is None or household_count < min_household_count:
                        log_print(f"DEBUG: BaseCalculator.calculate - {ptype_key} 세대수 {household_count} < min_household_count {min_household_count}, 취급 불가")
                        logger.warning(f"BaseCalculator.calculate - {ptype_key} 세대수 {household_count} < min_household_count {min_household_count}, 취급 불가")
                        validation_errors.append(f"{prop_label}은(는) 최소 {min_household_count}세대 이상이어야 취급 가능합니다 (현재: {household_count or '정보없음'}세대)")
                min_kb_price_for_type = conditions_for_ptype.get("min_kb_price")
                if min_kb_price_for_type is not None and kb_price < min_kb_price_for_type:
                    log_print(f"DEBUG: BaseCalculator.calculate - {ptype_key} KB price {kb_price}만원 < min_kb_price {min_kb_price_for_type}만원, 취급 불가")
                    logger.warning(f"BaseCalculator.calculate - {ptype_key} KB price {kb_price}만원 < min_kb_price {min_kb_price_for_type}만원, 취급 불가")
                    validation_errors.append(f"{prop_label}은(는) KB시세 {kb_price:,.0f}만원이 최소 {min_kb_price_for_type:,.0f}만원 이상이어야 취급 가능합니다 (현재: {kb_price:,.0f}만원, 부족: {min_kb_price_for_type - kb_price:,.0f}만원)")
        
        # 지분/공유지분 (data/banks·data/loan 공통: fractional_share_allowed)
        frac_cfg = self.config.get("fractional_share_allowed")
        if frac_cfg is not None:
            frac = infer_fractional_ownership(property_data)
            if frac is True and frac_cfg is False:
                log_print("DEBUG: BaseCalculator.calculate - 지분/공유지분 물건, fractional_share_allowed=false")
                validation_errors.append("지분·공유지분 물건은 취급 불가입니다")
                return {
                    "bank_name": self.bank_name,
                    "results": [],
                    "conditions": self.config.get("conditions", []),
                    "errors": validation_errors,
                    "min_amount": self.config.get("min_amount", 3000)
                }
        
        # KB시세 최소 금액 확인 (property_type_conditions에 없으면 전역 min_kb_price 사용)
        min_kb_price = self.config.get("min_kb_price")
        if min_kb_price is not None:
            # property_type_conditions에서 이미 체크했는지 확인
            already_checked = False
            if property_type_conditions and ptype_key:
                c = property_type_conditions.get(ptype_key)
                if c and c.get("min_kb_price") is not None:
                    already_checked = True
            
            if not already_checked and kb_price < min_kb_price:
                log_print(f"DEBUG: BaseCalculator.calculate - KB price {kb_price}만원 < min_kb_price {min_kb_price}만원, 취급 불가")
                logger.warning(f"BaseCalculator.calculate - KB price {kb_price}만원 < min_kb_price {min_kb_price}만원, 취급 불가")
                validation_errors.append(f"KB시세 {kb_price:,.0f}만원은 최소 {min_kb_price:,.0f}만원 이상이어야 취급 가능합니다 (현재: {kb_price:,.0f}만원, 부족: {min_kb_price - kb_price:,.0f}만원)")
        
        # 특이사항 및 직업 정보 추출 (한 번만 조회하여 재사용)
        special_notes = property_data.get("special_notes", "") or ""
        occupation = property_data.get("occupation", "") or ""

        # 재건축 단계 제한 (기본: 최대 5단계까지 허용, 금융사별 override 가능)
        reconstruction_keyword = str(self.config.get("reconstruction_keyword", "재건축") or "재건축")
        reconstruction_max_stage = self.config.get("reconstruction_max_stage", 5)
        detected_reconstruction_stage = extract_reconstruction_stage(property_data, keyword=reconstruction_keyword)
        if reconstruction_max_stage is not None and detected_reconstruction_stage is not None:
            try:
                max_stage_int = int(reconstruction_max_stage)
            except (TypeError, ValueError):
                max_stage_int = None
            if max_stage_int is not None and detected_reconstruction_stage > max_stage_int:
                validation_errors.append(
                    f"{reconstruction_keyword} {detected_reconstruction_stage}단계는 취급 불가합니다 "
                    f"(최대 {max_stage_int}단계까지 가능)"
                )
                log_print(
                    "DEBUG: BaseCalculator.calculate - 재건축 단계 제한 초과, "
                    f"detected={detected_reconstruction_stage}, max={max_stage_int}, bank={self.bank_name}"
                )
        
        # 특이사항 검증: 불가 키워드 체크
        # 기본 불가 키워드
        restricted_keywords = ["압류", "가압류", "경매취하자금"]
        # 추가 불가 키워드 (미래하우스론 등 특정 상품용)
        additional_restricted_keywords = self.config.get("additional_restricted_keywords", [])
        if additional_restricted_keywords:
            restricted_keywords.extend(additional_restricted_keywords)
        
        found_keywords = []
        for keyword in restricted_keywords:
            if keyword in special_notes:
                found_keywords.append(keyword)
                log_print(f"DEBUG: BaseCalculator.calculate - 특이사항에 '{keyword}' 발견, 취급 불가")
                logger.warning(f"BaseCalculator.calculate - 특이사항에 '{keyword}' 발견, 취급 불가")
        
        if found_keywords:
            validation_errors.append(f"특이사항에 '{', '.join(found_keywords)}'가 포함되어 취급 불가합니다")
        
        # 직업 제한 확인 (restricted_occupations)
        restricted_occupations_config = self.config.get("restricted_occupations", {})
        if restricted_occupations_config.get("enabled", False):
            if occupation:
                keywords = restricted_occupations_config.get("keywords", [])
                found_occupation_keywords = []
                for keyword in keywords:
                    if keyword in occupation:
                        found_occupation_keywords.append(keyword)
                        log_print(f"DEBUG: BaseCalculator.calculate - 직업 '{occupation}'에 제한 키워드 '{keyword}' 발견, 취급 불가")
                        logger.warning(f"BaseCalculator.calculate - 직업 '{occupation}'에 제한 키워드 '{keyword}' 발견, 취급 불가")
                
                if found_occupation_keywords:
                    comment = restricted_occupations_config.get("comment", "제한업종")
                    validation_errors.append(f"직업 '{occupation}'은(는) {comment}으로 취급 불가합니다 (발견된 키워드: {', '.join(found_occupation_keywords)})")
        
        # 법인사업자 제한 확인 (corporate_business_restriction)
        # enabled: true = 법인사업자 취급 가능(검사 생략), false = 법인사업자 취급 불가(키워드 시 불가)
        corporate_business_config = self.config.get("corporate_business_restriction", {})
        if corporate_business_config and not corporate_business_config.get("enabled", True):
            keywords = corporate_business_config.get("keywords", [])
            found_corporate_keywords = []
            
            # 직업 필드에서 확인
            if occupation:
                for keyword in keywords:
                    if keyword in occupation:
                        found_corporate_keywords.append(keyword)
                        log_print(f"DEBUG: BaseCalculator.calculate - 직업 '{occupation}'에 '{keyword}' 발견, 취급 불가")
                        logger.warning(f"BaseCalculator.calculate - 직업 '{occupation}'에 '{keyword}' 발견, 취급 불가")
            
            # 특이사항에서도 확인
            if special_notes:
                for keyword in keywords:
                    if keyword in special_notes:
                        found_corporate_keywords.append(keyword)
                        log_print(f"DEBUG: BaseCalculator.calculate - 특이사항에 '{keyword}' 발견, 취급 불가")
                        logger.warning(f"BaseCalculator.calculate - 특이사항에 '{keyword}' 발견, 취급 불가")
            
            # 요청사항에서도 확인
            requests_text = (property_data.get("requests") or "").strip()
            if requests_text:
                for keyword in keywords:
                    if keyword in requests_text:
                        found_corporate_keywords.append(keyword)
                        log_print(f"DEBUG: BaseCalculator.calculate - 요청사항에 '{keyword}' 발견, 취급 불가")
                        logger.warning(f"BaseCalculator.calculate - 요청사항에 '{keyword}' 발견, 취급 불가")
            
            if found_corporate_keywords:
                comment = corporate_business_config.get("comment", "법인사업자 취급 불가")
                validation_errors.append(comment)
        
        # 담보제공건 취급 불가 (JB하이론 등)
        collateral_provider_excluded = self.config.get("collateral_provider_excluded", False)
        if collateral_provider_excluded:
            has_collateral_provider = property_data.get("collateral_provider") is True
            name_str = str(property_data.get("name") or "")
            special_notes_str = (special_notes if isinstance(special_notes, str) else " ".join(str(x) for x in (special_notes or [])))
            has_collateral_in_notes = "담보제공" in special_notes_str or "담제자" in special_notes_str
            if has_collateral_provider or "(담)" in name_str or "(담보)" in name_str or has_collateral_in_notes:
                log_print(f"DEBUG: BaseCalculator.calculate - 담보제공건 취급 불가")
                validation_errors.append("담보제공건 취급 불가")
        
        # 금융사별 validation_rules 체크 (설정 파일에서 정의된 제한 조건)
        self._validate_validation_rules(property_data, validation_errors)
        
        # 고객 나이 검증: 75세 이하만 취급
        max_age = self.config.get("max_age")
        if max_age is not None:
            age = property_data.get("age")
            if age is not None:
                try:
                    age_int = int(age)
                    if age_int > max_age:
                        log_print(f"DEBUG: BaseCalculator.calculate - 나이 {age_int}세 > max_age {max_age}세, 취급 불가")
                        logger.warning(f"BaseCalculator.calculate - 나이 {age_int}세 > max_age {max_age}세, 취급 불가")
                        validation_errors.append(f"고객 나이 {age_int}세는 {max_age}세 이하여야 취급 가능합니다 (초과: {age_int - max_age}세)")
                except (ValueError, TypeError):
                    pass  # 나이가 숫자가 아니면 무시
        
        # 신용평점 최소 점수 검증
        min_credit_score = self.config.get("min_credit_score")
        if min_credit_score is not None:
            credit_score = property_data.get("credit_score")
            if credit_score is not None:
                try:
                    from utils.validators import validate_credit_score
                    credit_score_int = validate_credit_score(credit_score)
                    if credit_score_int is not None and credit_score_int < min_credit_score:
                        log_print(f"DEBUG: BaseCalculator.calculate - 신용평점 {credit_score_int}점 < min_credit_score {min_credit_score}점, 취급 불가")
                        logger.warning(f"BaseCalculator.calculate - 신용평점 {credit_score_int}점 < min_credit_score {min_credit_score}점, 취급 불가")
                        validation_errors.append(f"신용평점 {credit_score_int}점은 최소 {min_credit_score}점 이상이어야 취급 가능합니다 (부족: {min_credit_score - credit_score_int}점)")
                except (ValueError, TypeError):
                    pass  # 신용평점이 숫자가 아니면 무시
        
        # 투맨금융대부 등: 순위 제한 검증
        # - 동일 금융사 + 동일 채무자는 순위가 연속이 아니어도 하나로 합산
        # - 채무자 식별이 어려운 경우에는 기존과 동일하게 연속 동일 기관만 합산
        # 대환 요청 근저당(is_refinance=True)은 설정 후 말소되므로 카운트에서 제외
        max_priority_limit = self.config.get("max_priority_limit")
        if max_priority_limit is not None:
            mortgages_raw = property_data.get("mortgages", [])
            liens = [
                m for m in mortgages_raw
                if not m.get("is_tenant", False)
                and not m.get("is_refinance", False)
                and (m.get("institution") or "").strip() not in ("전세입자", "월세입자", "세입자")
            ]
            liens_sorted = sorted(liens, key=lambda x: x.get("priority", 999))
            groups = []
            seen_inst_debtor_keys = set()
            prev_inst = None  # 채무자 식별이 어려운 경우의 fallback(연속 동일 기관 합산)
            for m in liens_sorted:
                inst_raw = (m.get("institution") or "")
                inst = inst_raw.replace(" ", "")

                # 기본 금융사명: 괄호 앞 텍스트 (예: "애큐온캐피탈(2025.08.29/홍길동)" -> "애큐온캐피탈")
                inst_name = inst.split("(", 1)[0] if "(" in inst else inst

                # 채무자 추출: 괄호 안 마지막 '/' 뒤 텍스트를 채무자로 간주
                debtor = ""
                paren_match = re.search(r"\(([^)]*)\)", inst_raw)
                if paren_match:
                    inside = re.sub(r"\s+", "", paren_match.group(1))
                    if "/" in inside:
                        debtor = inside.rsplit("/", 1)[-1].strip()
                    # 날짜/기호 노이즈 제거
                    debtor = re.sub(r"[\d.\-_/()]+", "", debtor).strip()

                if inst_name and debtor:
                    key = f"{inst_name}|{debtor}"
                    if key not in seen_inst_debtor_keys:
                        seen_inst_debtor_keys.add(key)
                        groups.append(key)
                    # 동일 키는 연속/비연속 관계없이 합산되어 추가하지 않음
                    prev_inst = inst
                    continue

                # 채무자 파싱이 안 되면 기존 방식 유지(연속 동일 기관만 합산)
                if prev_inst is None or inst != prev_inst:
                    groups.append(inst)
                prev_inst = inst
            if len(groups) >= max_priority_limit:
                custom_msg = self.config.get("max_priority_limit_error_message")
                if custom_msg:
                    try:
                        validation_errors.append(
                            custom_msg.format(limit=max_priority_limit, n=len(groups))
                        )
                    except (KeyError, ValueError):
                        validation_errors.append(custom_msg)
                else:
                    validation_errors.append(
                        f"근저당권 {max_priority_limit}순위 초과로 진행 불가입니다 (현재 {len(groups)}순위, 동일 금융사 연속은 합산)"
                    )
        
        # 검증 오류가 있으면 즉시 반환
        if validation_errors:
            return {
                "bank_name": self.bank_name,
                "results": [],
                "conditions": self.config.get("conditions", []),
                "errors": validation_errors,
                "min_amount": self.config.get("min_amount", 3000)
            }
        
        # 하한가 적용 조건 확인
        lower_bound_config = self.config.get("lower_bound_price", {})
        lower_bound_applied = False  # 하한가 적용 여부 플래그
        if lower_bound_config.get("enabled", False):
            # 하한가 적용 조건 확인
            property_type = property_data.get("property_type", "")
            address = property_data.get("address", "")
            total_floors = property_data.get("total_floors")  # 건물 총층수
            
            # 아파트/주상복합 구분
            is_apartment = property_type and "아파트" in property_type and "주상복합" not in property_type
            is_residential_commercial = property_type and "주상복합" in property_type
            
            # 현재 층수 추출 (주소에서)
            floor = None
            if address:
                # 총층수 패턴 제외하고 현재 층수만 추출
                # "6층 (총층수 10층)" 에서 6만 추출
                floor_match = re.search(r'(\d+)층(?!\s*\))', address)
                if floor_match:
                    floor = int(floor_match.group(1))
            
            log_print(f"DEBUG: 하한가 체크 - property_type: {property_type}, floor: {floor}, total_floors: {total_floors}")
            
            # 새 양식: 물건 타입별 rules 확인
            apply_lower_bound = False
            
            if is_apartment and "apartment" in lower_bound_config:
                # 아파트 조건 확인
                apartment_rules = lower_bound_config["apartment"].get("rules", [])
                apply_lower_bound = self._check_lower_bound_rules(apartment_rules, floor, total_floors)
                log_print(f"DEBUG: 아파트 하한가 규칙 적용 결과: {apply_lower_bound}")
            elif is_residential_commercial and "residential_commercial" in lower_bound_config:
                # 주상복합 조건 확인
                rc_rules = lower_bound_config["residential_commercial"].get("rules", [])
                apply_lower_bound = self._check_lower_bound_rules(rc_rules, floor, total_floors)
                log_print(f"DEBUG: 주상복합 하한가 규칙 적용 결과: {apply_lower_bound}")
            elif (is_apartment or is_residential_commercial) and "apartment" not in lower_bound_config and "residential_commercial" not in lower_bound_config:
                # 기존 양식 호환: 단순히 아파트/주상복합 1,2층 체크
                if floor in [1, 2]:
                    apply_lower_bound = True
                    log_print(f"DEBUG: 기존 양식 하한가 적용 (1,2층)")
            
            if apply_lower_bound:
                lower_bound_price = extract_lower_bound_price(kb_price_raw)
                if lower_bound_price is not None:
                    log_print(f"DEBUG: BaseCalculator.calculate - 하한가 적용: 일반가 {kb_price}만원 -> 하한가 {lower_bound_price}만원 ({property_type} {floor}층, 총 {total_floors}층)")
                    logger.info(f"BaseCalculator.calculate - 하한가 적용: 일반가 {kb_price}만원 -> 하한가 {lower_bound_price}만원 ({property_type} {floor}층, 총 {total_floors}층)")
                    kb_price = lower_bound_price
                    lower_bound_applied = True
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
        
        # 지역 및 급지 검증 오류 수집
        region_errors = []
        
        if not is_valid_region:
            print(f"DEBUG: BaseCalculator.calculate - Region {region} is not in ALL_REGIONS list, 취급 불가지역")
            region_errors.append(f"지역 '{region}'은(는) 취급 가능한 지역 목록에 없습니다")
        
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
                # "광주": 광주광역시만 매칭, 경기도광주시 제외 (경기도광주시에 "광주" 포함으로 인한 오매칭 방지)
                if target == "광주":
                    if region.startswith("광주광역시"):
                        is_target_region = True
                        break
                    continue
                if target_full in region or target in region:  # "서울" in "서울특별시광진구" 또는 "경상북도" in "경상북도구미시"
                    is_target_region = True
                    break
            if not is_target_region:
                print(f"DEBUG: BaseCalculator.calculate - Region {region} is not in target regions: {target_regions}")
                region_errors.append("취급 대상 지역이 아닙니다")
        
        # 급지 확인
        grade = self.get_region_grade(region)
        print(f"DEBUG: BaseCalculator.calculate - region: {region}, grade: {grade}")
        if grade is None:
            print(f"DEBUG: BaseCalculator.calculate - grade is None for region: {region}, 취급 불가지역")
            region_errors.append("취급 불가지역")
        
        # 9급지인 경우 취급 불가지역으로 처리 (grade는 config에 따라 9 또는 "9"로 올 수 있음)
        if grade in (9, "9"):
            print(f"DEBUG: BaseCalculator.calculate - grade 9 for region: {region}, 취급 불가지역")
            region_errors.append("9급지로 취급 불가")
        
        # 지역 검증 오류가 있으면 반환
        if region_errors:
            return {
                "bank_name": self.bank_name,
                "results": [],
                "conditions": self.config.get("conditions", []),
                "errors": region_errors,
                "min_amount": self.config.get("min_amount", 3000)
            }
        
        # 면적 제한 확인 (BNK캐피탈 등 특정 금융사만)
        area_limit_config = self.config.get("area_limit", {})
        if area_limit_config.get("enabled", False):
            area = property_data.get("area")
            if area is not None:
                max_area = area_limit_config.get("max_area", 135)
                max_ltv_when_exceeded = area_limit_config.get("max_ltv_when_exceeded")
                excluded_regions = area_limit_config.get("excluded_regions", [])
                
                # max_ltv_when_exceeded가 있으면 면적 초과 시 LTV만 제한 (취급불가 아님)
                if not max_ltv_when_exceeded:
                    # 제외 지역(서울 등)이 아니고 면적이 제한을 초과하면 불가
                    is_excluded_region = False
                    for excluded in excluded_regions:
                        if excluded in region:
                            is_excluded_region = True
                            break
                    
                    if not is_excluded_region and area > max_area:
                        print(f"DEBUG: BaseCalculator.calculate - area {area}㎡ > max_area {max_area}㎡ for region {region}, 취급 불가")
                        # 소수점 3자리로 포맷팅
                        area_formatted = f"{area:.3f}".rstrip('0').rstrip('.') if area % 1 != 0 else f"{int(area)}"
                        max_area_formatted = f"{max_area:.3f}".rstrip('0').rstrip('.') if max_area % 1 != 0 else f"{int(max_area)}"
                        excess_area = area - max_area
                        excess_area_formatted = f"{excess_area:.3f}".rstrip('0').rstrip('.') if excess_area % 1 != 0 else f"{int(excess_area)}"
                        return {
                            "bank_name": self.bank_name,
                            "results": [],
                            "conditions": self.config.get("conditions", []),
                            "errors": [f"면적 {area_formatted}㎡는 서울지역 이외에서는 최대 {max_area_formatted}㎡까지 취급 가능합니다 (초과: {excess_area_formatted}㎡)"],
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
        # OK저축은행만: 면적·신용등급 등 고려 시 product_type(가계/사업) 전달
        # 그 외 금융사: _product_type 없이 전달 → 각 금융사 조견(max_ltv_by_grade 등)으로만 최대 LTV 계산
        if is_ok_bank:
            if is_household_for_ok:
                property_data_with_type = property_data.copy()
                property_data_with_type["_product_type"] = "household"
                max_ltv = self.get_max_ltv_by_grade(grade, region, property_data_with_type)
            else:
                property_data_with_type = property_data.copy()
                property_data_with_type["_product_type"] = "business"
                max_ltv = self.get_max_ltv_by_grade(grade, region, property_data_with_type)
        else:
            max_ltv = self.get_max_ltv_by_grade(grade, region, property_data)
        print(f"DEBUG: BaseCalculator.calculate - grade: {grade}, max_ltv: {max_ltv}, below_standard_ltv: {below_standard_ltv}")  # 추가
        if max_ltv is None or max_ltv == 0:
            print(f"DEBUG: BaseCalculator.calculate - max_ltv is None or 0 for grade {grade}, returning None")  # 추가
            return None
        
        # 기준 LTV 이하 지역인 경우 해당 LTV를 최대 LTV로 사용
        if is_below_standard:
            max_ltv = below_standard_ltv
            print(f"DEBUG: BaseCalculator.calculate - 기준 LTV 이하 지역: {region}, 적용 LTV: {max_ltv}%")

        # 물건유형별 최대 LTV 상한 (한국투자저축 빌라 75% 등)
        max_ltv_by_property_type = self.config.get("max_ltv_by_property_type", {})
        if max_ltv_by_property_type and ptype_key and ptype_key in max_ltv_by_property_type:
            property_ltv_cap = max_ltv_by_property_type[ptype_key]
            if max_ltv is not None and max_ltv > property_ltv_cap:
                print(
                    f"DEBUG: BaseCalculator.calculate - 물건유형 {ptype_key} LTV 상한 적용: "
                    f"{max_ltv}% -> {property_ltv_cap}%"
                )
                max_ltv = property_ltv_cap
        
        # GM대부 등: 시세 N억 미만 물건유형별 LTV 상한·스텝 (예: 아파트 2억 미만 60~65%)
        ltv_kb_rules = self.config.get("ltv_kb_price_override")
        if ltv_kb_rules and ptype_key is not None and kb_price is not None:
            for rule in ltv_kb_rules:
                if ptype_key not in rule.get("property_type_keys", []):
                    continue
                under = rule.get("under_kb_price")
                if under is not None and float(kb_price) < float(under):
                    lmin = float(rule.get("ltv_min", 60))
                    lmax = float(rule.get("ltv_max", 65))
                    if max_ltv is not None:
                        max_ltv = min(float(max_ltv), lmax)
                    self._gm_ltv_steps_override = sorted({int(lmin), int(lmax)}, reverse=True)
                    print(f"DEBUG: BaseCalculator.calculate - ltv_kb_price_override kb<{under}: max_ltv={max_ltv}, steps={self._gm_ltv_steps_override}")
                    break
        
        # 면적 초과 시 LTV 제한 (max_ltv_when_exceeded: 85㎡ 초과 시 LTV 85% 등)
        if area_limit_config.get("enabled", False) and area_limit_config.get("max_ltv_when_exceeded"):
            area = property_data.get("area")
            if area is not None and area > area_limit_config.get("max_area", 135):
                cap_ltv = area_limit_config["max_ltv_when_exceeded"]
                if max_ltv is not None and max_ltv > cap_ltv:
                    max_ltv = cap_ltv
                    print(f"DEBUG: BaseCalculator.calculate - 면적 {area}㎡ > {area_limit_config.get('max_area')}㎡, max_ltv 제한: {max_ltv}%")
        
        # 기존 근저당권 총액: 대환 제외·후순위 공통으로 선순위 채권최고액 합. 대환 상환액은 refinance_principal(원금)로 별도 차감.
        mortgages = property_data.get("mortgages", [])
        
        # 대환할 근저당권 찾기 (여러 개 대비하여 누적합으로 처리)
        refinance_principal = 0.0  # 대환할 근저당권 원금 합계
        refinance_institutions = []  # 대환하는 금융사 이름 리스트 (가계자금용)
        all_refinance_institutions = []  # 대환하는 모든 금융사 이름 리스트 (전체용)
        other_mortgages = []  # 나머지 근저당권들
        
        # 가계자금인 경우: 물상담보 제외, business_product_names(공통 목록)에 없는 것만 대환 가능
        if is_household_for_ok:
            business_product_names = self._get_business_product_names()
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
            # self_refinance_excluded 체크 (본인 금융사 대환 불가)
            self_refinance_excluded = self.config.get("self_refinance_excluded", [])
            is_bnk = self.bank_name == "BNK캐피탈" or "BNK캐피탈" in self.bank_name or "비엔케이캐피탈" in self.bank_name
            is_ok_bank = self.bank_name == "OK저축은행" or "OK저축은행" in self.bank_name or "오케이저축은행" in self.bank_name
            is_acuon = self.bank_name == "애큐온저축은행" or "애큐온" in self.bank_name
            is_mg_capital = self.bank_name == "MG캐피탈" or "MG캐피탈" in self.bank_name or "엠지케피탈" in self.bank_name
            is_business_product = is_bnk or is_ok_bank or is_acuon or is_mg_capital
            business_product_names = self._get_business_product_names() if is_business_product else []
            
            for mortgage in mortgages:
                if mortgage.get("is_refinance", False):
                    institution = mortgage.get("institution", "")
                    institution_clean = institution.replace(" ", "")
                    
                    # self_refinance_excluded 체크: 본인 금융사 대환 불가
                    is_self_refinance_excluded = False
                    if self_refinance_excluded:
                        # institution이 self_refinance_excluded 목록(본인 금융사 별칭)에 해당하면 대환 불가
                        for excluded_name in self_refinance_excluded:
                            excluded_clean = excluded_name.replace(" ", "")
                            if excluded_clean in institution_clean:
                                is_self_refinance_excluded = True
                                print(f"DEBUG: BaseCalculator.calculate - {self.bank_name}: '{institution}'는 self_refinance_excluded에 포함되어 본인 금융사 대환 불가, 후순위로 처리")
                                break
                    
                    if is_self_refinance_excluded:
                        # 본인 금융사 대환 불가이므로 후순위로 처리
                        other_mortgages.append(mortgage)
                        continue
                    
                    # refinance_all_requested: data/loan 상품 등 - 요청사항에 따른 대환 모두 허용
                    if self.config.get("refinance_all_requested"):
                        mortgage_amount = float(mortgage.get("amount", 0) or 0)
                        refinance_principal += mortgage_amount
                        if institution not in all_refinance_institutions:
                            all_refinance_institutions.append(institution)
                        print(f"DEBUG: BaseCalculator.calculate - refinance_all_requested: priority={mortgage.get('priority')}, institution={institution}, principal={mortgage_amount}만원")
                        continue
                    
                    # refinance_rules 적용 (팀엑스대부 등: 사업자->가계 대환불가, 가계->사업자 대환가능)
                    refinance_rules = self.config.get("refinance_rules", {})
                    if refinance_rules:
                        if product_type == "business" and "household" in refinance_rules.get("business_cannot_refinance", []):
                            if "가계" in institution or "가계자금" in institution:
                                other_mortgages.append(mortgage)
                                print(f"DEBUG: BaseCalculator.calculate - {self.bank_name} 사업자: '{institution}'는 가계자금이라 대환 불가, 후순위로 처리")
                                continue
                        if product_type == "household" and "business" in refinance_rules.get("household_can_refinance", []):
                            rr_business_names = self._get_business_product_names()
                            can_refinance_rr = any(ref_inst.replace(" ", "") in institution_clean for ref_inst in rr_business_names) or "사업자금" in institution
                            if not can_refinance_rr:
                                other_mortgages.append(mortgage)
                                print(f"DEBUG: BaseCalculator.calculate - {self.bank_name} 가계자금: '{institution}'는 사업자금이 아니라 대환 불가, 후순위로 처리")
                                continue
                    
                    # BNK캐피탈, OK저축은행, 애큐온저축은행, MG캐피탈인 경우 대환 가능 기관 체크
                    can_refinance = False
                    if is_business_product and business_product_names:
                        # 리스트에 있는 기관인지 확인
                        for ref_inst in business_product_names:
                            ref_inst_clean = ref_inst.replace(" ", "")
                            if ref_inst_clean in institution_clean:
                                can_refinance = True
                                break
                        
                        # 리스트에 없지만 '사업자금' 문자열이 있으면 대환 가능
                        if not can_refinance and "사업자금" in institution:
                            can_refinance = True
                            bank_display_name = "BNK캐피탈" if is_bnk else ("OK저축은행" if is_ok_bank else ("애큐온저축은행" if is_acuon else "MG캐피탈"))
                            print(f"DEBUG: BaseCalculator.calculate - {bank_display_name}: '{institution}'에 '사업자금' 포함되어 대환 가능")
                    else:
                        # BNK캐피탈, OK저축은행, 애큐온저축은행, MG캐피탈이 아니면 대환 가능
                        can_refinance = True
                    
                    if can_refinance:
                        mortgage_amount = float(mortgage.get("amount", 0) or 0)
                        refinance_principal += mortgage_amount
                        if institution not in all_refinance_institutions:
                            all_refinance_institutions.append(institution)
                        print(f"DEBUG: BaseCalculator.calculate - 대환할 근저당권 발견: priority={mortgage.get('priority')}, institution={institution}, principal={mortgage_amount}만원")
                    else:
                        # 대환 불가능한 기관은 후순위로 처리
                        bank_display_name = "BNK캐피탈" if is_bnk else ("OK저축은행" if is_ok_bank else ("애큐온저축은행" if is_acuon else "MG캐피탈"))
                        print(f"DEBUG: BaseCalculator.calculate - {bank_display_name}: '{institution}'는 대환 가능 기관이 아니므로 후순위로 처리")
                        other_mortgages.append(mortgage)
                else:
                    other_mortgages.append(mortgage)
        
        # 나머지 근저당(대환 제외) 합산: 항상 채권최고액. 대환 시 2단계에서 refinance_principal(대환 대상 원금)만 추가 차감.
        total_mortgage = self.calculate_total_mortgage(other_mortgages)
        print(
            f"DEBUG: BaseCalculator.calculate - 선순위 채권최고 합(대환 제외·후순위 동일): {total_mortgage}만원, "
            f"refinance_principal(대환 원금): {refinance_principal}만원"
        )
        
        print(f"DEBUG: BaseCalculator.calculate - mortgages: {mortgages}")  # 추가
        
        # BNK캐피탈인 경우 대환 요청이 있었는데 대환 가능한 기관이 없는지 확인
        is_bnk = self.bank_name == "BNK캐피탈" or "BNK캐피탈" in self.bank_name or "비엔케이캐피탈" in self.bank_name
        if is_bnk:
            # 대환 요청된 근저당권이 있는지 확인
            has_refinance_request = any(m.get("is_refinance", False) for m in mortgages)
            if has_refinance_request and refinance_principal == 0:
                # 대환 요청은 있었지만 대환 가능한 기관이 없음
                requested_institutions = []
                for mortgage in mortgages:
                    if mortgage.get("is_refinance", False):
                        requested_institutions.append(mortgage.get("institution", ""))
                
                institutions_str = ", ".join(requested_institutions) if requested_institutions else "요청된 기관"
                refinanceable_list = self._get_business_product_names()
                refinanceable_str = ", ".join(refinanceable_list[:5]) + ("..." if len(refinanceable_list) > 5 else "")
                
                return {
                    "bank_name": self.bank_name,
                    "results": [],
                    "conditions": self.config.get("conditions", []),
                    "errors": [
                        f"대환 요청된 기관({institutions_str})이 대환 가능 기관 목록에 없습니다",
                        f"대환 가능 기관: {refinanceable_str}",
                        f"참고: 기관명에 '사업자금'이 포함된 경우에도 대환 가능합니다"
                    ],
                    "min_amount": self.config.get("min_amount", 3000)
                }
        
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
                # bank_name이 사업자 상품명 리스트(공통 목록)에 있는지 확인
                business_product_names = self._get_business_product_names()
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
            
            # 사업자 상품인 경우: business_product_names(공통 목록)에 있는 기관만 대환 가능
            if is_business_product and is_refinance:
                # 대환할 근저당권이 business_product_names에 있는지 확인
                business_product_names = self._get_business_product_names()
                can_refinance = False
                refinance_institutions = []
                
                for mortgage in mortgages:
                    if mortgage.get("is_refinance", False):
                        institution = mortgage.get("institution", "")
                        institution_clean = institution.replace(" ", "")
                        found_in_list = False
                        for product_name in business_product_names:
                            product_name_clean = product_name.replace(" ", "")
                            if product_name_clean in institution_clean:
                                can_refinance = True
                                refinance_institutions.append(institution)
                                found_in_list = True
                                break
                        
                        # 리스트에 없지만 '사업자금' 문자열이 있으면 대환 가능
                        if not found_in_list and "사업자금" in institution:
                            can_refinance = True
                            refinance_institutions.append(institution)
                            print(f"DEBUG: BaseCalculator.calculate - OK저축은행 사업자 상품: '{institution}'에 '사업자금' 포함되어 대환 가능")
                
                if not can_refinance:
                    print(f"DEBUG: BaseCalculator.calculate - OK 저축은행 사업자 상품: 대환 요청된 기관이 사업자 상품이 아님")
                    # 대환 요청된 기관 목록 추출
                    requested_institutions = []
                    for mortgage in mortgages:
                        if mortgage.get("is_refinance", False):
                            requested_institutions.append(mortgage.get("institution", ""))
                    
                    institutions_str = ", ".join(requested_institutions) if requested_institutions else "요청된 기관"
                    return {
                        "bank_name": self.bank_name,
                        "results": [],
                        "conditions": self.config.get("conditions", []),
                        "errors": [
                            f"사업자 상품은 사업자금 기관만 대환 가능합니다",
                            f"대환 요청된 기관({institutions_str})이 사업자 상품 대환 가능 기관 목록에 없습니다"
                        ],
                        "min_amount": self.config.get("min_amount", 3000)
                    }
        
        # 사업자/가계 상품 정보를 인스턴스 변수로 저장 (get_interest_rate에서 사용)
        self._is_business_product = is_business_product
        self._is_household_product = is_household_product
        self._is_subordinate = len(other_mortgages) > 0  # 후순위 여부
        self._current_property_data = property_data
        # 창업사업자 vs 일반사업자 구분 (애큐온캐피탈 등)
        self._is_startup_business = self._check_is_startup_business(property_data)
        # 애큐온캐피탈 등: 프리랜서만 적혀 있으면 창업 키워드에 안 걸려 일반사업자로 나가는데, 프리랜서는 일반사업자 한도 부적용
        if is_business_product and not self._is_startup_business:
            occ_ex_msg = self._excluded_business_occupation_message(property_data)
            if occ_ex_msg:
                print(f"DEBUG: BaseCalculator.calculate - 사업자금 직업 제외: {occ_ex_msg}")
                return {
                    "bank_name": self.bank_name,
                    "results": [],
                    "conditions": self.config.get("conditions", []),
                    "errors": [occ_ex_msg],
                    "min_amount": self.config.get("min_amount", 3000),
                }
        
        # 후순위/선순위에 따른 최대 LTV 재조정 (키움저축-리테일 등)
        # 애큐온저축은행: max_ltv_by_priority_grade_region을 사용한 경우 재조정 불필요
        max_ltv_by_priority = self.config.get("max_ltv_by_priority_grade_region", {})
        if not max_ltv_by_priority:
            # max_ltv_by_priority_grade_region 설정이 없는 경우에만 재조정
            original_max_ltv = max_ltv  # 기존 값 저장 (디버그용)
            if self._is_subordinate:
                # 후순위인 경우: max_ltv_subordinate 확인
                max_ltv_subordinate = self.config.get("max_ltv_subordinate")
                if max_ltv_subordinate is not None:
                    # 후순위인 경우: max_ltv_subordinate를 우선 적용
                    # 급지 제한이 0이면 취급 불가 (예: 9급지), 그 외에는 max_ltv_subordinate 사용
                    if max_ltv is not None and max_ltv == 0:
                        # 급지 제한이 0이면 취급 불가
                        pass  # max_ltv는 0으로 유지
                    else:
                        # 급지 제한이 있거나 없거나, 후순위일 때는 max_ltv_subordinate 사용
                        max_ltv = max_ltv_subordinate
                    print(f"DEBUG: BaseCalculator.calculate - 후순위 대출, max_ltv_subordinate 적용: {max_ltv_subordinate}%, 기존 max_ltv(급지별): {original_max_ltv}%, 최종 max_ltv: {max_ltv}%")
            else:
                # 선순위인 경우: max_ltv_primary 확인
                max_ltv_primary = self.config.get("max_ltv_primary")
                if max_ltv_primary is not None:
                    # 선순위인 경우: max_ltv_primary와 급지별 제한 중 작은 값 사용
                    if max_ltv is not None:
                        max_ltv = min(max_ltv, max_ltv_primary)
                    else:
                        max_ltv = max_ltv_primary
                    print(f"DEBUG: BaseCalculator.calculate - 선순위 대출, max_ltv_primary 적용: {max_ltv_primary}%, 기존 max_ltv(급지별): {original_max_ltv}%, 최종 max_ltv: {max_ltv}%")
        
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
        
        # OK저축은행: 오피스텔인 경우 선순위만 산출 (세입자 1순위 있어도 2순위 불가)
        is_ok_bank = self.bank_name == "OK저축은행" or "OK저축은행" in self.bank_name or "오케이저축은행" in self.bank_name
        if is_ok_bank and self._is_subordinate:
            property_type = property_data.get("property_type", "")
            if property_type and "오피스텔" in property_type:
                print(f"DEBUG: BaseCalculator.calculate - OK 저축은행, 오피스텔인 경우 선순위만 산출 가능 (후순위 불가)")
                return {
                    "bank_name": self.bank_name,
                    "results": [],
                    "conditions": self.config.get("conditions", []),
                    "errors": ["오피스텔인 경우 선순위만 산출 가능 (세입자 1순위 시 2순위 불가)"],
                    "min_amount": self.config.get("min_amount", 3000)
                }
        
        # 세입자 후순위 토글/급지 제한
        # - tenant_subordinate_allowed=false: 세입자 있는 후순위는 전면 취급 불가
        # - max_subordinate_grade: 세입자 후순위 허용 시 급지 제한
        has_tenant = any(m.get("is_tenant") for m in other_mortgages)
        tenant_subordinate_allowed = self.config.get("tenant_subordinate_allowed")
        if tenant_subordinate_allowed is False and has_tenant and self._is_subordinate:
            print("DEBUG: BaseCalculator.calculate - 세입자 후순위 취급 불가 (tenant_subordinate_allowed=false)")
            return {
                "bank_name": self.bank_name,
                "results": [],
                "conditions": self.config.get("conditions", []),
                "errors": ["세입자 있는 후순위 취급 불가"],
                "min_amount": self.config.get("min_amount", 3000)
            }

        # max_subordinate_grade=0: 세입자 후순위 취급 불가 (JB하이론 등)
        max_subordinate_grade = self.config.get("max_subordinate_grade")
        if max_subordinate_grade is not None and has_tenant and self._is_subordinate:
            if max_subordinate_grade == 0:
                print(f"DEBUG: BaseCalculator.calculate - 세입자 후순위 취급 불가 (max_subordinate_grade=0)")
                return {
                    "bank_name": self.bank_name,
                    "results": [],
                    "conditions": self.config.get("conditions", []),
                    "errors": ["세입자 후순위 취급 불가"],
                    "min_amount": self.config.get("min_amount", 3000)
                }
            if grade is not None:
                try:
                    grade_int = int(grade)
                except (ValueError, TypeError):
                    grade_int = None
                if grade_int is not None and grade_int > max_subordinate_grade:
                    print(f"DEBUG: BaseCalculator.calculate - 세입자 후순위 대출, 급지 {grade_int} > max_subordinate_grade {max_subordinate_grade}, 취급 불가")
                    return {
                        "bank_name": self.bank_name,
                        "results": [],
                        "conditions": self.config.get("conditions", []),
                        "errors": [f"세입자 후순위는 1~{max_subordinate_grade}급지까지 가능합니다 (현재: {grade_int}급지)"],
                        "min_amount": self.config.get("min_amount", 3000)
                    }
        
        # 신용점수/등급 확인
        credit_score = property_data.get("credit_score")
        credit_grade = self.credit_score_to_grade(credit_score)
        
        # MG캐피탈: 내부 등급 파싱 (등급 우선)
        is_mg_capital = self.bank_name == "MG캐피탈" or "MG캐피탈" in self.bank_name or "엠지케피탈" in self.bank_name
        if is_mg_capital:
            mg_internal_grade = self._parse_mg_internal_grade(property_data)
            if mg_internal_grade is not None:
                credit_grade = mg_internal_grade
                print(f"DEBUG: BaseCalculator.calculate - MG캐피탈 내부 등급 적용: {credit_grade}등급")
        
        # 최대 신용등급 (애큐온캐피탈·data/loan 등 bank_name별 max_credit_grade)
        max_credit_grade_cfg = self.config.get("max_credit_grade")
        if max_credit_grade_cfg is not None and credit_grade is not None:
            try:
                if int(credit_grade) > int(max_credit_grade_cfg):
                    print(f"DEBUG: BaseCalculator.calculate - 신용등급 {credit_grade} > max_credit_grade {max_credit_grade_cfg}")
                    return {
                        "bank_name": self.bank_name,
                        "results": [],
                        "conditions": self.config.get("conditions", []),
                        "errors": [f"신용등급 {credit_grade}등급은 취급 불가입니다 (최대 {max_credit_grade_cfg}등급까지)"],
                        "min_amount": self.config.get("min_amount", 3000)
                    }
            except (TypeError, ValueError):
                pass
        
        # 택시 관련 한도 제한 확인
        taxi_limit_config = self.config.get("taxi_limit", {})
        max_amount_limit = None
        taxi_limit_applied_flag = False  # 택시 한도 제한이 실제로 적용되었는지 플래그
        
        # 일반 상품 최대 한도 제한 (config에서 읽기)
        # 창업/일반사업자 분리 한도 키가 있으면 우선 적용 (애큐온캐피탈 등)
        config_max_amount_limit = self.config.get("max_amount_limit")
        startup_max_amount_limit = self.config.get("startup_max_amount_limit")
        regular_max_amount_limit = self.config.get("regular_max_amount_limit")
        if getattr(self, "_is_startup_business", False) and startup_max_amount_limit is not None:
            config_max_amount_limit = startup_max_amount_limit
            print(f"DEBUG: BaseCalculator.calculate - 창업사업자 최대 한도 제한 적용: {config_max_amount_limit}만원")
        elif (not getattr(self, "_is_startup_business", False)) and regular_max_amount_limit is not None:
            config_max_amount_limit = regular_max_amount_limit
            print(f"DEBUG: BaseCalculator.calculate - 일반사업자 최대 한도 제한 적용: {config_max_amount_limit}만원")
        max_amount_limit_by_grade = self.config.get("max_amount_limit_by_grade", {})
        if max_amount_limit_by_grade and grade is not None:
            grade_str = str(grade)
            if grade_str in max_amount_limit_by_grade:
                max_amount_limit = max_amount_limit_by_grade[grade_str]
                print(f"DEBUG: BaseCalculator.calculate - 급지별 최대 한도 제한 (급지 {grade}): {max_amount_limit}만원")
        elif config_max_amount_limit is not None:
            max_amount_limit = config_max_amount_limit
            print(f"DEBUG: BaseCalculator.calculate - config에서 최대 한도 제한: {max_amount_limit}만원")
        
        if taxi_limit_config.get("enabled", False):
            if special_notes:
                keywords = taxi_limit_config.get("keywords", [])
                for keyword in keywords:
                    if keyword in special_notes:
                        taxi_limit = taxi_limit_config.get("max_amount", 10000)  # 기본값 1억
                        # 기존 한도 제한이 없거나 더 작은 경우에만 적용
                        if max_amount_limit is None or max_amount_limit > taxi_limit:
                            max_amount_limit = taxi_limit
                        taxi_limit_applied_flag = True  # 택시 한도 제한 적용 플래그 설정
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
        
        # 요청사항 「지분조건」+ config fractional_share_request_enabled: 최대 LTV 50% (급지·후순위·OK가계 등 반영 후)
        if self._fractional_share_ltv_cap_applies(property_data):
            if max_ltv is not None:
                max_ltv = min(int(max_ltv), 50)
            self._fractional_share_min_floor = 1000
            if self._gm_ltv_steps_override:
                self._gm_ltv_steps_override = [s for s in self._gm_ltv_steps_override if s <= 50]
                if not self._gm_ltv_steps_override:
                    self._gm_ltv_steps_override = [50]
            log_print(
                f"DEBUG: BaseCalculator.calculate - 지분조건(LTV cap) → 최대 LTV 50%, min진행 1000만원, "
                f"max_ltv={max_ltv}%, gm_steps={self._gm_ltv_steps_override}"
            )
        
        # 선순위일 때 max_amount_limit_primary 적용 (디에스론: 선순위 5억, 후순위 3억)
        max_amount_limit_primary = self.config.get("max_amount_limit_primary")
        if max_amount_limit_primary is not None and not self._is_subordinate:
            max_amount_limit = max_amount_limit_primary
            print(f"DEBUG: BaseCalculator.calculate - 선순위, max_amount_limit_primary 적용: {max_amount_limit}만원")
        
        # min_amount_by_grade: 급지별 최소진행금액 (디에스론: 4~5급지 3천만원)
        effective_min_amount = self.config.get("min_amount")
        min_amount_by_grade = self.config.get("min_amount_by_grade", {})
        if min_amount_by_grade and grade is not None:
            grade_str = str(grade)
            if grade_str in min_amount_by_grade:
                effective_min_amount = min_amount_by_grade[grade_str]
                print(f"DEBUG: BaseCalculator.calculate - 급지 {grade} 최소진행금액: {effective_min_amount}만원")
        
        # 요청사항 「지분조건」: 가용 1000만 미만이면 한도 미산출 (기존 min_amount보다 큰 쪽 적용)
        if getattr(self, "_fractional_share_min_floor", None) is not None:
            fm = self._fractional_share_min_floor
            if effective_min_amount is None:
                effective_min_amount = fm
            else:
                effective_min_amount = max(effective_min_amount, fm)
            print(f"DEBUG: BaseCalculator.calculate - 지분조건 요청 → 최소진행금액 하한 {fm}만원 (큰 값 적용): {effective_min_amount}만원")
        
        # JB하이론 / DSFNC 하이론: 대환 원금이 한도 초과 시 한도 미산출 (결과 전체 없음)
        is_jb = "JB" in self.bank_name or "제이비" in self.bank_name
        max_amount_limit_applies_to_total = self.config.get("max_amount_limit_applies_to_total", False)
        if is_refinance and max_amount_limit is not None and refinance_principal > max_amount_limit:
            if is_jb:
                print(f"DEBUG: BaseCalculator.calculate - JB하이론: 대환 원금 {refinance_principal}만원 > {max_amount_limit}만원, 한도 미산출")
            elif max_amount_limit_applies_to_total:
                print(f"DEBUG: BaseCalculator.calculate - 한도 총액 적용 상품: 대환 원금 {refinance_principal}만원 > {max_amount_limit}만원, 한도 미산출")
            if is_jb or max_amount_limit_applies_to_total:
                return None
        
        # 필요자금이 있으면 LTV별 계산을 건너뛰고 필요자금 기준으로 역산 계산
        required_amount = property_data.get("required_amount")
        results = []
        # 필요자금 기준 계산이 불가능할 때 일반 LTV 계산으로 fallback하기 위한 플래그
        fallback_to_ltv_steps = False
        
        # 택시 한도 제한이 적용되면 1억을 받기 위해 필요한 LTV를 역산
        # 택시 한도 제한이 실제로 적용된 경우에만 실행 (택시 키워드가 특이사항에 있을 때만)
        if taxi_limit_applied_flag and max_amount_limit is not None and required_amount is None:
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
                # 후순위/선순위 구분이 있는 경우 처리 (신용등급별 LTV steps 사용)
                is_subordinate = getattr(self, '_is_subordinate', False)
                ltv_steps = self._get_ltv_steps_by_grade(is_subordinate, credit_grade)
                
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
                    "type": "대환" if is_refinance else ("선순위" if not self._is_subordinate else "후순위"),
                    "available_amount": rounded_amount,
                    "total_amount": rounded_amount,
                    "is_refinance": is_refinance,
                    "credit_grade": rate_info.get("credit_grade"),
                    "below_standard_ltv": is_below_standard,
                    "taxi_limit_applied": True,  # 택시 한도 제한 적용 플래그
                    "refinance_institutions": (refinance_institutions if is_household_for_ok else all_refinance_institutions) if is_refinance else None  # 대환 시 대환하는 금융사 이름 (헤더 표시용)
                }
                
                results = [result]  # 하나의 결과만 반환
                print(f"DEBUG: BaseCalculator.calculate - 택시 한도 제한 결과 생성: LTV {calculated_ltv:.2f}%, amount {max_amount_limit}만원")
        
        # 필요자금 기준 계산 시도 (가능하면 필요자금 기준, 불가능하면 일반 LTV 계산으로 fallback)
        if required_amount is not None and not fallback_to_ltv_steps:
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
            
            # 필요자금 역산 기준
            # - 대환: 총 대출 목표액(required_amount)을 대환 원금 포함으로 해석, 채권최고액 기준(기존 로직 유지)
            # - 비대환: 후순위 표기와 동일 기준을 맞추기 위해
            #          MG/OK/애큐온은 원금 기준으로 역산 (필금과 후순위 표기 일치)
            #          그 외 금융사는 기존 채권최고액 기준 유지
            is_ok_bank_name = self.bank_name == "OK저축은행" or "OK저축은행" in self.bank_name or "오케이저축은행" in self.bank_name
            is_acuon_bank_name = self.bank_name == "애큐온저축은행" or "애큐온" in self.bank_name
            is_mg_bank_name = self.bank_name == "MG캐피탈" or "MG캐피탈" in self.bank_name or "엠지케피탈" in self.bank_name
            use_principal_based_required = (not is_refinance) and (is_ok_bank_name or is_acuon_bank_name or is_mg_bank_name)

            if is_refinance:
                effective_additional = max(0.0, required_amount - refinance_principal)
                required_component_amount = effective_additional * 1.2
                required_basis = "채권최고액기준(대환)"
            else:
                effective_additional = required_amount
                if use_principal_based_required:
                    required_component_amount = required_amount
                    required_basis = "원금기준(후순위표기동일)"
                else:
                    required_component_amount = required_amount * 1.2
                    required_basis = "채권최고액기준"

            # LTV 역산
            required_total = required_component_amount + mortgage_max_amount
            calculated_ltv = (required_total / kb_price) * 100
            
            print(f"DEBUG: BaseCalculator.calculate - basis={required_basis}, mortgage_max_amount={mortgage_max_amount}만원, effective_additional={effective_additional}만원, required_component_amount={required_component_amount}만원, required_total={required_total}만원, calculated_ltv={calculated_ltv:.2f}%")
            
            # 계산된 LTV가 max_ltv를 초과하면 불가능 -> 일반 LTV별 계산으로 fallback
            if calculated_ltv > max_ltv:
                print(f"DEBUG: BaseCalculator.calculate - calculated_ltv {calculated_ltv:.2f}% > max_ltv {max_ltv}%, falling back to LTV steps calculation")  # 추가
                fallback_to_ltv_steps = True
                results = []  # 필요자금 기준 결과는 없음, 일반 LTV 계산으로 넘어감
            else:
                # 계산된 정확한 LTV 사용 (ltv_steps에 없어도 됨)
                # 금리 조회를 위해 가장 가까운 ltv_steps 값 찾기
                # 후순위/선순위 구분이 있는 경우 처리 (신용등급별 LTV steps 사용)
                is_subordinate = getattr(self, '_is_subordinate', False)
                ltv_steps = self._get_ltv_steps_by_grade(is_subordinate, credit_grade)
                
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
                # 대환 케이스: effective_additional(추가 가용분)을 기준으로 한도 제한 적용
                # 비대환 케이스: required_amount 그대로 사용
                final_amount = effective_additional
                taxi_limit_applied = False
                if max_amount_limit is not None and final_amount > max_amount_limit:
                    final_amount = max_amount_limit
                    taxi_limit_applied = True
                    print(f"DEBUG: BaseCalculator.calculate - 택시 한도 제한 적용: {effective_additional}만원 -> {final_amount}만원")

                # 대환인 경우 total_amount와 available_amount 구분
                if is_refinance:
                    # 총 대출금액 = 대환 원금 + 추가 가용
                    total_amount = refinance_principal + final_amount
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
                    "type": "대환" if is_refinance else ("선순위" if not self._is_subordinate else "후순위"),
                    "available_amount": rounded_amount,
                    "total_amount": rounded_total_amount,
                    "is_refinance": is_refinance,
                    "credit_grade": rate_info.get("credit_grade"),
                    "below_standard_ltv": is_below_standard,  # 기준 LTV 이하 지역 여부
                    "taxi_limit_applied": taxi_limit_applied,  # 택시 한도 제한 적용 플래그
                    "fixed_rate_comment": rate_info.get("fixed_rate_comment"),  # 고정금리 코멘트
                    "refinance_institutions": (refinance_institutions if is_household_for_ok else all_refinance_institutions) if is_refinance else None  # 대환 시 대환하는 금융사 이름 (헤더 표시용)
                }
                
                results = [result]  # 하나의 결과만 반환
                print(f"DEBUG: BaseCalculator.calculate - created result with LTV {calculated_ltv:.2f}% and amount {final_amount}만원")  # 추가
        
        # 필요자금 기준 계산이 불가능하거나 필요자금이 없으면 일반 LTV별 계산
        if required_amount is None or fallback_to_ltv_steps:
            # fallback인 경우 results 초기화 (필요자금 기준 결과는 무시)
            if fallback_to_ltv_steps:
                results = []
            # max_limit_only: 최대 한도만 산출 (DSFNC, 퓨처하우스 제외 data/loan 상품)
            if self.config.get("max_limit_only"):
                ltv_steps = [int(max_ltv)] if max_ltv is not None and max_ltv > 0 else []
                print(f"DEBUG: BaseCalculator.calculate - max_limit_only: ltv_steps={ltv_steps}")
            # 필요자금이 없고 택시 한도 제한도 없으면 기존대로 LTV별 한도 계산
            # 가계자금인 경우 LTV 70%만 계산
            elif is_household_for_ok:
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
                    # 후순위/선순위 구분이 있는 경우 처리 (키움저축-리테일 등)
                    # 신용등급별 LTV steps 사용
                    is_subordinate = getattr(self, '_is_subordinate', False)
                    ltv_steps = self._get_ltv_steps_by_grade(is_subordinate, credit_grade)
            
            # max_ltv 이하로 필터링 (급지별 최대 LTV 반영)
            if max_ltv is not None and max_ltv > 0:
                # max_ltv 이하만 필터링 (85%는 83%를 초과하므로 제거)
                ltv_steps = [ltv for ltv in ltv_steps if ltv <= max_ltv]
                # max_ltv가 ltv_steps에 없으면 추가 (MG캐피탈 2급지 83% 같은 경우)
                if max_ltv not in ltv_steps:
                    ltv_steps.append(int(max_ltv))
                    ltv_steps = sorted(ltv_steps, reverse=True)
                    print(f"DEBUG: BaseCalculator.calculate - max_ltv {max_ltv}% 이하로 필터링 후 추가: {ltv_steps}")
                else:
                    print(f"DEBUG: BaseCalculator.calculate - max_ltv {max_ltv}% 이하로 필터링: {ltv_steps}")
            
            # ltv_steps가 비어있으면 에러
            if not ltv_steps:
                print(f"DEBUG: BaseCalculator.calculate - ltv_steps가 비어있음, max_ltv: {max_ltv}")
                return None
            
            print(f"DEBUG: BaseCalculator.calculate - max_ltv: {max_ltv}, ltv_steps: {ltv_steps}")  # 추가
            
            # 애큐온캐피탈: 신용 X일 때 금리 범위(1~7등급 min~max)로 산출
            max_ltv_by_region_credit_grade = self.config.get("max_ltv_by_region_credit_grade", {})
            region_grade_str = str(grade) if grade is not None else None
            rates_by_group = self.config.get("interest_rates_by_region_group_priority_business", {})
            grade_to_group = self.config.get("region_grade_to_group", {})
            is_acuon_capital_no_credit = (
                credit_grade is None
                and max_ltv_by_region_credit_grade
                and rates_by_group
                and region_grade_str
                and region_grade_str in max_ltv_by_region_credit_grade
                and not region_grade_str.startswith("_")
                and region_grade_str != "9"
                and grade_to_group.get(region_grade_str)
            )
            if is_acuon_capital_no_credit:
                max_ltv_map = max_ltv_by_region_credit_grade.get(region_grade_str, {})
                group = grade_to_group.get(region_grade_str)
                is_subordinate = getattr(self, '_is_subordinate', False)
                priority_key = "subordinate" if is_subordinate else "primary"
                bands = self.config.get("ltv_bands_subordinate" if is_subordinate else "ltv_bands_primary", [])
                allow_negative_available = has_bucuk_jageum_request(property_data)
                min_amount_config = effective_min_amount
                for ltv in ltv_steps:
                    if max_ltv is not None and ltv > max_ltv:
                        continue
                    any_grade_allows = False
                    for g in range(1, 8):
                        g_max = max_ltv_map.get(str(g), 0) if isinstance(max_ltv_map, dict) else 0
                        if g_max is not None and g_max >= ltv:
                            any_grade_allows = True
                            break
                    if not any_grade_allows:
                        continue
                    ltv_float = float(ltv)
                    ltv_key = None
                    for band in sorted(bands):
                        if ltv_float <= band:
                            ltv_key = str(band)
                            break
                    if not ltv_key:
                        continue
                    amount_info = self.calculate_available_amount(
                        kb_price, ltv, total_mortgage, is_refinance, refinance_principal
                    )
                    amount_for_min_rounded = self.round_down_to_hundred_thousand(
                        amount_info["total_amount"] if is_refinance else amount_info.get("available_limit", amount_info.get("available_amount", 0))
                    )
                    limit_not_calculated = (
                        (amount_info["available_amount"] <= 0 and not allow_negative_available)
                        or (min_amount_config is not None and amount_for_min_rounded < min_amount_config)
                    )
                    final_amount = self.round_down_to_hundred_thousand(amount_info["available_amount"]) if not limit_not_calculated else 0
                    final_total_amount = self.round_down_to_hundred_thousand(amount_info["total_amount"]) if not limit_not_calculated else 0
                    # 신용점수 없음(금리범위) 분기에서도 최대 한도 제한 동일 적용
                    if max_amount_limit is not None and not limit_not_calculated:
                        if max_amount_limit_applies_to_total and is_refinance:
                            final_total_amount = self.round_down_to_hundred_thousand(min(final_total_amount, max_amount_limit))
                            final_amount = self.round_down_to_hundred_thousand(max(0, final_total_amount - refinance_principal))
                            if final_amount <= 0 and not allow_negative_available:
                                continue
                        elif max_amount_limit_applies_to_total and not is_refinance:
                            final_amount = self.round_down_to_hundred_thousand(min(final_amount, max_amount_limit))
                            final_total_amount = final_amount
                        elif final_amount > max_amount_limit:
                            final_amount = self.round_down_to_hundred_thousand(max_amount_limit)
                            if not is_refinance:
                                final_total_amount = final_amount
                    # 해당 조건(창업/일반사업자)에 맞는 한도만 산출
                    is_startup = getattr(self, '_is_startup_business', False)
                    business_key = "startup" if is_startup else "regular"
                    biz_type = "startup" if is_startup else "regular"
                    group_rates = rates_by_group.get(group, {}).get(priority_key, {}).get(business_key, {})
                    if ltv_key in group_rates:
                        grade_rates = group_rates[ltv_key]
                        valid_rates = [float(grade_rates[str(g)]) for g in range(1, 8) if str(g) in grade_rates and grade_rates[str(g)] is not None]
                        if not valid_rates:
                            continue
                        rate_min, rate_max = min(valid_rates), max(valid_rates)
                        result = {
                            "ltv": ltv,
                            "amount": final_amount,
                            "interest_rate": None,
                            "interest_rate_range": (round(rate_min, 2), round(rate_max, 2)),
                            "type": "대환" if is_refinance else ("선순위" if not self._is_subordinate else "후순위"),
                            "available_amount": final_amount,
                            "total_amount": final_total_amount,
                            "is_refinance": is_refinance,
                            "credit_grade": None,
                            "credit_grade_sort": 99,
                            "below_standard_ltv": is_below_standard,
                            "fixed_rate_comment": None,
                            "refinance_institutions": (refinance_institutions if is_household_for_ok else all_refinance_institutions) if is_refinance else None,
                            "limit_not_calculated": limit_not_calculated,
                            "business_type": biz_type,
                        }
                        results.append(result)
                if results and self.config.get("sort_results_by_grade"):
                    results.sort(key=lambda x: (x.get("credit_grade_sort", 99), -(x.get("ltv", 0))))
                print(f"DEBUG: BaseCalculator.calculate - 애큐온캐피탈 신용 X 금리범위 산출: {len(results)}건")
            elif (
                max_ltv_by_region_credit_grade and credit_grade is None and region_grade_str
                and region_grade_str in max_ltv_by_region_credit_grade
                and not region_grade_str.startswith("_")
                and not rates_by_group
            ):
                # JB우리캐피탈: 신용 X일 때 등급별(1~7) LTV 산출, 동일 금리 등급 합산 표시
                is_jb_per_grade = True
                max_ltv_map = max_ltv_by_region_credit_grade.get(region_grade_str, {})
                primary_rates = self.config.get("primary_interest_rates_by_ltv", {})
                allow_negative_available = has_bucuk_jageum_request(property_data)
                min_amount_config = effective_min_amount
                for ltv in ltv_steps:
                    if max_ltv is not None and ltv > max_ltv:
                        continue
                    amount_info = self.calculate_available_amount(
                        kb_price, ltv, total_mortgage, is_refinance, refinance_principal
                    )
                    amount_for_min_check = amount_info["total_amount"] if is_refinance else amount_info.get("available_limit", amount_info.get("available_amount", 0))
                    amount_for_min_rounded = self.round_down_to_hundred_thousand(amount_for_min_check)
                    limit_not_calculated = (
                        (amount_info["available_amount"] <= 0 and not allow_negative_available)
                        or (min_amount_config is not None and amount_for_min_rounded < min_amount_config)
                    )
                    final_amount = self.round_down_to_hundred_thousand(amount_info["available_amount"]) if not limit_not_calculated else 0
                    final_total_amount = self.round_down_to_hundred_thousand(amount_info["total_amount"]) if not limit_not_calculated else 0
                    # JB 최대 한도 제한 (max_amount_limit, 대환/후순위 총액 1억, 신용등급 무관)
                    if max_amount_limit is not None:
                        if is_refinance:
                            final_total_amount = self.round_down_to_hundred_thousand(min(final_total_amount, max_amount_limit))
                            final_amount = self.round_down_to_hundred_thousand(max(0, final_total_amount - refinance_principal))
                            if final_amount <= 0 and not allow_negative_available:
                                continue
                            print(f"DEBUG: BaseCalculator.calculate - JB하이론 최대 한도 제한 적용: total {amount_info['total_amount']} -> {final_total_amount}만원, 가용 {final_amount}만원")
                        elif final_amount > max_amount_limit:
                            final_amount = self.round_down_to_hundred_thousand(max_amount_limit)
                            final_total_amount = final_amount
                            print(f"DEBUG: BaseCalculator.calculate - JB하이론 최대 한도 제한 적용(후순위): {amount_info['available_amount']}만원 -> {final_amount}만원")
                    ltv_rates = primary_rates.get(str(ltv), primary_rates.get(str(int(ltv)), {}))
                    grade_rate_list = []
                    for g in range(1, 8):
                        g_str = str(g)
                        g_max = max_ltv_map.get(g_str, 0) if isinstance(max_ltv_map, dict) else 0
                        if g_max is not None and g_max >= ltv:
                            rate = ltv_rates.get(g_str) if isinstance(ltv_rates, dict) else None
                            if rate is not None:
                                grade_rate_list.append((g, rate))
                    if not grade_rate_list:
                        continue
                    groups = []
                    i = 0
                    while i < len(grade_rate_list):
                        start_grade, rate = grade_rate_list[i]
                        j = i + 1
                        while j < len(grade_rate_list) and grade_rate_list[j][1] == rate and grade_rate_list[j][0] == grade_rate_list[j - 1][0] + 1:
                            j += 1
                        end_grade = grade_rate_list[j - 1][0]
                        credit_grade_str = f"{start_grade}~{end_grade}" if start_grade != end_grade else str(start_grade)
                        groups.append((credit_grade_str, start_grade, rate))
                        i = j
                    for credit_grade_str, sort_grade, rate in groups:
                        result = {
                            "ltv": ltv,
                            "amount": final_amount,
                            "interest_rate": rate,
                            "interest_rate_range": None,
                            "type": "대환" if is_refinance else ("선순위" if not self._is_subordinate else "후순위"),
                            "available_amount": final_amount,
                            "total_amount": final_total_amount,
                            "is_refinance": is_refinance,
                            "credit_grade": credit_grade_str,
                            "credit_grade_sort": sort_grade,
                            "below_standard_ltv": is_below_standard,
                            "fixed_rate_comment": None,
                            "refinance_institutions": (refinance_institutions if is_household_for_ok else all_refinance_institutions) if is_refinance else None,
                            "limit_not_calculated": limit_not_calculated,
                        }
                        results.append(result)
                # 등급별로 한도가 나온 경우, 해당 등급(구간 포함)의 한도 미산출 항목 제외
                # 예: 1~2등급에 한도 있으면 1~5·1~3 등 1,2를 포함하는 구간의 한도 미산출도 제외
                if results:
                    grades_with_limit: Set[int] = set()
                    for r in results:
                        if not r.get("limit_not_calculated", False) and r.get("credit_grade"):
                            grades_with_limit.update(_parse_grade_range(r["credit_grade"]))
                    if grades_with_limit:
                        results = [
                            r for r in results
                            if not (
                                r.get("limit_not_calculated", False)
                                and r.get("credit_grade")
                                and _grades_fully_covered(r["credit_grade"], grades_with_limit)
                            )
                        ]
                if results and self.config.get("sort_results_by_grade"):
                    results.sort(key=lambda x: (x.get("credit_grade_sort", 99), -(x.get("ltv", 0))))
            else:
                # 대환조건일 때는 0.1% 단위로 LTV 계산 (MG캐피탈 등)
                is_mg_capital = self.bank_name == "MG캐피탈" or "MG캐피탈" in self.bank_name or "엠지케피탈" in self.bank_name
                if is_refinance and is_mg_capital and max_ltv is not None:
                    # 대환조건: max_ltv부터 0.1%씩 감소시키며 한도가 나오는 최대 LTV 찾기
                    # 그리고 ltv_steps에 있는 LTV 단계들도 추가 산출
                    min_ltv_limit = min(ltv_steps) if ltv_steps else 60  # 최소 LTV 제한
                    calculated_max_ltv = None
                    calculated_ltvs = set()  # 이미 산출된 LTV 추적 (중복 방지)
                    
                    # 요청사항 또는 특이사항에 '부족자금'이 있는지 확인
                    allow_negative_available = has_bucuk_jageum_request(property_data)
                    
                    # 1단계: max_ltv부터 0.1%씩 감소시키며 한도가 나오는 최대 LTV 찾기
                    test_ltv = float(max_ltv)
                    while test_ltv >= min_ltv_limit:
                        # 소수점 1자리로 반올림
                        test_ltv_rounded = round(test_ltv, 1)
                        
                        # 가용 한도 계산
                        amount_info = self.calculate_available_amount(
                            kb_price, test_ltv_rounded, total_mortgage, is_refinance, refinance_principal
                        )
                        
                        # 가용 한도가 0보다 크면 (또는 부족자금 요청이 있으면) 해당 LTV 사용
                        if amount_info["available_amount"] > 0 or allow_negative_available:
                            calculated_max_ltv = test_ltv_rounded
                            print(f"DEBUG: BaseCalculator.calculate - MG캐피탈 대환: 최대 LTV {calculated_max_ltv}%에서 한도 발견, available_amount={amount_info['available_amount']}")
                            break
                        
                        # 0.1% 감소
                        test_ltv -= 0.1
                    
                    # 최대 LTV로 결과 생성
                    if calculated_max_ltv is not None:
                        amount_info = self.calculate_available_amount(
                            kb_price, calculated_max_ltv, total_mortgage, is_refinance, refinance_principal
                        )
                        
                        # 금리 조회
                        rate_info = self.get_interest_rate(credit_score, credit_grade, calculated_max_ltv, grade)
                        
                        # 가계 상품 한도 제한 적용
                        final_amount = amount_info["available_amount"]
                        if max_amount_limit is not None and final_amount > max_amount_limit:
                            final_amount = max_amount_limit
                            print(f"DEBUG: BaseCalculator.calculate - 가계 상품 한도 제한 적용: {amount_info['available_amount']}만원 -> {final_amount}만원")
                        
                        # 100만 단위로 절삭
                        final_amount = self.round_down_to_hundred_thousand(final_amount)
                        final_total_amount = self.round_down_to_hundred_thousand(amount_info["total_amount"])
                        
                        # 최소진행금액 체크: 대환 시 총 실행금액(대환+추가), 후순위 시 가한도 기준
                        min_amount = effective_min_amount
                        amount_for_min_check = amount_info["total_amount"] if is_refinance else amount_info.get("available_limit", amount_info.get("available_amount", 0))
                        amount_for_min_rounded = self.round_down_to_hundred_thousand(amount_for_min_check)
                        if min_amount is not None and amount_for_min_rounded < min_amount:
                            print(f"DEBUG: BaseCalculator.calculate - MG캐피탈 대환: 총실행금액 {amount_for_min_rounded}만원이 min_amount {min_amount}만원보다 작아서 제외")
                        else:
                            result = {
                                "ltv": calculated_max_ltv,
                                "amount": final_amount,
                                "interest_rate": rate_info.get("interest_rate"),
                                "interest_rate_range": rate_info.get("interest_rate_range"),
                                "type": "대환",
                                "available_amount": final_amount,
                                "total_amount": final_total_amount,
                                "is_refinance": True,
                                "credit_grade": rate_info.get("credit_grade"),
                                "below_standard_ltv": is_below_standard,
                                "fixed_rate_comment": rate_info.get("fixed_rate_comment"),
                                "refinance_institutions": refinance_institutions if is_household_for_ok else all_refinance_institutions
                            }
                            results.append(result)
                            calculated_ltvs.add(calculated_max_ltv)
                            print(f"DEBUG: BaseCalculator.calculate - MG캐피탈 대환: 최대 LTV {calculated_max_ltv}% 결과 추가")
                    
                    # 2단계: ltv_steps 순회하여 추가 산출 (이미 산출된 LTV 제외)
                    if ltv_steps:
                        for ltv in ltv_steps:
                            # 최대 LTV를 초과하면 스킵
                            if max_ltv is not None and ltv > max_ltv:
                                continue
                            
                            # 이미 산출된 LTV는 제외 (중복 방지)
                            if ltv in calculated_ltvs:
                                print(f"DEBUG: BaseCalculator.calculate - MG캐피탈 대환: LTV {ltv}%는 이미 산출되어 제외")
                                continue
                            
                            # 가용 한도 계산
                            amount_info = self.calculate_available_amount(
                                kb_price, ltv, total_mortgage, is_refinance, refinance_principal
                            )
                            
                            # 가용 한도가 마이너스일 경우 처리
                            if amount_info["available_amount"] <= 0:
                                if not allow_negative_available:
                                    print(f"DEBUG: BaseCalculator.calculate - MG캐피탈 대환: LTV {ltv}% - available_amount <= 0, skipping (부족자금 요청 없음)")
                                    continue
                                else:
                                    print(f"DEBUG: BaseCalculator.calculate - MG캐피탈 대환: LTV {ltv}% - available_amount <= 0, but allowing due to '부족자금' request")
                            
                            # 금리 조회
                            rate_info = self.get_interest_rate(credit_score, credit_grade, ltv, grade)
                            
                            # 가계 상품 한도 제한 적용
                            final_amount = amount_info["available_amount"]
                            if max_amount_limit is not None and final_amount > max_amount_limit:
                                final_amount = max_amount_limit
                                print(f"DEBUG: BaseCalculator.calculate - 가계 상품 한도 제한 적용: {amount_info['available_amount']}만원 -> {final_amount}만원")
                            
                            # 100만 단위로 절삭
                            final_amount = self.round_down_to_hundred_thousand(final_amount)
                            final_total_amount = self.round_down_to_hundred_thousand(amount_info["total_amount"])
                            
                            # 최소진행금액 체크: 대환 시 총 실행금액(대환+추가), 후순위 시 가한도 기준
                            min_amount = effective_min_amount
                            amount_for_min_check = amount_info["total_amount"] if is_refinance else amount_info.get("available_limit", amount_info.get("available_amount", 0))
                            amount_for_min_rounded = self.round_down_to_hundred_thousand(amount_for_min_check)
                            if min_amount is not None and amount_for_min_rounded < min_amount:
                                print(f"DEBUG: BaseCalculator.calculate - MG캐피탈 대환: LTV {ltv}% - 총실행금액 {amount_for_min_rounded}만원이 min_amount {min_amount}만원보다 작아서 제외")
                                continue
                            
                            result = {
                                "ltv": ltv,
                                "amount": final_amount,
                                "interest_rate": rate_info.get("interest_rate"),
                                "interest_rate_range": rate_info.get("interest_rate_range"),
                                "type": "대환",
                                "available_amount": final_amount,
                                "total_amount": final_total_amount,
                                "is_refinance": True,
                                "credit_grade": rate_info.get("credit_grade"),
                                "below_standard_ltv": is_below_standard,
                                "fixed_rate_comment": rate_info.get("fixed_rate_comment"),
                                "refinance_institutions": refinance_institutions if is_household_for_ok else all_refinance_institutions
                            }
                            results.append(result)
                            calculated_ltvs.add(ltv)
                            print(f"DEBUG: BaseCalculator.calculate - MG캐피탈 대환: LTV {ltv}% 결과 추가")
                    
                    # 3단계: 결과를 LTV 높은 순으로 정렬
                    if results:
                        results.sort(key=lambda x: x.get("ltv", 0), reverse=True)
                        print(f"DEBUG: BaseCalculator.calculate - MG캐피탈 대환: 결과 정렬 완료 (LTV 높은 순)")
                else:
                    # 기존 로직: ltv_steps 순회
                    for ltv in ltv_steps:
                        # 최대 LTV를 초과하면 스킵 (이미 필터링했지만 안전장치)
                        if max_ltv is not None and ltv > max_ltv:
                            print(f"DEBUG: LTV {ltv} > max_ltv {max_ltv}, skipping")  # 추가
                            continue
                        
                        # 가용 한도 계산
                        # OK저축은행, 애큐온저축은행, MG캐피탈인 경우 특별한 계산 방식 적용
                        is_acuon = self.bank_name == "애큐온저축은행" or "애큐온" in self.bank_name
                        is_mg_capital = self.bank_name == "MG캐피탈" or "MG캐피탈" in self.bank_name or "엠지케피탈" in self.bank_name
                        
                        if (is_ok_bank or is_acuon or is_mg_capital) and not is_refinance:
                            # 저축은행/캐피탈 후순위: 현재 LTV 한도에서 기존 근저당권이 차지하는 LTV 수준의 한도를 차감
                            # 기존 근저당권이 차지하는 LTV = total_mortgage / kb_price * 100
                            existing_ltv = (total_mortgage / kb_price) * 100 if kb_price > 0 else 0
                            # 기존 근저당권 LTV 수준의 한도 계산
                            existing_ltv_limit = kb_price * (existing_ltv / 100)
                            # 현재 LTV 한도에서 기존 근저당권 LTV 수준 한도를 차감
                            max_amount_principal = kb_price * (ltv / 100)
                            available_principal = max_amount_principal - existing_ltv_limit
                            amount_info = {
                                "total_amount": max(0, available_principal),
                                "available_amount": max(0, available_principal),
                                "available_limit": max(0, available_principal)  # 후순위는 가한도와 가용금액이 동일
                            }
                            bank_display_name = "OK저축은행" if is_ok_bank else ("애큐온저축은행" if is_acuon else "MG캐피탈")
                            print(f"DEBUG: BaseCalculator.calculate - {bank_display_name} 후순위 특별 계산: ltv={ltv}%, existing_ltv={existing_ltv:.2f}%, max_amount={max_amount_principal}, existing_limit={existing_ltv_limit}, available={available_principal}")
                        elif (is_ok_bank or is_acuon or is_mg_capital) and is_refinance:
                            # 저축은행/캐피탈 대환: 일반 대환 계산 방식 사용 (calculate_available_amount)
                            amount_info = self.calculate_available_amount(
                                kb_price, ltv, total_mortgage, is_refinance, refinance_principal
                            )
                            bank_display_name = "OK저축은행" if is_ok_bank else ("애큐온저축은행" if is_acuon else "MG캐피탈")
                            print(f"DEBUG: BaseCalculator.calculate - {bank_display_name} 대환 계산: ltv={ltv}%, amount_info={amount_info}")
                        else:
                            # 일반 계산 방식
                            amount_info = self.calculate_available_amount(
                                kb_price, ltv, total_mortgage, is_refinance, refinance_principal
                            )
                        
                        print(f"DEBUG: LTV {ltv} - amount_info: {amount_info}")  # 추가
                        
                        # 요청사항 또는 특이사항에 '부족자금'이 있는지 확인
                        allow_negative_available = has_bucuk_jageum_request(property_data)
                        
                        # 가용 한도가 마이너스일 경우 처리
                        # - '부족자금'이 있는 경우만: 마이너스여도 산출
                        # - 그 외: 가용 한도가 0 이하면 스킵 (대환이든 후순위든 상관없이)
                        if amount_info["available_amount"] <= 0:
                            if not allow_negative_available:
                                print(f"DEBUG: LTV {ltv} - available_amount <= 0, skipping (부족자금 요청 없음)")  # 추가
                                continue
                            else:
                                print(f"DEBUG: LTV {ltv} - available_amount <= 0, but allowing due to '부족자금' request")  # 추가
                        
                        # 금리 조회 (82% LTV의 경우 region_grade에 따라 다른 금리 적용)
                        # hide_credit_grade: 신용등급 무시하고 급지별 단일금리 (디에스론 3급지 80% 등)
                        credit_grade_for_rate = None if self.config.get("hide_credit_grade") else credit_grade
                        rates_by_group = self.config.get("interest_rates_by_region_group_priority_business", {})
                        rate_info = self.get_interest_rate(credit_score, credit_grade_for_rate, ltv, grade)
                        
                        # 한도 제한 적용: 총액 한도(대환금액 포함) vs 가용 한도
                        final_amount = amount_info["available_amount"]
                        final_total_amount = amount_info["total_amount"]
                        if max_amount_limit is not None:
                            if max_amount_limit_applies_to_total and is_refinance:
                                # 총액 한도: total_amount = min(계산값, 한도), available = total - 대환원금
                                final_total_amount = min(amount_info["total_amount"], max_amount_limit)
                                final_amount = final_total_amount - refinance_principal
                                if final_amount <= 0 and not allow_negative_available:
                                    print(f"DEBUG: BaseCalculator.calculate - 총액 한도 적용: LTV {ltv}% 가용 {final_amount}만원 <= 0, 스킵")
                                    continue
                                print(f"DEBUG: BaseCalculator.calculate - 총액 한도 적용: total {amount_info['total_amount']} -> {final_total_amount}만원, 가용 {final_amount}만원")
                            elif max_amount_limit_applies_to_total and not is_refinance:
                                # 후순위: 한도가 가용금액 상한 (하이론 3~4급지 3천만원 등)
                                final_amount = min(amount_info["available_amount"], max_amount_limit)
                                final_total_amount = final_amount
                                print(f"DEBUG: BaseCalculator.calculate - 총액 한도 적용(후순위): 가용 {amount_info['available_amount']} -> {final_amount}만원")
                            elif not max_amount_limit_applies_to_total and final_amount > max_amount_limit:
                                final_amount = max_amount_limit
                                print(f"DEBUG: BaseCalculator.calculate - 가계 상품 한도 제한 적용: {amount_info['available_amount']}만원 -> {final_amount}만원")
                        
                        # 100만 단위로 절삭
                        final_amount = self.round_down_to_hundred_thousand(final_amount)
                        final_total_amount = self.round_down_to_hundred_thousand(final_total_amount)
                        
                        # 최소진행금액 체크: 대환 시 총 실행금액(대환+추가), 후순위 시 가한도 기준
                        min_amount = effective_min_amount
                        if max_amount_limit_applies_to_total:
                            amount_for_min_check = final_total_amount
                        else:
                            amount_for_min_check = amount_info["total_amount"] if is_refinance else amount_info.get("available_limit", amount_info.get("available_amount", 0))
                        amount_for_min_rounded = self.round_down_to_hundred_thousand(amount_for_min_check)
                        if min_amount is not None and amount_for_min_rounded < min_amount:
                            print(f"DEBUG: LTV {ltv} - 총실행금액 {amount_for_min_rounded}만원이 min_amount {min_amount}만원보다 작아서 제외 (가용금액: {final_amount}만원)")
                            continue
                        
                        result = {
                            "ltv": ltv,
                            "amount": final_amount,
                            "interest_rate": rate_info.get("interest_rate"),
                            "interest_rate_range": rate_info.get("interest_rate_range"),
                            "type": "대환" if is_refinance else ("선순위" if not self._is_subordinate else "후순위"),
                            "available_amount": final_amount,
                            "total_amount": final_total_amount,
                            "is_refinance": is_refinance,
                            "credit_grade": rate_info.get("credit_grade"),
                            "below_standard_ltv": is_below_standard,
                            "fixed_rate_comment": rate_info.get("fixed_rate_comment"),
                            "refinance_institutions": (refinance_institutions if is_household_for_ok else all_refinance_institutions) if is_refinance else None
                        }
                        if rates_by_group:
                            result["business_type"] = "startup" if self._is_startup_business else "regular"
                        results.append(result)
        
        # 결과가 없으면 에러 메시지와 함께 반환 (가용 한도 부족 등)
        if not results:
            print(f"DEBUG: BaseCalculator.calculate - no results found for {self.bank_name}")
        elif self.config.get("sort_results_by_grade"):
            def _grade_sort_key(r):
                g = r.get("credit_grade_sort")
                if g is not None:
                    return g
                g = r.get("credit_grade")
                return g if isinstance(g, (int, float)) else 99
            results.sort(key=lambda x: (_grade_sort_key(x), -(x.get("ltv", 0))))
            print(f"DEBUG: BaseCalculator.calculate - {self.bank_name}: sort_results_by_grade 적용 (등급순, LTV 높은순)")
        if not results:
            # 최대 LTV로 계산했을 때 가용 한도 확인
            max_ltv_amount = kb_price * (max_ltv / 100)
            min_amount = effective_min_amount if effective_min_amount is not None else 3000

            # 신용등급별 LTV 제한이 있는 경우 메시지에 등급 정보 추가
            # max_ltv_by_grade는 급지(지역등급) 기준이므로 신용등급 문구 제외
            # max_ltv_by_region_credit_grade만 신용등급 x 급지 복합 기준
            _has_credit_grade_ltv = bool(self.config.get("max_ltv_by_region_credit_grade"))
            if credit_grade is not None and _has_credit_grade_ltv:
                _grade_note = f" / 신용 {credit_grade}등급 기준 최대 LTV {max_ltv:g}%"
            else:
                _grade_note = ""

            # 선순위 채권최고(대환 제외 분 = other_mortgages)가 담보한도를 넘는지. 대환 대상 원금은 여기서 제외(2단계에서 차감).
            if total_mortgage > max_ltv_amount:
                shortage = total_mortgage - max_ltv_amount
                existing_pct = (total_mortgage / kb_price * 100) if kb_price else 0.0
                print(f"DEBUG: BaseCalculator.calculate - 선순위 채권최고가 최대 LTV 한도 초과: {shortage:.0f}만원 초과")
                return {
                    "bank_name": self.bank_name,
                    "results": [],
                    "conditions": self.config.get("conditions", []),
                    "errors": [
                        f"기존 근저당권이 최대 LTV {max_ltv:g}% 한도 초과{_grade_note} "
                        f"(선순위 채권최고 약 {existing_pct:.2f}%, 담보한도 {max_ltv:g}% 대비 초과 {shortage:,.0f}만원)"
                    ],
                    "min_amount": min_amount
                }
            else:
                # 1차 잔여 한도(담보한도 − 선순위 채권최고). 대환 시 calculate_available_amount에서 대환 원금을 한 번 더 뺌.
                max_available = max_ltv_amount - total_mortgage
                max_available_rounded = self.round_down_to_hundred_thousand(max_available)
                if max_available_rounded > 0 and max_available_rounded < min_amount:
                    print(f"DEBUG: BaseCalculator.calculate - 최대 가용한도 {max_available_rounded}만원이 최소진행금액 {min_amount}만원보다 작음")
                    return {
                        "bank_name": self.bank_name,
                        "results": [],
                        "conditions": self.config.get("conditions", []),
                        "errors": [
                            f"최소진행금액 부족{_grade_note} "
                            f"(최대 LTV {max_ltv:g}% 적용 시 가용한도: {max_available_rounded:,.0f}만원, "
                            f"최소진행금액: {min_amount:,.0f}만원)"
                        ],
                        "min_amount": min_amount
                    }

            # 위 분기에서 사유를 못 담은 경우(가용 0·반올림, 금리 미산출 등): 한도 없음 이유를 errors로 반환 (MG캐피탈 등 동일)
            tm_check = total_mortgage
            max_avail_raw = max_ltv_amount - tm_check
            max_avail_rnd = self.round_down_to_hundred_thousand(max_avail_raw)
            existing_pct = (tm_check / kb_price * 100) if kb_price else 0.0
            loan_phase = "대환" if is_refinance else "후순위"
            if max_avail_rnd <= 0:
                fallback_err = (
                    f"{loan_phase} 가용 한도 없음 (선순위 채권최고 약 {existing_pct:.2f}%{_grade_note} / 담보 여력 없음)"
                )
            else:
                fallback_err = (
                    f"한도 미산출 ({loan_phase}, 최대 LTV {max_ltv:g}%{_grade_note} 기준 가용 약 {max_avail_rnd:,.0f}만원, 금리·조건 미충족 가능)"
                )
            print(f"DEBUG: BaseCalculator.calculate - no results for {self.bank_name}, fallback message: {fallback_err}")
            return {
                "bank_name": self.bank_name,
                "results": [],
                "conditions": self.config.get("conditions", []),
                "errors": [fallback_err],
                "min_amount": min_amount,
            }
        
        print(f"DEBUG: BaseCalculator.calculate - {self.bank_name} found {len(results)} results")  # 추가
        
        # MG캐피탈 프로모션 적용 시 은행명 변경
        final_bank_name = self.bank_name
        promotion_rejection_reason = None
        if getattr(self, '_promotion_applied', False):
            promotion_name = getattr(self, '_promotion_name', '프로모션 금리 적용')
            final_bank_name = f"{self.bank_name}({promotion_name})"
            print(f"DEBUG: BaseCalculator.calculate - 프로모션 적용, 은행명 변경: {final_bank_name}")
        else:
            # 1,2급지인데 프로모션 미적용인 경우 사유 포함
            promotion_rejection_reason = getattr(self, '_promotion_rejection_reason', None)
            if promotion_rejection_reason:
                print(f"DEBUG: BaseCalculator.calculate - 프로모션 미적용 사유: {promotion_rejection_reason}")
        
        # MG캐피탈 감정건(감정가·탁감가 동일 취급) 시 한도 밑에 가산금리 안내 문구 추가
        conditions = list(self.config.get("conditions", []))
        is_mg_capital_return = final_bank_name == "MG캐피탈" or "MG캐피탈" in final_bank_name
        if is_mg_capital_return and property_data:
            kb_price_raw_str = str(property_data.get("kb_price_raw") or "")
            if "탁감가" in kb_price_raw_str or "감정가" in kb_price_raw_str or "은행감정가" in kb_price_raw_str:
                conditions.append("※ 표시금리는 감정건(감정가·탁감가) 가산금리 1%p가 적용된 금리입니다")
        
        # 총액(대환/추가대출) N억 이상 시 안내 문구 추가 (amount_condition_threshold, amount_condition_message)
        amount_condition_threshold = self.config.get("amount_condition_threshold")
        amount_condition_message = self.config.get("amount_condition_message")
        if amount_condition_threshold is not None and amount_condition_message and results:
            for r in results:
                total = r.get("total_amount") or r.get("available_amount") or r.get("amount") or 0
                if total >= amount_condition_threshold:
                    conditions.append(amount_condition_message)
                    break
        
        # 적용 시세 타입 및 금액 (금융사별 시세 표시용)
        if lower_bound_applied:
            price_type_used = "하한"
        elif property_data and ("탁감가" in str(property_data.get("kb_price_raw") or "") or "감정가" in str(property_data.get("kb_price_raw") or "") or "은행감정가" in str(property_data.get("kb_price_raw") or "")):
            price_type_used = "탁감가"
        else:
            price_type_used = "일반"
        kb_price_used = kb_price  # 계산에 사용된 최종 시세
        
        out = {
            "bank_name": final_bank_name,
            "results": results,
            "conditions": conditions,
            "errors": [],
            "min_amount": effective_min_amount if effective_min_amount is not None else self.config.get("min_amount", 3000),
            "promotion_rejection_reason": promotion_rejection_reason,  # 프로모션 미적용 사유 (1,2급지만)
            "lower_bound_applied": lower_bound_applied,  # 하한가 적용 여부
            "kb_price_used": kb_price_used,  # 적용된 시세 금액 (만원)
            "price_type_used": price_type_used,  # 적용된 시세 타입: 일반/하한/탁감가
            "region_grade": grade,  # 급지 (show_region_grade 시 헤더에 N급지 표시)
            "hide_credit_grade": self.config.get("hide_credit_grade", False),
            "show_region_grade": self.config.get("show_region_grade", False),
            "hide_conditions": self.config.get("hide_conditions", False)
        }
        # 펀딩상품 금리 (팀엑스대부 등 - 일반 한도와 동일, 금리만 추가 표시)
        funding_rate = self.config.get("funding_rate")
        if funding_rate:
            out["funding_rate"] = funding_rate
        # 투맨금융대부 등: 세입자 있을 때 한도 밑 캡션 (전,월세 동의·미동의 진행 가능)
        tenant_caption = self.config.get("tenant_consent_caption")
        if tenant_caption and property_data and has_tenant_in_property(property_data):
            out["tenant_consent_caption"] = tenant_caption
        return out
    
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
    
    def _get_ltv_steps_by_grade(self, is_subordinate: bool, credit_grade: Optional[int]) -> List[int]:
        """
        신용등급별 LTV steps 조회
        ltv_by_priority_business_type_grade 설정이 있으면 사용하고, 없으면 기존 로직 사용
        """
        gm_ov = getattr(self, "_gm_ltv_steps_override", None)
        if gm_ov:
            print(f"DEBUG: _get_ltv_steps_by_grade - ltv_kb_price_override steps: {gm_ov}")
            return list(gm_ov)
        
        ltv_by_priority = self.config.get("ltv_by_priority_business_type_grade", {})
        if ltv_by_priority:
            # 신용등급별 LTV steps 사용
            priority_key = "subordinate" if is_subordinate else "primary"
            business_type = "regular"  # startup은 제거됨
            
            if priority_key in ltv_by_priority and business_type in ltv_by_priority[priority_key]:
                grade_config = ltv_by_priority[priority_key][business_type]
                
                # 신용등급에 따라 키 선택
                grade_key = None
                if credit_grade is not None:
                    if 1 <= credit_grade <= 6:
                        grade_key = "1-6"
                    elif credit_grade == 7:
                        grade_key = "7"
                    elif credit_grade == 8:
                        grade_key = "8"
                
                if grade_key and grade_key in grade_config:
                    ltv_steps = grade_config[grade_key]
                    if ltv_steps is not None:
                        print(f"DEBUG: _get_ltv_steps_by_grade - {priority_key} 대출, 신용등급 {credit_grade} ({grade_key}), ltv_by_priority_business_type_grade 사용: {ltv_steps}")
                        return ltv_steps
                    else:
                        # null인 경우 취급 불가
                        print(f"DEBUG: _get_ltv_steps_by_grade - {priority_key} 대출, 신용등급 {credit_grade} ({grade_key})는 null로 취급 불가")
                        return []
        
        # ltv_by_priority_business_type_grade 설정이 없거나 해당 등급이 없으면 기존 로직 사용
        subordinate_steps = self.config.get("ltv_steps_subordinate", [])
        primary_steps = self.config.get("ltv_steps_primary", [])
        
        if is_subordinate and subordinate_steps:
            print(f"DEBUG: _get_ltv_steps_by_grade - 후순위 대출, ltv_steps_subordinate 사용: {subordinate_steps}")
            return subordinate_steps
        elif not is_subordinate and primary_steps:
            print(f"DEBUG: _get_ltv_steps_by_grade - 선순위 대출, ltv_steps_primary 사용: {primary_steps}")
            return primary_steps
        else:
            default_steps = self.config.get("ltv_steps", [90, 85, 80, 75, 70, 65])
            print(f"DEBUG: _get_ltv_steps_by_grade - 기본 ltv_steps 사용: {default_steps}")
            return default_steps
    
    def _check_is_startup_business(self, property_data: Dict[str, Any]) -> bool:
        """
        창업사업자 여부 판단 (애큐온캐피탈 등)
        - 직업: 직장인 -> 창업사업자 (단, startup_occupation_exceptions에 있으면 일반사업자)
        - 특이사항: 즉발, 즉발사업자, 가라사업자, 즉발보유, 가라사업자보유 -> 창업사업자
        - 그 외 '사업자' 보유 -> 일반사업자
        """
        startup_config = self.config.get("startup_business_keywords", {})
        if not startup_config:
            return False  # 설정 없으면 일반사업자
        occupation = (property_data.get("occupation") or "").strip()
        special_notes = (property_data.get("special_notes") or "").strip()
        requests = (property_data.get("requests") or "").strip()
        # 긴 직업명이 짧은 키워드(직장인)에 먼저 걸리지 않도록: 예외 직업은 창업 아님(일반사업자)
        for exc in self.config.get("startup_occupation_exceptions", []) or []:
            if exc and exc in occupation:
                print(f"DEBUG: _check_is_startup_business - occupation exception '{exc}' -> 일반사업자")
                return False
        combined = f"{occupation} {special_notes} {requests}"
        occ_keywords = startup_config.get("occupation", [])
        notes_keywords = startup_config.get("special_notes", [])
        for kw in occ_keywords:
            if kw in occupation:
                return True
        for kw in notes_keywords:
            if kw in special_notes or kw in requests:
                return True
        return False

    def _excluded_business_occupation_message(self, property_data: Dict[str, Any]) -> Optional[str]:
        """
        사업자금 상품인데 직업이 일반사업자 한도 산출 제외인 경우 (애큐온캐피탈: 프리랜서 등).
        창업사업자로 이미 분류되면(None 유지) 적용하지 않음.
        """
        ex = self.config.get("excluded_occupation_for_business_product")
        if not ex:
            return None
        keywords = ex.get("keywords") or []
        occupation = (property_data.get("occupation") or "").strip()
        for kw in keywords:
            if kw and kw in occupation:
                return ex.get("error_message") or f"직업에 '{kw}'가 포함된 경우 사업자금 한도 산출 대상이 아닙니다."
        return None

    def _validate_validation_rules(
        self, 
        property_data: Dict[str, Any], 
        validation_errors: List[str]
    ) -> None:
        """
        설정 파일의 validation_rules를 읽어서 검증 수행
        
        Args:
            property_data: 부동산 정보
            validation_errors: 검증 오류 목록 (추가할 에러를 여기에 append)
        """
        validation_rules = self.config.get("validation_rules", {})
        if not validation_rules.get("enabled", False):
            return
        
        occupation = property_data.get("occupation", "") or ""
        special_notes = property_data.get("special_notes", "") or ""
        requests = property_data.get("requests", "") or ""
        combined_text = (special_notes + " " + requests).strip()
        
        # 1. 직업 요구사항 체크 (required_keywords, forbidden_keywords)
        occupation_requirements = validation_rules.get("occupation_requirements", {})
        if occupation_requirements:
            required_keywords = occupation_requirements.get("required_keywords", [])
            forbidden_keywords = occupation_requirements.get("forbidden_keywords", [])
            check_fields = occupation_requirements.get("check_fields", ["occupation", "special_notes", "requests"])
            
            # 필수 키워드 체크
            if required_keywords:
                found_required = False
                for keyword in required_keywords:
                    if "occupation" in check_fields and occupation and keyword in occupation:
                        found_required = True
                        break
                    if "special_notes" in check_fields and special_notes and keyword in special_notes:
                        found_required = True
                        break
                    if "requests" in check_fields and requests and keyword in requests:
                        found_required = True
                        break
                
                if not found_required:
                    error_msg_template = occupation_requirements.get("error_message", 
                        f"직업이 '{', '.join(required_keywords)}'인 경우만 취급 가능합니다 (현재 직업: '{{occupation}}')")
                    error_msg = error_msg_template.format(occupation=occupation if occupation else "정보없음")
                    log_print(f"DEBUG: BaseCalculator._validate_validation_rules - 필수 키워드 없음: {required_keywords}")
                    logger.warning(f"BaseCalculator._validate_validation_rules - 필수 키워드 없음: {required_keywords}")
                    validation_errors.append(error_msg)
                    return  # 필수 조건 불만족 시 다른 체크 스킵
            
            # 금지 키워드 체크
            if forbidden_keywords:
                found_forbidden = []
                for keyword in forbidden_keywords:
                    if "occupation" in check_fields and occupation and keyword in occupation:
                        found_forbidden.append(keyword)
                        log_print(f"DEBUG: BaseCalculator._validate_validation_rules - 직업 '{occupation}'에 금지 키워드 '{keyword}' 발견")
                        logger.warning(f"BaseCalculator._validate_validation_rules - 직업 '{occupation}'에 금지 키워드 '{keyword}' 발견")
                    if "special_notes" in check_fields and special_notes and keyword in special_notes:
                        if keyword not in found_forbidden:
                            found_forbidden.append(keyword)
                            log_print(f"DEBUG: BaseCalculator._validate_validation_rules - 특이사항에 금지 키워드 '{keyword}' 발견")
                            logger.warning(f"BaseCalculator._validate_validation_rules - 특이사항에 금지 키워드 '{keyword}' 발견")
                    if "requests" in check_fields and requests and keyword in requests:
                        if keyword not in found_forbidden:
                            found_forbidden.append(keyword)
                            log_print(f"DEBUG: BaseCalculator._validate_validation_rules - 요청사항에 금지 키워드 '{keyword}' 발견")
                            logger.warning(f"BaseCalculator._validate_validation_rules - 요청사항에 금지 키워드 '{keyword}' 발견")
                
                if found_forbidden:
                    error_msg = occupation_requirements.get("forbidden_error_message",
                        f"'{', '.join(found_forbidden)}'는 취급 불가합니다")
                    validation_errors.append(error_msg)
                    return  # 금지 키워드 발견 시 다른 체크 스킵
        
        # 2. 제한 키워드 체크 (restricted_keywords)
        restricted_keywords_config = validation_rules.get("restricted_keywords", {})
        if restricted_keywords_config:
            check_fields = restricted_keywords_config.get("check_fields", ["special_notes", "requests"])
            keywords = restricted_keywords_config.get("keywords", [])
            
            found_keywords = []
            for keyword in keywords:
                for field in check_fields:
                    if field == "special_notes" and special_notes and keyword in special_notes:
                        if keyword not in found_keywords:
                            found_keywords.append(keyword)
                            log_print(f"DEBUG: BaseCalculator._validate_validation_rules - 특이사항에 제한 키워드 '{keyword}' 발견")
                            logger.warning(f"BaseCalculator._validate_validation_rules - 특이사항에 제한 키워드 '{keyword}' 발견")
                    elif field == "requests" and requests and keyword in requests:
                        if keyword not in found_keywords:
                            found_keywords.append(keyword)
                            log_print(f"DEBUG: BaseCalculator._validate_validation_rules - 요청사항에 제한 키워드 '{keyword}' 발견")
                            logger.warning(f"BaseCalculator._validate_validation_rules - 요청사항에 제한 키워드 '{keyword}' 발견")
            
            if found_keywords:
                error_msg_template = restricted_keywords_config.get("error_message",
                    "특이사항/요청사항에 '{keywords}'가 포함되어 취급 불가합니다")
                error_msg = error_msg_template.format(keywords=', '.join(found_keywords))
                validation_errors.append(error_msg)
                return  # 제한 키워드 발견 시 복합 규칙 체크 스킵
        
        # 3. 근저당 기관명 제한 (DSFNC 등: 가압류·압류 선순위는 취급 불가)
        mortgage_institution_restricted = validation_rules.get("mortgage_institution_restricted", {})
        if mortgage_institution_restricted:
            keywords = mortgage_institution_restricted.get("keywords", [])
            if keywords:
                # 긴 키워드 우선 (「가압류」에 「압류」가 포함되는 중복 방지)
                kw_sorted = sorted(keywords, key=lambda x: len(x or ""), reverse=True)
                found_inst = []
                for m in property_data.get("mortgages") or []:
                    inst = (m.get("institution") or "").strip()
                    if not inst:
                        continue
                    for kw in kw_sorted:
                        if kw and kw in inst:
                            if kw not in found_inst:
                                found_inst.append(kw)
                            break
                if found_inst:
                    error_msg = mortgage_institution_restricted.get(
                        "error_message",
                        f"근저당 선순위에 '{', '.join(found_inst)}'가 포함되어 취급 불가입니다",
                    )
                    validation_errors.append(error_msg)
                    log_print(f"DEBUG: BaseCalculator._validate_validation_rules - 근저당 기관명 제한: {found_inst}")
                    logger.warning(f"BaseCalculator._validate_validation_rules - 근저당 기관명 제한: {found_inst}")
                    return

        # 3-1. 근저당권 설정일 기반 개월수 제한 (날짜가 있는 경우에만 적용)
        mortgage_age_restricted = validation_rules.get("mortgage_age_restricted", {})
        if mortgage_age_restricted and mortgage_age_restricted.get("enabled", False):
            default_min_months = mortgage_age_restricted.get("default_min_months", 0)
            check_refinance_only = mortgage_age_restricted.get("check_refinance_only", True)
            date_field_candidates = mortgage_age_restricted.get(
                "date_field_candidates",
                ["setup_date", "설정일", "registration_date", "date"],
            )
            institution_rules = mortgage_age_restricted.get("institution_rules", [])

            violations = []
            for m in property_data.get("mortgages") or []:
                if check_refinance_only and not m.get("is_refinance", False):
                    continue

                date_str = None
                for f in date_field_candidates:
                    val = m.get(f)
                    if isinstance(val, str) and val.strip():
                        date_str = val.strip()
                        break
                if not date_str:
                    # 날짜가 없으면 해당 건은 제한 검사에서 제외(요청하신 정책)
                    continue

                parsed_date = self._parse_mortgage_date(date_str)
                if parsed_date is None:
                    # 날짜 형식 파싱 실패 시에도 해당 건은 검사 제외
                    continue

                min_months = int(default_min_months or 0)
                inst_name = (m.get("institution") or "").strip()
                for rule in institution_rules:
                    keyword = (rule.get("keyword") or "").strip()
                    if keyword and keyword in inst_name:
                        try:
                            min_months = max(min_months, int(rule.get("min_months", 0)))
                        except (TypeError, ValueError):
                            pass

                if min_months <= 0:
                    continue

                elapsed_months = self._months_since(parsed_date)
                if elapsed_months < min_months:
                    violations.append(
                        {
                            "institution": inst_name or "기관명없음",
                            "date": date_str,
                            "elapsed_months": elapsed_months,
                            "min_months": min_months,
                        }
                    )

            if violations:
                violation_text = ", ".join(
                    [
                        f"{v['institution']}({v['date']}, {v['elapsed_months']}개월)"
                        for v in violations
                    ]
                )
                error_msg_template = mortgage_age_restricted.get(
                    "error_message",
                    "대환 대상 근저당권의 설정일 기준 경과개월이 부족하여 취급 불가합니다: {violations}",
                )
                validation_errors.append(error_msg_template.format(violations=violation_text))
                return
        
        # 4. 복합 규칙 체크 (complex_rules)
        complex_rules = validation_rules.get("complex_rules", [])
        for rule in complex_rules:
            conditions = rule.get("conditions", {})
            occupation_keywords = conditions.get("occupation_keywords", [])
            combined_text_keywords = conditions.get("combined_text_keywords", [])
            require_all = conditions.get("require_all", True)
            
            # 직업 키워드 체크
            has_occupation_match = False
            if occupation_keywords:
                for keyword in occupation_keywords:
                    if keyword in occupation:
                        has_occupation_match = True
                        break
            
            # 복합 텍스트 키워드 체크
            has_combined_match = False
            if combined_text_keywords:
                if require_all:
                    # 모든 키워드가 있어야 함
                    has_combined_match = all(keyword in combined_text for keyword in combined_text_keywords)
                else:
                    # 하나라도 있으면 됨
                    has_combined_match = any(keyword in combined_text for keyword in combined_text_keywords)
            
            # 규칙 조건 충족 여부 확인
            rule_triggered = False
            if require_all:
                # 모든 조건을 만족해야 함
                rule_triggered = (not occupation_keywords or has_occupation_match) and (not combined_text_keywords or has_combined_match)
            else:
                # 하나라도 만족하면 됨
                rule_triggered = (occupation_keywords and has_occupation_match) or (combined_text_keywords and has_combined_match)
            
            if rule_triggered:
                error_msg = rule.get("error_message", f"{rule.get('name', '규칙')}인 경우 취급 불가합니다")
                log_print(f"DEBUG: BaseCalculator._validate_validation_rules - 복합 규칙 '{rule.get('name')}' 충족, 취급 불가")
                logger.warning(f"BaseCalculator._validate_validation_rules - 복합 규칙 '{rule.get('name')}' 충족, 취급 불가")
                validation_errors.append(error_msg)
                return  # 복합 규칙 충족 시 다른 규칙 체크는 하지 않음

    def _parse_mortgage_date(self, value: str) -> Optional[date]:
        """
        문자열 형태의 설정일을 date로 파싱.
        지원 형식: YYYY.MM.DD, YYYY-MM-DD, YYYY/MM/DD, YYYY년 M월 D일
        """
        if not value:
            return None
        text = str(value).strip()

        # YYYY년 M월 D일
        m = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except (TypeError, ValueError):
                return None

        # YYYY.MM.DD / YYYY-MM-DD / YYYY/MM/DD
        m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except (TypeError, ValueError):
                return None

        return None

    def _months_since(self, target_date: date) -> int:
        """target_date부터 오늘까지의 경과 개월 수."""
        today = date.today()
        months = (today.year - target_date.year) * 12 + (today.month - target_date.month)
        if today.day < target_date.day:
            months -= 1
        return max(0, months)
    
    def validate_kb_price(self, kb_price: Any) -> Optional[float]:
        """
        KB시세 검증 및 변환
        시세가 없으면 None 반환 (산출 불가)
        """
        print(f"DEBUG: BaseCalculator.validate_kb_price - input: {kb_price}, type: {type(kb_price)}")
        result = validate_kb_price(kb_price)
        print(f"DEBUG: BaseCalculator.validate_kb_price - output: {result}")
        return result
    
    def get_region_grade(self, region: str) -> Optional[Union[int, str]]:
        """
        지역별 급지 조회
        region_grades에 명시된 지역만 처리 (fallback 없음)
        명시되지 않은 지역은 None 반환하여 취급 불가지역으로 처리
        region_grade_prefix_rules 가 있으면 starts_with 순으로 먼저 매칭 (GM대부 등)
        """
        prefix_rules = self.config.get("region_grade_prefix_rules")
        if prefix_rules:
            region_clean = region.replace(" ", "")
            default_grade = None
            for rule in prefix_rules:
                sw = rule.get("starts_with")
                gr = rule.get("grade")
                if sw is None or sw == "":
                    default_grade = gr
                    continue
                sw_clean = sw.replace(" ", "")
                if region.startswith(sw) or region_clean.startswith(sw_clean):
                    print(f"DEBUG: get_region_grade - prefix rule '{sw}' -> {gr}")
                    return gr
            if default_grade is not None:
                print(f"DEBUG: get_region_grade - prefix default -> {default_grade}")
                return default_grade
        
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
        
        # 4. 구/동 단위 region에 대한 부모 지역 fallback (다른 금융사 호환)
        # 예: 경기도화성시동탄구 -> 경기도화성시, 경기도수원시영통구이의동 -> 경기도수원시영통구
        region_to_parent = {
            "경기도화성시동탄구": "경기도화성시", "경기도화성시만세구": "경기도화성시",
            "경기도화성시효행구": "경기도화성시", "경기도화성시병점구": "경기도화성시",
            "경기도수원시영통구이의동": "경기도수원시영통구", "경기도수원시영통구원천동": "경기도수원시영통구",
            "경기도수원시영통구하동": "경기도수원시영통구",
            "경기도성남시수정구창곡동": "경기도성남시수정구",
            "경기도남양주시별내동": "경기도남양주시", "경기도남양주시다산동": "경기도남양주시",
            "인천광역시서구청라동": "인천광역시서구", "인천광역시서구가정동": "인천광역시서구",
            "인천광역시서구신현동": "인천광역시서구",
        }
        parent_region = region_to_parent.get(region_clean)
        if parent_region and parent_region in region_grades:
            grade = region_grades.get(parent_region)
            if grade is not None and not self._is_metropolitan_key(parent_region):
                print(f"DEBUG: get_region_grade - parent fallback: {region_clean} -> {parent_region} -> grade {grade}")
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
                            # LTV 100% 적용 조건 확인 (1급지, 신용 2등급 이내, 500세대 이상, 준공 10년 이내)
                            ltv_100_conditions = self.config.get("ltv_100_conditions", {})
                            if ltv_100_conditions:
                                region_required = ltv_100_conditions.get("region_grade")
                                credit_max = ltv_100_conditions.get("credit_grade_max")
                                min_households = ltv_100_conditions.get("min_households")
                                completion_years_max = ltv_100_conditions.get("completion_years_max")
                                grade_num = int(grade) if str(grade).isdigit() else None
                                household_count = property_data.get("household_count")
                                if (region_required is not None and grade_num == region_required
                                        and credit_max is not None and credit_grade_number <= credit_max
                                        and min_households is not None
                                        and household_count is not None and int(household_count) >= int(min_households)):
                                    if completion_years_max is not None:
                                        years_since = self._parse_ok_years_since_completion(property_data)
                                        if years_since is not None and years_since <= completion_years_max:
                                            max_ltv = max(max_ltv, 100)
                                            print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 LTV 100% 조건 충족 -> max_ltv {max_ltv}%")
                                        else:
                                            print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 LTV 100% 미충족: 준공년도 (years_since={years_since}, max={completion_years_max})")
                                    else:
                                        max_ltv = max(max_ltv, 100)
                                        print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 LTV 100% 조건 충족(준공조건 없음) -> max_ltv {max_ltv}%")
                                elif grade_num != region_required or credit_grade_number > (credit_max or 99):
                                    print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 LTV 100% 미충족: 급지={grade_num}(필요={region_required}), 신용등급={credit_grade_number}(이내={credit_max})")
                                elif household_count is None or int(household_count) < int(min_households or 0):
                                    print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 LTV 100% 미충족: 세대수 {household_count or '없음'} < {min_households}")
                            print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 면적별 LTV: area={area}㎡, grade={grade}, credit_grade={credit_grade_number}등급 -> LTV {max_ltv}%")
                            # 키움저축-리테일 LTV 차감 적용
                            max_ltv = self._apply_kiwoom_ltv_adjustments(max_ltv, property_data)
                            return max_ltv
                else:
                    # 신용점수가 없는 경우: 해당 급지의 최대 LTV 사용 (면적과 급지만 고려)
                    print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 신용점수 없음, 면적과 급지만으로 최대 LTV 계산")
                    max_ltv = self._get_ok_max_ltv_by_area_grade(area, grade)
                    if max_ltv is not None:
                        print(f"DEBUG: get_max_ltv_by_grade - OK저축은행 면적별 LTV (신용점수 없음): area={area}㎡, grade={grade} -> LTV {max_ltv}%")
                        # 키움저축-리테일 LTV 차감 적용
                        max_ltv = self._apply_kiwoom_ltv_adjustments(max_ltv, property_data)
                        return max_ltv
        
        # 애큐온저축은행: max_ltv_by_priority_grade_region 설정 확인 (선순위/후순위, 신용등급, 급지별 최대 LTV)
        max_ltv_by_priority = self.config.get("max_ltv_by_priority_grade_region", {})
        if max_ltv_by_priority and property_data is not None:
            # 후순위 여부 확인 (mortgages가 있으면 후순위)
            mortgages = property_data.get("mortgages", [])
            is_subordinate = len(mortgages) > 0
            
            # 신용점수로 신용등급 확인
            credit_score = property_data.get("credit_score")
            credit_grade = self.credit_score_to_grade(credit_score) if credit_score is not None else None
            
            priority_key = "subordinate" if is_subordinate else "primary"
            
            if priority_key in max_ltv_by_priority:
                grade_config = max_ltv_by_priority[priority_key]
                
                # 신용등급에 따라 키 선택 (신용점수 없음(X)일 때 fallback 적용)
                grade_key = None
                if credit_grade is not None:
                    if 1 <= credit_grade <= 6:
                        grade_key = "1-6"
                    elif credit_grade == 7:
                        grade_key = "7"
                    elif credit_grade == 8:
                        grade_key = "8"
                else:
                    # 신용점수 없음: credit_grade_none_fallback 사용. LTV·한도만 등급 적용, 금리는 구간(최저~최고)으로 산출
                    grade_key = self.config.get("credit_grade_none_fallback", "1-6")
                
                if grade_key and grade_key in grade_config:
                    region_ltv_map = grade_config[grade_key]
                    if region_ltv_map is not None:
                        # 급지별 최대 LTV 조회
                        grade_str = str(grade)
                        if grade_str in region_ltv_map:
                            result = region_ltv_map[grade_str]
                            print(f"DEBUG: get_max_ltv_by_grade - 애큐온저축은행 {priority_key} 대출, 신용등급 {credit_grade} ({grade_key}), 급지 {grade} -> LTV {result}%")
                            # 키움저축-리테일 LTV 차감 적용
                            result = self._apply_kiwoom_ltv_adjustments(result, property_data)
                            return result
                    else:
                        # null인 경우 취급 불가
                        print(f"DEBUG: get_max_ltv_by_grade - 애큐온저축은행 {priority_key} 대출, 신용등급 {credit_grade} ({grade_key})는 null로 취급 불가")
                        return None
        
        # JB우리캐피탈 등: max_ltv_by_region_credit_grade (급지 x 신용등급별 최대 LTV)
        max_ltv_by_region_credit_grade = self.config.get("max_ltv_by_region_credit_grade", {})
        if max_ltv_by_region_credit_grade and property_data is not None:
            region_grade_str = str(grade)
            if region_grade_str in max_ltv_by_region_credit_grade and not region_grade_str.startswith("_"):
                credit_grade_map = max_ltv_by_region_credit_grade[region_grade_str]
                if isinstance(credit_grade_map, dict):
                    credit_score = property_data.get("credit_score")
                    credit_grade = self.credit_score_to_grade(credit_score) if credit_score is not None else None
                    if credit_grade is not None and 1 <= credit_grade <= 7:
                        credit_grade_str = str(credit_grade)
                        if credit_grade_str in credit_grade_map:
                            result = credit_grade_map[credit_grade_str]
                            if result is not None and result > 0:
                                result = self._apply_kiwoom_ltv_adjustments(result, property_data)
                                return result
                        return None
                    else:
                        credit_grade_none_fallback = self.config.get("credit_grade_none_fallback", "1")
                        if credit_grade_none_fallback in credit_grade_map:
                            result = credit_grade_map[credit_grade_none_fallback]
                            if result is not None and result > 0:
                                result = self._apply_kiwoom_ltv_adjustments(result, property_data)
                                return result
        
        # 기존 로직 (max_ltv_by_grade 사용)
        max_ltv_by_grade = self.config.get("max_ltv_by_grade", {})
        print(f"DEBUG: get_max_ltv_by_grade - grade: {grade} (type: {type(grade)}), region: {region}, max_ltv_by_grade keys: {list(max_ltv_by_grade.keys())}")  # 추가
        
        # 문자 급지인 경우 (OK 저축은행 등)
        if isinstance(grade, str):
            result = max_ltv_by_grade.get(grade)
            print(f"DEBUG: get_max_ltv_by_grade - 문자 급지: {grade} -> LTV {result}%")
            # 키움저축-리테일 LTV 차감 적용
            result = self._apply_kiwoom_ltv_adjustments(result, property_data)
            return result
        
        # 1급지인 경우 A/B/C 그룹 구분
        if grade == 1 and region:
            region_clean = region.replace(" ", "")
            grade_1_group_a = self.config.get("grade_1_group_a", [])
            grade_1_group_b = self.config.get("grade_1_group_b", [])
            grade_1_group_c = self.config.get("grade_1_group_c", [])
            
            # A 그룹 확인
            for a_region in grade_1_group_a:
                if a_region.replace(" ", "") == region_clean:
                    result = max_ltv_by_grade.get("1")
                    print(f"DEBUG: get_max_ltv_by_grade - 1급지 A그룹: {region} -> LTV {result}%")
                    # 키움저축-리테일 LTV 차감 적용
                    result = self._apply_kiwoom_ltv_adjustments(result, property_data)
                    return result
            
            # B 그룹 확인
            for b_region in grade_1_group_b:
                if b_region.replace(" ", "") == region_clean:
                    result = max_ltv_by_grade.get("1_b")
                    print(f"DEBUG: get_max_ltv_by_grade - 1급지 B그룹: {region} -> LTV {result}%")
                    # 키움저축-리테일 LTV 차감 적용
                    result = self._apply_kiwoom_ltv_adjustments(result, property_data)
                    return result
            
            # C 그룹 확인 (또는 A/B 외 1급지 → C그룹)
            for c_region in grade_1_group_c:
                if c_region.replace(" ", "") == region_clean:
                    result = max_ltv_by_grade.get("1_c")
                    print(f"DEBUG: get_max_ltv_by_grade - 1급지 C그룹: {region} -> LTV {result}%")
                    # 키움저축-리테일 LTV 차감 적용
                    result = self._apply_kiwoom_ltv_adjustments(result, property_data)
                    return result
            
            # 1급지이지만 A/B/C 그룹에 없으면 기본값 (C 그룹)
            result = max_ltv_by_grade.get("1_c", max_ltv_by_grade.get("1"))
            print(f"DEBUG: get_max_ltv_by_grade - 1급지 (기본값 C그룹): {region} -> LTV {result}%")
            # 키움저축-리테일 LTV 차감 적용
            result = self._apply_kiwoom_ltv_adjustments(result, property_data)
            return result
        
        # JSON 키는 문자열이므로 int를 문자열로 변환하여 조회
        result = max_ltv_by_grade.get(str(grade))
        print(f"DEBUG: get_max_ltv_by_grade - result: {result}")  # 추가
        
        # 키움저축-리테일 LTV 차감 적용
        result = self._apply_kiwoom_ltv_adjustments(result, property_data)
        
        return result
    
    def _apply_kiwoom_ltv_adjustments(self, max_ltv: Optional[float], property_data: Optional[Dict[str, Any]]) -> Optional[float]:
        """
        키움저축-리테일: primary_ltv_adjustments 적용
        - 신용등급 7-8구간: LTV 5% 차감
        - 전용면적 110㎡ 초과: LTV 5% 차감
        
        Args:
            max_ltv: 최대 LTV
            property_data: 담보물건 정보
            
        Returns:
            차감 적용된 최대 LTV
        """
        if max_ltv is None or property_data is None:
            return max_ltv
        
        is_kiwoom_retail = "키움저축-리테일" in self.bank_name or "키움저축리테일" in self.bank_name
        if not is_kiwoom_retail:
            return max_ltv
        
        primary_ltv_adjustments = self.config.get("primary_ltv_adjustments", {})
        if not primary_ltv_adjustments:
            return max_ltv
        
        total_reduction = 0.0
        
        # 신용등급 7-8구간 차감 확인
        credit_grade_7_8_reduction = primary_ltv_adjustments.get("credit_grade_7_8_ltv_reduction", 0)
        if credit_grade_7_8_reduction > 0:
            credit_score = property_data.get("credit_score")
            if credit_score is not None:
                credit_grade = self.credit_score_to_grade(credit_score)
                if credit_grade in [7, 8]:
                    total_reduction += credit_grade_7_8_reduction
                    print(f"DEBUG: _apply_kiwoom_ltv_adjustments - 키움저축-리테일: 신용등급 {credit_grade}등급으로 LTV {credit_grade_7_8_reduction}% 차감")
        
        # 전용면적 110㎡ 초과 차감 확인
        area_over_110_reduction = primary_ltv_adjustments.get("area_over_110_ltv_reduction", 0)
        if area_over_110_reduction > 0:
            area = property_data.get("area")
            if area is not None:
                try:
                    area_float = float(area)
                    if area_float > 110:
                        total_reduction += area_over_110_reduction
                        print(f"DEBUG: _apply_kiwoom_ltv_adjustments - 키움저축-리테일: 전용면적 {area_float}㎡ 초과로 LTV {area_over_110_reduction}% 차감")
                except (ValueError, TypeError):
                    pass
        
        # 차감 적용
        if total_reduction > 0:
            result = max(0, max_ltv - total_reduction)
            print(f"DEBUG: _apply_kiwoom_ltv_adjustments - 키움저축-리테일: 총 LTV {total_reduction}% 차감 적용, 최종 LTV: {result}% (원래: {max_ltv}%)")
            return result
        
        return max_ltv
    
    def _get_ok_credit_grade_number(self, credit_score: int) -> Optional[int]:
        """
        OK저축은행: 신용점수를 등급 번호(1~8)로 변환
        
        Args:
            credit_score: 신용점수
        
        Returns:
            등급 번호 (1~8) 또는 None
        """
        score_range_to_grade = self.config.get("credit_score_range_to_grade_number", {})
        # credit_score_range_to_grade_number가 없으면 credit_score_to_grade를 fallback으로 사용
        if not score_range_to_grade:
            score_range_to_grade = self.config.get("credit_score_to_grade", {})
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
    
    def _parse_ok_years_since_completion(self, property_data: Optional[Dict[str, Any]]) -> Optional[int]:
        """
        OK저축은행 LTV 100% 조건: 준공/사용승인 기준 경과년수 파싱.
        property_data에서 years_since_completion(숫자), approval_date(YYYY.MM.DD), completion_date,
        또는 special_notes/requests의 'N년차', '사용승인일 YYYY.MM.DD(N년차)' 문구로부터 산출.
        
        Returns:
            준공/사용승인 후 경과년수 (int), 없으면 None
        """
        if not property_data:
            return None
        # 1) 직접 필드
        years = property_data.get("years_since_completion")
        if years is not None and isinstance(years, (int, float)):
            return int(years)
        # 2) approval_date 또는 completion_date (YYYY.MM.DD 또는 YYYY-MM-DD)
        for key in ("approval_date", "completion_date"):
            raw = property_data.get(key)
            if not raw or not isinstance(raw, str):
                continue
            raw = raw.strip()
            # YYYY.MM.DD / YYYY-MM-DD
            m = re.match(r"(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})", raw)
            if m:
                try:
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    d_obj = date(y, mo, d)
                    today = date.today()
                    years = today.year - d_obj.year
                    if (today.month, today.day) < (d_obj.month, d_obj.day):
                        years -= 1
                    return max(0, years)
                except (ValueError, TypeError):
                    pass
        # 3) 특이사항/요청사항에서 'N년차' 또는 '사용승인일 ... (N년차)' 추출
        text = (property_data.get("special_notes") or "") + " " + (property_data.get("requests") or "")
        if text:
            # "34년차" 또는 "(34년차)" 패턴
            m = re.search(r"\(?(\d+)\s*년\s*차\)?", text)
            if m:
                return int(m.group(1))
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
    
    def _check_lower_bound_rules(self, rules: List[Dict], floor: Optional[int], total_floors: Optional[int]) -> bool:
        """
        하한가 적용 규칙 체크
        
        Args:
            rules: 하한가 규칙 리스트
            floor: 현재 층수
            total_floors: 건물 총층수
        
        Returns:
            하한가 적용 여부
        """
        if floor is None:
            return False
        
        # 총층수 조건이 있는 규칙들 (total_floors_min/max가 하나라도 있는 규칙)
        rules_with_total_floors = [r for r in rules if r.get("total_floors_min") is not None or r.get("total_floors_max") is not None]

        # 총층수 미입력 시 폴백: 모든 총층수 규칙에서 공통으로 하한가 적용되는 층이면 적용
        if total_floors is None and rules_with_total_floors:
            all_lower_floors = [set(r.get("lower_bound_floors", [])) for r in rules_with_total_floors if r.get("lower_bound_floors")]
            if all_lower_floors:
                intersection = set.intersection(*all_lower_floors)
                if floor in intersection:
                    log_print(f"DEBUG: _check_lower_bound_rules - 총층수 미입력 폴백: floor={floor} (공통 적용층 {sorted(intersection)})")
                    return True

        for rule in rules:
            # 총층수 조건 확인
            total_floors_min = rule.get("total_floors_min")
            total_floors_max = rule.get("total_floors_max")
            lower_bound_floors = rule.get("lower_bound_floors", [])
            
            # 총층수 조건이 있는 경우
            if total_floors_min is not None or total_floors_max is not None:
                if total_floors is None:
                    # 총층수 정보가 없으면 이 규칙은 건너뜀 (폴백은 위에서 이미 처리)
                    continue
                
                # 최소 총층수 조건 확인
                if total_floors_min is not None and total_floors < total_floors_min:
                    continue
                
                # 최대 총층수 조건 확인
                if total_floors_max is not None and total_floors > total_floors_max:
                    continue
            
            # 총층수 조건을 만족하면, 현재 층수가 하한가 적용 층수에 포함되는지 확인
            if floor in lower_bound_floors:
                log_print(f"DEBUG: _check_lower_bound_rules - 규칙 매칭: floor={floor}, total_floors={total_floors}, rule={rule}")
                return True
        
        return False
    
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
        ltv: Union[int, float], 
        total_mortgage: float,
        is_refinance: bool = False,
        refinance_principal: float = 0.0
    ) -> Dict[str, float]:
        """
        가용 한도 계산.
        
        - total_mortgage: 대환 제외 선순위 채권최고액 합(만원). 후순위·대환 공통.
        - 대환 시 refinance_principal: 대환 대상 근저당 **원금** 합. 담보한도에서 1차 차감(채권최고) 후 2차로 차감.
        
        Args:
            kb_price: KB시세 (만원)
            ltv: LTV 비율 (예: 85)
            total_mortgage: 선순위 채권최고 합(만원, 대환 제외 분)
            is_refinance: 대환 여부
            refinance_principal: 대환할 근저당권 원금 (만원)
        
        Returns:
            {
                "total_amount": 전체 대출 금액 (원금),
                "available_amount": 가용 한도 (원금)
            }
        """
        max_amount_principal = kb_price * (ltv / 100)
        print(f"DEBUG: calculate_available_amount - kb_price: {kb_price}, ltv: {ltv}, total_mortgage(선순위채권최고): {total_mortgage}, is_refinance: {is_refinance}, refinance_principal(대환 원금): {refinance_principal}")  # 추가
        print(f"DEBUG: calculate_available_amount - max_amount_principal (kb_price * ltv/100): {max_amount_principal}")  # 추가
        
        if is_refinance:
            # 1단계: 남은 LTV 한도 = 담보한도 − 대환 아닌 선순위 채권최고
            available_amount = max_amount_principal - total_mortgage
            # 2단계: 그 잔여에서 대환 대상 근저당 원금 상환분 차감
            # 마이너스도 허용 (대환 한도 부족해도 산출)
            available_principal = available_amount - refinance_principal
            
            # 대환 총 실행금액(원금) = 대환원금 + 추가금
            total_refinance_amount = refinance_principal + available_principal
            
            result = {
                "total_amount": total_refinance_amount,
                "available_amount": available_principal,  # 최종 가용한도 (2단계)
                "available_limit": available_amount  # 가한도 (1단계) - 최소진행금액 체크용
            }
            print(f"DEBUG: calculate_available_amount - 대환: available_amount(1단계, 가한도)={available_amount}, available_principal(최종)={available_principal}, total_refinance_amount={total_refinance_amount}, result={result}")  # 추가
            return result
        else:
            # 후순위: 담보한도에서 선순위 채권최고액 합을 차감
            available_principal = max_amount_principal - total_mortgage
            result = {
                "total_amount": max(0, available_principal),
                "available_amount": max(0, available_principal),
                "available_limit": max(0, available_principal)  # 후순위는 가한도와 가용금액이 동일
            }
            print(f"DEBUG: calculate_available_amount - 후순위: available_principal={available_principal}, result={result}")  # 추가
            return result
    
    def _parse_mg_internal_grade(self, property_data: Optional[Dict[str, Any]]) -> Optional[int]:
        """
        MG캐피탈 내부 등급 파싱
        
        신용점수란, 특이사항, 요청사항에서 다음 형식의 등급을 추출:
        - "1등급" ~ "7등급"
        - "내부 1등급" ~ "내부 7등급"
        
        Args:
            property_data: 담보물건 정보
        
        Returns:
            내부 등급 (1-7) 또는 None
        """
        import re
        
        if property_data is None:
            return None
        
        # 확인할 필드들 (우선순위: 신용점수 원본 > 특이사항 > 요청사항)
        fields_to_check = [
            property_data.get("credit_score_raw"),  # 신용점수란 원본 (검증 전 값, "내부 4등급" 등)
            property_data.get("special_notes"),
            property_data.get("requests")
        ]
        
        # 등급 패턴: "내부 1등급", "내부1등급", "1등급" 등
        pattern = r'(?:내부\s*)?([1-7])등급'
        
        for field in fields_to_check:
            if field is None:
                continue
            
            field_str = str(field)
            match = re.search(pattern, field_str)
            if match:
                grade = int(match.group(1))
                print(f"DEBUG: _parse_mg_internal_grade - 내부 등급 발견: {grade}등급 (원본: '{field_str}')")
                return grade
        
        return None
    
    def _check_mg_promotion(
        self,
        ltv: int,
        region_grade: Optional[Union[int, str]],
        credit_grade: Optional[int],
        property_data: Optional[Dict[str, Any]]
    ) -> float:
        """
        MG캐피탈 프로모션 조건 체크 및 할인율 반환
        
        프로모션 조건:
        1. 물건지 급지 1, 2급지
        2. 고객 신용등급 5등급 이내
        3. 아파트, 주상복합 200세대 이상
        4. LTV 85% 이내
        
        할인:
        - 1급지: -0.3%
        - 2급지: -0.4%
        
        Args:
            ltv: LTV 비율
            region_grade: 지역 급지
            credit_grade: 신용등급
            property_data: 담보물건 정보
        
        Returns:
            할인율 (음수값, 예: -0.3) 또는 0.0 (프로모션 미적용)
        """
        promotions = self.config.get("promotions", [])
        if not promotions:
            return 0.0
        
        for promotion in promotions:
            conditions = promotion.get("conditions", {})
            discounts = promotion.get("discounts", {})
            apply_to = promotion.get("apply_to", ["primary", "subordinate"])
            
            # 선/후순위 적용 여부 체크
            is_subordinate = getattr(self, '_is_subordinate', False)
            loan_type = "subordinate" if is_subordinate else "primary"
            if loan_type not in apply_to:
                print(f"DEBUG: _check_mg_promotion - 프로모션 미적용 (대출타입 {loan_type} 미해당)")
                continue
            
            # 조건 1: 급지 체크 (1, 2급지만)
            allowed_grades = conditions.get("region_grades", [])
            if region_grade is None or int(region_grade) not in allowed_grades:
                print(f"DEBUG: _check_mg_promotion - 프로모션 미적용 (급지 {region_grade} 미해당, 허용: {allowed_grades})")
                continue
            
            # 1,2급지인 경우에만 미적용 사유 수집
            rejection_reasons = []
            
            # 조건 2: 신용등급 체크 (5등급 이내)
            max_credit_grade = conditions.get("max_credit_grade")
            if max_credit_grade is not None:
                if credit_grade is None or credit_grade > max_credit_grade:
                    rejection_reasons.append(f"신용등급 {credit_grade}등급 (5등급 이내)")
                    print(f"DEBUG: _check_mg_promotion - 프로모션 미적용 (신용등급 {credit_grade} > {max_credit_grade}등급)")
            
            # 조건 3: 물건 타입 및 세대수 체크
            if property_data:
                property_type = property_data.get("property_type", "")
                allowed_property_types = conditions.get("property_types", [])
                
                # 물건 타입 체크
                type_matched = False
                for allowed_type in allowed_property_types:
                    if allowed_type in property_type:
                        type_matched = True
                        break
                
                if not type_matched:
                    rejection_reasons.append(f"물건타입 {property_type}")
                    print(f"DEBUG: _check_mg_promotion - 프로모션 미적용 (물건타입 {property_type} 미해당, 허용: {allowed_property_types})")
                
                # 세대수 체크
                min_household_count = conditions.get("min_household_count")
                if min_household_count is not None:
                    household_count = property_data.get("household_count")
                    if household_count is None or household_count < min_household_count:
                        rejection_reasons.append(f"세대수 {household_count or '정보없음'}세대 ({min_household_count}세대 이상)")
                        print(f"DEBUG: _check_mg_promotion - 프로모션 미적용 (세대수 {household_count} < {min_household_count})")
            else:
                # property_data가 없으면 프로모션 미적용
                rejection_reasons.append("물건정보 없음")
                print(f"DEBUG: _check_mg_promotion - 프로모션 미적용 (property_data 없음)")
            
            # 조건 4: LTV 체크
            max_ltv = conditions.get("max_ltv")
            if max_ltv is not None and ltv > max_ltv:
                rejection_reasons.append(f"LTV {ltv}% (85% 이내)")
                print(f"DEBUG: _check_mg_promotion - 프로모션 미적용 (LTV {ltv}% > {max_ltv}%)")
            
            # 미적용 사유가 있으면 저장하고 continue
            if rejection_reasons:
                self._promotion_rejection_reason = ", ".join(rejection_reasons)
                continue
            
            # 모든 조건 충족 - 급지에 따른 할인율 반환
            region_grade_str = str(int(region_grade))
            discount = discounts.get(region_grade_str, 0.0)
            print(f"DEBUG: _check_mg_promotion - 프로모션 적용! 급지 {region_grade}, 할인: {discount}%")
            
            # 프로모션 적용 플래그 설정
            self._promotion_applied = True
            self._promotion_name = promotion.get("name", "프로모션")
            self._promotion_rejection_reason = None  # 적용되면 사유 초기화
            
            return discount
        
        return 0.0
    
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
        # GM대부 등: 물건유형·지역급(S/M/P)·시세 구간별 금리 범위 (신용 미사용, show_interest_rate_range)
        profiles = self.config.get("interest_rate_range_by_profile")
        pdat = getattr(self, "_current_property_data", None)
        if profiles and pdat and self.config.get("show_interest_rate_range"):
            ptk = get_property_type_key(
                (pdat.get("property_type") or ""),
                (pdat.get("special_notes") or ""),
            )
            kb_v = float(pdat.get("kb_price") or 0)
            rg_str = str(region_grade) if region_grade is not None else ""
            for pr in profiles:
                m = pr.get("match") or {}
                pts = m.get("property_type_keys")
                if pts and ptk not in pts:
                    continue
                rgs = m.get("region_grades")
                if rgs is not None and rg_str not in rgs:
                    continue
                if m.get("kb_price_gte") is not None and kb_v < float(m["kb_price_gte"]):
                    continue
                if m.get("kb_price_lt") is not None and kb_v >= float(m["kb_price_lt"]):
                    continue
                rng = pr.get("range")
                if rng and len(rng) >= 2:
                    lo, hi = float(rng[0]), float(rng[1])
                    print(f"DEBUG: get_interest_rate - interest_rate_range_by_profile -> {lo}~{hi}%")
                    return {
                        "interest_rate": None,
                        "interest_rate_range": (round(lo, 2), round(hi, 2)),
                        "credit_grade": None,
                        "promotion_applied": False,
                    }
        
        # 애큐온캐피탈: 급지별·창업/일반사업자별·선후순위별 금리
        rates_by_group = self.config.get("interest_rates_by_region_group_priority_business", {})
        if rates_by_group and credit_grade is not None:
            region_grade_str = str(region_grade) if region_grade is not None else None
            grade_to_group = self.config.get("region_grade_to_group", {})
            group = grade_to_group.get(region_grade_str) if region_grade_str else None
            if group and group in rates_by_group:
                is_subordinate = getattr(self, '_is_subordinate', False)
                is_startup = getattr(self, '_is_startup_business', False)
                priority_key = "subordinate" if is_subordinate else "primary"
                business_key = "startup" if is_startup else "regular"
                group_rates = rates_by_group[group].get(priority_key, {}).get(business_key, {})
                bands = self.config.get("ltv_bands_subordinate" if is_subordinate else "ltv_bands_primary", [])
                ltv_float = float(ltv)
                ltv_key = None
                for band in sorted(bands):
                    if ltv_float <= band:
                        ltv_key = str(band)
                        break
                if ltv_key and ltv_key in group_rates:
                    grade_rates = group_rates[ltv_key]
                    grade_key = str(credit_grade)
                    if grade_key in grade_rates:
                        rate = grade_rates[grade_key]
                        if rate is not None:
                            return {
                                "interest_rate": round(float(rate), 2),
                                "interest_rate_range": None,
                                "credit_grade": credit_grade
                            }
                        return {"interest_rate": None, "interest_rate_range": None, "credit_grade": credit_grade}

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
        
        # 기준금리 + 가산금리 방식인지 확인
        base_interest_rate = self.config.get("base_interest_rate")
        interest_rate_by_ltv_grade = self.config.get("interest_rate_by_ltv_grade", {})
        
        if base_interest_rate is not None and interest_rate_by_ltv_grade:
            # 기준금리 + 가산금리 방식
            # 82% LTV이고 2급지인 경우 특별 처리
            if ltv == 82 and region_grade == 2:
                ltv_key = "82_2"
            elif ltv == 82 and region_grade == 1:
                ltv_key = "82_1"
            else:
                ltv_key = str(ltv)
            
            print(f"DEBUG: get_interest_rate - 기준금리 방식: base_interest_rate={base_interest_rate}, ltv={ltv}, region_grade={region_grade}, ltv_key={ltv_key}")
            
            if ltv_key not in interest_rate_by_ltv_grade:
                print(f"DEBUG: get_interest_rate - LTV {ltv_key} not found in interest_rate_by_ltv_grade")
                return {
                    "interest_rate": None,
                    "interest_rate_range": None,
                    "credit_grade": credit_grade
                }
            
            grade_rates = interest_rate_by_ltv_grade[ltv_key]
            print(f"DEBUG: get_interest_rate - grade_rates for LTV {ltv_key}: {grade_rates}")
            
            if credit_grade is not None:
                # 신용등급이 있으면 해당 등급의 가산금리 사용
                grade_key = str(credit_grade)
                print(f"DEBUG: get_interest_rate - looking for grade_key: {grade_key}")
                if grade_key in grade_rates:
                    additional_rate = grade_rates[grade_key]
                    final_rate = base_interest_rate + additional_rate
                    print(f"DEBUG: get_interest_rate - 기준금리 {base_interest_rate}% + 가산금리 {additional_rate}% = {final_rate}% for grade {credit_grade}")
                    return {
                        "interest_rate": round(final_rate, 2),
                        "interest_rate_range": None,
                        "credit_grade": credit_grade
                    }
                else:
                    print(f"DEBUG: get_interest_rate - grade_key {grade_key} not found in grade_rates")
            
            # 신용등급이 없으면 최저~최고 금리 범위 반환
            all_additional_rates = [v for v in grade_rates.values() if isinstance(v, (int, float))]
            if all_additional_rates:
                min_additional = min(all_additional_rates)
                max_additional = max(all_additional_rates)
                min_rate = base_interest_rate + min_additional
                max_rate = base_interest_rate + max_additional
                print(f"DEBUG: get_interest_rate - no credit_grade, returning range: {min_rate}~{max_rate}")
                return {
                    "interest_rate": None,
                    "interest_rate_range": (round(min_rate, 2), round(max_rate, 2)),
                    "credit_grade": None
                }
            
            print(f"DEBUG: get_interest_rate - no rates found, returning None")
            return {
                "interest_rate": None,
                "interest_rate_range": None,
                "credit_grade": credit_grade
            }
        
        # 기존 방식 (interest_rates_by_ltv 사용)
        # 키움저축-리테일 등 후순위/선순위 구분이 있는 경우 처리
        # 애큐온저축은행: 후순위 금리는 급지별로 다름 (subordinate_interest_rates_by_ltv_region)
        is_subordinate = getattr(self, '_is_subordinate', False)
        subordinate_rates = self.config.get("subordinate_interest_rates_by_ltv", {})
        subordinate_rates_by_region = self.config.get("subordinate_interest_rates_by_ltv_region", {})
        primary_rates = self.config.get("primary_interest_rates_by_ltv", {})
        
        # 애큐온저축은행: 후순위 금리가 급지별로 있는 경우
        if is_subordinate and subordinate_rates_by_region and region_grade is not None:
            region_grade_str = str(region_grade)
            if region_grade_str in subordinate_rates_by_region:
                ltv_rates = subordinate_rates_by_region[region_grade_str]
                print(f"DEBUG: get_interest_rate - 애큐온저축은행 후순위 대출, subordinate_interest_rates_by_ltv_region 사용 (급지 {region_grade})")
            else:
                ltv_rates = {}
                print(f"DEBUG: get_interest_rate - 애큐온저축은행 후순위 대출, 급지 {region_grade}에 대한 금리 정보 없음")
        elif is_subordinate and subordinate_rates:
            # 후순위 대출이고 subordinate_interest_rates_by_ltv가 있으면 사용
            ltv_rates = subordinate_rates
            print(f"DEBUG: get_interest_rate - 후순위 대출, subordinate_interest_rates_by_ltv 사용")
        elif is_subordinate and primary_rates:
            # JB하이론 등: subordinate 없을 때 primary_rates fallback (선후순위 동일 금리)
            ltv_rates = primary_rates
            print(f"DEBUG: get_interest_rate - 후순위 대출, primary_interest_rates_by_ltv fallback 사용")
        elif not is_subordinate and primary_rates:
            # 선순위 대출이고 primary_interest_rates_by_ltv가 있으면 사용
            ltv_rates = primary_rates
            print(f"DEBUG: get_interest_rate - 선순위 대출, primary_interest_rates_by_ltv 사용")
        else:
            # 기본값: interest_rates_by_ltv 사용
            ltv_rates = self.config.get("interest_rates_by_ltv", {})
            print(f"DEBUG: get_interest_rate - 기본 interest_rates_by_ltv 사용")
        
        # 82% LTV이고 2급지인 경우 특별 처리
        if ltv == 82 and region_grade == 2:
            ltv_key = "82_2"
            print(f"DEBUG: get_interest_rate - 82% LTV with region_grade 2, using key: {ltv_key}")  # 추가
        else:
            # 소수점 LTV 지원: 1자리까지 반올림
            ltv_float = float(ltv)
            ltv_rounded = round(ltv_float, 1)
            ltv_key = str(ltv_rounded) if ltv_rounded != int(ltv_rounded) else str(int(ltv_rounded))
        
        print(f"DEBUG: get_interest_rate - ltv: {ltv}, credit_score: {credit_score}, credit_grade: {credit_grade}, region_grade: {region_grade}, is_subordinate: {is_subordinate}")  # 추가
        print(f"DEBUG: get_interest_rate - ltv_key: {ltv_key}, available ltv_keys: {list(ltv_rates.keys())}")  # 추가
        
        # 애큐온저축은행, MG캐피탈: LTV 키가 없으면 범위 기반으로 금리 조회
        is_acuon = self.bank_name == "애큐온저축은행" or "애큐온" in self.bank_name
        is_mg_capital = self.bank_name == "MG캐피탈" or "MG캐피탈" in self.bank_name or "엠지케피탈" in self.bank_name
        if ltv_key not in ltv_rates:
            if (is_acuon or is_mg_capital) and ((is_subordinate and subordinate_rates_by_region) or (not is_subordinate and primary_rates) or (is_subordinate and subordinate_rates)):
                # MG캐피탈: LTV 범위 기반 매칭
                if is_mg_capital:
                    ltv_float = float(ltv)
                    # LTV 범위 정의: 60% 이하, 60.1~65%, 65.1~70%, 70.1~75%, 75.1~80%, 80.1~85%
                    ltv_ranges = [
                        (0, 60, "60"),
                        (60.1, 65, "65"),
                        (65.1, 70, "70"),
                        (70.1, 75, "75"),
                        (75.1, 80, "80"),
                        (80.1, 85, "85")
                    ]
                    
                    matched_key = None
                    for min_ltv, max_ltv, key in ltv_ranges:
                        if min_ltv <= ltv_float <= max_ltv:
                            if key in ltv_rates:
                                matched_key = key
                                break
                    
                    if matched_key:
                        ltv_key = matched_key
                        print(f"DEBUG: get_interest_rate - MG캐피탈: LTV {ltv}%는 범위 매칭으로 {ltv_key}% 금리 테이블 사용")
                    else:
                        print(f"DEBUG: get_interest_rate - MG캐피탈: LTV {ltv}%에 대한 적절한 범위를 찾을 수 없음")
                        return {
                            "interest_rate": None,
                            "interest_rate_range": None,
                            "credit_grade": credit_grade
                        }
                else:
                    # 애큐온저축은행: 기존 로직 (상향 적용)
                    # 사용 가능한 LTV 키 중에서 요청된 LTV 이상인 것 중 가장 작은 값 찾기 (요청된 LTV 이상의 금리)
                    # 소수점 LTV 지원: float로 변환하여 비교
                    ltv_float = float(ltv)
                    available_keys = []
                    for k in ltv_rates.keys():
                        try:
                            k_float = float(k)
                            if k_float >= ltv_float:
                                available_keys.append(k_float)
                        except ValueError:
                            continue
                    
                    if available_keys:
                        closest_key = min(available_keys)  # 요청된 LTV 이상인 것 중 가장 작은 값 (예: 83.5% → 85%, 82.1% → 85%, 77.3% → 80%)
                        # 정수면 정수로, 소수점이면 1자리까지
                        if closest_key == int(closest_key):
                            ltv_key = str(int(closest_key))
                        else:
                            ltv_key = str(round(closest_key, 1))
                        bank_display_name = "애큐온저축은행"
                        print(f"DEBUG: get_interest_rate - {bank_display_name}: LTV {ltv}%에 대한 키 없음, 가장 가까운 이상 금리 키 {ltv_key}% 사용")
                    else:
                        bank_display_name = "애큐온저축은행"
                        print(f"DEBUG: get_interest_rate - {bank_display_name}: LTV {ltv}%에 대한 적절한 금리 키를 찾을 수 없음")
                        return {
                            "interest_rate": None,
                            "interest_rate_range": None,
                            "credit_grade": credit_grade
                        }
            else:
                print(f"DEBUG: get_interest_rate - LTV {ltv_key} not found in interest_rates_by_ltv")  # 추가
                return {
                    "interest_rate": None,
                    "interest_rate_range": None,
                    "credit_grade": credit_grade
                }
        
        grade_rates = ltv_rates[ltv_key]
        print(f"DEBUG: get_interest_rate - grade_rates for LTV {ltv_key}: {grade_rates}")  # 추가
        
        # MG캐피탈: 급지별 가산금리 및 아파트/주상복합이 아닌 경우 +1% 적용
        is_mg_capital = self.bank_name == "MG캐피탈" or "MG캐피탈" in self.bank_name or "엠지케피탈" in self.bank_name
        grade_additional_rate = 0.0
        non_apartment_additional_rate = 0.0
        bank_appraisal_additional_rate = 0.0
        promotion_discount = 0.0
        
        if is_mg_capital:
            # 급지별 가산금리 적용
            business_grade_additional_rates = self.config.get("business_grade_additional_rates", {})
            if region_grade is not None:
                grade_key = str(region_grade)
                grade_additional_rate = business_grade_additional_rates.get(grade_key, 0.0)
                print(f"DEBUG: get_interest_rate - MG캐피탈 급지별 가산금리: {grade_additional_rate}% (급지 {region_grade})")
            
            # 아파트/주상복합이 아닌 경우 +1% 적용
            property_data = getattr(self, '_current_property_data', None)
            if property_data:
                property_type = property_data.get("property_type", "")
                is_apartment_or_complex = property_type and ("아파트" in property_type or "주상복합" in property_type)
                if not is_apartment_or_complex:
                    non_apartment_additional_rate = self.config.get("non_apartment_additional_rate", 1.0)
                    print(f"DEBUG: get_interest_rate - MG캐피탈 아파트/주상복합이 아닌 경우 가산금리: {non_apartment_additional_rate}% (물건 타입: {property_type})")
                
                # 탁감가(감정건) 시 가산금리 1% 적용
                kb_price_raw_str = str(property_data.get("kb_price_raw") or "")
                if "탁감가" in kb_price_raw_str or "감정가" in kb_price_raw_str or "은행감정가" in kb_price_raw_str:
                    bank_appraisal_additional_rate = self.config.get("bank_appraisal_additional_rate", 1.0)
                    print(f"DEBUG: get_interest_rate - MG캐피탈 감정건 가산금리: {bank_appraisal_additional_rate}%")
                
                # 비아파트 + 감정건이 동시에 해당되더라도 총 가산은 +1.0%p로 제한
                if non_apartment_additional_rate > 0 and bank_appraisal_additional_rate > 0:
                    bank_appraisal_additional_rate = 0.0
                    print("DEBUG: get_interest_rate - MG캐피탈 비아파트+감정건 동시 해당, 총 가산금리 +1.0%p로 제한")
            
            # MG캐피탈 프로모션 체크 및 할인 적용
            promotion_discount = self._check_mg_promotion(ltv, region_grade, credit_grade, property_data)
            if promotion_discount != 0.0:
                print(f"DEBUG: get_interest_rate - MG캐피탈 프로모션 할인: {promotion_discount}% (급지 {region_grade})")
        
        # show_interest_rate_range 플래그 확인: 신용등급 구분 없이 금리 구간 표시 여부
        show_interest_rate_range = self.config.get("show_interest_rate_range", False)
        if show_interest_rate_range:
            # 신용등급 구분 없이 해당 LTV의 최저~최고 금리 범위 반환 (0=취급불가 제외)
            all_rates = [v for v in grade_rates.values() if isinstance(v, (int, float)) and v > 0]
            if not all_rates:
                all_rates = [v for v in grade_rates.values() if isinstance(v, (int, float))]
            if all_rates:
                min_rate = min(all_rates) + grade_additional_rate + non_apartment_additional_rate + bank_appraisal_additional_rate + promotion_discount
                max_rate = max(all_rates) + grade_additional_rate + non_apartment_additional_rate + bank_appraisal_additional_rate + promotion_discount
                print(f"DEBUG: get_interest_rate - show_interest_rate_range=true, returning range: {min_rate}~{max_rate}% (신용등급 구분 없음, 급지 가산: {grade_additional_rate}%, 비아파트 가산: {non_apartment_additional_rate}%, 감정건 가산: {bank_appraisal_additional_rate}%, 프로모션: {promotion_discount}%)")  # 추가
                return {
                    "interest_rate": None,
                    "interest_rate_range": (round(min_rate, 2), round(max_rate, 2)),
                    "credit_grade": None,
                    "promotion_applied": promotion_discount != 0.0
                }
            else:
                print(f"DEBUG: get_interest_rate - show_interest_rate_range=true but no rates found")
        
        # 기존 로직: 신용등급별 금리 반환
        if credit_grade is not None:
            # 신용등급이 있으면 해당 등급의 금리 반환
            grade_key = str(credit_grade)
            print(f"DEBUG: get_interest_rate - looking for grade_key: {grade_key}")  # 추가
            if grade_key in grade_rates:
                rate = grade_rates[grade_key]
                # MG캐피탈: 급지별 가산금리, 비아파트 +1%, 감정건 +1%, 프로모션 할인
                final_rate = rate + grade_additional_rate + non_apartment_additional_rate + bank_appraisal_additional_rate + promotion_discount
                print(f"DEBUG: get_interest_rate - found rate: {rate}% for grade {credit_grade}, final rate: {final_rate}% (급지 가산: {grade_additional_rate}%, 비아파트 가산: {non_apartment_additional_rate}%, 감정건 가산: {bank_appraisal_additional_rate}%, 프로모션: {promotion_discount}%)")  # 추가
                return {
                    "interest_rate": round(final_rate, 2),
                    "interest_rate_range": None,
                    "credit_grade": credit_grade,
                    "promotion_applied": promotion_discount != 0.0
                }
            else:
                print(f"DEBUG: get_interest_rate - grade_key {grade_key} not found in grade_rates")  # 추가
        
        # 신용점수 없을 때: hide_credit_grade + region_grade 있으면 급지별 단일금리 반환 (DSFNC: 2급지 70%→8.4%, 5급지 70%→10.9%)
        hide_credit_grade = self.config.get("hide_credit_grade", False)
        if hide_credit_grade and region_grade is not None and credit_grade is None:
            grade_key = str(region_grade)
            if grade_key in grade_rates:
                rate = grade_rates[grade_key]
                if rate is not None and rate > 0:
                    final_rate = rate + grade_additional_rate + non_apartment_additional_rate + bank_appraisal_additional_rate + promotion_discount
                    return {
                        "interest_rate": round(final_rate, 2),
                        "interest_rate_range": None,
                        "credit_grade": None,
                        "promotion_applied": promotion_discount != 0.0
                    }
        
        # 신용점수/등급이 없으면 최저~최고 금리 범위 반환
        # 0은 취급 불가(해당 없음)를 의미하므로 제외 (DSFNC 등 단일금리 상품에서 0.00%~10.90% 방지)
        all_rates = [v for v in grade_rates.values() if isinstance(v, (int, float)) and v > 0]
        if not all_rates:
            all_rates = [v for v in grade_rates.values() if isinstance(v, (int, float))]
        if all_rates:
            min_rate = min(all_rates) + grade_additional_rate + non_apartment_additional_rate + bank_appraisal_additional_rate + promotion_discount
            max_rate = max(all_rates) + grade_additional_rate + non_apartment_additional_rate + bank_appraisal_additional_rate + promotion_discount
            min_r, max_r = round(min_rate, 2), round(max_rate, 2)
            print(f"DEBUG: get_interest_rate - no credit_grade, returning range: {min_rate}~{max_rate} (급지 가산: {grade_additional_rate}%, 비아파트 가산: {non_apartment_additional_rate}%, 감정건 가산: {bank_appraisal_additional_rate}%, 프로모션: {promotion_discount}%)")  # 추가
            if min_r == max_r:
                return {
                    "interest_rate": min_r,
                    "interest_rate_range": None,
                    "credit_grade": None,
                    "promotion_applied": promotion_discount != 0.0
                }
            return {
                "interest_rate": None,
                "interest_rate_range": (min_r, max_r),
                "credit_grade": None,
                "promotion_applied": promotion_discount != 0.0
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
        사업자/가계 금리 테이블 값은 CoFix가 반영된 최종 기준값으로 간주한다.
        따라서 계산 시 CoFix를 추가로 더하지 않고, 테이블값 + 가산(급지/조정금리)만 적용한다.
        
        Args:
            credit_score: 신용점수
            ltv: LTV 비율
            region_grade: 지역 급지 (1, 2, 3, 4) - 숫자로 통일됨
            cofix_rate: CoFix 금리(설정 보존용, 계산에는 추가하지 않음)
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
                final_rate = spread_rate + additional_rate + household_adjustment
                print(f"DEBUG: _get_ok_interest_rate - credit_score: {credit_score}, score_range: {score_range}, table_rate: {spread_rate}, cofix(additional none): {cofix_rate}, additional: {additional_rate}, household_adjustment: {household_adjustment}, final: {final_rate}")
                
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
        all_rates = [v + additional_rate + household_adjustment for v in score_rates.values() if isinstance(v, (int, float))]
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
    
    @staticmethod
    def _has_personal_mortgage(property_data: Dict[str, Any]) -> bool:
        """
        근저당권 설정 중 개인설정이 있으면 True.
        - 특이사항에 '개인설정' 문구가 있거나
        - 설정내역 중 기관명이 금융기관이 아닌 경우(개인명으로 판단)
        """
        if not property_data:
            return False
        special_notes = (property_data.get("special_notes") or "").strip()
        if "개인설정" in special_notes:
            return True
        # 기관명이 금융기관이 아닌 순위가 하나라도 있으면 개인설정
        # 가압류·압류 등은 법적 담보 표시로 개인설정(개인명 근저당)과 구분 → 후순위/대환 산출 허용
        exclude_keywords = ("신탁", "물상담보", "전세입자", "전세권", "세입자", "월세입자", "가압류", "압류")
        for m in property_data.get("mortgages") or []:
            institution = (m.get("institution") or "").strip()
            if not institution:
                continue
            inst_type = classify_financial_institution(institution)
            if inst_type != "기타":
                continue
            if any(kw in institution for kw in exclude_keywords):
                continue
            return True
        return False
    
    @classmethod
    def _ensure_price_input_snapshot(cls, property_data: Optional[Dict[str, Any]]) -> None:
        """
        여러 금융사를 순차 계산할 때, 앞선 calculate()가 property_data['kb_price'] 등을 채워도
        'KB AI만 입력' 여부는 사용자 최초 입력 기준으로 유지되도록 스냅샷을 남긴다.
        """
        if not property_data:
            return
        property_data["_price_input_snapshot"] = {
            "kb_price": property_data.get("kb_price"),
            "kb_price_raw": property_data.get("kb_price_raw"),
            "price_type": property_data.get("price_type"),
            "kb_ai_price": property_data.get("kb_ai_price"),
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
        # 개인설정이 있으면 후순위/대환 취급 불가 → 한도 산출 안 함
        if cls._has_personal_mortgage(property_data):
            return [{
                "bank_name": "",
                "results": [],
                "errors": ["개인설정 후순위는 취급 불가"],
                "personal_mortgage_ineligible": True
            }]
        # data/banks 폴더 경로
        current_dir = os.path.dirname(os.path.abspath(__file__))
        banks_dir = os.path.join(current_dir, "..", "data", "banks")
        
        if not os.path.exists(banks_dir):
            return []
        
        calculators = []
        
        # 모든 JSON 파일 찾기 및 계산기 생성 (파일명 정렬로 1_, 2_, 3_... 순서 유지)
        for filename in sorted(os.listdir(banks_dir)):
            if filename.endswith("_config.json") or filename.endswith(".json"):
                config_path = os.path.join(banks_dir, filename)
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        raw_config = json.load(f)
                    # data/banks/*.json 의 enabled (루트). _comment_enabled 참고. false면 한도 산출 제외
                    if raw_config.get("enabled", True) is False:
                        print(f"⏭️ banks/{filename} 한도 산출 비활성화 (enabled: false)")
                        continue
                    calculator = cls(config_path)
                    calculators.append(calculator)
                except Exception as e:
                    print(f"⚠️  계산기 로드 실패 ({filename}): {e}")
                    continue
        
        # 모든 계산기 실행
        cls._ensure_price_input_snapshot(property_data)
        results = []
        for calculator in calculators:
            try:
                # OK저축은행인 경우 가계자금과 사업자금을 각각 계산
                is_ok_bank = calculator.bank_name == "OK저축은행" or "OK저축은행" in calculator.bank_name or "오케이저축은행" in calculator.bank_name
                
                if is_ok_bank:
                    # 가계자금 계산
                    household_result = calculator.calculate(property_data, product_type="household")
                    if household_result is not None and not cls._should_exclude_property_type_mismatch(household_result):
                        household_result["bank_name"] = "OK저축은행 가계자금"
                        results.append(household_result)
                    
                    # 사업자금 계산
                    business_result = calculator.calculate(property_data, product_type="business")
                    if business_result is not None and not cls._should_exclude_property_type_mismatch(business_result):
                        business_result["bank_name"] = "OK저축은행 사업자금"
                        results.append(business_result)
                else:
                    # 일반 금융사: config의 product_type이 있으면 전달 (사업자 상품은 business로 계산)
                    cfg_product_type = calculator.config.get("product_type")
                    result = calculator.calculate(property_data, product_type=cfg_product_type)
                    if result is not None and not cls._should_exclude_property_type_mismatch(result):
                        # 취급 불가지역인 경우도 포함 (errors에 "취급 불가지역"이 있으면)
                        results.append(result)
            except Exception as e:
                print(f"계산기 {calculator.bank_name} 에러: {e}")
                continue
        
        # DSFNC: 하이론 한도가 디에스론보다 클 때만 둘 다 표시, 아니면 디에스론만
        results = cls._filter_dsfnc_results(results)
        
        return results
    
    @classmethod
    def _should_exclude_property_type_mismatch(cls, result: Dict) -> bool:
        """물건 타입 불일치로 인한 취급 불가 결과는 출력에서 제외 (GM대부 빌라/오피스텔 + 아파트 등)"""
        if not result:
            return False
        if result.get("results"):
            return False  # 한도 산출 결과가 있으면 포함
        errors = result.get("errors") or []
        for err in errors:
            if "취급 불가 물건 타입" in str(err):
                return True
        return False

    @classmethod
    def _filter_dsfnc_results(cls, results: list) -> list:
        """DSFNC 디에스론/디에스-하이론: 하이론 한도 > 디에스론 한도일 때만 둘 다 표시, 아니면 디에스론만"""
        dsfnc_desron = next((r for r in results if r.get("bank_name") in ("DSFNC 디에스론", "디에스론")), None)
        dsfnc_hiroon = next((r for r in results if r.get("bank_name") in ("DSFNC 하이론", "하이론", "디에스-하이론")), None)
        if not dsfnc_desron or not dsfnc_hiroon:
            return results
        
        def _get_max_amount(bank_result):
            res_list = bank_result.get("results") or []
            valid = [x for x in res_list if not x.get("limit_not_calculated", False)]
            if not valid:
                return 0
            amounts = [x.get("available_amount") or x.get("amount", 0) or 0 for x in valid]
            return max(amounts) if amounts else 0
        
        max_desron = _get_max_amount(dsfnc_desron)
        max_hiroon = _get_max_amount(dsfnc_hiroon)
        
        if max_desron >= max_hiroon:
            results = [r for r in results if r.get("bank_name") not in ("DSFNC 하이론", "하이론", "디에스-하이론")]
            print(f"DEBUG: BaseCalculator - DSFNC 디에스론 한도({max_desron}만) >= 하이론({max_hiroon}만), 하이론 제외")
        else:
            print(f"DEBUG: BaseCalculator - DSFNC 하이론 한도({max_hiroon}만) > 디에스론({max_desron}만), 둘 다 표시")
        return results
    
    @classmethod
    def calculate_all_loans(cls, property_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        모든 대출 상품에 대해 계산 수행 (data/loan 폴더)
        FSS 폴더와 Local 폴더 모두 처리
        
        Args:
            property_data: 파싱된 담보물건 정보
        
        Returns:
            계산 결과 리스트 (에러 메시지가 있는 경우도 포함)
        """
        # 개인설정이 있으면 후순위/대환 취급 불가 → 한도 산출 안 함
        if cls._has_personal_mortgage(property_data):
            return [{
                "bank_name": "",
                "results": [],
                "errors": ["개인설정 후순위는 취급 불가"],
                "personal_mortgage_ineligible": True
            }]
        current_dir = os.path.dirname(os.path.abspath(__file__))
        loan_base_dir = os.path.join(current_dir, "..", "data", "loan")
        
        if not os.path.exists(loan_base_dir):
            print(f"⚠️  data/loan 폴더가 없습니다: {loan_base_dir}")
            return []
        
        calculators = []
        
        # FSS 폴더와 Local 폴더 모두 처리
        subfolders = ["FSS", "Local"]
        for subfolder in subfolders:
            loan_dir = os.path.join(loan_base_dir, subfolder)
            if not os.path.exists(loan_dir):
                print(f"⚠️  {subfolder} 폴더가 없습니다: {loan_dir}")
                continue
            
            # 각 폴더의 모든 JSON 파일 찾기 및 계산기 생성
            for filename in os.listdir(loan_dir):
                if filename.endswith("_config.json") or filename.endswith(".json"):
                    config_path = os.path.join(loan_dir, filename)
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            raw_config = json.load(f)
                        # data/loan/*/*.json 의 enabled (루트). _comment_enabled 참고. false면 한도 산출 제외
                        if raw_config.get("enabled", True) is False:
                            print(f"⏭️ {subfolder}/{filename} 한도 산출 비활성화 (enabled: false)")
                            continue
                        # products 배열이 있으면 다중 상품 (DSFNC 등)
                        products = raw_config.get("products", [])
                        if products:
                            base_name = raw_config.get("bank_name", "Unknown")
                            show_product_name_only = raw_config.get("show_product_name_only", False)
                            for prod in products:
                                merged = {**raw_config, **prod}
                                if show_product_name_only:
                                    merged["bank_name"] = prod.get("product_name", base_name)
                                else:
                                    merged["bank_name"] = f"{base_name} {prod.get('product_name', '')}".strip()
                                del merged["products"]
                                calculator = cls(merged)
                                calculators.append(calculator)
                                print(f"✅ {subfolder}/{filename} ({merged['bank_name']}) 계산기 로드 완료")
                        else:
                            calculator = cls(config_path)
                            calculators.append(calculator)
                            print(f"✅ {subfolder}/{filename} 계산기 로드 완료")
                    except Exception as e:
                        print(f"⚠️  계산기 로드 실패 ({subfolder}/{filename}): {e}")
                        continue
        
        # 모든 계산기 실행
        cls._ensure_price_input_snapshot(property_data)
        results = []
        for calculator in calculators:
            try:
                # OK저축은행인 경우 가계자금과 사업자금을 각각 계산
                is_ok_bank = calculator.bank_name == "OK저축은행" or "OK저축은행" in calculator.bank_name or "오케이저축은행" in calculator.bank_name
                
                if is_ok_bank:
                    # 가계자금 계산
                    household_result = calculator.calculate(property_data, product_type="household")
                    if household_result is not None and not cls._should_exclude_property_type_mismatch(household_result):
                        household_result["bank_name"] = "OK저축은행 가계자금"
                        results.append(household_result)
                    
                    # 사업자금 계산
                    business_result = calculator.calculate(property_data, product_type="business")
                    if business_result is not None and not cls._should_exclude_property_type_mismatch(business_result):
                        business_result["bank_name"] = "OK저축은행 사업자금"
                        results.append(business_result)
                else:
                    # 일반 금융사는 기존대로 계산
                    result = calculator.calculate(property_data)
                    if result is not None and not cls._should_exclude_property_type_mismatch(result):
                        # 취급 불가지역인 경우도 포함 (errors에 "취급 불가지역"이 있으면)
                        results.append(result)
            except Exception as e:
                print(f"계산기 {calculator.bank_name} 에러: {e}")
                continue
        
        # DSFNC: 하이론 한도가 디에스론보다 클 때만 둘 다 표시, 아니면 디에스론만
        results = cls._filter_dsfnc_results(results)
        
        return results

