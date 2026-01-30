# -*- coding: utf-8 -*-
"""
LTV 표시 테스트 (채권최고액 기준 / 원금 기준)
"""
import sys
sys.path.insert(0, '.')

from parsers.registry_parser import analyze_pdf
from KB_api.kb_price_api import get_kb_price_from_registry
from utils.mortgage_calculator import calculate_principal, extract_manual_ratios
import re

# 권현주 PDF 테스트
print("=" * 60)
print("권현주 250819.pdf LTV 계산 테스트")
print("=" * 60)

result = analyze_pdf('pdf_Parsing_example/권현주 250819.pdf')
kb_result = get_kb_price_from_registry(result.부동산_주소, result.면적)

if kb_result and kb_result.get('kb_price'):
    kb_price = kb_result['kb_price']
    print(f"\nKB시세: {kb_price:,}만원")
    
    if result.근저당권목록:
        mortgage_amounts = []  # 채권최고액
        principal_amounts = []  # 원금
        
        print(f"\n근저당권 목록:")
        for i, m in enumerate(result.근저당권목록, 1):
            amount_match = re.search(r'([\d,]+)\s*원', m.채권최고액)
            if amount_match:
                amount_won = int(amount_match.group(1).replace(',', ''))
                amount_man = amount_won // 10000
                
                # 원금 계산
                principal_won, used_ratio, is_clean = calculate_principal(
                    amount_won,
                    m.근저당권자
                )
                principal_man = principal_won // 10000
                
                mortgage_amounts.append(amount_man)
                principal_amounts.append(principal_man)
                
                print(f"{i}순위: {m.근저당권자}")
                print(f"  채권최고액: {amount_man:,}만원")
                print(f"  원금: {principal_man:,}만원 ({used_ratio}%)")
        
        # LTV 계산
        total_mortgage = sum(mortgage_amounts)
        total_principal = sum(principal_amounts)
        
        ltv_mortgage = (total_mortgage / kb_price) * 100
        ltv_principal = (total_principal / kb_price) * 100
        
        print(f"\n채권최고액 합계: {total_mortgage:,}만원")
        print(f"원금 합계: {total_principal:,}만원")
        print(f"\nLTV 표시: {ltv_mortgage:.2f}% / {ltv_principal:.2f}%")
        print(f"  (채권최고액 기준 / 원금 기준)")
else:
    print("KB시세 정보 없음")
