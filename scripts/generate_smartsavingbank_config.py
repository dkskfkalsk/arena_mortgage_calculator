"""스마트저축은행 조견 JSON 생성 스크립트 (1회 실행용)"""
import json
import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MG_PATH = ROOT / "data" / "banks" / "1_MGcapital.json"
OUT_PATH = ROOT / "data" / "banks" / "8_smartsavingbank.json"

JEONBUK_GRADE9 = {
    "전북특별자치도완주군", "전북특별자치도진안군", "전북특별자치도무주군",
    "전북특별자치도장수군", "전북특별자치도임실군", "전북특별자치도순창군",
    "전북특별자치도고창군", "전북특별자치도부안군",
}
JEONNAM_GRADE9 = {
    "전라남도담양군", "전라남도곡성군", "전라남도구례군", "전라남도고흥군",
    "전라남도보성군", "전라남도화순군", "전라남도장흥군", "전라남도강진군",
    "전라남도해남군", "전라남도영암군", "전라남도무안군", "전라남도함평군",
    "전라남도영광군", "전라남도장성군", "전라남도완도군", "전라남도진도군",
    "전라남도신안군",
}


def rate_group_for(key: str) -> str:
    if key.startswith("서울특별시") or key.startswith("광주광역시") or key.startswith("전북특별자치도"):
        return "1"
    if key.startswith("경기도") or key.startswith("전라남도") or key.startswith("제주특별자치도") or key.startswith("인천광역시"):
        return "2"
    return "3"


def max_ltv_for(key: str) -> int:
    if key == "광주광역시동구":
        return 90
    if key.startswith("광주광역시"):
        return 95
    if "전주시" in key:
        return 90
    if any(x in key for x in ("군산시", "정읍시", "익산시")):
        return 85
    if any(x in key for x in ("김제시", "남원시")):
        return 80
    if key in JEONBUK_GRADE9:
        return 0
    if key.startswith("전북특별자치도"):
        return 90
    if any(x in key for x in ("목포시", "순천시")):
        return 90
    if any(x in key for x in ("나주시", "여수시", "광양시")):
        return 85
    if key in JEONNAM_GRADE9:
        return 0
    if key.startswith("전라남도"):
        return 90
    if key == "제주특별자치도제주시":
        return 85
    if key == "제주특별자치도서귀포시":
        return 80
    if key.startswith("서울특별시") or key.startswith("경기도"):
        return 95
    if key.startswith(("인천광역시", "대전광역시", "대구광역시", "부산광역시", "울산광역시")):
        return 90
    if key.startswith(("세종특별자치시", "충청남도", "충청북도", "경상남도", "경상북도", "강원특별자치도")):
        return 85
    return 95


def build_region_grades(mg_grades: dict) -> dict:
    out = {}
    keep9 = JEONBUK_GRADE9 | JEONNAM_GRADE9
    for k, v in mg_grades.items():
        if k in keep9:
            out[k] = 9
        elif v == 9:
            out[k] = 5
        else:
            out[k] = v
    return out


def rates_table(rows: list) -> dict:
    """rows: [(ltv, [g1..g8]), ...]  null -> None"""
    out = {}
    for ltv, grades in rows:
        out[str(ltv)] = {str(i + 1): (g if g != "X" else None) for i, g in enumerate(grades)}
    return out


