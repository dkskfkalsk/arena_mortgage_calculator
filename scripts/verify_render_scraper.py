# -*- coding: utf-8 -*-
"""Render main.py 로직을 로컬에서 직접 실행"""
import sys
import os
from pathlib import Path

# render-playwright 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent / "render-playwright"))

# Render main.py의 _scrape 함수 직접 호출
from main import _scrape

print("=== Render 스크래퍼 로직 로컬 검증 ===\n")
print("complex_id=4024 (진흥아파트) 테스트 중...\n")

result = _scrape("4024")

print("결과:")
print(f"  approval_date: {result.get('approval_date')}")
print(f"  years_since_completion: {result.get('years_since_completion')}")
print(f"  households: {result.get('households')}")
print(f"  buildings: {result.get('buildings')}")
print(f"  redevelop_stages: {result.get('redevelop_stages')}")
print(f"  error: {result.get('error')}")

print("\n검증:")
if result.get("error"):
    print(f"  ❌ 오류 발생: {result.get('error')}")
elif result.get("approval_date"):
    print(f"  ✅ 사용승인일 추출 성공: {result.get('approval_date')}")
else:
    print(f"  ⚠️ approval_date 없음 (body_text에서 패턴 매칭 실패)")

if result.get("households"):
    print(f"  ✅ 세대수 추출 성공: {result.get('households')}")
else:
    print(f"  ⚠️ households 없음")
