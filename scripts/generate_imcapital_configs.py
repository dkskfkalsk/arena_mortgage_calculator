"""IM캐피탈 SOHO주택론·SOHO아파트론 config 생성"""
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
BANKS = os.path.join(ROOT, "data", "banks")

# MG region_grades 기반 9급지 목록 (취급불가용)
with open(os.path.join(BANKS, "1_MGcapital.json"), encoding="utf-8") as f:
    MG = json.load(f)
ALL_MG_KEYS = set(MG["region_grades"].keys())

SEOUL_GU = [
    "강남구", "강동구", "강북구", "강서구", "도봉구", "동대문구", "동작구", "마포구",
    "송파구", "양천구", "영등포구", "용산구", "관악구", "광진구", "구로구", "노원구",
    "서대문구", "서초구", "성동구", "성북구", "은평구", "종로구", "중구", "중랑구", "금천구",
]

GRADE_1A = {f"서울특별시{g}": "1A" for g in SEOUL_GU}

GRADE_1B_KEYS = [
    "경기도고양시덕양구", "경기도고양시일산동구",
    "경기도수원시장안구", "경기도수원시권선구", "경기도수원시팔달구", "경기도수원시영통구",
    "경기도광명시", "경기도부천시소사구", "경기도부천시원미구",
    "경기도성남시분당구", "경기도성남시수정구", "경기도성남시중원구",
    "경기도구리시", "경기도군포시", "경기도김포시", "경기도화성시",
    "경기도안산시단원구", "경기도안양시동안구",
    "경기도용인시기흥구", "경기도용인시수지구", "경기도하남시",
    "인천광역시남동구", "인천광역시검단구", "인천광역시서해구",
    "인천광역시부평구", "인천광역시연수구",
    "세종특별자치시세종시",
]

GRADE_2_KEYS = [
    "경기도고양시일산서구", "경기도부천시오정구", "경기도안산시상록구",
    "경기도안양시만안구", "경기도용인시처인구", "경기도양주시", "경기도여주시",
    "경기도광주시", "경기도남양주시", "경기도오산시", "경기도시흥시",
    "경기도의정부시", "경기도파주시", "경기도의왕시", "경기도포천시",
    "인천광역시계양구",
]

# 5대 광역시 (MG region_grades에서 해당 시·구 추출)
METRO_PREFIXES = ("부산광역시", "대구광역시", "광주광역시", "전남광주통합특별시", "대전광역시", "울산광역시")
for key in ALL_MG_KEYS:
    if any(key.startswith(p) for p in METRO_PREFIXES):
        if key not in GRADE_1A and key not in set(GRADE_1B_KEYS):
            GRADE_2_KEYS.append(key)

GRADE_3_KEYS = ["경기도이천시", "경기도안성시"]
GRADE_4_KEYS = [
    "경기도동두천시", "경기도과천시", "경기도평택시",
    "인천광역시영종구", "인천광역시제물포구",
]

region_grades_jutaek = dict(GRADE_1A)
for k in GRADE_1B_KEYS:
    region_grades_jutaek[k] = "1B"
for k in GRADE_2_KEYS:
    if k not in region_grades_jutaek:
        region_grades_jutaek[k] = "2"
for k in GRADE_3_KEYS:
    region_grades_jutaek[k] = "3"
for k in GRADE_4_KEYS:
    region_grades_jutaek[k] = "4"
for k in ALL_MG_KEYS:
    if k not in region_grades_jutaek:
        region_grades_jutaek[k] = 9

max_ltv_by_region_credit_grade = {
    "1A": {"1": 90, "2": 90, "3": 90, "4": 90, "5": 85, "6": 85, "7": 70},
    "1B": {"1": 85, "2": 85, "3": 85, "4": 85, "5": 80, "6": 75, "7": 70},
    "2": {"1": 80, "2": 80, "3": 80, "4": 80, "5": 80, "6": 80, "7": 80},
    "3": {"1": 75, "2": 75, "3": 75, "4": 75, "5": 75, "6": 75, "7": 75},
    "4": {"1": 70, "2": 70, "3": 70, "4": 70, "5": 70, "6": 70, "7": 70},
    "9": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0},
}

