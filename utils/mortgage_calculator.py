# -*- coding: utf-8 -*-
"""
근저당권 원금 계산 모듈
- 채권최고액으로부터 원금 역산
- 금융사 유형별 설정 비율 자동 판별
"""

import json
import os
import re
from typing import List, Optional, Tuple, Dict

_SAVINGS_BANKS_CACHE: Optional[List[str]] = None


def _normalize_institution_name(name: str) -> str:
    """금융사명 비교용 정규화 (공백·(주) 등 제거)."""
    n = (name or "").strip()
    for token in (" ", "㈜", "(주)", "（주）"):
        n = n.replace(token, "")
    return n


def _institution_name_core(name: str) -> str:
    """저축은행/저축 접미사를 제거한 핵심 명칭 (유니온저축 ↔ 유니온저축은행 매칭용)."""
    n = _normalize_institution_name(name)
    for suffix in ("저축은행", "저축"):
        if n.endswith(suffix):
            return n[: -len(suffix)]
    return n


def _load_savings_bank_names() -> List[str]:
    """refinanceable_institutions.json의 savings_banks 목록 (캐시)."""
    global _SAVINGS_BANKS_CACHE
    if _SAVINGS_BANKS_CACHE is not None:
        return _SAVINGS_BANKS_CACHE
    base = os.path.join(os.path.dirname(__file__), "..", "data", "banks", "refinanceable_institutions.json")
    try:
        with open(base, "r", encoding="utf-8") as f:
            data = json.load(f)
        _SAVINGS_BANKS_CACHE = list(data.get("savings_banks") or [])
    except Exception:
        _SAVINGS_BANKS_CACHE = []
    return _SAVINGS_BANKS_CACHE


def is_known_savings_bank(name: str) -> bool:
    """
    저축은행 여부 판별.
    - '저축은행' 문자열 포함
    - 마스터 savings_banks 명단 매칭 (유니온저축 등 축약명 포함)
    """
    normalized = _normalize_institution_name(name)
    if not normalized:
        return False
    if "저축은행" in normalized:
        return True
    core = _institution_name_core(name)
    for sb in _load_savings_bank_names():
        sb_norm = _normalize_institution_name(sb)
        if not sb_norm:
            continue
        if sb_norm in normalized or normalized in sb_norm:
            return True
        if len(core) >= 3 and core == _institution_name_core(sb):
            return True
    return False


