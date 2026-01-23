# -*- coding: utf-8 -*-
"""패턴 테스트"""
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
        print("=== 갑구 텍스트 (처음 800자) ===")
        print(repr(gapgu_text[:800]))
        print("\n=== 소유자 패턴 테스트 ===")
        
        # 패턴 1: DOTALL 모드
        pattern1 = r'([가-힣]{2,4})\s*\(\s*소유자\s*\)[\r\n]+\s*(\d{6})-[\d\*]+'
        matches1 = list(re.finditer(pattern1, gapgu_text, re.DOTALL))
        print(f"패턴1 (소유자 키워드, DOTALL): {len(matches1)}개")
        for m in matches1:
            print(f"  - {m.group(1)} ({m.group(2)})")
        
        # 패턴 2: 이름 다음 줄 주민번호
        pattern2 = r'([가-힣]{2,4})[\r\n]+\s*(\d{6})-[\d\*]+'
        matches2 = list(re.finditer(pattern2, gapgu_text, re.DOTALL))
        print(f"\n패턴2 (이름 다음 줄 주민번호, DOTALL): {len(matches2)}개")
        for m in matches2[:10]:  # 처음 10개만
            resident_num = m.group(2)
            if len(resident_num) == 6 and resident_num.isdigit():
                try:
                    mm = int(resident_num[2:4])
                    dd = int(resident_num[4:6])
                    if 1 <= mm <= 12 and 1 <= dd <= 31:
                        print(f"  - {m.group(1)} ({m.group(2)})")
                except:
                    pass

if __name__ == "__main__":
    main()
