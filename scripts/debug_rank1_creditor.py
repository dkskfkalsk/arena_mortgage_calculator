# -*- coding: utf-8 -*-
"""1순위 creditor 확인"""
import os
import sys
import re
import fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_dir = os.path.join(base, "pdf_Parsing_example")
    
    path = os.path.join(pdf_dir, "전욱현 260121.pdf")
    
    # PDF 텍스트 추출
    doc = fitz.open(path)
    text = "\n".join([p.get_text() or "" for p in doc])
    doc.close()
    
    # 을구에서 1순위 블록 찾기
    eulgu_pattern = r'을\s*구[\s\S]*?(?=출력일시|$)'
    eulgu_match = re.search(eulgu_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if eulgu_match:
        eulgu_text = eulgu_match.group(0)
        
        # 1순위 근저당권설정 찾기
        rank1_match = re.search(r'^1\s+근저당권설정', eulgu_text, re.MULTILINE)
        if rank1_match:
            start_pos = rank1_match.start()
            # 다음 순위까지
            next_rank_match = re.search(r'^2\s+근저당권설정', eulgu_text[start_pos+1:], re.MULTILINE)
            if next_rank_match:
                end_pos = start_pos + 1 + next_rank_match.start()
            else:
                end_pos = min(start_pos + 1000, len(eulgu_text))
            
            rank1_block = eulgu_text[start_pos:end_pos]
            
            print("=== 1순위 블록 ===")
            print(rank1_block[:500])
            print("\n=== 근저당권자 검색 ===")
            
            # 근저당권자 패턴 찾기
            creditor_patterns = [
                r'근저당권자\s+([가-힣a-zA-Z0-9]+(?:\s+[가-힣a-zA-Z0-9]+)*)',
                r'근저당권자\s+([^\n]+)',
            ]
            
            for pattern in creditor_patterns:
                matches = list(re.finditer(pattern, rank1_block))
                print(f"\nPattern: {pattern}")
                print(f"  Found: {len(matches)} matches")
                for match in matches:
                    print(f"  Match: '{match.group(0)}'")
                    print(f"  Group 1: '{match.group(1)}'")

if __name__ == "__main__":
    main()
