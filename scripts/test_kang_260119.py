# -*- coding: utf-8 -*-
"""강신원 260119.pdf: 등기부 파싱 + KB 시세 + 재건축 여부 검증.
사용: python scripts/test_kang_260119.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.registry_parser import RegistryParser
from KB_api.kb_price_api import get_kb_price_from_registry

PDF_NAME = "강신원 260119.pdf"
ROOT = os.path.dirname(os.path.dirname(__file__))
PDF_PATH = os.path.join(ROOT, "pdf_Parsing_example", PDF_NAME)
OUT_PATH = os.path.join(ROOT, "tests", "강신원_260119_검증결과.txt")


def _log(msg: str, lines: list) -> None:
    lines.append(msg)


def main():
    lines = []
    _log("=" * 70, lines)
    _log("  강신원 260119.pdf - 등기부 파싱 + KB 시세 + 재건축", lines)
    _log("=" * 70, lines)

    # 1) 등기부 파싱
    parser = RegistryParser()
    doc = parser.parse(PDF_PATH)
    address = doc.부동산_주소 or ""
    area = doc.면적 or ""

    _log("\n[ 1 ] 등기부 추출", lines)
    _log("-" * 50, lines)
    _log(f"  주소 : {address}", lines)
    _log(f"  면적 : {area}", lines)

    if not address or not area:
        _log("\n[오류] 주소 또는 면적 추출 실패. 등기부 텍스트 확인 필요.", lines)
        _write(lines)
        return

    # 2) KB 시세 (get_kb_price_from_registry 내부에서 단지명 추출·법정동·단지 매칭·면적 매칭·재건축 merge)
    _log("\n[ 2 ] KB 시세 조회 (get_kb_price_from_registry)", lines)
    _log("-" * 50, lines)
    kb = get_kb_price_from_registry(address, area)
    if kb:
        _log(f"  KB 매매가    : {kb.get('kb_price_raw')} (하한: {kb.get('kb_price_min_raw')})", lines)
        _log(f"  단지명       : {kb.get('complex_name')}", lines)
        _log(f"  등기부 면적  : {kb.get('area_requested', area)}㎡", lines)
        _log(f"  매칭 면적    : {kb.get('area')}㎡", lines)
        if kb.get('area_diff') is not None:
            area_diff = kb.get('area_diff')
            if area_diff > 5.0:
                _log(f"  [!] 면적 차이  : {area_diff:.2f}㎡ (큼)", lines)
            else:
                _log(f"  면적 차이      : {area_diff:.2f}㎡", lines)
        _log(f"  재건축 단지  : {kb.get('redevelop_yn')}", lines)
        _log(f"  재건축 단계  : {kb.get('redevelop_stages')}", lines)
        if kb.get("redevelop_error"):
            _log(f"  재건축 스크래퍼: {kb.get('redevelop_error')}", lines)
    else:
        _log("  (시세 조회 실패)", lines)

    _log("\n" + "=" * 70, lines)
    _write(lines)


def _write(lines: list) -> None:
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    # 터미널에는 ASCII만 (인코딩 이슈 회피)
    print("Done. Results -> tests/강신원_260119_검증결과.txt")


if __name__ == "__main__":
    main()
