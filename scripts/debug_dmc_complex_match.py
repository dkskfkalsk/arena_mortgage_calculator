# -*- coding: utf-8 -*-
"""디엠씨래미안클라시스 ↔ DMC래미안클라시스 매칭/추출/KB조회 디버그."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from KB_api import kb_price_api as m
from KB_api.kb_price_api import get_kb_price_from_registry


def extract_like_registry(address: str) -> str | None:
    """get_kb_price_from_registry와 동일한 단지명 추출 경로."""
    complex_name = m._extract_complex_name_from_address(address)
    if complex_name:
        return complex_name

    brand_alt = "|".join(
        re.escape(b)
        for b in m._COMPLEX_BRAND_SUFFIXES
        if len(b) >= 2 and b not in ("뉴", "더", "디", "엘", "리", "꿈")
    )
    complex_patterns = [
        r"([가-힣A-Za-z0-9]+(?:\s+[가-힣A-Za-z0-9]+){0,3}\s*\d*\s*(?:단지|타운|빌리지|시티|아파트|오피스텔))",
        r"((?:e|E)[\s\-]?편한세상\s*[가-힣A-Za-z0-9]+)",
        r"((?:THE|the)\s+[가-힣A-Za-z0-9]+(?:\s+[가-힣A-Za-z0-9]+)*)",
        r"([가-힣]+)오피스텔",
        r"([가-힣]+)아파트",
        r"([가-힣]+)빌라",
        r"([가-힣]+)다가구",
        r"([가-힣]+마을)",
        r"([가-힣]+단지)",
        r"([가-힣]+(?:힐스|힐스테이트)[가-힣]*)",
        rf"([가-힣A-Za-z0-9]*(?:{brand_alt})[가-힣A-Za-z0-9]*)",
    ]
    for pattern in complex_patterns:
        match = re.search(pattern, address)
        if match:
            candidate = m._clean_extracted_complex_name(match.group(1).strip())
            if not m._is_invalid_complex_name(candidate):
                return candidate

    match = re.search(
        r"\d+(?:-\d+)?\s+([가-힣]+?)(?=\s+제\d+동|\s+제\d+층|\s+제\d+호|$)",
        address,
    )
    if match:
        potential = match.group(1).strip()
        if len(potential) >= 2 and not m._is_invalid_complex_name(potential):
            return potential
    return None


def main() -> None:
    print("=== 1) 알파벳 음차 변환 ===")
    cases = [
        "디엠씨래미안클라시스",
        "DMC래미안클라시스",
        "시티자이",
        "아이파크",
        "이편한세상",
        "케이비골든타워",
    ]
    for c in cases:
        print(
            f"  {c!r}\n"
            f"    convert={m._hangul_letter_prefix_to_latin_name(c)!r}\n"
            f"    variants={m._expand_complex_name_search_variants(c)}\n"
            f"    tail={m._complex_name_hangul_tail(c)!r}\n"
            f"    norm={m._normalize_kb_complex_name_for_match(c)!r}"
        )

    print("\n=== 2) 동등/유사도 ===")
    pairs = [
        ("디엠씨래미안클라시스", "DMC래미안클라시스"),
        ("디엠씨래미안", "DMC래미안클라시스"),
        ("시티자이", "CT자이"),
        ("래미안클라시스", "DMC래미안클라시스"),
    ]
    for a, b in pairs:
        print(
            f"  {a} <-> {b}\n"
            f"    eq={m._complex_names_equivalent(a, b)} "
            f"score={m._score_complex_name_similarity(a, b):.2f}"
        )

    print("\n=== 3) 주소에서 단지명 추출 ===")
    addrs = [
        "서울특별시 서대문구 증가로 191 디엠씨래미안클라시스 제101동 제10층 제1001호",
        "서울특별시 서대문구 남가좌동 384 디엠씨래미안클라시스 제101동",
        "서울 서대문구 증가로 191 DMC래미안클라시스 제101동 제10층 제1001호",
    ]
    for address in addrs:
        name = extract_like_registry(address)
        print(
            f"  extract={name!r} convert={m._hangul_letter_prefix_to_latin_name(name or '')!r} "
            f"eq_DMC={m._complex_names_equivalent(name or '', 'DMC래미안클라시스')}"
        )

    print("\n=== 4) KB API 실조회 ===")
    tests = [
        (
            "도로명+한글단지",
            "서울특별시 서대문구 증가로 191 디엠씨래미안클라시스 제101동 제10층 제1001호",
            "84.9",
        ),
        (
            "지번+한글단지",
            "서울특별시 서대문구 남가좌동 384 디엠씨래미안클라시스 제101동 제10층 제1001호",
            "84.9",
        ),
        (
            "지번+영문단지",
            "서울특별시 서대문구 남가좌동 384 DMC래미안클라시스 제101동 제10층 제1001호",
            "84.9",
        ),
    ]
    for label, test_address, area in tests:
        print(f"\n  [{label}] {test_address}")
        result = get_kb_price_from_registry(test_address, area)
        if result:
            print(
                f"  OK complex={result.get('complex_name')} "
                f"kb_price={result.get('kb_price')} "
                f"exclusive_area={result.get('exclusive_area') or result.get('area')}"
            )
        else:
            print("  FAIL: None")


if __name__ == "__main__":
    main()
