# -*- coding: utf-8 -*-
"""소유자 추출 디버그"""
import os
import sys
import re
import fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_dir = os.path.join(base, "pdf_Parsing_example")
    
    path = os.path.join(pdf_dir, "김연정&장재동 260123.pdf")
    
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
    
    # PDF 텍스트 추출
    doc = fitz.open(path)
    text = "\n".join([p.get_text() or "" for p in doc])
    doc.close()
    
    print("=== 소유자 패턴 검색 ===\n")
    
    # 주요 등기사항 요약에서 소유자 찾기
    summary_pattern = r'소유현황[\s\S]*?(?=\d+\s+근저당권설정|\[|출력일시|$)'
    summary_match = re.search(summary_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if summary_match:
        summary_text = summary_match.group(0)
        print("=== 요약 섹션 ===")
        print(summary_text[:500])
        print("\n=== 소유자 패턴 매칭 ===")
        
        # 다양한 패턴 시도
        patterns = [
            r'(\S{2,4})\s*\(?\s*소유자\s*\)?\s*(\d{6})-\*+\s*(단독소유|[\d/]+지분)?\s*([가-힣\s\d\-\(\),]+?)(?=\d+\s|$|\n\n)',
            r'(\S{2,4})\s*\(?\s*소유자\s*\)?\s*(\d{6})',
            r'소유자\s+(\S{2,4})\s+(\d{6})',
        ]
        
        for pattern in patterns:
            matches = list(re.finditer(pattern, summary_text, re.MULTILINE))
            print(f"\nPattern: {pattern}")
            print(f"  Found: {len(matches)} matches")
            for match in matches:
                print(f"  Match: {match.groups()}")
    
    # 갑구에서도 찾기
    gapgu_pattern = r'갑\s*구[\s\S]*?(?=을\s*구|출력일시|$)'
    gapgu_match = re.search(gapgu_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if gapgu_match:
        gapgu_text = gapgu_match.group(0)
        print("\n=== 갑구 섹션 ===")
        print(gapgu_text[:1000])
        
        # 소유권이전 패턴 찾기
        owner_patterns = [
            r'소유권이전\s+[\s\S]*?소유자\s+(\S+)\s+(\d{6})',
            r'소유자\s+(\S+)\s+(\d{6})',
        ]
        
        for pattern in owner_patterns:
            matches = list(re.finditer(pattern, gapgu_text, re.MULTILINE))
            print(f"\n갑구 Pattern: {pattern}")
            print(f"  Found: {len(matches)} matches")
            for match in matches:
                print(f"  Match: {match.groups()}")

if __name__ == "__main__":
    main()
