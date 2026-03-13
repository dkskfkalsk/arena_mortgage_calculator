# -*- coding: utf-8 -*-
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parsers.registry_parser import RegistryParser

pdf_path = r"pdf_Parsing_example/김건호 광진구.pdf"
parser = RegistryParser()
parser.extract_text_from_pdf(pdf_path)

# rank_pattern 매칭 확인
summary_pattern = r'\(근\)저당권\s*및\s*전세권\s*등[\s\S]*?(?=\[\s*참\s*고|출력일시|$)'
summary_match = re.search(summary_pattern, parser.text, re.DOTALL | re.IGNORECASE)
summary_text = summary_match.group(0) if summary_match else ""

rank_pattern = r'(\d+)\s+근저당권설정'
rank_matches = list(re.finditer(rank_pattern, summary_text))

lines = []
lines.append("=== rank_pattern 매칭 ===")
lines.append(f"찾은 순위: {[m.group(1) for m in rank_matches]}")

for i, rm in enumerate(rank_matches):
    rank = rm.group(1)
    start = rm.start()
    end = rank_matches[i+1].start() if i+1 < len(rank_matches) else len(summary_text)
    block = summary_text[start:end]
    lines.append(f"\n--- 순위 {rank} 블록 ---")
    lines.append(block[:600])
    
    # 채권최고액
    am = re.search(r'채권최고액[\s\S]*?금?\s*([\d,]+)\s*원', block)
    lines.append(f"채권최고액: {'O' if am else 'X'} {am.group(1) if am else ''}")
    
    # 근저당권자
    cm = re.search(r'근저당권자\s*[:：]?\s*([가-힣a-zA-Z0-9]+(?:\s+[가-힣a-zA-Z0-9]+)*)', block)
    if cm:
        cred = cm.group(1).strip()
        cred = re.split(r'\n\s*\d+|\n\s*[가-힣]+\s*근저당권', cred)[0].strip()
        cred = re.sub(r'\s+', '', cred)
        lines.append(f"근저당권자: O '{cred}' len={len(cred)}")
    else:
        lines.append("근저당권자: X")

# 말소 패턴 확인 (3번)
lines.append("\n=== 3번 말소 여부 ===")
cancel_patterns = [
    r'3번\s*근저당권\s*설정\s*등\s*기\s*말\s*소',
    r'3\s+근저당권설정등기말소',
]
for p in cancel_patterns:
    m = re.search(p, parser.text, re.IGNORECASE)
    lines.append(f"패턴 '{p[:30]}...': {'매칭됨' if m else '없음'}")

# 말소 패턴 (3번) - rank_boundary 포함하여 실제 사용 패턴과 동일하게
lines.append("\n=== 말소 패턴 (3번) - 실제 cancel_patterns ===")
rank_num = "3"
rank_boundary = r'(?<!\d)' if rank_num.isdigit() else ''
cancel_patterns = [
    rf'{rank_boundary}{rank_num}번\s*근저당권\s*설정\s*등\s*기\s*말\s*소',
    rf'{rank_boundary}{rank_num}번\s*근저당권\s*설정\s*등.*?\n\s*기\s*말\s*소',
    rf'{rank_boundary}{rank_num}번\s*근저당권\s*설정\s*등\s*기.*?말\s*소',
    rf'{rank_boundary}{rank_num}번\s*근저당권\s*설정[,\s]*.*?등\s*기\s*말\s*소',
    rf'{rank_boundary}{rank_num}번[,\s]*(?:[,\s]|\d+번)*근저당권\s*설정\s*등\s*기\s*말\s*소',
    rf'{rank_boundary}{rank_num}번\s*근저당권\s*말\s*소(?!\s*[가-힣a-zA-Z])',
]
for i, p in enumerate(cancel_patterns):
    m = re.search(p, parser.text, re.DOTALL | re.IGNORECASE)
    if m:
        lines.append(f"  패턴{i+1} 매칭됨! 매칭구간: ...{parser.text[max(0,m.start()-20):m.end()+30]}...")
    else:
        lines.append(f"  패턴{i+1}: 없음")

# "3번" 또는 "3번" 근처 텍스트 확인 (오매칭 가능성)
lines.append("\n=== '3번' 관련 텍스트 전체 검색 ===")
for m in re.finditer(r'.{0,30}3번.{0,50}', parser.text):
    lines.append(f"  ...{m.group(0)}...")

# 최종 결과
mortgages = parser._extract_mortgages()
lines.append("\n=== 최종 추출 근저당권 ===")
for m in mortgages:
    lines.append(f"  {m.순위번호}순위: {m.근저당권자}")

with open("debug_mortgage_output.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
