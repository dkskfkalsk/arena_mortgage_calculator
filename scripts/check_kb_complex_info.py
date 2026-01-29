# -*- coding: utf-8 -*-
"""KB API 단지 정보 응답 필드 확인 (세대수 등)"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from KB_api.kb_price_api import KBPriceAPI

# 권현주 PDF 단지: 곡반정동 1180, 단지기본일련번호 15385
api = KBPriceAPI()
complex_id = "15385"
out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "kb_complex_info_keys.txt")

# 1) get_complex_info (land-complex/complex/info) 응답 키 확인
info = api.get_complex_info(complex_id)
lines = ["=== get_complex_info(15385) ==="]
if info:
    lines.append("Keys: " + ", ".join(info.keys()))
    for k, v in info.items():
        lines.append(f"  {k}: {v}")
else:
    lines.append("(None)")

# 2) fastPriceInfo 단지 목록에서 해당 단지 항목 키 확인
dongcode = "4817012700"
complexes = api.get_complex_list(dongcode)
target = next((c for c in complexes if str(c.get("단지기본일련번호")) == complex_id), None)
lines.append("\n=== fastPriceInfo 단지 항목 ===")
if target:
    lines.append("Keys: " + ", ".join(target.keys()))
    for k, v in target.items():
        if k == "매매":
            lines.append(f"  {k}: (리스트 {len(v)}개)")
        else:
            lines.append(f"  {k}: {v}")
else:
    lines.append("(해당 단지 없음)")

with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("Written:", out_path)
print(lines[0])
print(lines[1][:200])
