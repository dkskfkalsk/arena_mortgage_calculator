# -*- coding: utf-8 -*-
"""재건축 정규식 직접 테스트"""
import re

# 실제 페이지에서 가져온 텍스트 (개행 포함)
test_text = """재건축 진행현황
1단계기본계획수립
2단계정비구역지정
3단계조합설립추진
'2025.01.24
4단계추진위원회승인
'2025.08.18
5단계조합설립인가
6단계사업시행인가
7단계관리처분인가
8단계착공 및 철거
9단계일반분양"""

print("=== 테스트 텍스트 ===")
print(test_text)
print(f"\n텍스트 길이: {len(test_text)}")

# 수정된 정규식
pattern = r"(\d+)단계([가-힣]+)\s*['']?\s*(\d{4}\.\d{2}\.\d{2})"

print(f"\n=== 정규식 패턴 ===")
print(pattern)

matches = list(re.finditer(pattern, test_text))
print(f"\n매칭된 개수: {len(matches)}")

for i, m in enumerate(matches):
    print(f"\n[{i+1}] 전체 매칭: '{m.group(0)}'")
    print(f"    단계: {m.group(1)}")
    print(f"    이름: {m.group(2)}")
    print(f"    날짜: {m.group(3)}")

# 추가: 단계명 없이 날짜만 있는 케이스도 테스트
test_text2 = """5단계조합설립인가
6단계사업시행인가"""

print("\n\n=== 날짜 없는 케이스 테스트 ===")
print(test_text2)
matches2 = list(re.finditer(pattern, test_text2))
print(f"매칭된 개수: {len(matches2)} (예상: 0)")
