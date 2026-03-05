# -*- coding: utf-8 -*-
"""
법정동코드 전방위 테스트: complex_id 32849(거제코아루파크드림) 추출 가능 경로 분석

목적:
1. 주변 법정동코드로 fastPriceInfo API 호출 → 32849가 반환되는지 확인
2. complex_id 32849가 KB API 어디서 추출 가능한지 파악
3. kbland.kr/c/32849 페이지가 존재하는데 API에서 안 나오는 원인 분석
"""
import json
import sys
import time
from pathlib import Path

import requests

# 프로젝트 루트 추가
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = "https://api.kbland.kr"
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://kbland.kr/",
    "Origin": "https://kbland.kr",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

TARGET_COMPLEX_ID = "32849"  # 거제코아루파크드림

# 거제시 일운면 주변 법정동코드 (전국_dongcode_data.json 기반)
DONGCODES_TO_TEST = [
    # 일운면 전체 및 리 단위
    ("4831031000", "일운면 전체"),
    ("4831031021", "일운면 망치리"),
    ("4831031022", "일운면 구조라리"),
    ("4831031023", "일운면 와현리"),
    ("4831031024", "일운면 지세포리"),  # 거제코아루파크드림 소재지
    ("4831031025", "일운면 소동리"),
    ("4831031026", "일운면 옥림리"),
    # 인접 면
    ("4831032000", "동부면 전체"),
    ("4831032021", "동부면 산촌리"),
    ("4831033000", "남부면 전체"),
    ("4831034000", "거제면 전체"),
    # 거제시 동 단위 (일부)
    ("4831010100", "능포동"),
    ("4831010900", "고현동"),
    ("4831010600", "옥포동"),
    # 5자리, 8자리 등 다른 형식 (API가 지원할 수 있음)
    ("48310", "거제시 5자리"),
    ("4831031", "일운면 7자리"),
    ("48310310", "일운면 8자리"),
]


def call_fast_price_info(dongcode: str, type_code: str = "1", trade_type: str = "0") -> list:
    """fastPriceInfo API 호출"""
    url = f"{BASE}/land-price/price/fastPriceInfo"
    params = {"법정동코드": dongcode, "유형": type_code, "거래유형": trade_type}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("dataBody", {}).get("data", []) or []
    except Exception as e:
        print(f"  [ERR] {e}")
        return []


def call_complex_info(complex_id: str) -> dict | None:
    """land-complex/complex/info API - 단지 기본정보"""
    url = f"{BASE}/land-complex/complex/info"
    params = {"단지기본일련번호": complex_id}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("dataBody", {}).get("data")
    except Exception as e:
        print(f"  [ERR] {e}")
        return None


def call_mpri_by_type(complex_id: str) -> list:
    """mpriByType API - 단지별 시세"""
    url = f"{BASE}/land-complex/complex/mpriByType"
    params = {"단지기본일련번호": complex_id}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("dataBody", {}).get("data", []) or []
    except Exception as e:
        print(f"  [ERR] {e}")
        return []


def main():
    print("=" * 70)
    print("법정동코드 전방위 테스트: complex_id 32849 (거제코아루파크드림)")
    print("=" * 70)

    # 1. complex_id 32849가 KB API에 존재하는지 확인 (info, mpriByType)
    print("\n[1] complex_id 32849 직접 조회 (info API)")
    info = call_complex_info(TARGET_COMPLEX_ID)
    if info:
        print("  [OK] get_complex_info(32849) 성공 - KB 시스템에 단지 존재")
        print(f"     단지명: {info.get('단지명', info.get('complexName', 'N/A'))}")
        print(f"     주소: {info.get('주소', info.get('address', 'N/A'))}")
        print(f"     법정동코드(API): {info.get('법정동코드', info.get('dongcode', 'N/A'))}")
    else:
        print("  [X] get_complex_info(32849) 실패 - 단지 미존재 또는 API 오류")

    print("\n[2] complex_id 32849 시세 조회 (mpriByType API)")
    prices = call_mpri_by_type(TARGET_COMPLEX_ID)
    if prices:
        print(f"  [OK] mpriByType 성공 - 시세 {len(prices)}개 타입")
    else:
        print("  [X] mpriByType 실패")

    # 2. 각 법정동코드로 fastPriceInfo 호출 → 32849 포함 여부
    print("\n[3] 법정동코드별 fastPriceInfo 결과 (32849 포함 여부)")
    print("-" * 70)

    found_in_dongcodes = []
    all_complex_ids_seen = set()

    for dongcode, label in DONGCODES_TO_TEST:
        time.sleep(0.3)  # API 부하 방지
        complexes = call_fast_price_info(dongcode)
        ids = [str(c.get("단지기본일련번호", "")) for c in complexes if c.get("단지기본일련번호") is not None]
        names = [c.get("단지명", "?") for c in complexes]

        has_32849 = TARGET_COMPLEX_ID in ids
        if has_32849:
            found_in_dongcodes.append((dongcode, label))

        all_complex_ids_seen.update(ids)

        status = "[OK] 32849 있음" if has_32849 else "  -"
        print(f"  {dongcode} ({label}): {len(complexes)}개 단지 {status}")
        if complexes and len(complexes) <= 8:
            print(f"      단지: {names}")
        elif complexes:
            print(f"      단지(일부): {names[:5]}...")

    # 3. 결과 요약
    print("\n" + "=" * 70)
    print("결과 요약")
    print("=" * 70)

    if found_in_dongcodes:
        print(f"\n[OK] complex_id 32849가 반환된 법정동코드: {found_in_dongcodes}")
    else:
        print(f"\n[X] 어떤 법정동코드로도 fastPriceInfo에서 32849가 반환되지 않음")
        print(f"   테스트한 법정동코드: {len(DONGCODES_TO_TEST)}개")

    # 4. API info에서 32849의 법정동코드 확인 (있으면)
    if info:
        api_dongcode = info.get("법정동코드") or info.get("dongcode") or info.get("lawdCd")
        if api_dongcode:
            print(f"\n[*] get_complex_info(32849) 응답의 법정동코드: {api_dongcode} (일운면 지세포리)")
            print(f"    -> fastPriceInfo(4831031024)는 32849를 반환하지 않음 (KB API 데이터 불일치)")

    # 5. complex_id 추출 가능 경로 정리
    print("\n" + "=" * 70)
    print("complex_id 32849 추출 가능 경로 분석")
    print("=" * 70)
    print("""
[추출 가능]
• kbland.kr/c/32849 URL: 단지 페이지 직접 접근 가능 (complex_id는 URL 경로)
• get_complex_info(32849): 단지 기본정보 조회 가능 (complex_id를 알고 있을 때)
• mpriByType(32849): 시세 조회 가능 (complex_id를 알고 있을 때)

[추출 불가]
• fastPriceInfo(법정동코드): 법정동코드로 단지 목록 조회 시 32849가 응답에 포함되지 않음
  → KB API가 해당 법정동에서 32849를 반환하지 않는 것으로 추정
  → kbland.kr 웹사이트는 별도 검색/매핑 DB를 사용할 가능성

[권장 대안]
• 단지명→complex_id 수동 매핑 테이블: "거제코아루파크드림" → 32849
• 공공데이터 실거래가 API: LAWD_CD=4831031024, APT_NAME=거제코아루파크드림
""")


if __name__ == "__main__":
    main()
