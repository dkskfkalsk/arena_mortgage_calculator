# -*- coding: utf-8 -*-
"""
김경연 251230.pdf 로컬 테스트
- PDF 파싱, KB 시세, 세대수 등이 정상 조회되는지 확인
- 실행: 프로젝트 루트에서 python scripts/test_kim_kyungyeon.py
- 결과는 scripts/test_kim_kyungyeon_result.txt 에도 저장됨
"""
import sys
import os
import logging

# 로그 레벨 낮춰서 출력 간결하게
logging.getLogger("parsers").setLevel(logging.WARNING)
logging.getLogger("KB_api").setLevel(logging.WARNING)

# 프로젝트 루트를 path에 추가 (스크립트 위치 기준)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_script_dir)
sys.path.insert(0, _root)
os.chdir(_root)

def main():
    pdf_path = os.path.join(_root, "pdf_Parsing_example", "김경연 251230.pdf")
    lines = []
    def out(s=""):
        lines.append(s)
        print(s)

    out("=" * 60)
    out("김경연 251230.pdf 로컬 테스트")
    out("=" * 60)

    # 1. PDF 파싱
    from parsers.registry_parser import analyze_pdf
    result = analyze_pdf(pdf_path)
    out("")
    out("[1] PDF 파싱 결과")
    out(f"    주소: {result.부동산_주소}")
    out(f"    면적: {result.면적}")
    out(f"    층수정보: {getattr(result, '층수정보', '-')}")

    # 2. KB 시세 조회
    from KB_api.kb_price_api import get_kb_price_from_registry
    kb_result = get_kb_price_from_registry(result.부동산_주소, result.면적)
    out("")
    out("[2] KB 시세 조회")
    if kb_result:
        out(f"    KB시세: {kb_result.get('kb_price')} 만원")
        out(f"    단지명: {kb_result.get('complex_name')}")
        out(f"    단지ID: {kb_result.get('complex_id')} (kbland.kr/c/{kb_result.get('complex_id')})")
        out(f"    세대수: {kb_result.get('households')}")
        out(f"    면적: {kb_result.get('area')} m2")
    else:
        out("    실패: KB 시세를 찾을 수 없음")
        result_path = os.path.join(_script_dir, "test_kim_kyungyeon_result.txt")
        with open(result_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return 1

    # 3. 근저당권 요약 (등기부 기준)
    if hasattr(result, "근저당권목록") and result.근저당권목록:
        out("")
        out("[3] 근저당권 (활성)")
        for m in result.근저당권목록:
            out(f"    {m.순위번호}순위: {m.근저당권자} {m.채권최고액}")

    out("")
    out("=" * 60)
    out("테스트 완료: 김경연 고객 데이터 정상 조회됨")
    out("=" * 60)

    # 결과 파일 저장
    result_path = os.path.join(_script_dir, "test_kim_kyungyeon_result.txt")
    with open(result_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return 0

if __name__ == "__main__":
    sys.exit(main())
