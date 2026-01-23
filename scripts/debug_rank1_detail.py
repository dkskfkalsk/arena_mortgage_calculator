# -*- coding: utf-8 -*-
"""1순위 상세 확인"""
import os
import sys
import re
import fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_dir = os.path.join(base, "pdf_Parsing_example")
    
    path = os.path.join(pdf_dir, "전욱현 260121.pdf")
    
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
    
    # PDF 텍스트 추출
    doc = fitz.open(path)
    text = "\n".join([p.get_text() or "" for p in doc])
    doc.close()
    
    # 을구에서 1순위 관련 모든 항목 찾기
    eulgu_pattern = r'을\s*구[\s\S]*?(?=출력일시|$)'
    eulgu_match = re.search(eulgu_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if eulgu_match:
        eulgu_text = eulgu_match.group(0)
        
        print("=== 1순위 관련 모든 항목 ===\n")
        
        # 1순위 또는 1-숫자 패턴 찾기
        rank1_pattern = r'(\d+)\s*-\s*(\d+)\s*근저당권|^(\d+)\s+근저당권설정'
        
        # 더 정확하게: 순위번호로 시작하는 항목들 찾기
        lines = eulgu_text.split('\n')
        in_rank1_section = False
        current_rank = None
        
        for i, line in enumerate(lines):
            # 순위번호 패턴 찾기 (예: "1", "1-1", "1-2", "3-2")
            rank_match = re.match(r'^(\d+)(?:-(\d+))?\s*', line.strip())
            if rank_match:
                main_rank = rank_match.group(1)
                sub_rank = rank_match.group(2)
                
                if main_rank == '1' or (main_rank == '3' and sub_rank == '2'):
                    print(f"\n--- Line {i}: {line.strip()} ---")
                    # 다음 몇 줄 출력
                    for j in range(i, min(i+10, len(lines))):
                        print(f"  {lines[j]}")
                    
                    # 채권최고액 찾기
                    section_text = '\n'.join(lines[i:min(i+10, len(lines))])
                    amount_pattern = r'채권최고액[\s\S]*?금?\s*([\d,]+)\s*원'
                    amount_match = re.search(amount_pattern, section_text)
                    if amount_match:
                        print(f"  >>> Amount: {amount_match.group(1)}")
                    
                    # 근저당권자 찾기
                    creditor_pattern = r'근저당권자\s+([가-힣a-zA-Z0-9]+(?:\s+[가-힣a-zA-Z0-9]+)*)'
                    creditor_match = re.search(creditor_pattern, section_text)
                    if creditor_match:
                        print(f"  >>> Creditor: {creditor_match.group(1).strip()}")

if __name__ == "__main__":
    main()
