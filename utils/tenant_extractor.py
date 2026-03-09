# -*- coding: utf-8 -*-
"""
세입자(전세/월세) 정보 추출 - PDF 캡션, 메시지 파싱 공통
"""

import re
from typing import Dict, Optional, Any


# 세입자 인식 키워드
TENANT_KEYWORDS = r'전세세입자|월세세입자|전세입자|월세입자|세입자|임차보증금'


def extract_tenant_info(text: str, parse_amount_fn=None) -> Optional[Dict[str, Any]]:
    """
    텍스트에서 세입자(전세/월세) 정보 추출
    
    Args:
        text: 캡션 또는 메시지 텍스트
        parse_amount_fn: 금액 파싱 함수 (만원 단위 반환). None이면 내부 파싱 사용
    
    Returns:
        {'deposit_man': int, 'monthly_rent_man': int|None, 'display_name': str} 또는 None
    """
    if not text or not re.search(TENANT_KEYWORDS, text):
        return None
    
    deposit_man = None
    monthly_rent_man = None
    
    def _parse_deposit(txt):
        if not txt:
            return None
        txt = txt.strip().replace(',', '').replace(' ', '')
        m = re.search(r'(\d+\.?\d*)\s*억', txt)
        if m:
            try:
                return int(float(m.group(1)) * 10000)
            except ValueError:
                pass
        if parse_amount_fn:
            return parse_amount_fn(txt)
        m = re.search(r'^(\d+)$', txt)
        if m:
            return int(m.group(1))
        m = re.search(r'[\d,]+', txt)
        if m:
            try:
                return int(m.group(0).replace(',', ''))
            except ValueError:
                pass
        return None
    
    deposit_patterns = [
        (r'1순위\s*(?:전세|월세)?입자[^\d]*(\d{4,})', 1),
        (r'보증금\s*[:：]?\s*([\d,.\s억천만원]+)', 1),
        (r'(?:전세|월세)?세입자[^\d]*보증금\s*[:：]?\s*([\d,.\s억천만원]+)', 1),
        (r'임차보증금\s*[:：]?\s*([\d,.\s억천만원]+)', 1),
        (r'(?:전세|월세)?세입자[^\d]*원금\s*[:：]?\s*(\d[\d,.\s]*)', 1),
        (r'(\d+\.?\d*)\s*억\s*원?', 1),
    ]
    for dp, grp in deposit_patterns:
        m = re.search(dp, text)
        if m:
            val = _parse_deposit(m.group(grp))
            if val and val >= 100:
                deposit_man = val
                break
    
    monthly_patterns = [
        r'\((\d+)\s*만\s*원?\)',
        r'월세\s*[:：]?\s*\(?\s*(\d+)\s*만\s*원?\)?',
        r'월세\s*[:：]?\s*(\d+)',
        r'(\d+)\s*만\s*원?\s*월세',
    ]
    for mp in monthly_patterns:
        m = re.search(mp, text)
        if m:
            num = int(re.search(r'\d+', m.group(1) if m.lastindex else m.group(0)).group(0))
            if 1 <= num <= 9999:
                monthly_rent_man = num
                break
    
    if deposit_man:
        return {
            'deposit_man': deposit_man,
            'monthly_rent_man': monthly_rent_man,
            'display_name': '월세입자' if monthly_rent_man else '세입자',
        }
    return None


def tenant_to_mortgage(tenant: Dict[str, Any], priority: int, has_trust: bool = False) -> Dict[str, Any]:
    """
    세입자 정보를 메시지 파서/계산기용 mortgage 딕셔너리로 변환
    
    Args:
        tenant: extract_tenant_info 반환값
        priority: 1 (신탁 없음) 또는 2 (신탁 있음)
        has_trust: 신탁 존재 여부
    
    Returns:
        {'priority': int, 'amount': float, 'max_amount': float, 'institution': str, 'is_refinance': False}
    """
    dep = tenant['deposit_man']
    mon = tenant.get('monthly_rent_man')
    name = tenant['display_name']
    return {
        'priority': priority,
        'amount': float(dep),
        'max_amount': float(dep),
        'institution': name,
        'is_refinance': False,
        'is_tenant': True,
        'monthly_rent_man': float(mon) if mon else None,
    }