INTEREST_JUTAEK = {
    "1": {
        70: [7.87, 8.08, 8.55, 9.07, 9.29, 9.86, 10.36],
        75: [8.17, 8.38, 8.85, 9.47, 9.69, 10.26, 10.76],
        80: [8.57, 8.78, 9.25, 9.67, 9.89, 10.46, 10.96],
        85: [9.37, 9.58, 10.05, 10.77, 10.99, 11.56, 12.06],
        90: [9.87, 10.08, 10.55, 11.27, 11.49, 12.06, 12.56],
    },
    "2": {
        70: [8.57, 8.78, 9.25, 9.77, 9.99, 10.56, 11.06],
        75: [8.87, 9.08, 9.55, 10.17, 10.39, 10.96, 11.46],
        80: [9.27, 9.48, 9.95, 10.37, 10.59, 11.16, 11.66],
        85: [10.07, 10.28, 10.75, 11.47, 11.69, 12.26, 12.76],
        90: [10.57, 10.78, 11.25, 11.97, 12.19, 12.76, 13.26],
    },
    "3": {
        70: [8.87, 9.08, 9.55, 10.07, 10.29, 10.86, 11.36],
        75: [9.17, 9.38, 9.85, 10.47, 10.69, 11.26, 11.76],
        80: [9.57, 9.78, 10.25, 10.67, 10.89, 11.46, 11.96],
        85: [10.37, 10.58, 11.05, 11.77, 11.99, 12.56, 13.06],
        90: [10.87, 11.08, 11.55, 12.27, 12.49, 13.06, 13.56],
    },
    "4": {
        70: [8.87, 9.08, 9.55, 10.07, 10.29, 10.86, 11.36],
        75: [9.17, 9.38, 9.85, 10.47, 10.69, 11.26, 11.76],
        80: [9.57, 9.78, 10.25, 10.67, 10.89, 11.46, 11.96],
        85: [10.37, 10.58, 11.05, 11.77, 11.99, 12.56, 13.06],
        90: [10.87, 11.08, 11.55, 12.27, 12.49, 13.06, 13.56],
    },
}


def rates_dict(ltv_rates: dict) -> dict:
    out = {}
    for ltv, grades in ltv_rates.items():
        out[str(ltv)] = {str(i + 1): r for i, r in enumerate(grades)}
    return out


def build_interest_jutaek():
    groups = {}
    for g, ltv_map in INTEREST_JUTAEK.items():
        rd = rates_dict(ltv_map)
        groups[g] = {
            "primary": {"regular": rd},
            "subordinate": {"regular": rd},
        }
    return groups


INTEREST_APART = {
    "1": {  # 서울
        70: [10.50, 10.71, 11.58, 11.80, 12.42, 12.99, 13.89],
        75: [10.70, 10.91, 11.78, 12.00, 12.62, 13.19, 14.09],
        80: [11.10, 11.31, 12.18, 12.40, 13.02, 13.59, 14.39],
        85: [11.90, 12.11, 12.98, 13.20, 13.82, 14.39, 14.89],
        90: [12.30, 12.52, 13.18, 13.40, 13.82, 14.39, 14.89],
        95: [12.70, 12.91, 13.38, 13.60, 13.82, 14.39, 14.89],
    },
    "2": {  # 경기
        70: [10.80, 11.01, 11.88, 12.10, 12.72, 13.29, 14.19],
        75: [11.00, 11.21, 12.08, 12.30, 12.92, 13.49, 14.39],
        80: [11.40, 11.61, 12.48, 12.70, 13.32, 13.89, 14.69],
        85: [12.20, 12.41, 13.28, 13.50, 14.12, 14.69, 15.19],
        90: [12.60, 12.81, 13.48, 13.70, 14.12, 14.69, 15.19],
        95: [13.00, 13.21, 13.68, 13.90, 14.12, 14.69, 15.19],
    },
    "3": {  # 인천·세종
        70: [11.30, 11.51, 12.38, 12.60, 13.22, 13.79, 14.69],
        75: [11.50, 11.71, 12.58, 12.80, 13.42, 13.99, 14.89],
        80: [11.90, 12.11, 12.98, 13.20, 13.82, 14.39, 15.19],
        85: [12.70, 12.91, 13.78, 14.00, 14.62, 15.19, 15.69],
        90: [13.10, 13.31, 13.98, 14.20, 14.62, 15.19, 15.69],
        95: [13.50, 13.71, 14.18, 14.40, 14.62, 15.19, 15.69],
    },
    "4": {  # 광역시·그외
        70: [11.30, 11.51, 12.38, 12.60, 13.22, 13.79, 14.69],
        75: [11.50, 11.71, 12.58, 12.80, 13.42, 13.99, 14.89],
        80: [11.90, 12.11, 12.98, 13.20, 13.82, 14.39, 15.19],
        85: [12.70, 12.91, 13.78, 14.00, 14.62, 15.19, 15.69],
        90: [13.10, 13.31, 13.98, 14.20, 14.62, 15.19, 15.69],
        95: [13.50, 13.71, 14.18, 14.40, 14.62, 15.19, 15.69],
    },
}