def classify_financial_institution(name: str) -> str:
    """
    금융사 이름으로 유형 분류
    
    Args:
        name: 금융사 이름 (근저당권자)
    
    Returns:
        금융사 유형 ('조합', '은행', '저축은행', '캐피탈', '대부', '보험', '전세권', '공공기관', '기타')
    """
    name = name.strip()
    
    # 공공기관 체크 (주택담보대출 수행 기관 - 후순위 취급 가능)
    # - 지정 키워드: 한국토지주택공사, 주택도시보증공사, 서울주택도시공사 등
    # - 근저당권 이름에 '공사'가 포함되면 공공기관으로 처리
    if any(keyword in name for keyword in ['한국토지주택공사', '토지주택공사', '주택도시보증공사', '서울주택도시공사', '주택공사', 'LH', 'HUG', '주택도시보증']):
        return '공공기관'
    if '공사' in name:
        return '공공기관'
    
    # 전세권 체크 (최우선)
    if '전세권' in name:
        return '전세권'
    
    # 저축은행 체크 (은행보다 우선) — 마스터 명단 기반 (유니온저축 등 축약명 포함)
    if is_known_savings_bank(name):
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
    
    # 대부 체크 (캐피탈보다 먼저: 에이파이낸셜대부 등이 '파이낸셜'로 캐피탈 오인되지 않게)
    if any(keyword in name for keyword in ['대부', '크레디트', '리드코프']):
        return '대부'
    
    # 캐피탈 체크
    if any(keyword in name for keyword in ['캐피탈', '파이낸스', '파이낸셜']):
        return '캐피탈'
    
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
        '공공기관': (110, 130),  # LH, 주택도시보증공사 등 - 은행과 유사
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
        '공공기관': 110,
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
    
    # 모든 금융사: 10% 단위로만 검색 (110, 120, 130 등). 1% 단위(112% 등)는 사용하지 않음
    step = 10
    
    # 범위 내에서 깔끔하게 떨어지는 비율 찾기
    for ratio in range(min_ratio, max_ratio + 1, step):
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
    - "1순위 원금 12787 120%" (원금 등 중간 텍스트 있어도 인식)
    
    Args:
        message: 텔레그램 메시지 (캡션)
    
    Returns:
        {순위번호: 비율} 딕셔너리 (예: {"1": 120, "2": 130})
    """
    ratios = {}
    
    # 패턴 1: "N순위" 뒤에 퍼센트 (콜론·공백 유연)
    pattern = r'(\d+)\s*순위\s*[:：\s]*(\d+)\s*%'
    for match in re.finditer(pattern, message, re.IGNORECASE):
        rank = match.group(1)
        ratio = int(match.group(2))
        if 100 <= ratio <= 200:
            ratios[rank] = ratio
    
    # 패턴 2: "N순위" 키워드가 있는 줄에서 % 추출 (원금 12787 120% 등 중간 텍스트 허용)
    for line in message.split('\n'):
        if re.search(r'\d+\s*순위', line):
            pct_match = re.search(r'(\d+)\s*%', line)
            if pct_match:
                pct = int(pct_match.group(1))
                rank_match = re.search(r'(\d+)\s*순위', line)
                if rank_match and 100 <= pct <= 200:
                    rank = rank_match.group(1)
                    ratios[rank] = pct
    
    return ratios


def extract_manual_principals(message: str) -> Dict[str, int]:
    """
    메시지에서 감액등기용 수동 원금 추출
    
    형식 예시:
    - "기대출" 섹션: "국민 50,490/45,900" (금융사 채권최고액/원금, 슬래시 뒤가 원금)
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
    
    # 형식 0: "기대출" 섹션 - "금융사 채권최고액/원금" (슬래시 뒤가 원금, 등장 순서=순위)
    gidaechul_match = re.search(r'기대출\s*\n([\s\S]*?)(?=\n\n|\n기대출|\n요청사항|\n특이사항|$)', message, re.IGNORECASE)
    if gidaechul_match:
        section = gidaechul_match.group(1)
        # "국민 50,490/45,900" 또는 "한투캐 13,680/11,400" 패턴
        pattern_slash = r'([가-힣a-zA-Z]{2,})\s+([\d,]+)/([\d,]+)'
        for rank, match in enumerate(re.finditer(pattern_slash, section), 1):
            name = match.group(1).strip()
            if any(kw in name for kw in ['등급', '점수', '신용', '원금', '합계']):
                continue
            principal_str = match.group(3).replace(',', '')
            try:
                principal = int(principal_str)
                if principal >= 100 and principal < 100000:
                    result[str(rank)] = principal
                    result[name] = principal  # 금융사명으로도 매칭 가능
            except ValueError:
                pass
    
    # 형식 2 (순위 기반): "N순위 원금 000" / "N순위 : 원금 000" (콜론·공백 유연)
    pattern_rank = r'(\d+)\s*순위\s*[:：\s]*원금\s*[:：\s]*([\d,]+)\s*만?\s*원?'
    for match in re.finditer(pattern_rank, message, re.IGNORECASE):
        rank = match.group(1)
        num_str = match.group(2).replace(',', '')
        try:
            num = int(num_str)
            if num > 0 and num < 100000:
                result[rank] = num
        except ValueError:
            pass
    
    # 형식 2-2: "N순위" 키워드가 있는 줄에서 원금 추출 (1순위 원금 12787 120% 등)
    for line in message.split('\n'):
        if re.search(r'\d+\s*순위', line) and re.search(r'원금', line, re.IGNORECASE):
            rank_match = re.search(r'(\d+)\s*순위', line)
            if rank_match:
                rank = rank_match.group(1)
                # 원금 뒤의 숫자 (만원 단위, 4자리 이상)
                num_match = re.search(r'원금\s*[:：\s]*([\d,]+)', line, re.IGNORECASE)
                if num_match:
                    num_str = num_match.group(1).replace(',', '')
                    try:
                        num = int(num_str)
                        if num > 0 and num < 100000:
                            result[rank] = num
                    except ValueError:
                        pass
    
    # 형식 1-2: "N.금융사명 X만(Y만)" - 순위+금융사별 원금 (동일 금융사 여러 순위 구분)
    # "1.주식회사국민은행 36,850만(33,500만)/110%" → 순위1=33,500
    # "2.주식회사국민은행 14,300만(13,000만)/110%" → 순위2=13,000
    # 등장 순서대로 순위 1,2,3... 매핑 (선순위 1,2 / 대환 1 등 섹션 구분 무관)
    pattern_rank_creditor = r'(\d+)\s*[\.)]\s*([가-힣a-zA-Z]+)\s+[\d,]+\s*만?\s*\(([\d,]+)\s*만?\)'
    for seq, match in enumerate(re.finditer(pattern_rank_creditor, message), 1):
        name = match.group(2).strip()
        if any(kw in name for kw in ['등급', '점수', '신용', '원금', '합계']):
            continue
        num_str = match.group(3).replace(',', '')
        try:
            num = int(num_str)
            if num >= 100 and num < 100000:
                result[str(seq)] = num  # 등장 순서대로 순위 매핑
        except ValueError:
            pass
    
    # 형식 1-1: "금융사명 X만(Y만)" - 괄호 안 Y가 원금 (채권최고액 X, 원금 Y)
    # 순위 형식이 이미 추출된 경우 덮어쓰지 않음 (동일 금융사 여러 순위 시 순위 기반 우선)
    # "국민은행 21,650만(19,682만)/110%" → 원금 19,682 추출 (기존 패턴은 21,650 채권최고액을 잘못 추출함)
    pattern_parentheses = r'([가-힣a-zA-Z]{2,})\s+[\d,]+\s*만?\s*\(([\d,]+)\s*만?\)'
    for match in re.finditer(pattern_parentheses, message):
        name = match.group(1).strip()
        num_str = match.group(2).replace(',', '')
        if any(kw in name for kw in ['등급', '점수', '신용', '원금']):
            continue
        try:
            num = int(num_str)
            if num >= 100 and num < 100000:
                result[name] = num
        except ValueError:
            pass
    
    # 형식 1: "금융사명 숫자" (괄호 없는 경우 - "신한 16900", "리드코프 4000" 등)
    # 이미 괄호 형식으로 추출된 금융사는 덮어쓰지 않음
    pattern_name = r'([가-힣a-zA-Z]{2,})\s+(\d[\d,]*)\s*만?\s*원?'
    for match in re.finditer(pattern_name, message):
        name = match.group(1).strip()
        if name in result:
            continue  # 괄호 형식에서 이미 추출됨
        num_str = match.group(2).replace(',', '')
        if any(kw in name for kw in ['등급', '점수', '신용', '원금']):
            continue
        try:
            num = int(num_str)
            if num >= 100 and num < 100000:
                result[name] = num
        except ValueError:
            pass
    
    return result
