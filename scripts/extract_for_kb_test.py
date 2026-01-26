# -*- coding: utf-8 -*-
"""등기부 PDF에서 주소/면적 추출 후 KB API URL 생성. 사용: python extract_for_kb_test.py [PDF파일명]"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.registry_parser import analyze_pdf
from KB_api.kb_price_api import KBPriceAPI

# PDF: 인자로 별칭 또는 파일명. 한글 인자는 터미널 인코딩 이슈로 별칭 사용 권장.
PDF_ALIASES = {"1": "문영순 260108.pdf", "2": "김용운등기.pdf", "kim": "김용운등기.pdf"}
arg = sys.argv[1] if len(sys.argv) > 1 else "1"
pdf_name = PDF_ALIASES.get(arg, arg)
root = os.path.dirname(os.path.dirname(__file__))
pdf_path = os.path.join(root, "pdf_Parsing_example", pdf_name)
doc = analyze_pdf(pdf_path)

address = doc.부동산_주소 or ""
area = doc.면적 or ""

api = KBPriceAPI()
dongcode = api.find_dongcode(address) if address else None

# fastPriceInfo URL
url = ""
if dongcode:
    url = f"https://api.kbland.kr/land-price/price/fastPriceInfo?법정동코드={dongcode}&유형=1&거래유형=0"

# 출력 파일명: "김용운등기.pdf" -> "김용운등기_KB시세_API_테스트.txt"
base = os.path.splitext(pdf_name)[0]

# 결과를 tests 폴더에 쓸 내용
lines = [
    "=" * 70,
    f"  KB 시세 API 테스트 - {pdf_name}",
    "=" * 70,
    "",
    "[ 1 ] 등기부 추출",
    "-" * 50,
    f"  주소   : {address}",
    f"  면적   : {area}",
    "",
    "[ 2 ] 법정동코드",
    "-" * 50,
    f"  {dongcode or '(찾지 못함)'}",
    "",
    "[ 3 ] fastPriceInfo API URL (복붙용)",
    "-" * 50,
    "  아래 줄 전체를 복사해 브라우저 주소창에 붙여넣으세요.",
    "",
    url if url else "(법정동코드를 찾지 못해 URL 생성 불가)",
    "",
    "[ 4 ] 응답에서 확인할 것",
    "-" * 50,
    "  ① dataBody.data 가 배열이고, 길이 ≥ 1 인지",
    "  ② dataBody.data[0] 에 '매매' 키가 있고, 값이 배열인지",
    "  ③ 매매[0] 에 공급면적, 일반평균, 하위평균(또는 유사 키) 있는지",
    "  ④ 시세가 '매매' 말고 다른 키에 있으면, 그 키 이름 메모",
    "",
    "[ 5 ] 예시 URL (대구 달서구 본리동, 응답 구조 확인용)",
    "-" * 50,
    "https://api.kbland.kr/land-price/price/fastPriceInfo?법정동코드=2729011400&유형=1&거래유형=0",
    "",
    "=" * 70,
]
print("\n".join(lines))

# tests 폴더에 저장
out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, f"{base}_KB시세_API_테스트.txt")
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\n저장: {out_path}")
