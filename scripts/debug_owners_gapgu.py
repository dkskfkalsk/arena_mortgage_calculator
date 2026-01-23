# -*- coding: utf-8 -*-
"""갑구 소유자 상세 디버그"""
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
    
    # 갑구 찾기
    gapgu_pattern = r'갑\s*구[\s\S]*?(?=을\s*구|출력일시|$)'
    gapgu_match = re.search(gapgu_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if gapgu_match:
        gapgu_text = gapgu_match.group(0)
        print("=== 갑구 전체 텍스트 (처음 2000자) ===")
        print(gapgu_text[:2000])
        print("\n=== 소유권이전 항목 찾기 ===")
        
        # 소유권이전 패턴 찾기
        transfer_pattern = r'(\d+(?:-\d+)?)\s+소유권이전'
        transfer_matches = list(re.finditer(transfer_pattern, gapgu_text))
        print(f"소유권이전 항목: {len(transfer_matches)}개")
        
        for i, match in enumerate(transfer_matches):
            print(f"\n{i+1}. 항목번호: {match.group(1)}")
            start = match.start()
            # 다음 항목까지
            if i + 1 < len(transfer_matches):
                end = transfer_matches[i+1].start()
            else:
                end = min(start + 2000, len(gapgu_text))
            
            block = gapgu_text[start:end]
            print(f"   블록 길이: {len(block)}")
            print(f"   블록 내용 (처음 500자):\n{block[:500]}")
            
            # 소유자 패턴 찾기
            owner_pattern = r'소유자\s+([가-힣]{2,4})\s+(\d{6})-[\d\*]+'
            owner_matches = list(re.finditer(owner_pattern, block))
            print(f"   소유자: {len(owner_matches)}명")
            for om in owner_matches:
                print(f"     - {om.group(1)} ({om.group(2)})")

if __name__ == "__main__":
    main()
