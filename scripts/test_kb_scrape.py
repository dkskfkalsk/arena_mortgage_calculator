# -*- coding: utf-8 -*-
"""
kbland.kr/c/{id} 페이지에서 사용승인일·재건축 정보 스크래핑 테스트
complex_id=4024 (진흥아파트)
"""
import os
import re
import sys

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Vercel 환경 체크 해제 (로컬 테스트용)
os.environ.pop("VERCEL", None)
os.environ.pop("VERCEL_ENV", None)


def parse_approval_date(text: str):
    """사용승인일 추출 - 기존 및 확장 패턴"""
    approval_date, years_since = None, None
    # 기존: 사용승인일 YYYY.MM.DD(N년차) 또는 사용승인일 YYYY.MM.DD
    m = re.search(r"사용\s*승인\s*일\s*(\d{4}\.\d{2}\.\d{2})\s*(?:\(\s*(\d+)\s*년\s*차\s*\))?", text)
    if m:
        approval_date = m.group(1)
        if m.lastindex >= 2 and m.group(2):
            try:
                years_since = int(m.group(2))
            except ValueError:
                pass
    return approval_date, years_since


def parse_redevelop_stages(text: str):
    """재건축 단계 추출 - 기존 및 확장 패턴 (4단계추진위원회승인'2025.08.18 형식)"""
    stages = []
    # 확장 패턴: N단계 + 단계명 (공백 없을 수 있음) + ' 또는 공백 + YYYY.MM.DD
    patterns = [
        # 4단계추진위원회승인'2025.08.18
        r"(\d+)단계\s*([가-힣]+)['\s]*(\d{4}\.\d{2}\.\d{2})",
        # 5단계 조합설립인가 2017.06.01 (기존)
        r"(\d+)단계\s+([가-힣]+)\s+(\d{4}\.\d{2}\.\d{2})",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            stages.append({
                "step": int(m.group(1)),
                "name": m.group(2),
                "date": m.group(3),
            })
    # 중복 제거 (step 기준)
    seen = set()
    unique = []
    for s in stages:
        if s["step"] not in seen:
            seen.add(s["step"])
            unique.append(s)
    return unique


def main():
    complex_id = "4024"  # 진흥아파트
    print(f"=== KB 스크래핑 테스트 (complex_id={complex_id}) ===\n")

    try:
        from KB_api.kb_complex_scraper import get_complex_extra_info
        result = get_complex_extra_info(complex_id)
    except Exception as e:
        print(f"get_complex_extra_info 오류: {e}")
        print("\n--- Playwright 없이 텍스트 샘플로 파싱 테스트 ---")
        # 샘플 텍스트로 파싱 함수 테스트
        sample = """
        사용승인일 1987.08.03(40년차)
        기본정보
        아파트 432세대 12개동
        4단계추진위원회승인'2025.08.18
        """
        a, y = parse_approval_date(sample)
        print(f"사용승인일: {a}, 년차: {y}")
        stages = parse_redevelop_stages(sample)
        print(f"재건축 단계: {stages}")
        return

    print("get_complex_extra_info 결과:")
    print(f"  approval_date: {result.get('approval_date')}")
    print(f"  years_since_completion: {result.get('years_since_completion')}")
    print(f"  redevelop_yn: {result.get('redevelop_yn')}")
    print(f"  redevelop_stages: {result.get('redevelop_stages')}")
    print(f"  households: {result.get('households')}")
    print(f"  buildings: {result.get('buildings')}")
    print(f"  error: {result.get('error')}")

    # body 텍스트가 있다면 파싱 테스트 (스크래퍼 내부에서 body_text 저장 안 하므로 여기서는 불가)
    print("\n--- 완료 ---")


if __name__ == "__main__":
    main()
