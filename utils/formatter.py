# -*- coding: utf-8 -*-
"""
결과 포맷팅 유틸리티
"""

from typing import Dict, List, Any, Optional, Tuple


def format_interest_rate(
    interest_rate: Optional[float],
    interest_rate_range: Optional[Tuple[float, float]]
) -> str:
    """
    금리 포맷팅
    - 신용점수 있을 때: "6.65%"
    - 신용점수 없을 때: "6.20%~10.70%"
    """
    if interest_rate is not None:
        return f"{interest_rate:.2f}%"
    elif interest_rate_range is not None:
        min_rate, max_rate = interest_rate_range
        return f"{min_rate:.2f}%~{max_rate:.2f}%"
    else:
        return "금리 정보 없음"


def format_amount(amount: float) -> str:
    """
    금액 포맷팅 (만원 단위)
    예: 49300 -> "49,300만"
    """
    return f"{int(amount):,}만"


def format_result(bank_result: Dict[str, Any]) -> str:
    """
    결과 포맷팅
    
    예:
    * BNK캐피탈 (4등급기준)
    후순위 74% 43,900만 / 6.65%
    """
    bank_name = bank_result.get("bank_name", "Unknown")
    results = bank_result.get("results", [])
    conditions = bank_result.get("conditions", [])
    errors = bank_result.get("errors", [])
    
    # 취급 불가지역인 경우
    if errors and "취급 불가지역" in errors:
        return f"* {bank_name}\n취급 불가지역"
    
    # 가용 한도 부족 등 에러가 있는 경우
    if errors and len(errors) > 0:
        error_msg = "\n".join(errors)
        return f"* {bank_name}\n{error_msg}"
    
    if not results:
        return f"* {bank_name}\n산출 불가"
    
    # 모든 결과가 최소진행금액 부족(3천만원 미만)인지 확인
    # 대환인 경우: total_amount(전체 대출 금액) 기준
    # 후순위인 경우: amount 기준
    all_below_minimum = all(
        (result.get("total_amount") if result.get("is_refinance", False) else result.get("amount", 0)) < 3000
        for result in results
    )
    if all_below_minimum:
        # 첫 번째 결과의 신용등급 확인
        first_result = results[0]
        credit_grade = first_result.get("credit_grade")
        
        # 헤더 (신용등급이 있으면 표시)
        if credit_grade:
            header = f"* {bank_name} ({credit_grade}등급기준)"
        else:
            header = f"* {bank_name}"
        
        return f"{header}\n최소진행금액 부족으로 진행 어렵습니다"
    
    # 첫 번째 결과의 신용등급 확인
    first_result = results[0]
    credit_grade = first_result.get("credit_grade")
    
    # 헤더 (신용등급이 있으면 표시)
    if credit_grade:
        header = f"* {bank_name} ({credit_grade}등급기준)"
    else:
        header = f"* {bank_name}"
    
    lines = [header]
    
    for result in results:
        ltv = result.get("ltv", 0)
        amount = result.get("amount", 0)
        interest_rate = result.get("interest_rate")
        interest_rate_range = result.get("interest_rate_range")
        result_type = result.get("type", "후순위")
        is_refinance = result.get("is_refinance", False)
        
        # 금리 포맷팅
        rate_str = format_interest_rate(interest_rate, interest_rate_range)
        
        # 금액 포맷팅
        amount_str = format_amount(amount)
        
        # LTV 포맷팅 (소수점이 있으면 표시, 없으면 정수로)
        if isinstance(ltv, float) and ltv % 1 != 0:
            ltv_str = f"{ltv:.2f}%"
        else:
            ltv_str = f"{int(ltv)}%"
        
        # 대환인 경우 전체 금액과 가용한도 표시
        if is_refinance:
            total_amount = result.get("total_amount", 0)
            available_amount = result.get("available_amount", 0)
            line = f"{result_type} {ltv_str} {format_amount(total_amount)} / {rate_str} / 가용 {format_amount(available_amount)}"
        else:
            line = f"{result_type} {ltv_str} {amount_str} / {rate_str}"
        
        # 기준 LTV 이하 지역인 경우 메시지 추가
        below_standard_ltv = result.get("below_standard_ltv", False)
        if below_standard_ltv:
            line += " (기준 LTV이하 지역, 낙찰가율이내로 제한)"
        
        # 택시 한도 제한인 경우 메시지 추가
        taxi_limit_applied = result.get("taxi_limit_applied", False)
        if taxi_limit_applied:
            line += " (개인택시, 운수업 1억 제한)"
        
        # 3천만원 미만이면 "최소진행금액 부족" 메시지 추가
        if amount < 3000:
            line += " (최소진행금액 부족)"
        
        lines.append(line)
    
    # 특이 조건 추가
    if conditions:
        for condition in conditions[:3]:  # 최대 3개만 표시
            lines.append(f"- {condition}")
    
    return "\n".join(lines)


def format_all_results(
    all_results: List[Dict[str, Any]]
) -> str:
    """
    모든 금융사 결과를 포맷팅
    
    Args:
        all_results: 모든 금융사 계산 결과 리스트
    
    Returns:
        포맷팅된 문자열
    """
    if not all_results:
        return "산출 가능한 금융사가 없습니다.\n\n※ KB시세가 없으면 산출이 불가능합니다."
    
    formatted_results = []
    
    for bank_result in all_results:
        formatted = format_result(bank_result)
        formatted_results.append(formatted)
    
    return "\n\n".join(formatted_results)

