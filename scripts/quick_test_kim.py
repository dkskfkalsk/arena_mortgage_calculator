# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')

from parsers.registry_parser import analyze_pdf
from KB_api.kb_price_api import get_kb_price_from_registry

r = analyze_pdf('pdf_Parsing_example/김경연 251230.pdf')
print(f"Address: {r.부동산_주소}")
print(f"Area: {r.면적}")

kb = get_kb_price_from_registry(r.부동산_주소, r.면적)
if kb:
    print(f"KB price: {kb.get('kb_price')} man-won")
    print(f"Complex ID: {kb.get('complex_id')}")
    print(f"Complex name: {kb.get('complex_name')}")
else:
    print("No KB price found")
