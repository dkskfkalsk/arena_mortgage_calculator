# -*- coding: utf-8 -*-
"""fastPriceInfo API 응답에서 단지별 필드 확인"""
import json
import requests

url = "https://api.kbland.kr/land-price/price/fastPriceInfo"
params = {"법정동코드": "4117110100", "유형": "1", "거래유형": "0"}
headers = {"Accept": "application/json", "Referer": "https://kbland.kr/", "User-Agent": "Mozilla/5.0"}

r = requests.get(url, params=params, headers=headers, timeout=15)
data = r.json()
complexes = data.get("dataBody", {}).get("data", [])
# 진흥아파트(4024) 찾기
for c in complexes:
    if str(c.get("단지기본일련번호")) == "4024":
        print("진흥아파트(4024) 필드:")
        for k, v in c.items():
            if v and str(v).strip():
                print(f"  {k}: {v}")
        break
else:
    print("4024 없음, 첫 단지 키:")
    if complexes:
        print(list(complexes[0].keys()))