def build_interest_apart():
    groups = {}
    for g, ltv_map in INTEREST_APART.items():
        rd = rates_dict(ltv_map)
        groups[g] = {
            "primary": {"regular": rd},
            "subordinate": {"regular": rd},
        }
    return groups


COMMON_LOWER_BOUND = {
    "enabled": True,
    "apartment": {
        "rules": [
            {"total_floors_min": 3, "lower_bound_floors": [1, 2]},
            {"total_floors_max": 2, "lower_bound_floors": [1]},
        ]
    },
    "residential_commercial": {
        "rules": [
            {"total_floors_min": 3, "lower_bound_floors": [1, 2]},
            {"total_floors_max": 2, "lower_bound_floors": [1]},
        ]
    },
    "officetel": {
        "rules": [
            {"total_floors_min": 3, "lower_bound_floors": [1, 2]},
            {"total_floors_max": 2, "lower_bound_floors": [1]},
        ]
    },
    "description": "3층 이상 1~2층 하한가, 2층 이하 1층 하한가",
}

COMMON_VALIDATION = {
    "enabled": True,
    "occupation_requirements": {
        "required_keywords": ["사업자", "사업자보유"],
        "forbidden_keywords": [],
        "error_message": "사업자 또는 사업자보유인 경우만 취급 가능합니다 (현재 직업: '{occupation}')",
        "check_fields": ["occupation", "special_notes", "requests"],
    },
    "restricted_keywords": {
        "check_fields": ["special_notes", "requests"],
        "keywords": ["제3자 담보", "별도등기", "압류", "가등기", "가압류"],
        "error_message": "특이사항/요청사항에 '{keywords}'가 포함되어 취급 불가합니다",
        "_comment": "별도등기 포함 시 취급 불가 (등기부 파싱 시 '별도등기 있음'으로 special_notes 유입)",
    },
    "complex_rules": [],
}

COMMON_BASE = {
    "refinance_self_aliases": ["IM캐피탈", "아이엠캐피탈"],
    "_comment_refinance_self_aliases": "마스터 대환 명단에서 자기만 제외할 때 사용. business_product_names 미지정 시 적용.",
    "enabled": True,
    "_comment_enabled": "한도 산출 on/off. false면 calculate_all_banks에서 이 금융사 제외",
    "use_principal_for_calculation": False,
    "_comment_use_principal_for_calculation": "레거시(무시): 선순위 차감은 항상 채권최고, 대환 상환액만 원금. base_calculator 고정",
    "fractional_share_request_enabled": False,
    "_comment_fractional_share_request_enabled": "요청에 지분조건 있을 때 이 금융사만 최대 LTV 50%·최소 1000만 적용",
    "product_type": "business",
    "self_refinance_excluded": ["IM캐피탈", "아이엠캐피탈"],
    "_comment_self_refinance_excluded": "본인 금융사 대환 불가 - 후순위 추가대출로 처리",
    "credit_score_to_grade": {
        "915-1000": 1,
        "875-914": 2,
        "840-874": 3,
        "780-839": 4,
        "745-779": 5,
        "680-744": 6,
        "580-679": 7,
        "440-579": 8,
    },
    "max_credit_grade": 7,
    "max_age": 65,
    "_comment_max_age": "차주 만65세 초과 취급 불가 (담보제공자 나이제한 없음)",
    "max_age_error_message": "*차주 기준 만65세 초과 진행 불가(담보제공 나이제한 없음)",
    "corporate_business_restriction": {
        "enabled": False,
        "keywords": ["법인사업자", "법인"],
        "comment": "법인사업자 취급 불가",
        "_comment": "enabled false = 키워드 발견 시 취급 불가",
    },
    "_comment_corporate_business_restriction": "enabled true = 법인사업자 취급 가능, false = 취급 불가(키워드 검사)",
    "show_interest_rate_range": False,
    "validation_rules": COMMON_VALIDATION,
    "promotions": [],
}

