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
    
    # 대부 체크 (대부/크레디트 명시 + 대부업체명 별도 매핑)
    if any(keyword in name for keyword in ['대부', '크레디트', '리드코프']):
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
        '대부': (130, 170),
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
    금액이 십만원 단위로 깔끔하게 떨어지는지 확인
    
    일의 자리(1만원)까지 계산하지 않고, 십의 자리(10만원) 단위까지만 본다.
    
    Args:
        amount: 금액 (원 단위)
    
    Returns:
        True이면 십만원 단위로 깔끔함 (10만원으로 나누어떨어짐)
    """
    return amount % 100000 == 0


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


def extract_manual_principals(message: str) -> Dict[str, int]:
    """
    메시지에서 감액등기용 수동 원금 추출
    
    형식 예시:
    - "신한 16900/리드코프 4000" (금융사명 + 공백 + 원금만원, 슬래시 구분)
    - "2순위 원금 4000만원" 또는 "2순위 원금 4000만"
    
    Args:
        message: 텔레그램 메시지 (캡션)
    
    Returns:
        {금융사명_또는_순위: 원금_만원} 딕셔너리
        예: {"신한": 16900, "리드코프": 4000} 또는 {"2": 4000}
    """
    result = {}
    
    if not message:
        return result
    
    # 형식 2 먼저 (순위 기반 - 더 구체적): "N순위 원금 000만원" 또는 "N순위 원금 000만"
    pattern_rank = r'(\d+)\s*순위\s+원금\s+([\d,]+)\s*만?\s*원?'
    for match in re.finditer(pattern_rank, message, re.IGNORECASE):
        rank = match.group(1)
        num_str = match.group(2).replace(',', '')
        try:
            num = int(num_str)
            if num > 0 and num < 100000:
                result[rank] = num
        except ValueError:
            pass
    
    # 형식 1: "금융사명 숫자" (한글 2자 이상 + 공백 + 숫자, 만원 단위)
    # "신한 16900", "리드코프 4000" 등 - 신용등급(1등급 850) 등 제외
    pattern_name = r'([가-힣a-zA-Z]{2,})\s+(\d[\d,]*)\s*만?\s*원?'
    for match in re.finditer(pattern_name, message):
        name = match.group(1).strip()
        num_str = match.group(2).replace(',', '')
        # "등급", "점수" 등 신용 관련 키워드 제외
        if any(kw in name for kw in ['등급', '점수', '신용', '원금']):
            continue
        try:
            num = int(num_str)
            if num >= 100 and num < 100000:  # 100만원~99999만원
                result[name] = num
        except ValueError:
            pass
    
    return result
