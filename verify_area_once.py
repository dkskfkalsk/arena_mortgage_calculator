# -*- coding: utf-8 -*-
"""박규용등기부.pdf 면적만 확인 (코드 수정 없음)"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parsers.registry_parser import analyze_pdf

base = os.path.dirname(os.path.abspath(__file__))
pdf_path = os.path.join(base, "pdf_Parsing_example", "박규용등기부.pdf")
if not os.path.exists(pdf_path):
    sys.exit(2)

doc = analyze_pdf(pdf_path)
print("면적:", doc.면적)
print("기대값: 74.90 (제17층 제1705호 전용면적)")
ok = doc.면적 and "74.90" in doc.면적
print("결과:", "OK" if ok else "FAIL")
sys.exit(0 if ok else 1)
