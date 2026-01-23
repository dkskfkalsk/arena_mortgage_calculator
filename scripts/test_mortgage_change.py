# -*- coding: utf-8 -*-
"""근저당권 변경 테스트"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.registry_parser import analyze_pdf

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
        
        try:
            doc = analyze_pdf(path)
            print(f"근저당권: {len(doc.근저당권목록)}건")
            for m in doc.근저당권목록:
                # 만단위로 변환
                amount_str = m.채권최고액.replace("금 ", "").replace("원", "").replace(",", "")
                try:
                    amount_num = int(amount_str)
                    amount_man = amount_num // 10000
                    print(f"  - {m.순위번호}순위 {m.근저당권자}({m.채무자}) {amount_man:,}만원")
                except:
                    print(f"  - {m.순위번호}순위 {m.근저당권자}({m.채무자}) {m.채권최고액}")
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
