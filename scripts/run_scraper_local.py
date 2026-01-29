# -*- coding: utf-8 -*-
"""
로컬에서 KB /c/ 스크래핑 실행 (세대수·동수 추출)

사용법:
  python scripts/run_scraper_local.py [complex_id]
  python scripts/run_scraper_local.py --pdf "pdf_Parsing_example/권현주 250819.pdf"

- complex_id만 주면 해당 단지 /c/ 페이지 스크래핑만 수행
- --pdf 주면 PDF 파싱 → KB 시세 조회(스크래퍼 포함) → 결과 출력

필요: pip install playwright && playwright install chromium
"""
import sys
import os

# Vercel 환경 변수 제거 후 import (로컬에서 스크래퍼 활성화)
for key in ("VERCEL", "VERCEL_ENV"):
    os.environ.pop(key, None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    if "--pdf" in sys.argv:
        idx = sys.argv.index("--pdf")
        pdf_path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 인자 없거나 경로 없으면 기본 PDF (권현주 250819.pdf) 사용
        if not pdf_path:
            pdf_path = os.path.join(root, "pdf_Parsing_example", "권현주 250819.pdf")
        elif not os.path.isabs(pdf_path):
            pdf_path = os.path.join(root, pdf_path)
        if not os.path.exists(pdf_path):
            # 한글 경로 깨짐 시 기본 PDF 재시도
            default_pdf = os.path.join(root, "pdf_Parsing_example", "권현주 250819.pdf")
            if os.path.exists(default_pdf):
                pdf_path = default_pdf
                print("[기본 PDF 사용]", pdf_path)
            else:
                print("PDF not found:", pdf_path)
                sys.exit(1)
        run_with_pdf(pdf_path)
    else:
        complex_id = sys.argv[1] if len(sys.argv) > 1 else "15385"
        run_scraper_only(complex_id)


def run_scraper_only(complex_id: str):
    """단지 ID로 /c/ 페이지 스크래핑만 실행"""
    from KB_api.kb_complex_scraper import get_complex_extra_info

    print(f"[로컬] 스크래핑 시작: https://kbland.kr/c/{complex_id}")
    result = get_complex_extra_info(complex_id)

    print("\n=== 스크래핑 결과 ===")
    print("URL:", result.get("source_url"))
    print("단지명:", result.get("complex_name"))
    print("세대수:", result.get("households"))
    print("동수:", result.get("buildings"))
    print("재건축 여부:", result.get("redevelop_yn"))
    if result.get("redevelop_stages"):
        print("재건축 단계:", result["redevelop_stages"])
    if result.get("error"):
        print("오류:", result["error"])


def run_with_pdf(pdf_path: str):
    """PDF 파싱 → KB 시세 조회(스크래퍼 포함) → 결과 출력"""
    from parsers.registry_parser import analyze_pdf
    from KB_api.kb_price_api import get_kb_price_from_registry

    print(f"[로컬] PDF 파싱: {pdf_path}")
    doc = analyze_pdf(pdf_path)
    addr = doc.부동산_주소 or ""
    area_str = doc.면적 or ""
    if not addr or not area_str:
        print("주소 또는 면적 없음")
        return

    print(f"주소: {addr}")
    print(f"면적: {area_str}")
    print("\n[로컬] KB 시세 조회 (스크래퍼 포함)...")
    result = get_kb_price_from_registry(addr, area_str)

    if not result:
        print("KB 시세 조회 실패")
        return

    print("\n=== KB 시세 + 스크래핑 결과 ===")
    print("단지명:", result.get("complex_name"))
    print("KB 시세(일반):", result.get("kb_price"), "만원")
    print("KB 시세(하한):", result.get("kb_price_min"), "만원")
    print("세대수:", result.get("households"))
    print("동수:", result.get("buildings"))
    print("재건축 여부:", result.get("redevelop_yn"))
    if result.get("households") or result.get("buildings"):
        print("(세대수/동수는 /c/ 페이지 스크래핑으로 채워짐)")


if __name__ == "__main__":
    main()
