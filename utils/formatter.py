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
    
    if not results:
        return f"* {bank_name}\n산출 불가"
    
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
        
        # 대환인 경우 전체 금액과 가용한도 표시
        if is_refinance:
            total_amount = result.get("total_amount", 0)
            available_amount = result.get("available_amount", 0)
            line = f"{result_type} {ltv}% {format_amount(total_amount)}만 / 가용 {format_amount(available_amount)}만 / {rate_str}"
        else:
            line = f"{result_type} {ltv}% {amount_str} / {rate_str}"
        
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

