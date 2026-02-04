# -*- coding: utf-8 -*-
"""api.kbland.kr land-complex/complex/info API 응답 구조 확인"""
import json
import requests

url = "https://api.kbland.kr/land-complex/complex/info"
params = {"단지기본일련번호": "4024"}
headers = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    "Referer": "https://kbland.kr/",
}

r = requests.get(url, params=params, headers=headers, timeout=15)
print("Status:", r.status_code)
data = r.json()
# 보기 좋게 출력 (키 목록 + 사용승인일 관련)
body = data.get("dataBody", {}).get("data") or data
if isinstance(body, dict):
    print("Keys:", list(body.keys()))
    for k in ["사용승인일", "준공일", "세대수", "총세대수", "동수", "재건축여부"]:
        if k in body:
            print(f"  {k}: {body[k]}")
print("\nFull data (truncated):")
print(json.dumps(body, ensure_ascii=False, indent=2)[:3000])
