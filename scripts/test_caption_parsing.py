# -*- coding: utf-8 -*-
"""
캡션에서 특이사항/요청사항 파싱 테스트
"""
import sys
import re

# parse_complex_amount 함수 정의 (webhook.py에서 사용)
def parse_complex_amount(text):
    """복합 단위 금액을 만원으로 변환"""
    if not text:
        return None
    
    text = text.strip()
    result = 0
    
    eok_match = re.search(r'(\d+(?:\.\d+)?)\s*억', text)
    if eok_match:
        result += float(eok_match.group(1)) * 10000
    
    cheon_match = re.search(r'(\d+)\s*천만', text)
    if cheon_match:
        result += int(cheon_match.group(1)) * 1000
    
    man_match = re.search(r'(\d+(?:,\d+)*)\s*만', text)
    if man_match:
        result += float(man_match.group(1).replace(',', ''))
    
    won_match = re.search(r'^([\d,]+)$', text.replace(' ', ''))
    if won_match and result == 0:
        amount_str = won_match.group(1).replace(',', '')
        if len(amount_str) >= 8:
            result = float(amount_str) / 10000
        else:
            result = float(amount_str)
    
    return int(result) if result else None

# 테스트용 parse_caption_info 함수 (간소화 버전)
def parse_caption_info_test(caption):
    """캡션에서 특이사항과 요청사항 추출"""
    info = {
        'special_notes': [],
        'request': '',
    }
    
    if not caption:
        return info
    
    # 특이사항 추출
    special_notes_match = re.search(r'특이사항\s*[:：]?\s*(.+?)(?=\n요청사항|\n\n|$)', caption, re.IGNORECASE | re.DOTALL)
    if special_notes_match:
        special_note_text = special_notes_match.group(1).strip()
        special_note_text = re.sub(r'\s+', ' ', special_note_text).strip()
        if special_note_text:
            info['special_notes'].append(special_note_text)
    
    # 요청사항 추출
    request_match = re.search(r'요청사항\s*[:：]?\s*(.+?)(?=\n특이사항|\n\n|$)', caption, re.IGNORECASE | re.DOTALL)
    if request_match:
        request_text = request_match.group(1).strip()
        request_text = re.sub(r'\s+', ' ', request_text).strip()
        if request_text:
            info['request'] = request_text
    
    return info

# 테스트 케이스
test_cases = [
    {
        'name': '테스트 1: 특이사항과 요청사항 모두 있음',
        'caption': '''김철수
신용점수 850
아파트
KB시세 1억5천만원

특이사항 : 압류 있음

요청사항 : 1순위 대환조건'''
    },
    {
        'name': '테스트 2: 콜론 없이',
        'caption': '''이영희
4등급
빌라

특이사항 전세권 설정되어 있음

요청사항 부족자금 확인'''
    },
    {
        'name': '테스트 3: 여러 줄',
        'caption': '''박민수
신용 750
오피스텔

특이사항 : 압류 2건
가압류 1건 있음

요청사항 : 전액 대환
후순위 추가대출'''
    },
    {
        'name': '테스트 4: 순서 바뀜',
        'caption': '''홍길동
신용 900

요청사항 : 선순위 확인

특이사항: 재건축 진행중'''
    },
]

print("=" * 60)
print("캡션 파싱 테스트")
print("=" * 60)

for test in test_cases:
    print(f"\n{test['name']}")
    print("-" * 60)
    print("입력 캡션:")
    print(test['caption'])
    print()
    
    result = parse_caption_info_test(test['caption'])
    
    print("파싱 결과:")
    print(f"  특이사항: {' / '.join(result['special_notes']) if result['special_notes'] else '(없음)'}")
    print(f"  요청사항: {result['request'] if result['request'] else '(없음)'}")
    print()
