# -*- coding: utf-8 -*-
"""
세입자(전세/월세) 정보 추출 - PDF 캡션, 메시지 파싱 공통
"""

import re
from typing import Dict, Optional, Any


# 세입자 인식 키워드
TENANT_KEYWORDS = r'전세세입자|월세세입자|전세입자|월세입자|세입자|임차보증금'

# 설정내역 기관명으로 쓰이는 세입자 표기 (완전일치 + '세입자' 포함 변형)
TENANT_INSTITUTION_NAMES = (
    "전세세입자",
    "월세세입자",
    "전세입자",
    "월세입자",
    "세입자",
    "임차보증금",
)


def is_tenant_institution(name: Optional[str]) -> bool:
    """근저당 기관명이 세입자(전세/월세) 표기인지 여부."""
    n = (name or "").strip()
    if not n:
        return False
    if n in TENANT_INSTITUTION_NAMES:
        return True
    return "세입자" in n


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
        txt = txt.strip().replace(',', '').replace(' ', '').replace('，', '')
        # 억 단위: 1억 → 10000만원
        m = re.search(r'(\d+\.?\d*)\s*억', txt)
        if m:
            try:
                return int(float(m.group(1)) * 10000)
            except ValueError:
                pass
        # 천만 단위: 3천만 → 3000만원
        m = re.search(r'(\d+)\s*천\s*만', txt)
        if m:
            try:
                return int(m.group(1)) * 1000
            except ValueError:
                pass
        # 만 단위: 3000만, 3,000만 → 3000만원 (parse_amount_fn이 있으면 복합 형식 지원)
        if parse_amount_fn:
            val = parse_amount_fn(txt)
            if val is not None:
                return val
        m = re.search(r'^(\d+)$', txt)
        if m:
            return int(m.group(1))
        m = re.search(r'(\d+)\s*만', txt)
        if m:
            return int(m.group(1))
        m = re.search(r'[\d]+', txt)
        if m:
            try:
                return int(m.group(0))
            except ValueError:
                pass
        return None
    
    # 보증금 패턴 (콤마 포함 숫자 [\d,]+ 지원, 다양한 형식)
    deposit_patterns = [
        # 1순위 월세입자 3,000만 / 월세 120만원 (콤마 포함, 만 단위)
        (r'(?:1|2)순위\s*[:：\s]*(?:전세|월세)?입자[^\d]*([\d,]+)\s*만\s*원?', 1),
        (r'(?:1|2)순위\s*(?:전세|월세)?입자[^\d]*([\d,]+)\s*만\s*원?', 1),
        # 월세입자(40만) 원금 5000 / 전세입자(30만) 원금 3000 - 괄호 안 월세, 원금 뒤 보증금
        (r'(?:전세|월세)?입자\s*\([^)]*\)\s*원금\s*[:：]?\s*([\d,.\s]+)', 1),
        (r'(?:1|2)순위\s*[:：\s]*(?:전세|월세)?입자\s*\([^)]*\)\s*원금\s*[:：]?\s*([\d,.\s]+)', 1),
        # 1순위 월세입자 3000 / 1순위 월세입자 3,000 (숫자만, 4자리 이상)
        (r'(?:1|2)순위\s*[:：\s]*(?:전세|월세)?입자[^\d]*(?:원금\s*[:：]?\s*)?([\d,]+)', 1),
        (r'(?:1|2)순위\s*(?:전세|월세)?입자[^\d]*(?:원금\s*[:：]?\s*)?([\d,]+)', 1),
        # 월세입자 3,000만 / 전세입자 5000만원 (입자 뒤 금액+만)
        (r'(?:전세|월세)?입자[^\d]*([\d,]+)\s*만\s*원?', 1),
        (r'(?:전세|월세)?세입자[^\d]*([\d,]+)\s*만\s*원?', 1),
        # 전세입자 5000만원 / 전세입자 5000 (5000)만원(100%)
        (r'(?:전세|월세)?입자[^\d]*([\d,]+)\s*(?:\([\d,]+\))?\s*만원', 1),
        (r'(?:전세|월세)?입자[^\d]*([\d,]+)(?:\s*[/(]|$)', 1),
        (r'(?:전세|월세)?세입자[^\d]*([\d,]+)', 1),
        # 보증금/임차보증금/원금 (콜론·공백 유연)
        (r'보증금\s*[:：\s]*([\d,.\s억천만원]+)', 1),
        (r'(?:전세|월세)?세입자[^\d]*보증금\s*[:：\s]*([\d,.\s억천만원]+)', 1),
        (r'(?:전세|월세)?입자[^\d]*원금\s*[:：\s]*([\d,.\s]+)', 1),
        (r'임차보증금\s*[:：\s]*([\d,.\s억천만원]+)', 1),
        (r'(?:전세|월세)?세입자[^\d]*원금\s*[:：\s]*([\d,.\s]+)', 1),
        # 3천만, 5천만원 (1순위 월세입자 3천만) - 캡처 전체를 _parse_deposit에 전달
        (r'(?:1|2)순위\s*(?:전세|월세)?입자[^\d]*(\d+\s*천\s*만)\s*원?', 1),
        (r'(?:전세|월세)?입자[^\d]*(\d+\s*천\s*만)\s*원?', 1),
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
        r'\((\d+)\s*만\s*원?\)',           # (120만원)
        r'월세\s*[:：]?\s*\(?\s*([\d,]+)\s*만\s*원?\)?',  # 월세 120만원, 월세 1,200만
        r'월세\s*[/／]\s*([\d,]+)\s*만',    # / 월세 120만
        r'월세\s*[:：]?\s*([\d,]+)',        # 월세 120
        r'([\d,]+)\s*만\s*원?\s*월세',     # 120만원 월세
    ]
    for mp in monthly_patterns:
        m = re.search(mp, text)
        if m:
            raw = m.group(1) if m.lastindex else m.group(0)
            num_str = re.sub(r'[^\d]', '', raw) or raw
            try:
                num = int(num_str) if num_str else 0
            except ValueError:
                continue
            if 1 <= num <= 9999:
                monthly_rent_man = num
                break
    
    if deposit_man:
        # 표시명: 월세 있으면 월세입자, 전세입자 키워드 있으면 전세입자, 아니면 세입자
        if monthly_rent_man:
            display_name = '월세입자'
        elif re.search(r'전세(?:세)?입자', text):
            display_name = '전세입자'
        else:
            display_name = '세입자'
        return {
            'deposit_man': deposit_man,
            'monthly_rent_man': monthly_rent_man,
            'display_name': display_name,
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
