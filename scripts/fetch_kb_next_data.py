# -*- coding: utf-8 -*-
"""
kbland.kr/c/15385 (이현하이클래스웰가) 세대수 확인용 스크립트.

Next.js _next/data/{buildId}/c/15385.json 을 requests로 호출해
실제 응답 구조를 확인합니다. (Vercel에서도 동일한 requests로 호출 가능)

실행 (프로젝트 루트에서):
  python scripts/fetch_kb_next_data.py

출력: buildId, _next/data JSON 상위 키, 세대수/동수 후보 필드
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

COMPLEX_ID = "15385"  # 이현하이클래스웰가
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://kbland.kr/",
}


def get_build_id(session):
    """메인 또는 /c/ 페이지에서 __NEXT_DATA__.buildId 추출."""
    for url in ("https://kbland.kr/", f"https://kbland.kr/c/{COMPLEX_ID}"):
        try:
            r = session.get(url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            text = r.text or ""
            m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>([^<]+)</script>', text)
            if not m:
                m = re.search(r'<script[^>]*type=["\']application/json["\'][^>]*id=["\']__NEXT_DATA__["\'][^>]*>([^<]+)</script>', text)
            if m:
                data = json.loads(m.group(1))
                bid = data.get("buildId")
                if isinstance(bid, str) and bid:
                    return bid, url
        except Exception as e:
            print(f"  buildId 추출 실패 {url}: {e}")
    return None, None


def find_keys(obj, target_keys, path="", found=None):
    """중첩 dict/list에서 target_keys가 나오는 경로와 값 수집."""
    if found is None:
        found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if k in target_keys:
                found.append((p, v))
            find_keys(v, target_keys, p, found)
    elif isinstance(obj, list) and obj and path.count(".") < 10:
        for i, item in enumerate(obj[:3]):
            find_keys(item, target_keys, f"{path}[{i}]", found)
    return found


def main():
    try:
        import requests
    except ImportError:
        print("pip install requests 후 실행하세요.")
        return

    session = requests.Session()
    print("1) buildId 추출 중...")
    build_id, from_url = get_build_id(session)
    if not build_id:
        print("   buildId를 찾지 못했습니다. (HTML에 __NEXT_DATA__ 없음)")
        return
    print(f"   buildId: {build_id} (from {from_url})")

    url = f"https://kbland.kr/_next/data/{build_id}/c/{COMPLEX_ID}.json"
    print(f"\n2) GET {url}")
    r = session.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=10)
    if r.status_code != 200:
        print(f"   HTTP {r.status_code}")
        return
    data = r.json()
    print("   OK")

    print("\n3) 상위 키:", list(data.keys()) if isinstance(data, dict) else type(data))

    h_keys = ["세대수", "households", "totHshldCnt", "hshldCnt", "총세대수", "totalHouseholdCnt"]
    b_keys = ["동수", "buildings", "bldgCnt", "totBldgCnt", "총동수"]
    found_h = find_keys(data, h_keys)
    found_b = find_keys(data, b_keys)
    print("\n4) 세대수 후보 필드:")
    for path, val in found_h:
        print(f"   {path} = {val}")
    print("   동수 후보 필드:")
    for path, val in found_b:
        print(f"   {path} = {val}")

    out_path = os.path.join(ROOT, "scripts", "kb_next_data_15385.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n5) 전체 JSON 저장: {out_path}")


if __name__ == "__main__":
    main()
