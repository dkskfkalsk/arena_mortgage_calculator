# -*- coding: utf-8 -*-
"""진석태 등기 1 (2).pdf 파싱 및 KB 시세 조회 디버그 (c/14094 매칭 확인)"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.registry_parser import analyze_pdf
from KB_api.kb_price_api import KBPriceAPI, get_kb_price_from_registry

pdf_name = "진석태 등기 1 (2).pdf"
root = os.path.dirname(os.path.dirname(__file__))
pdf_path = os.path.join(root, "pdf_Parsing_example", pdf_name)
if not os.path.exists(pdf_path):
    print("PDF not found:", pdf_path)
    sys.exit(1)

doc = analyze_pdf(pdf_path)
addr = doc.부동산_주소 or ""
area_str = doc.면적 or ""
print("=== 등기부 파싱 ===")
print("주소:", repr(addr))
print("면적:", repr(area_str))
print()

api = KBPriceAPI()
dongcode = api.find_dongcode(addr)
print("=== 추출 ===")
print("법정동코드:", dongcode)
print()

if dongcode:
    complexes = api.get_complex_list(dongcode)
    print("=== fastPriceInfo 단지 목록 (complex_id 14094 포함 여부) ===")
    print("단지 수:", len(complexes) if complexes else 0)
    target = None
    for i, c in enumerate(complexes or []):
        mid = c.get("단지기본일련번호")
        if str(mid) == "14094":
            target = c
            name = c.get("단지명") or c.get("name", "")
            addr_api = c.get("주소", "")
            mae = c.get("매매") or []
            print(f"  [FOUND] 단지기본일련번호=14094: {name}, 주소={addr_api}, 매매타입={len(mae)}개")
            break
    if not target:
        for i, c in enumerate((complexes or [])[:20]):
            name = c.get("단지명") or c.get("name", "")
            mid = c.get("단지기본일련번호")
            print(f"  [{i+1}] id={mid} {name}")
    print()

area_val = None
try:
    import re
    m = re.search(r"([\d.]+)", str(area_str))
    if m:
        area_val = float(m.group(1))
except Exception:
    pass
print("=== KB 시세 조회 (get_kb_price_from_registry) ===")
if addr and area_str:
    result = get_kb_price_from_registry(addr, area_str)
    if result:
        print("성공: kb_price=%s 만원, complex_id=%s, 단지=%s" % (
            result.get("kb_price"), result.get("complex_id"), result.get("complex_name")))
    else:
        print("실패 (None)")
else:
    print("주소/면적 없음")
