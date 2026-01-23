# -*- coding: utf-8 -*-
"""간단한 테스트"""
import os
import sys
import re
import fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_dir = os.path.join(base, "pdf_Parsing_example")
    
    path = os.path.join(pdf_dir, "김연정&장재동 260123.pdf")
    
    doc = fitz.open(path)
    pages_text = [p.get_text() or "" for p in doc]
    doc.close()
    
    # 마지막 페이지
    page_text = pages_text[-1]
    
    # 갑구 찾기
    gapgu_pattern = r'갑\s*구[\s\S]*?(?=을\s*구|출력일시|$)'
    gapgu_match = re.search(gapgu_pattern, page_text, re.DOTALL | re.IGNORECASE)
    
    if gapgu_match:
        gapgu_text = gapgu_match.group(0)
        lines = gapgu_text.split('\n')
        
        print(f"총 줄 수: {len(lines)}")
        print("\n=== '소유자' 키워드가 있는 줄 찾기 ===")
        for i, line in enumerate(lines):
            if '소유자' in line:
                print(f"줄 {i}: {repr(line)}")
                if i + 1 < len(lines):
                    print(f"  다음 줄: {repr(lines[i+1])}")
                if i + 2 < len(lines):
                    print(f"  다다음 줄: {repr(lines[i+2])}")
                print()

if __name__ == "__main__":
    main()
