# -*- coding: utf-8 -*-
"""근저당권 변경 확인 디버깅"""
import os
import sys
import re
import fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_dir = os.path.join(base, "pdf_Parsing_example")
    
    test_files = [
        "전욱현 260121.pdf",
        "이은탁 260122.pdf",
        "김재복 & 안윤주 260122.pdf"
    ]
    
    for filename in test_files:
        path = os.path.join(pdf_dir, filename)
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue
        
        print(f"\n{'='*70}")
        print(f"Testing: {filename}")
        print('='*70)
        
        # PDF 텍스트 추출
        doc = fitz.open(path)
        text = "\n".join([p.get_text() or "" for p in doc])
        doc.close()
        
        # 요약 섹션 찾기
        summary_section_pattern = r'\(근\)저당권\s*및\s*전세권\s*등[\s\S]*?(?=\[\s*참\s*고|출력일시|$)'
        summary_match = re.search(summary_section_pattern, text, re.DOTALL | re.IGNORECASE)
        
        if summary_match:
            summary_text = summary_match.group(0)
            
            # 1순위 관련 모든 항목 찾기
            print("\n--- 1순위 관련 항목 ---")
            # "1순위", "1 근저당권설정", "1 근저당권 변경" 등 패턴 찾기
            rank1_patterns = [
                r'1\s+근저당권설정',
                r'1\s+근저당권\s*변경',
                r'1\s+근저당권\s*증액',
                r'1\s+근저당권\s*감액',
                r'1번\s*근저당권',
            ]
            
            for pattern in rank1_patterns:
                matches = list(re.finditer(pattern, summary_text, re.IGNORECASE))
                if matches:
                    print(f"\nPattern: {pattern}")
                    for match in matches:
                        start = max(0, match.start() - 50)
                        end = min(len(summary_text), match.end() + 200)
                        context = summary_text[start:end]
                        print(f"  Found at position {match.start()}:")
                        print(f"  Context: {context[:150]}...")
                        
                        # 채권최고액 찾기
                        amount_pattern = r'채권최고액[\s\S]*?금?\s*([\d,]+)\s*원'
                        amount_match = re.search(amount_pattern, context)
                        if amount_match:
                            print(f"  Amount: {amount_match.group(1)}")
        
        # 을구에서도 확인
        print("\n--- 을구에서 1순위 관련 항목 ---")
        eulgu_pattern = r'을\s*구[\s\S]*?(?=출력일시|$)'
        eulgu_match = re.search(eulgu_pattern, text, re.DOTALL | re.IGNORECASE)
        if eulgu_match:
            eulgu_text = eulgu_match.group(0)
            # 1순위 관련 항목 찾기 (예: "3-2 근저당권 변경")
            rank1_items = re.finditer(r'(\d+)\s*-\s*(\d+)\s*근저당권', eulgu_text)
            for item in rank1_items:
                print(f"  Found: {item.group(0)}")
                # 주변 텍스트 확인
                start = max(0, item.start() - 100)
                end = min(len(eulgu_text), item.end() + 300)
                context = eulgu_text[start:end]
                print(f"  Context: {context[:200]}...")
                
                # 채권최고액 찾기
                amount_pattern = r'채권최고액[\s\S]*?금?\s*([\d,]+)\s*원'
                amount_match = re.search(amount_pattern, context)
                if amount_match:
                    print(f"  Amount: {amount_match.group(1)}")

if __name__ == "__main__":
    main()
