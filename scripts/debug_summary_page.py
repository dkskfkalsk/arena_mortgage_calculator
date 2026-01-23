# -*- coding: utf-8 -*-
"""요약본 페이지 확인"""
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
    pages_text = [p.get_text() or "" for p in doc]
    doc.close()
    
    print(f"총 페이지 수: {len(pages_text)}\n")
    
    # 마지막 페이지와 마지막에서 2번째 페이지 확인
    for i, page_idx in enumerate([-1, -2] if len(pages_text) >= 2 else [-1]):
        if abs(page_idx) > len(pages_text):
            continue
            
        page_text = pages_text[page_idx]
        page_num = len(pages_text) + page_idx + 1
        
        print(f"=== 페이지 {page_num} (인덱스 {page_idx}) ===")
        print(f"텍스트 길이: {len(page_text)}")
        
        # 요약본 키워드 확인
        keywords = ['소유현황', '갑구', '을구', '요약', '소유자']
        found_keywords = [kw for kw in keywords if kw in page_text]
        print(f"발견된 키워드: {found_keywords}")
        
        # 갑구 찾기
        gapgu_match = re.search(r'갑\s*구', page_text, re.IGNORECASE)
        if gapgu_match:
            print(f"갑구 발견: 위치 {gapgu_match.start()}")
            gapgu_section = page_text[gapgu_match.start():gapgu_match.start() + 500]
            print(f"갑구 섹션 (처음 500자):\n{gapgu_section}\n")
            
            # 소유자 패턴 찾기
            owner_pattern = r'(?:소유자\s+)?([가-힣]{2,4})\s+(\d{6})-[\d\*]+'
            owner_matches = list(re.finditer(owner_pattern, gapgu_section))
            print(f"소유자 패턴 매칭: {len(owner_matches)}개")
            for match in owner_matches:
                print(f"  - {match.group(1)} ({match.group(2)})")
        else:
            print("갑구를 찾을 수 없습니다.")
        
        # 소유현황 찾기
        if '소유현황' in page_text:
            summary_match = re.search(r'소유현황[\s\S]*?(?=\d+\s+근저당권설정|출력일시|$)', page_text, re.DOTALL | re.IGNORECASE)
            if summary_match:
                summary_text = summary_match.group(0)
                print(f"\n소유현황 섹션 (처음 500자):\n{summary_text[:500]}\n")
        
        print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    main()
