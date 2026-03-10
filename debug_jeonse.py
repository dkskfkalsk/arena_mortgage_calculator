# -*- coding: utf-8 -*-
"""전세권 추출 디버그 - 동금동 83-4 강경화.pdf"""
import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parsers.registry_parser import RegistryParser

pdf_path = r"pdf_Parsing_example/동금동 83-4 강경화.pdf"
if not os.path.exists(pdf_path):
    pdf_path = r"../pdf_Parsing_example/동금동 83-4 강경화.pdf"

parser = RegistryParser()
parser.extract_text_from_pdf(pdf_path)

# 전세권 추출 (수정 전 로직 그대로 동작)
jeonse_list = parser._extract_jeonse()

lines = []
lines.append("=" * 60)
lines.append("전세권 추출 결과 (동금동 83-4 강경화.pdf)")
lines.append("=" * 60)

if not jeonse_list:
    lines.append("\n[추출된 전세권] 없음")
else:
    for i, j in enumerate(jeonse_list, 1):
        lines.append(f"\n{i}. 순위번호: {j.순위번호}")
        lines.append(f"   전세권자(근저당권자): {j.근저당권자}")
        lines.append(f"   대상소유자(채무자): {j.채무자}")
        lines.append(f"   전세금(채권최고액): {j.채권최고액}")
        lines.append(f"   설정일: {j.설정일}")
        lines.append(f"   권리종류: {j.권리종류}")

# 요약 섹션에서 전세권 관련 원문 추출
summary_pattern = r'\(근\)저당권\s*및\s*전세권\s*등[\s\S]*?(?=\[\s*참\s*고|출력일시|$)'
m = re.search(summary_pattern, parser.text, re.DOTALL | re.IGNORECASE)
if m:
    lines.append("\n" + "=" * 60)
    lines.append("요약본 섹션 '(근)저당권 및 전세권 등' 원문 (발췌)")
    lines.append("=" * 60)
    text = m.group(0)
    section_lines = text.split('\n')
    for i, line in enumerate(section_lines):
        if '전세권' in line or (i > 0 and '전세금' in section_lines[i-1]):
            lines.append(repr(line[:120]))

# 실제 매칭된 텍스트 블록 (jeonse_pattern으로 추출된 부분)
jeonse_pattern = r'(\d+)\s+전세권설정\s+(\d{4})년(\d{1,2})월(\d{1,2})일[\s\S]*?전세금\s*금?\s*([\d,]+)\s*원[\s\S]*?전세권자\s+(\S+)'
if m:
    for match in re.finditer(jeonse_pattern, m.group(0)):
        lines.append("\n[매칭된 원문 블록]")
        lines.append(match.group(0)[:400] + ("..." if len(match.group(0)) > 400 else ""))

# 전세권 산출 흐름
lines.append("\n" + "=" * 60)
lines.append("전세권 산출 흐름 (코드 로직)")
lines.append("=" * 60)
lines.append("1. 요약본에서 '(근)저당권 및 전세권 등' 섹션 검색")
lines.append("2. 패턴: (순위) 전세권설정 (날짜) ... 전세금 금(금액)원 ... 전세권자 (이름)")
lines.append("3. 대상소유자: 전세금 뒤 ~ 전세권자 앞의 한글 이름 (강경화 등)")
lines.append("4. 말소 여부 확인: 'N 전세권설정등기말소' 등 없으면 유효 전세권으로 포함")

# 파일로 저장 후 출력
output = "\n".join(lines)
with open("debug_jeonse_output.txt", "w", encoding="utf-8") as f:
    f.write(output)
print(output)
