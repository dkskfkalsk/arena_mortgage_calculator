# -*- coding: utf-8 -*-
"""공동명의 테스트"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.registry_parser import analyze_pdf

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_dir = os.path.join(base, "pdf_Parsing_example")
    
    path = os.path.join(pdf_dir, "김연정&장재동 260123.pdf")
    
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
    
    print(f"=== {os.path.basename(path)} 분석 ===\n")
    
    try:
        doc = analyze_pdf(path)
        print(f"소유자 수: {len(doc.소유자목록)}명")
        for i, owner in enumerate(doc.소유자목록, 1):
            print(f"  {i}. {owner.성명} ({owner.생년월일}) - {owner.지분}")
        
        # 성명 표시 형식 확인
        if len(doc.소유자목록) >= 2:
            owner_names = ", ".join([o.성명 for o in doc.소유자목록[:2]])
            print(f"\n성명 표시: {owner_names}")
        elif len(doc.소유자목록) == 1:
            print(f"\n성명 표시: {doc.소유자목록[0].성명}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
