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
    * BNK캐피탈 (4등급기준) (하한가 적용)
    후순위 74% 43,900만 / 6.65%
    """
    bank_name = bank_result.get("bank_name", "Unknown")
    results = bank_result.get("results", [])
    conditions = bank_result.get("conditions", [])
    errors = bank_result.get("errors", [])
    min_amount = bank_result.get("min_amount", 3000)  # 기본값 3000만원
    lower_bound_applied = bank_result.get("lower_bound_applied", False)  # 하한가 적용 여부
    
    # 하한가 적용 표시 문자열
    lower_bound_suffix = " (하한가 적용)" if lower_bound_applied else ""
    
    # 취급 불가지역인 경우
    if errors and "취급 불가지역" in errors:
        return f"* {bank_name}\n취급 불가지역"
    
    # 가용 한도 부족 등 에러가 있는 경우
    if errors and len(errors) > 0:
        error_msg = "\n".join(errors)
        return f"* {bank_name}\n{error_msg}"
    
    if not results:
        return f"* {bank_name}\n산출 불가"
    
    # 모든 결과가 최소진행금액 부족인지 확인
    # 대환인 경우: total_amount(전체 대출 금액) 기준
    # 후순위인 경우: amount 기준
    all_below_minimum = all(
        (result.get("total_amount") if result.get("is_refinance", False) else result.get("amount", 0)) < min_amount
        for result in results
    )
    if all_below_minimum:
        # 첫 번째 결과의 신용등급 확인
        first_result = results[0]
        credit_grade = first_result.get("credit_grade")
        
        # 헤더 (신용등급이 있으면 표시)
        if credit_grade:
            header = f"* {bank_name} ({credit_grade}등급기준){lower_bound_suffix}"
        else:
            header = f"* {bank_name}{lower_bound_suffix}"
        
        return f"{header}\n최소진행금액 부족으로 진행 어렵습니다"
    
    # 첫 번째 결과의 신용등급 확인
    first_result = results[0]
    credit_grade = first_result.get("credit_grade")
    
    # 헤더 (신용등급이 있으면 표시)
    if credit_grade:
        header = f"* {bank_name} ({credit_grade}등급기준){lower_bound_suffix}"
    else:
        header = f"* {bank_name}{lower_bound_suffix}"
    
    lines = [header]
    
    # 고정금리 코멘트 확인 (모든 결과 중 하나라도 있으면 맨 끝에 표시)
    fixed_rate_comment = None
    for result in results:
        comment = result.get("fixed_rate_comment")
        if comment:
            fixed_rate_comment = comment
            break  # 첫 번째로 찾은 코멘트 사용 (모든 결과가 같은 코멘트를 가지므로)
    
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
            refinance_institutions = result.get("refinance_institutions")
            if refinance_institutions:
                # 가계자금 대환 시 대환하는 금융사 이름 표시
                institutions_str = ", ".join(refinance_institutions)
                line = f"{result_type} {ltv_str} {format_amount(total_amount)} / {rate_str} / 가용 {format_amount(available_amount)} ({institutions_str} 대환)"
            else:
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
        
        # 최소진행금액 미만이면 "최소진행금액 부족" 메시지 추가 (대환인 경우는 제외)
        if not is_refinance and amount < min_amount:
            line += " (최소진행금액 부족)"
        
        lines.append(line)
    
    # 고정금리 코멘트를 맨 끝에 한 번만 추가
    if fixed_rate_comment:
        lines.append(fixed_rate_comment)
    
    # MG캐피탈 프로모션 미적용 사유 표시 (1,2급지인데 미적용인 경우)
    promotion_rejection_reason = bank_result.get("promotion_rejection_reason")
    if promotion_rejection_reason and "MG캐피탈" in bank_name:
        lines.append(f"(프로모션 미적용: {promotion_rejection_reason})")
    
    # 특이 조건 추가
    if conditions:
        for condition in conditions[:3]:  # 최대 3개만 표시
            lines.append(f"- {condition}")
    
    return "\n".join(lines)


def format_all_results(
    all_results: List[Dict[str, Any]],
    property_data: Optional[Dict[str, Any]] = None
) -> str:
    """
    모든 금융사 결과를 포맷팅
    
    Args:
        all_results: 모든 금융사 계산 결과 리스트
        property_data: 파싱된 담보물건 정보 (근저당권 정보 포함, 선택적)
    
    Returns:
        포맷팅된 문자열
    """
    if not all_results:
        return "산출 가능한 금융사가 없습니다.\n\n※ KB시세가 없으면 산출이 불가능합니다."
    
    # 개인설정이 있는 경우: 후순위 취급 불가 안내만 표시
    if any(r.get("personal_mortgage_ineligible") for r in all_results):
        return "개인설정 후순위는 취급 불가"
    
    # 전체 결과에서 대환/후순위 여부 및 대환하는 기관 목록 확인
    all_refinance_results = []
    all_subordinate_results = []
    all_refinance_institutions_set = set()
    
    for bank_result in all_results:
        results = bank_result.get("results", [])
        if not results:
            continue
        
        # 각 결과의 대환 여부 확인
        for result in results:
            is_refinance = result.get("is_refinance", False)
            if is_refinance:
                all_refinance_results.append(bank_result)
                # 대환하는 기관 목록 수집
                refinance_institutions = result.get("refinance_institutions")
                if refinance_institutions:
                    if isinstance(refinance_institutions, list):
                        all_refinance_institutions_set.update(refinance_institutions)
                    else:
                        all_refinance_institutions_set.add(str(refinance_institutions))
            else:
                all_subordinate_results.append(bank_result)
    
    # 순위 계산
    priority_text = ""
    if property_data:
        mortgages = property_data.get("mortgages", [])
        if mortgages:
            # 대환하는 근저당권 확인
            refinance_mortgages = [m for m in mortgages if m.get("is_refinance", False)]
            remaining_mortgages = [m for m in mortgages if not m.get("is_refinance", False)]
            
            # 대환하는 근저당권이 있는 경우
            if refinance_mortgages:
                # 대환하는 근저당권 중 가장 낮은 순위 확인
                refinance_priorities = [m.get("priority", 0) for m in refinance_mortgages if m.get("priority")]
                min_refinance_priority = min(refinance_priorities) if refinance_priorities else None
                
                # 1순위를 대환하는 경우
                if min_refinance_priority == 1:
                    priority_text = "선순위"
                else:
                    # 남는 근저당권들을 순위 순으로 정렬
                    remaining_mortgages_sorted = sorted(remaining_mortgages, key=lambda x: x.get("priority", 999))
                    
                    # 대환 후 순위 재배치
                    # 남는 근저당권이 있으면 가장 높은 순위 찾기
                    if remaining_mortgages_sorted:
                        # 남는 근저당권 중 가장 높은 순위 (재배치 전 원래 순위)
                        max_remaining_priority = max(m.get("priority", 0) for m in remaining_mortgages_sorted)
                        # 진행 순위 = 가장 높은 남는 순위 + 1
                        # 하지만 중간 순위를 대환하는 경우도 고려
                        # 예: 1,2,3,4 중 2,3 대환 → 1은 1순위 유지, 4는 2순위로 올라감 → 진행: 3순위
                        
                        # 더 정확하게: 대환하는 순위 중 가장 낮은 순위가 진행 순위
                        if min_refinance_priority:
                            priority_text = f"{min_refinance_priority}순위"
                    else:
                        # 모든 근저당권을 대환하는 경우
                        priority_text = "선순위"
            else:
                # 대환하지 않는 경우: 후순위 진행
                if remaining_mortgages:
                    # 남는 근저당권 중 가장 높은 순위 찾기
                    max_remaining_priority = max(m.get("priority", 0) for m in remaining_mortgages)
                    # 진행 순위 = 가장 높은 남는 순위 + 1
                    next_priority = max_remaining_priority + 1
                    priority_text = f"{next_priority}순위"
                else:
                    # 근저당권이 없는 경우
                    priority_text = "선순위"
    
    # 탁감가 정보 확인 (property_data에서 kb_price_raw 확인)
    appraisal_price_info = None
    if property_data:
        kb_price_raw = property_data.get("kb_price_raw", "")
        kb_price = property_data.get("kb_price")
        
        # kb_price_raw에 탁감가 또는 감정가 키워드가 있는지 확인
        if kb_price_raw and ("탁감가" in str(kb_price_raw) or "감정가" in str(kb_price_raw)):
            # 탁감가 금액 추출 (kb_price 사용 또는 kb_price_raw에서 추출)
            if kb_price:
                # 숫자 포맷팅 (쉼표 추가)
                price_str = f"{int(kb_price):,}"
                appraisal_price_info = f"탁감가 {price_str}만"
            else:
                # kb_price_raw에서 숫자 추출 시도
                import re
                price_match = re.search(r'([\d,]+)', str(kb_price_raw))
                if price_match:
                    price_str = price_match.group(1)
                    appraisal_price_info = f"탁감가 {price_str}만"
    
    # 전체 진행 여부 판단
    header_lines = []
    if all_refinance_results and not all_subordinate_results:
        # 모든 결과가 대환인 경우
        if all_refinance_institutions_set:
            institutions_str = ", ".join(sorted(all_refinance_institutions_set))
            if priority_text:
                header_text = f"※ 대환 진행 ({institutions_str}) - {priority_text} 진행"
            else:
                header_text = f"※ 대환 진행 ({institutions_str})"
        else:
            if priority_text:
                header_text = f"※ 대환 진행 - {priority_text} 진행"
            else:
                header_text = "※ 대환 진행"
        
        # 탁감가 정보가 있으면 추가
        if appraisal_price_info:
            header_text += f" / {appraisal_price_info}"
        header_lines.append(header_text)
    elif all_subordinate_results and not all_refinance_results:
        # 모든 결과가 후순위인 경우
        if priority_text:
            header_text = f"※ 후순위 진행 - {priority_text} 진행"
        else:
            header_text = "※ 후순위 진행"
        
        # 탁감가 정보가 있으면 추가
        if appraisal_price_info:
            header_text += f" / {appraisal_price_info}"
        header_lines.append(header_text)
    elif all_refinance_results and all_subordinate_results:
        # 혼합된 경우
        if all_refinance_institutions_set:
            institutions_str = ", ".join(sorted(all_refinance_institutions_set))
            if priority_text:
                header_text = f"※ 대환/후순위 혼합 진행 (대환: {institutions_str}) - {priority_text} 진행"
            else:
                header_text = f"※ 대환/후순위 혼합 진행 (대환: {institutions_str})"
        else:
            if priority_text:
                header_text = f"※ 대환/후순위 혼합 진행 - {priority_text} 진행"
            else:
                header_text = "※ 대환/후순위 혼합 진행"
        
        # 탁감가 정보가 있으면 추가
        if appraisal_price_info:
            header_text += f" / {appraisal_price_info}"
        header_lines.append(header_text)
    
    formatted_results = []
    
    for bank_result in all_results:
        formatted = format_result(bank_result)
        formatted_results.append(formatted)
    
    # 헤더가 있으면 맨 위에 추가
    if header_lines:
        return "\n".join(header_lines) + "\n\n" + "\n\n".join(formatted_results)
    else:
        return "\n\n".join(formatted_results)

