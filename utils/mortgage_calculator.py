# -*- coding: utf-8 -*-
"""
근저당권 원금 계산 모듈
- 채권최고액으로부터 원금 역산
- 금융사 유형별 설정 비율 자동 판별
"""

import re
from typing import Optional, Tuple, Dict


def classify_financial_institution(name: str) -> str:
    """
    금융사 이름으로 유형 분류
    
    Args:
        name: 금융사 이름 (근저당권자)
    
    Returns:
        금융사 유형 ('조합', '은행', '저축은행', '캐피탈', '대부', '보험', '전세권', '기타')
    """
    name = name.strip()
    
    # 전세권 체크 (최우선)
    if '전세권' in name:
        return '전세권'
    
    # 저축은행 체크 (은행보다 우선)
    if '저축은행' in name:
        return '저축은행'
    
    # 조합 체크
    if any(keyword in name for keyword in ['조합', '신협', '새마을']):
        return '조합'
    
    # 1금융권 인터넷은행 (케이뱅크, 카카오뱅크, 토스뱅크) - 은행과 동일 110% 적용
    if any(keyword in name for keyword in ['케이뱅크', '카카오뱅크', '토스뱅크', 'k뱅크', 'kbank', '카뱅']):
        return '은행'
    
    # 은행 체크
    if '은행' in name:
        return '은행'
    
    # 캐피탈 체크
    if any(keyword in name for keyword in ['캐피탈', '파이낸스', '파이낸셜']):
        return '캐피탈'
    
    # 대부 체크
    if any(keyword in name for keyword in ['대부', '크레디트']):
        return '대부'
    
    # 보험 체크
    if any(keyword in name for keyword in ['보험', '생명', '화재']):
        return '보험'
    
    return '기타'


def get_ratio_range(institution_type: str) -> Tuple[int, int]:
    """
    금융사 유형별 설정 비율 범위 반환
    
    Args:
        institution_type: 금융사 유형
    
    Returns:
        (최소비율, 최대비율) 튜플 (단위: %)
    """
    ranges = {
        '조합': (110, 130),
        '은행': (110, 130),
        '저축은행': (120, 150),
        '캐피탈': (120, 150),
        '대부': (120, 170),
        '보험': (110, 130),
        '전세권': (100, 100),
        '기타': (100, 100),  # 기타는 채권최고액=원금
    }
    return ranges.get(institution_type, (100, 100))


def get_default_ratio(institution_type: str) -> int:
    """
    금융사 유형별 기본 설정 비율 반환
    
    Args:
        institution_type: 금융사 유형
    
    Returns:
        기본 비율 (단위: %)
    """
    defaults = {
        '조합': 120,
        '은행': 110,
        '저축은행': 130,
        '캐피탈': 130,
        '대부': 150,
        '보험': 120,
        '전세권': 100,
        '기타': 100,
    }
    return defaults.get(institution_type, 120)


def calculate_principal(
    max_claim_amount: int,
    institution_name: str,
    manual_ratio: Optional[int] = None
) -> Tuple[int, int, bool]:
    """
    채권최고액으로부터 원금 계산
    
    Args:
        max_claim_amount: 채권최고액 (원 단위)
        institution_name: 금융사 이름
        manual_ratio: 수동 지정 비율 (%, 예: 120)
    
    Returns:
        (원금, 적용된_비율, 깔끔한_금액_여부) 튜플
        - 원금: 원 단위
        - 적용된_비율: 사용된 비율 (%)
        - 깔끔한_금액_여부: True이면 만원 단위로 깔끔하게 떨어짐
    """
    # 수동 비율이 지정된 경우
    if manual_ratio:
        principal = int(max_claim_amount * 100 / manual_ratio)
        is_clean = is_clean_amount(principal)
        return principal, manual_ratio, is_clean
    
    # 금융사 유형 판별
    inst_type = classify_financial_institution(institution_name)
    min_ratio, max_ratio = get_ratio_range(inst_type)
    
    # 범위 내에서 깔끔하게 떨어지는 비율 찾기
    for ratio in range(min_ratio, max_ratio + 1):
        principal = int(max_claim_amount * 100 / ratio)
        if is_clean_amount(principal):
            return principal, ratio, True
    
    # 깔끔하게 떨어지는 비율이 없으면 기본 비율 사용
    default_ratio = get_default_ratio(inst_type)
    principal = int(max_claim_amount * 100 / default_ratio)
    return principal, default_ratio, False


def is_clean_amount(amount: int) -> bool:
    """
    금액이 만원 단위로 깔끔하게 떨어지는지 확인
    
    Args:
        amount: 금액 (원 단위)
    
    Returns:
        True이면 만원 단위로 깔끔함 (소수점 0.01 미만)
    """
    amount_in_man = amount / 10000
    # 소수점 이하가 0.01 미만이면 깔끔한 것으로 판정
    return abs(amount_in_man - round(amount_in_man)) < 0.01


def extract_manual_ratios(message: str) -> Dict[str, int]:
    """
    메시지에서 수동 지정된 비율 추출
    
    형식 예시:
    - "1순위 120%설정"
    - "2순위 130%"
    - "3순위:150%"
    
    Args:
        message: 텔레그램 메시지 (캡션)
    
    Returns:
        {순위번호: 비율} 딕셔너리 (예: {"1": 120, "2": 130})
    """
    ratios = {}
    
    # 패턴: "N순위" 뒤에 퍼센트 (다양한 형식 지원)
    pattern = r'(\d+)\s*순위\s*[:：\s]*(\d+)\s*%'
    matches = re.finditer(pattern, message, re.IGNORECASE)
    
    for match in matches:
        rank = match.group(1)
        ratio = int(match.group(2))
        ratios[rank] = ratio
    
    return ratios
