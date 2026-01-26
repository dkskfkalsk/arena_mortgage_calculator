# -*- coding: utf-8 -*-
"""신용점수 X 입력 시 애큐온저축은행 산출 테스트"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.message_parser import MessageParser
from calculator.base_calculator import BaseCalculator

msg = """성   명 : 안승현 (43)
직   업 : 사업자
신용점수 : X
거주여부 : 비거주(전세동의)
소유현황 : 공유(동의가능)
주   소 : 서울특별시서초구방배동982-1방배현대멤피스2201동 2층 203호
면   적 : 162.8㎡
세대수 : 90세대 (1개동 이상)
구   분 : 아파트
KB시세 : 일반 237,500만원
            하한 227,500만원
=========설정내역=========
1순위 : 장흥군수협
           36,000 (30,000)만원
2순위 : 도봉새마을금고
           18,000 (15,000)만원
3순위 : 임차인
           140,000 (140,000)만원
81.68% / 77.89%
========================
특이사항 : 
요청사항 : *4순위 한도 확인 부탁드립니다.
"""

def main():
    parser = MessageParser()
    data = parser.parse(msg)
    print("=== 파싱 결과 (일부) ===")
    print("kb_price:", data.get("kb_price"), "| credit_score:", data.get("credit_score"), "| region:", data.get("region"), "| property_type:", data.get("property_type"))
    print("mortgages 수:", len(data.get("mortgages", [])))
    print()
    results = BaseCalculator.calculate_all_banks(data)
    names = [r.get("bank_name") for r in results]
    print("=== 산출된 금융사 ===")
    for n in names:
        print(" -", n)
    acuon = [r for r in results if "애큐온" in (r.get("bank_name") or "")]
    print()
    if acuon:
        print("[OK] 애큐온저축은행 산출됨")
        r = acuon[0]
        print("  results 수:", len(r.get("results", [])))
        for i, x in enumerate(r.get("results", [])[:3]):
            print(f"    [{i+1}] LTV={x.get('ltv')}%, amount={x.get('amount')}만원, type={x.get('type')}")
        if r.get("errors"):
            print("  errors:", r["errors"])
    else:
        print("[X] 애큐온저축은행 미산출")

if __name__ == "__main__":
    main()
