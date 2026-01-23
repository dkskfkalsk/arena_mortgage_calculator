# -*- coding: utf-8 -*-
"""소유자 상세 디버그"""
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
    
    # 주요 등기사항 요약에서 소유현황 찾기
    summary_pattern = r'소유현황[\s\S]*?(?=\d+\s+근저당권설정|\[|출력일시|$)'
    summary_match = re.search(summary_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if summary_match:
        summary_text = summary_match.group(0)
        print("=== 소유현황 섹션 ===")
        print(summary_text)
        print("\n=== 소유자 이름 찾기 ===")
        
        # 이름 패턴 찾기 (한글 2-4자)
        name_pattern = r'([가-힣]{2,4})'
        names = re.findall(name_pattern, summary_text)
        print(f"한글 이름 패턴: {names}")
        
        # 주민번호 패턴 찾기
        resident_pattern = r'(\d{6})-\*+'
        residents = re.findall(resident_pattern, summary_text)
        print(f"주민번호 패턴: {residents}")
    
    # 갑구에서 최신 소유권이전 찾기
    gapgu_pattern = r'갑\s*구[\s\S]*?(?=을\s*구|출력일시|$)'
    gapgu_match = re.search(gapgu_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if gapgu_match:
        gapgu_text = gapgu_match.group(0)
        print("\n=== 갑구에서 최신 소유권이전 찾기 ===")
        
        # 소유권이전 패턴 찾기 (최신 것)
        transfer_patterns = [
            r'소유권이전\s+\d+년\d+월\d+일[\s\S]*?소유자\s+([가-힣]+)\s+(\d{6})',
            r'소유권이전[\s\S]*?소유자\s+([가-힣]+)\s+(\d{6})',
        ]
        
        for pattern in transfer_patterns:
            matches = list(re.finditer(pattern, gapgu_text, re.MULTILINE))
            print(f"\nPattern: {pattern}")
            print(f"  Found: {len(matches)} matches")
            for match in matches:
                print(f"  Match: {match.groups()}")
                # 주변 텍스트 출력
                start = max(0, match.start() - 100)
                end = min(len(gapgu_text), match.end() + 200)
                print(f"  Context: {gapgu_text[start:end]}")

if __name__ == "__main__":
    main()
