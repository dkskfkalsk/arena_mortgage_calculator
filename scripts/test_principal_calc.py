# -*- coding: utf-8 -*-
"""
원금 계산 로직 테스트
"""
import sys
sys.path.insert(0, '.')

from parsers.registry_parser import analyze_pdf
from utils.mortgage_calculator import calculate_principal, extract_manual_ratios

# 권현주 PDF 테스트
print("=" * 60)
print("권현주 250819.pdf 테스트")
print("=" * 60)

result = analyze_pdf('pdf_Parsing_example/권현주 250819.pdf')

if result.근저당권목록:
    print(f"\n근저당권 {len(result.근저당권목록)}건 발견:\n")
    
    for i, m in enumerate(result.근저당권목록, 1):
        print(f"{i}순위: {m.근저당권자} ({m.권리종류})")
        print(f"  채무자: {m.채무자}")
        print(f"  채권최고액: {m.채권최고액}")
        
        # 금액 추출
        import re
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
            
            print(f"  채권최고액(만원): {amount_man:,}만원")
            print(f"  원금(만원): {principal_man:,}만원")
            print(f"  적용 비율: {used_ratio}%")
            print(f"  깔끔한 금액: {'OK' if is_clean else 'NO'}")
            print(f"  출력 형식: {amount_man:,} ({principal_man:,})만원")
        print()
else:
    print("근저당권 없음")

# 정소영 PDF 테스트 (전세권)
print("\n" + "=" * 60)
print("정소영 251230.pdf 테스트 (전세권)")
print("=" * 60)

result2 = analyze_pdf('pdf_Parsing_example/정소영 251230.pdf')

if result2.근저당권목록:
    print(f"\n근저당권/전세권 {len(result2.근저당권목록)}건 발견:\n")
    
    for i, m in enumerate(result2.근저당권목록, 1):
        print(f"{i}순위: {m.근저당권자} ({m.권리종류})")
        print(f"  채무자: {m.채무자}")
        print(f"  채권최고액: {m.채권최고액}")
        
        # 금액 추출
        amount_match = re.search(r'([\d,]+)\s*원', m.채권최고액)
        if amount_match:
            amount_won = int(amount_match.group(1).replace(',', ''))
            amount_man = amount_won // 10000
            
            if m.권리종류 == "전세권":
                print(f"  전세금(만원): {amount_man:,}만원")
                print(f"  출력 형식: {amount_man:,} ({amount_man:,})만원 (전세권=원금)")
            else:
                # 원금 계산
                principal_won, used_ratio, is_clean = calculate_principal(
                    amount_won,
                    m.근저당권자
                )
                principal_man = principal_won // 10000
                
                print(f"  채권최고액(만원): {amount_man:,}만원")
                print(f"  원금(만원): {principal_man:,}만원")
                print(f"  적용 비율: {used_ratio}%")
                print(f"  출력 형식: {amount_man:,} ({principal_man:,})만원")
        print()
else:
    print("근저당권/전세권 없음")

# 수동 비율 테스트
print("\n" + "=" * 60)
print("수동 비율 추출 테스트")
print("=" * 60)

test_messages = [
    "1순위 120%설정",
    "2순위: 130%",
    "3순위 150% 4순위 170%",
    "1순위:110%설정 2순위 120%",
]

for msg in test_messages:
    ratios = extract_manual_ratios(msg)
    print(f"메시지: {msg}")
    print(f"추출된 비율: {ratios}\n")