jutaek = {
    **COMMON_BASE,
    "bank_name": "IM캐피탈_SOHO주택론",
    "conditions": [
        "*만기일시상환(3년)",
    ],
    "household_condition_lt": 100,
    "household_condition_message": "*100세대미만, 공시지가 10억 이하 취급 불가",
    "_comment_household_condition": "세대수 100미만일 때 한도 산출 결과에 주석 추가 (거절 아님)",
    "target_regions": ["서울", "경기", "인천", "부산", "광주", "대전", "울산", "대구", "세종"],
    "region_grades": region_grades_jutaek,
    "_comment_region_grades": "1A=서울(90%), 1B=수도권1급지(85%), 2=2급지(80%), 3=3급지(75%), 4=4급지(70%), 9=취급불가",
    "max_ltv_by_region_credit_grade": max_ltv_by_region_credit_grade,
    "_comment_max_ltv_by_region_credit_grade": "급지 x 신용등급별 최대 LTV. min(급지상한,신용상한) 반영값. 신용없음 시 1등급 키(지역별 최대 LTV) 사용",
    "region_grade_to_group": {
        "1A": "1",
        "1B": "1",
        "2": "2",
        "3": "3",
        "4": "4",
    },
    "ltv_steps": [90, 85, 80, 75, 70],
    "ltv_bands_primary": [70, 75, 80, 85, 90],
    "ltv_bands_subordinate": [70, 75, 80, 85, 90],
    "_comment_ltv_bands": "선·후순위 동일 금리. LTV 구간 band 매칭",
    "interest_rates_by_region_group_priority_business": build_interest_jutaek(),
    "_comment_interest_structure": "급지그룹(1~4) x LTV(70~90) x 신용등급. 선·후순위 동일",
    "min_amount": 5000,
    "max_amount_limit": 150000,
    "_comment_max_amount_limit": "최대 한도 15억원",
    "min_kb_price": 30000,
    "_comment_min_kb_price": "물건 시세 3억원 이상",
    "price_sources": {
        "_comment": "시세 소스 사용 여부 설정 (1: 사용, 0: 사용안함). 우선순위: kb_price > kb_ai_price > bank_appraisal_price > realestatetech_price > korea_realestate_price > housematch_price",
        "kb_price": 1,
        "_comment_kb_price": "KB시세",
        "kb_ai_price": 0,
        "_comment_kb_ai_price": "KB AI시세",
        "bank_appraisal_price": 0,
        "_comment_bank_appraisal_price": "탁감가 (은행감정가)",
        "realestatetech_price": 1,
        "_comment_realestatetech_price": "부동산테크 시세",
        "korea_realestate_price": 0,
        "_comment_korea_realestate_price": "한국부동산원 시세",
        "housematch_price": 0,
        "_comment_housematch_price": "하우스머치 시세",
    },
    "business_property_types": {
        "_comment": "사업자금 상품 취급 물건 타입 설정 (1: 취급, 0: 취급안함)",
        "apartment": 1,
        "apartment_no_land_registry": 0,
        "_comment_apartment_no_land_registry": "아파트 (대지권 미등기) 취급 불가",
        "residential_commercial": 1,
        "_comment_residential_commercial": "주상복합",
        "villa": 0,
        "_comment_villa": "빌라",
        "officetel": 0,
        "_comment_officetel": "오피스텔",
        "detached_house": 0,
        "_comment_detached_house": "단독주택",
        "multi_family_house": 0,
        "_comment_multi_family_house": "공동주택",
    },
    "lower_bound_price": COMMON_LOWER_BOUND,
}

