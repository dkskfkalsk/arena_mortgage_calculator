# -*- coding: utf-8 -*-
"""KB API complex info 확인"""
import requests

# 일반 아파트 (진흥아파트, 4024)
response1 = requests.get("https://api.kbland.kr/land-complex/complex/info?complexNo=4024")
print("=== 4024 (진흥아파트) ===")
if response1.ok:
    data1 = response1.json()
    print(f"complexNm: {data1.get('data', {}).get('complexNm')}")
    print(f"complexPyengName: {data1.get('data', {}).get('complexPyengName')}")
    print(f"bjdongNm: {data1.get('data', {}).get('bjdongNm')}")
    print(f"useAprvYmd: {data1.get('data', {}).get('useAprvYmd')}")
    print(f"complexFeatureDesc: {data1.get('data', {}).get('complexFeatureDesc')}")
    print(f"complexDscr: {data1.get('data', {}).get('complexDscr')}")
    print("전체 keys:", list(data1.get('data', {}).keys()))
else:
    print(f"Error: {response1.status_code}")

print("\n" + "="*50 + "\n")

# 주상복합 (43564)
response2 = requests.get("https://api.kbland.kr/land-complex/complex/info?complexNo=43564")
print("=== 43564 (주상복합?) ===")
if response2.ok:
    data2 = response2.json()
    print(f"complexNm: {data2.get('data', {}).get('complexNm')}")
    print(f"complexPyengName: {data2.get('data', {}).get('complexPyengName')}")
    print(f"bjdongNm: {data2.get('data', {}).get('bjdongNm')}")
    print(f"useAprvYmd: {data2.get('data', {}).get('useAprvYmd')}")
    print(f"complexFeatureDesc: {data2.get('data', {}).get('complexFeatureDesc')}")
    print(f"complexDscr: {data2.get('data', {}).get('complexDscr')}")
    print("전체 keys:", list(data2.get('data', {}).keys()))
else:
    print(f"Error: {response2.status_code}")