# 선순위 금리
PRIMARY = {
    "1": rates_table([
        (70, [7.00, 7.50, 7.50, 7.70, 7.90, 8.40, 8.60, 8.60]),
        (75, [7.00, 7.50, 7.50, 7.70, 7.90, 8.40, 8.60, 8.60]),
        (80, [7.07, 7.59, 7.60, 7.81, 8.02, 8.55, 8.78, 9.67]),
        (85, [7.18, 7.74, 7.73, 7.96, 8.19, 8.78, 9.04, 10.06]),
        (90, [7.88, 8.50, 8.51, 8.75, 9.03, 9.72, 10.05, 11.34]),
        (95, [7.98, 8.62, 8.63, 8.89, 9.19, 9.93, 10.29, 11.70]),
    ]),
    "2": rates_table([
        (70, [7.50, 8.00, 8.00, 8.20, 8.40, 8.90, 9.10, 9.10]),
        (75, [7.50, 8.00, 8.00, 8.20, 8.40, 8.90, 9.10, 9.10]),
        (80, [7.69, 8.25, 8.26, 8.48, 8.72, 9.31, 9.58, 10.62]),
        (85, [7.79, 8.38, 8.38, 8.62, 8.88, 9.52, 9.82, 10.98]),
        (90, [7.88, 8.50, 8.51, 8.75, 9.03, 9.72, 10.05, 11.34]),
        (95, [7.98, 8.62, 8.63, 8.89, 9.19, 9.93, 10.29, 11.70]),
    ]),
    "3": rates_table([
        (70, [7.50, 8.00, 8.00, 8.20, 8.40, 8.90, 9.10, 9.10]),
        (75, [7.69, 8.25, 8.26, 8.48, 8.72, 9.31, 9.58, 10.62]),
        (80, [7.79, 8.38, 8.38, 8.62, 8.88, 9.52, 9.82, 10.98]),
        (85, [7.88, 8.50, 8.51, 8.75, 9.03, 9.72, 10.05, 11.34]),
        (90, [7.98, 8.62, 8.63, 8.89, 9.19, 9.93, 10.29, 11.70]),
        (95, [8.07, 8.75, 8.76, 9.03, 9.35, 10.13, 10.53, 12.06]),
    ]),
}

SUB_LTE55 = {
    "1": rates_table([
        (70, [7.00, 7.50, 7.50, 7.70, 7.90, 8.40, 8.60, 8.60]),
        (75, [7.00, 7.50, 7.50, 7.70, 7.90, 8.40, 8.60, 8.60]),
        (80, [7.00, 7.50, 7.51, 7.70, 7.90, 8.40, 8.60, 9.41]),
        (85, [7.36, 7.95, 7.97, 8.21, 8.47, 9.15, 9.48, 10.72]),
        (90, [8.36, 9.12, 9.14, 9.44, 9.82, 10.75, 11.24, 13.13]),
        (95, [8.45, 9.24, 9.26, 9.57, 9.79, 10.95, 11.48, "X"]),
    ]),
    "2": rates_table([
        (70, [7.50, 8.00, 8.00, 8.20, 8.40, 8.90, 9.10, 9.10]),
        (75, [7.50, 8.00, 8.00, 8.20, 8.40, 8.90, 9.10, 9.10]),
        (80, [7.88, 8.50, 8.51, 8.75, 9.03, 9.72, 10.05, 11.34]),
        (85, [8.17, 8.87, 8.89, 9.16, 9.50, 10.34, 10.77, 12.41]),
        (90, [8.36, 9.12, 9.14, 9.44, 9.82, 10.75, 11.24, 13.13]),
        (95, [8.45, 9.24, 9.26, 9.57, 9.97, 10.95, 11.48, "X"]),
    ]),
    "3": rates_table([
        (70, [7.50, 8.00, 8.00, 8.20, 8.40, 8.90, 9.10, 9.10]),
        (75, [7.98, 8.62, 8.63, 8.89, 9.19, 9.93, 10.29, 11.70]),
        (80, [8.26, 9.00, 9.01, 9.30, 9.66, 10.54, 11.00, 12.77]),
        (85, [8.45, 9.24, 9.26, 9.57, 9.97, 10.95, 11.48, "X"]),
        (90, [8.64, 9.49, 9.52, 9.85, 10.29, 11.36, 11.95, "X"]),
        (95, [8.74, 9.62, 9.64, 9.99, 10.45, 11.57, 12.19, "X"]),
    ]),
}