apart = {
    **COMMON_BASE,
    "bank_name": "IM캐피탈_SOHO아파트론",
    "conditions": [
        "*고정금리 원리금균등상환(최대84개월)",
    ],
    "target_regions": [
        "서울", "경기", "인천", "부산", "광주", "대전", "울산",
        "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주", "대구", "세종",
    ],
    "region_grade_prefix_rules": [
        {"starts_with": "서울특별시", "grade": 1},
        {"starts_with": "경기도", "grade": 2},
        {"starts_with": "인천광역시", "grade": 3},
        {"starts_with": "세종특별자치시", "grade": 3},
        {"starts_with": "부산광역시", "grade": 4},
        {"starts_with": "대구광역시", "grade": 4},
        {"starts_with": "광주광역시", "grade": 4},
        {"starts_with": "전남광주통합특별시", "grade": 4},
        {"starts_with": "대전광역시", "grade": 4},
        {"starts_with": "울산광역시", "grade": 4},
        {"starts_with": "", "grade": 5},
    ],
    "_comment_region_grade_prefix_rules": "1=서울, 2=경기, 3=인천·세종, 4=광역시(인천제외), 5=그외. LTV용 급지(광역시/그외 분리)",
    "_comment_max_ltv_by_grade_property_type": "물건유형 x 급지별 최대 LTV. 아파트·주상복합: 1·2=95, 3·4=90, 5=85 / 그외물건: 1·2=90, 3·4=85, 5=70",
    "max_ltv_by_grade_property_type": {
        "apartment": {"1": 95, "2": 95, "3": 90, "4": 90, "5": 85},
        "residential_commercial": {"1": 95, "2": 95, "3": 90, "4": 90, "5": 85},
        "villa": {"1": 90, "2": 90, "3": 85, "4": 85, "5": 70},
        "multi_family_house": {"1": 90, "2": 90, "3": 85, "4": 85, "5": 70},
        "officetel": {"1": 90, "2": 90, "3": 85, "4": 85, "5": 70},
    },
    "region_grade_to_group": {
        "1": "1",
        "2": "2",
        "3": "3",
        "4": "4",
        "5": "4"
    },
    "_comment_region_grade_to_group": "급지→금리그룹. 5급지(그외)는 금리그룹4(광역시·그외)",
    "rate_region_group_prefix_rules": [
        {"starts_with": "서울특별시", "group": "1"},
        {"starts_with": "경기도", "group": "2"},
        {"starts_with": "인천광역시", "group": "3"},
        {"starts_with": "세종특별자치시", "group": "3"},
        {"starts_with": "부산광역시", "group": "4"},
        {"starts_with": "대구광역시", "group": "4"},
        {"starts_with": "광주광역시", "group": "4"},
        {"starts_with": "전남광주통합특별시", "group": "4"},
        {"starts_with": "대전광역시", "group": "4"},
        {"starts_with": "울산광역시", "group": "4"},
        {"starts_with": "", "group": "4"},
    ],
    "_comment_rate_region_group": "금리 1=서울, 2=경기, 3=인천·세종, 4=광역시·그외(인천제외)",
    "ltv_steps": [95, 90, 85, 80, 75, 70],
    "ltv_bands_primary": [70, 75, 80, 85, 90, 95],
    "ltv_bands_subordinate": [70, 75, 80, 85, 90, 95],
    "interest_rates_by_region_group_priority_business": build_interest_apart(),
    "_comment_interest_structure": "지역그룹(1~4) x LTV(70~95) x 신용등급. 선·후순위 동일",
    "min_amount": 2000,
    "max_amount_limit": 10000,
    "_comment_max_amount_limit": "최대 한도 1억원",
    "min_kb_price": 8000,
    "_comment_min_kb_price": "물건 시세 8천만원 이상",
    "price_sources": {
        "_comment": "시세 소스 사용 여부 설정 (1: 사용, 0: 사용안함). 우선순위: kb_price > kb_ai_price > bank_appraisal_price > realestatetech_price > korea_realestate_price > housematch_price",
        "kb_price": 1,
        "_comment_kb_price": "KB시세",
        "kb_ai_price": 0,
        "_comment_kb_ai_price": "KB AI시세",
        "bank_appraisal_price": 1,
        "_comment_bank_appraisal_price": "탁감가 (은행감정가)",
        "realestatetech_price": 0,
        "_comment_realestatetech_price": "부동산테크 시세",
        "korea_realestate_price": 0,
        "_comment_korea_realestate_price": "한국부동산원 시세",
        "housematch_price": 0,
        "_comment_housematch_price": "하우스머치 시세",
    },
    "business_property_types": {
        "_comment": "사업자금 상품 취급 물건 타입 설정 (1: 취급, 0: 취급안함)",
        "apartment": 1,
        "apartment_no_land_registry": 0,
        "_comment_apartment_no_land_registry": "아파트 (대지권 미등기) 취급 불가",
        "residential_commercial": 1,
        "_comment_residential_commercial": "주상복합",
        "villa": 1,
        "_comment_villa": "연립주택",
        "officetel": 1,
        "_comment_officetel": "오피스텔",
        "detached_house": 0,
        "_comment_detached_house": "단독주택",
        "multi_family_house": 1,
        "_comment_multi_family_house": "다세대주택",
    },
    "lower_bound_price": COMMON_LOWER_BOUND,
}

for name, cfg in [
    ("2_IMcapital_SOHO주택론.json", jutaek),
    ("2_IMcapital_SOHO아파트론.json", apart),
]:
    path = os.path.join(BANKS, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"Written {path}")

# 구버전 파일명 잔존 시 중복 산출 방지를 위해 제거
for obsolete in ("9_IMcapital_SOHO주택론.json", "10_IMcapital_SOHO아파트론.json"):
    obsolete_path = os.path.join(BANKS, obsolete)
    if os.path.exists(obsolete_path):
        os.remove(obsolete_path)
        print(f"Removed obsolete {obsolete_path}")
