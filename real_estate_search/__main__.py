# -*- coding: utf-8 -*-
"""등기부 PDF 한 건으로 실거래가 줄 확인: python -m real_estate_search "temp/파일.pdf" """

import logging
import sys

from parsers.registry_parser import analyze_pdf
from KB_api.kb_price_api import get_kb_price_from_registry

from .molit_trade import lookup_registry_trade_line


def main() -> int:
    if len(sys.argv) < 2:
        print('사용법: python -m real_estate_search "등기부.pdf"')
        return 2
    logging.disable(logging.CRITICAL)
    result = analyze_pdf(sys.argv[1])
    kb = get_kb_price_from_registry(result.부동산_주소, result.면적, registry_text=result.원본텍스트) or {}
    print(f"주   소 : {result.부동산_주소}")
    print(f"면   적 : {result.면적}")
    print(f"단지명 : {kb.get('complex_name') or ''}")
    if kb.get("kb_price"):
        print(f"KB시세 : 일반 {int(kb['kb_price']):,}만원")
    line = lookup_registry_trade_line(
        result.부동산_주소,
        result.면적,
        complex_name=kb.get("complex_name"),
        property_type=kb.get("complex_type") or result.부동산구분,
    )
    print(line or "실거래가 : 조회 생략 (단지명 또는 법정동코드 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
