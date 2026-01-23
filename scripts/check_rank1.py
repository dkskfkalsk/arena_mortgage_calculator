# -*- coding: utf-8 -*-
"""1순위 확인"""
import os
import sys
import re
import fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.registry_parser import analyze_pdf

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_dir = os.path.join(base, "pdf_Parsing_example")
    
    path = os.path.join(pdf_dir, "전욱현 260121.pdf")
    
    print("=== 전욱현 260121.pdf 분석 ===\n")
    
    # PDF 파싱
    doc = analyze_pdf(path)
    print(f"추출된 근저당권: {len(doc.근저당권목록)}건")
    for m in doc.근저당권목록:
        amount_str = m.채권최고액.replace("금 ", "").replace("원", "").replace(",", "")
        try:
            amount_num = int(amount_str)
            amount_man = amount_num // 10000
            print(f"  {m.순위번호}순위: {m.근저당권자} - {amount_man:,}만원")
        except:
            print(f"  {m.순위번호}순위: {m.근저당권자} - {m.채권최고액}")
    
    # PDF 텍스트에서 1순위 관련 확인
    pdf_doc = fitz.open(path)
    text = "\n".join([p.get_text() or "" for p in pdf_doc])
    pdf_doc.close()
    
    print("\n=== PDF 텍스트에서 1순위 검색 ===\n")
    
    # 요약 섹션에서 1순위 찾기
    summary_pattern = r'\(근\)저당권\s*및\s*전세권\s*등[\s\S]*?(?=\[\s*참\s*고|출력일시|$)'
    summary_match = re.search(summary_pattern, text, re.DOTALL | re.IGNORECASE)
    if summary_match:
        summary_text = summary_match.group(0)
        rank1_matches = list(re.finditer(r'1\s+근저당권설정', summary_text))
        print(f"요약 섹션에서 '1 근저당권설정' 패턴: {len(rank1_matches)}개 발견")
        for match in rank1_matches:
            start = max(0, match.start() - 50)
            end = min(len(summary_text), match.end() + 200)
            print(f"  Context: {summary_text[start:end][:200]}...")
    
    # 을구에서 1순위 찾기
    eulgu_pattern = r'을\s*구[\s\S]*?(?=출력일시|$)'
    eulgu_match = re.search(eulgu_pattern, text, re.DOTALL | re.IGNORECASE)
    if eulgu_match:
        eulgu_text = eulgu_match.group(0)
        # "1 근저당권설정" 또는 "1-숫자 근저당권" 패턴 찾기
        rank1_items = list(re.finditer(r'^1\s+근저당권설정|^1\s*-\s*\d+\s*근저당권', eulgu_text, re.MULTILINE | re.IGNORECASE))
        print(f"\n을구에서 1순위 관련 항목: {len(rank1_items)}개 발견")
        for item in rank1_items:
            start = max(0, item.start() - 50)
            end = min(len(eulgu_text), item.end() + 200)
            print(f"  Found: {item.group(0)}")
            print(f"  Context: {eulgu_text[start:end][:200]}...")
            
            # 채권최고액 찾기
            section = eulgu_text[item.start():item.end() + 300]
            amount_match = re.search(r'채권최고액[\s\S]*?금?\s*([\d,]+)\s*원', section)
            if amount_match:
                print(f"  Amount: {amount_match.group(1)}")

if __name__ == "__main__":
    main()
