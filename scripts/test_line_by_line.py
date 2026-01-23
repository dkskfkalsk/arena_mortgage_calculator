# -*- coding: utf-8 -*-
"""줄 단위 테스트"""
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
        print("=== 갑구 텍스트를 줄 단위로 ===")
        lines = gapgu_text.split('\n')
        
        for i, line in enumerate(lines):
            if '소유자' in line or (i > 0 and '소유자' in lines[i-1]):
                print(f"줄 {i}: {repr(line)}")
                if i + 1 < len(lines):
                    print(f"  다음 줄: {repr(lines[i+1])}")
                print()
        
        # "소유자" 키워드가 있는 줄 찾기
        print("\n=== 소유자 패턴 매칭 ===")
        for i, line in enumerate(lines):
            name_match = re.search(r'([가-힣]{2,4})\s*\(\s*소유자\s*\)', line)
            if name_match:
                name = name_match.group(1)
                print(f"줄 {i}: 이름 '{name}' 발견")
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    resident_match = re.search(r'(\d{6})-[\d\*]+', next_line)
                    if resident_match:
                        print(f"  다음 줄에서 주민번호 발견: {resident_match.group(1)}")
                    else:
                        print(f"  다음 줄: {repr(next_line)}")

if __name__ == "__main__":
    main()
