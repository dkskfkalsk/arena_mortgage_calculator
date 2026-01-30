# -*- coding: utf-8 -*-
"""
KB 부동산 API 중 세대수(households)를 반환하는 엔드포인트 탐색.
권현주 PDF 단지: 이현하이클래스웰가 15385 (실제 세대수 1,268)
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

BASE = "https://api.kbland.kr"
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Cache-Control": "no-cache",
    "Origin": "https://kbland.kr",
    "Referer": "https://kbland.kr/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
COMPLEX_ID = "15385"
HOUSEHOLD_KEYS = ["세대수", "households", "totHshldCnt", "hshldCnt", "총세대수", "totalHouseholdCnt", "hshldCo"]


def flatten(obj, prefix="", out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                flatten(v, p, out)
            else:
                out.append((p, v))
    elif isinstance(obj, list) and obj and prefix.count(".") < 5:
        for i, x in enumerate(obj[:5]):
            flatten(x, f"{prefix}[{i}]", out)
    return out


def find_household_candidates(flat):
    candidates = []
    for path, v in flat:
        if v is None:
            continue
        k = path.split(".")[-1].split("[")[0]
        if any(hk in k for hk in ["세대", "household", "hshld", "호수", "호"]):
            candidates.append((path, v))
        if isinstance(v, (int, float)) and 100 <= v <= 2000 and "가격" not in path and "price" not in path.lower():
            candidates.append((path, v))
        if isinstance(v, str) and re.match(r"^[\d,]+$", str(v).replace(",", "")):
            n = int(str(v).replace(",", ""))
            if 100 <= n <= 2000:
                candidates.append((path, v))
    return candidates


def try_get(url, params):
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None, r.status_code, None
        return r.json(), r.status_code, None
    except Exception as e:
        return None, -1, str(e)


def main():
    # 가능한 land-complex 엔드포인트 후보
    endpoints = [
        ("/land-complex/complex/info", {"단지기본일련번호": COMPLEX_ID}),
        ("/land-complex/complex/detail", {"단지기본일련번호": COMPLEX_ID}),
        ("/land-complex/complex/overview", {"단지기본일련번호": COMPLEX_ID}),
        ("/land-complex/complex/baseInfo", {"단지기본일련번호": COMPLEX_ID}),
        ("/land-complex/complex/summary", {"단지기본일련번호": COMPLEX_ID}),
        ("/land-complex/complex/basic", {"단지기본일련번호": COMPLEX_ID}),
        ("/land-complex/detail", {"단지기본일련번호": COMPLEX_ID}),
        ("/land-complex/complex/complexInfo", {"단지기본일련번호": COMPLEX_ID}),
        ("/land-complex/complex/건물정보", {"단지기본일련번호": COMPLEX_ID}),
        ("/land-complex/complex/complexDetail", {"단지기본일련번호": COMPLEX_ID}),
        ("/land-complex/complex/getComplexDetail", {"단지기본일련번호": COMPLEX_ID}),
        ("/land-complex/complex/단지상세", {"단지기본일련번호": COMPLEX_ID}),
        ("/map/complex/detail", {"complexId": COMPLEX_ID, "단지기본일련번호": COMPLEX_ID}),
        ("/map/complex/info", {"complexId": COMPLEX_ID}),
    ]
    print(f"=== KB API 세대수 탐색 (단지기본일련번호={COMPLEX_ID}) ===\n")
    for path, params in endpoints:
        url = BASE + path
        data, status, err = try_get(url, params)
        if err:
            print(f"[SKIP] {path}  error={err}")
            continue
        if status != 200:
            print(f"[{status}] {path}")
            continue
        flat = flatten(data)
        cand = find_household_candidates(flat)
        print(f"[200] {path}")
        if cand:
            for p, v in cand:
                print(f"      후보: {p} = {v}")
        # 상위 키만 출력 (구조 파악)
        if isinstance(data, dict):
            top = list(data.keys())[:12]
            print(f"      top keys: {top}")
        print()
    print("=== fastPriceInfo 단지 항목 내 세대 관련 필드 ===")
    url = f"{BASE}/land-price/price/fastPriceInfo"
    r = requests.get(url, params={"법정동코드": "4817012700", "유형": "1", "거래유형": "0"}, headers=HEADERS, timeout=15)
    if r.status_code == 200:
        j = r.json()
        body = j.get("dataBody") or {}
        arr = body.get("data") or []
        for c in arr:
            if str(c.get("단지기본일련번호")) == COMPLEX_ID:
                for k, v in c.items():
                    if "세대" in k or "호" in k or "동" in k:
                        print(f"  {k}: {v}")
                break

    print("\n=== mpriByType 응답 구조 (세대/동/호 등) ===")
    r2 = requests.get(f"{BASE}/land-complex/complex/mpriByType", params={"단지기본일련번호": COMPLEX_ID}, headers=HEADERS, timeout=15)
    if r2.status_code == 200:
        j2 = r2.json()
        flat2 = flatten(j2)
        for path, v in flat2:
            if any(x in path for x in ["세대", "동", "호", "household", "hshld", "bldg"]) or (
                isinstance(v, (int, float)) and 100 <= v <= 5000 and "가격" not in path and "price" not in path.lower()
            ):
                print(f"  {path} = {v}")

    print("\n=== 물건식별자로 추가 경로 시도 ===")
    info = requests.get(f"{BASE}/land-complex/complex/info", params={"단지기본일련번호": COMPLEX_ID}, headers=HEADERS, timeout=15).json()
    data = (info.get("dataBody") or {}).get("data") or {}
    molgun = data.get("물건식별자")
    if molgun:
        for ep, prm in [
            ("/land-complex/complex/detail", {"물건식별자": molgun}),
            ("/land-complex/complex/detail", {"단지기본일련번호": COMPLEX_ID, "물건식별자": molgun}),
        ]:
            d, st, err = try_get(BASE + ep, prm)
            if st != 200 or err:
                continue
            status = (d or {}).get("dataBody", {}).get("status") if isinstance(d, dict) else None
            if status == 404:
                continue
            flat = flatten(d) if d else []
            cand = find_household_candidates(flat)
            print(f"  [200] {ep} {prm}")
            for p, v in cand[:15]:
                print(f"    {p} = {v}")


if __name__ == "__main__":
    main()