SUB_LTE65 = {
    "1": rates_table([
        (70, [7.00, 7.50, 7.50, 7.70, 7.90, 8.40, 8.60, 8.60]),
        (75, [7.00, 7.50, 7.50, 7.70, 7.90, 8.40, 8.60, 8.60]),
        (80, [7.04, 7.54, 7.55, 7.75, 7.95, 8.47, 8.69, 9.52]),
        (85, [7.48, 8.12, 8.13, 8.39, 8.69, 9.43, 9.79, "X"]),
        (90, [8.64, 9.49, 9.52, 9.85, 10.29, 11.36, 11.95, "X"]),
        (95, [8.83, 9.74, 9.77, 10.12, 10.60, 11.77, 12.43, "X"]),
    ]),
    "2": rates_table([
        (70, [7.50, 8.00, 8.00, 8.20, 8.40, 8.90, 9.10, 9.10]),
        (75, [7.50, 8.00, 8.00, 8.20, 8.40, 8.90, 9.10, 9.10]),
        (80, [8.17, 8.87, 8.89, 9.16, 9.50, 10.34, 10.77, 12.41]),
        (85, [8.45, 9.24, 9.26, 9.57, 9.97, 10.95, 11.48, "X"]),
        (90, [8.64, 9.49, 9.52, 9.85, 10.29, 11.36, 11.95, "X"]),
        (95, [8.83, 9.74, 9.77, 10.12, 10.60, 11.77, 12.43, "X"]),
    ]),
    "3": rates_table([
        (70, [7.50, 8.00, 8.00, 8.20, 8.40, 8.90, 9.10, 9.10]),
        (75, [8.45, 9.24, 9.26, 9.57, 9.97, 10.95, 11.48, "X"]),
        (80, [8.83, 9.74, 9.77, 10.12, 10.60, 11.77, 12.43, "X"]),
        (85, [8.93, 9.86, 9.89, 10.26, 10.76, 11.98, "X", "X"]),
        (90, [9.02, 9.99, 10.02, 10.40, 10.92, 12.18, "X", "X"]),
        (95, [9.12, 10.11, 10.15, 10.53, 11.07, 12.39, "X", "X"]),
    ]),
}

SUB_GT65 = {
    "1": rates_table([
        (70, [7.00, 7.50, 7.50, 7.70, 7.90, 8.40, 8.60, 8.60]),
        (75, [7.00, 7.50, 7.50, 7.70, 7.90, 8.40, 8.60, 8.60]),
        (80, [7.00, 7.50, 7.50, 7.70, 7.90, 8.40, 8.60, "X"]),
        (85, [7.91, 8.20, 8.22, 8.33, 8.53, 9.22, 9.56, "X"]),
        (90, [8.93, 9.86, 9.89, 10.26, 10.76, 11.98, "X", "X"]),
        (95, [9.02, 9.99, 10.02, 10.40, 10.92, 12.18, "X", "X"]),
    ]),
    "2": rates_table([
        (70, [7.50, 8.00, 8.00, 8.20, 8.40, 8.90, 9.10, 9.10]),
        (75, [7.50, 8.00, 8.00, 8.20, 8.40, 8.90, 9.10, 9.10]),
        (80, [8.86, 9.44, 9.48, 9.70, 10.10, 11.06, 11.71, "X"]),
        (85, [8.86, 9.74, 9.77, 10.12, 10.60, 11.77, 12.43, "X"]),
        (90, [8.93, 9.86, 9.89, 10.26, 10.76, 11.98, "X", "X"]),
        (95, [9.02, 9.99, 10.02, 10.40, 10.92, 12.18, "X", "X"]),
    ]),
    "3": rates_table([
        (70, [7.50, 8.00, 8.00, 8.20, 8.40, 8.90, 9.10, 9.10]),
        (75, [9.02, 9.99, 10.02, 10.40, 10.92, 12.18, "X", "X"]),
        (80, [9.12, 10.11, 10.15, 10.53, 11.07, 12.39, "X", "X"]),
        (85, [9.21, 10.24, 10.27, 10.67, 11.23, "X", "X", "X"]),
        (90, [9.31, 10.36, 10.40, 10.81, 11.39, "X", "X", "X"]),
        (95, [9.40, 10.48, 10.52, 10.94, 11.54, "X", "X", "X"]),
    ]),
}


