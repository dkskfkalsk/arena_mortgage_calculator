# -*- coding: utf-8 -*-
"""직접 확인"""
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
        
        # "김연정" 또는 "장재동" 키워드 찾기
        print("=== '김연정' 또는 '장재동' 키워드 찾기 ===")
        if '김연정' in gapgu_text:
            print("'김연정' 발견!")
            idx = gapgu_text.find('김연정')
            print(f"주변 텍스트: {repr(gapgu_text[max(0, idx-20):idx+100])}")
        
        if '장재동' in gapgu_text:
            print("\n'장재동' 발견!")
            idx = gapgu_text.find('장재동')
            print(f"주변 텍스트: {repr(gapgu_text[max(0, idx-20):idx+100])}")
        
        # "소유자" 키워드 찾기
        print("\n=== '소유자' 키워드 찾기 ===")
        if '소유자' in gapgu_text:
            print("'소유자' 발견!")
            idx = gapgu_text.find('소유자')
            print(f"주변 텍스트: {repr(gapgu_text[max(0, idx-30):idx+50])}")
        else:
            print("'소유자' 키워드를 찾을 수 없습니다.")
            # 대신 "791106" 또는 "771228" 주민번호 찾기
            print("\n=== 주민번호 패턴 찾기 ===")
            resident_pattern = r'(\d{6})-[\d\*]+'
            matches = list(re.finditer(resident_pattern, gapgu_text))
            for match in matches[:5]:
                idx = match.start()
                print(f"주민번호 {match.group(1)} 주변: {repr(gapgu_text[max(0, idx-30):idx+30])}")

if __name__ == "__main__":
    main()
