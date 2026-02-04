# -*- coding: utf-8 -*-
"""재건축 패턴 테스트"""
import re

# 테스트 케이스
test_cases = [
    "4단계 추진위원회승인 '2025.08.18",
    "4단계추진위원회승인'2025.08.18",
    "4단계 추진위원회승인 '2025.08.18",  # curly quote
    "5단계조합설립인가 2017.06.01",
]

patterns = [
    (r"(\d+)단계\s*([가-힣]+)['\s]*(\d{4}\.\d{2}\.\d{2})", "현재"),
    (r"(\d+)단계\s*([가-힣]+)['\s''\s]*(\d{4}\.\d{2}\.\d{2})", "curly quote 추가"),
]

for pattern, desc in patterns:
    print(f"\n=== 패턴: {desc} ===")
    print(f"regex: {pattern}")
    for text in test_cases:
        m = re.search(pattern, text)
        if m:
            print(f"  OK '{text}' -> step={m.group(1)}, name={m.group(2)}, date={m.group(3)}")
        else:
            print(f"  FAIL '{text}' -> no match")