def main():
    with open(MG_PATH, encoding="utf-8") as f:
        mg = json.load(f)

    region_grades = build_region_grades(mg["region_grades"])
    max_ltv_by_address = {}
    rate_region_group_by_address = {}
    for key in region_grades:
        if region_grades[key] != 9:
            max_ltv_by_address[key] = max_ltv_for(key)
            rate_region_group_by_address[key] = rate_group_for(key)

    interest_rates_by_region_group_priority_business = {}
    for g in ("1", "2", "3"):
        interest_rates_by_region_group_priority_business[g] = {
            "primary": {"regular": PRIMARY[g]},
        }

    subordinate_interest_rates_by_senior_ltv = {}
    for g in ("1", "2", "3"):
        subordinate_interest_rates_by_senior_ltv[g] = {
            "lte_55": SUB_LTE55[g],
            "lte_65": SUB_LTE65[g],
            "gt_65": SUB_GT65[g],
        }

    config = {
        "bank_name": "스마트저축은행",
        "refinance_self_aliases": ["스마트저축은행", "스마트저축"],
        "_comment_refinance_self_aliases": "마스터 대환 명단에서 자기만 제외할 때 사용.",
        "enabled": True,
        "_comment_enabled": "한도 산출 on/off",
        "use_principal_for_calculation": False,
        "fractional_share_request_enabled": False,
        "target_regions": mg["target_regions"] + ["대구", "세종"],
        "product_type": "business",
        "self_refinance_excluded": ["스마트저축은행", "스마트저축"],
        "_comment_self_refinance_excluded": "본인 금융사 대환 불가 - 후순위 추가대출로 처리",
        "region_grades": region_grades,
        "_comment_region_grades": "MG 구조 기반. 전북·전남 미지정 군만 9급지(취급불가). 그 외 MG 9급지는 5급지로 취급.",
        "max_ltv_by_address": max_ltv_by_address,
        "_comment_max_ltv_by_address": "주소(시군구)별 최대 LTV. region_grades 9급지는 미포함.",
        "rate_region_group_by_address": rate_region_group_by_address,
        "_comment_rate_region_group": "금리용 1·2·3급지. 1=서울·광주·전북, 2=경기·전남·제주·인천, 3=그 외",
        "ltv_steps": [95, 90, 85, 80, 75, 70],
        "ltv_bands_primary": [70, 75, 80, 85, 90, 95],
        "ltv_bands_subordinate": [70, 75, 80, 85, 90, 95],
        "_comment_ltv_bands": "LTV 구간: 요청 LTV 이하 최소 band 키 사용",
        "credit_score_to_grade": mg["credit_score_to_grade"],
        "max_credit_grade": 8,
        "interest_rates_by_region_group_priority_business": interest_rates_by_region_group_priority_business,
        "subordinate_interest_rates_by_senior_ltv": subordinate_interest_rates_by_senior_ltv,
        "_comment_subordinate_senior_ltv": "후순위: 선순위 LTV ≤55% → lte_55, 55%<≤65% → lte_65, >65% → gt_65",
        "senior_ltv_tier_thresholds": {"lte_55": 55, "lte_65": 65},
        "min_amount": 3000,
        "max_amount_limit": 200000,
        "_comment_max_amount_limit": "최대 한도 20억원",
        "min_kb_price": 15000,
        "_comment_min_kb_price": "시세 1.5억원 미만 취급 불가",
        "price_sources": {
            "kb_price": 1,
            "kb_ai_price": 0,
            "bank_appraisal_price": 1,
            "realestatetech_price": 1,
            "korea_realestate_price": 0,
            "housematch_price": 0,
        },
        "business_property_types": {
            "apartment": 1,
            "apartment_no_land_registry": 1,
            "residential_commercial": 1,
            "villa": 0,
            "officetel": 0,
            "detached_house": 0,
            "multi_family_house": 0,
        },
        "conditions": [
            "실사업자 매출증빙필수 / 전북,전남,광주,제주보물건 또는 사업장소재지 필수조건"
        ],
        "amount_condition_threshold": 50000,
        "amount_condition_message": "*5억 초과건 실사업자 현장조사 대상입니다.",
        "lower_bound_price": {
            "enabled": True,
            "apartment": {"rules": [{"lower_bound_floors": [1, 2, 3]}]},
            "residential_commercial": {"rules": [{"lower_bound_floors": [1, 2, 3]}]},
            "apartment_no_land_registry": {"rules": [{"lower_bound_floors": [1, 2, 3]}]},
            "description": "아파트/주상복합/대지권미등기 — 1~3층 하한가",
        },
        "show_interest_rate_range": False,
        "validation_rules": copy.deepcopy(mg["validation_rules"]),
        "corporate_business_restriction": {"enabled": True},
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"Wrote {OUT_PATH} ({len(region_grades)} regions)")


if __name__ == "__main__":
    main()
