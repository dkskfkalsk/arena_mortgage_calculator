# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calculator.base_calculator import BaseCalculator
from utils.formatter import format_result

cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "banks", "2_hantocapital.json")
calc = BaseCalculator(cfg)


def base(**kw):
    data = {
        "kb_price": 53000,
        "kb_price_raw": "일반 53,000만원",
        "region": "서울특별시강남구",
        "address": "서울특별시 강남구 역삼동 10층",
        "property_type": "아파트",
        "area": 84,
        "household_count": 600,
        "credit_score": 950,
        "occupation": "개인사업자",
        "mortgages": [
            {"priority": 1, "institution": "국민은행", "amount": 8000, "max_amount": 10000, "is_refinance": False}
        ],
    }
    data.update(kw)
    return data


def ltvs(result):
    return [(r.get("ltv"), r.get("interest_rate"), r.get("promotion_name")) for r in result.get("results") or []]


def run(name, data, checks):
    result = calc.calculate(data, product_type="business")
    text = format_result(result) if result else ""
    ok = True
    notes = []
    for label, fn in checks:
        passed = fn(result, text)
        if not passed:
            ok = False
            notes.append(label)
    print(("OK " if ok else "FAIL ") + name + ((" | " + ", ".join(notes)) if notes else ""))
    if not ok:
        print("  ltvs", ltvs(result) if result else None)
        print("  errors", (result or {}).get("errors"))
        print("  text", text.replace("\n", " | "))
    return ok


cases = []

cases.append(run(
    "강남 93 추가",
    base(),
    [
        ("93", lambda r, t: any(x[0] == 93 and x[1] == 9.62 and x[2] == "한도프로모션" for x in ltvs(r))),
        ("90 plain", lambda r, t: any(x[0] == 90 and x[1] == 9.12 and not x[2] for x in ltvs(r))),
        ("label", lambda r, t: "한도프로모션" in t),
        ("no 5억", lambda r, t: "5억초과" not in t),
    ],
))

cases.append(run(
    "93이 5억 초과면 그 줄만 제외",
    base(kb_price=70000, kb_price_raw="일반 70,000만원"),
    [
        ("no 93", lambda r, t: all(x[0] != 93 for x in ltvs(r))),
        ("90 stays", lambda r, t: any(x[0] == 90 and not x[2] for x in ltvs(r))),
        ("msg", lambda r, t: "5억초과" in t),
    ],
))

cases.append(run(
    "강북은 프로모션 없음",
    base(region="서울특별시강북구", address="서울특별시 강북구 미아동 10층"),
    [("no 93", lambda r, t: r and all(x[0] != 93 for x in ltvs(r)) and "한도프로모션" not in t)],
))

cases.append(run(
    "4등급 120㎡는 90 추가",
    base(credit_score=800, area=120, kb_price=40000, kb_price_raw="일반 40,000만원"),
    [
        ("90 promo", lambda r, t: any(x[0] == 90 and x[1] == 10.12 and x[2] == "한도프로모션" for x in ltvs(r))),
        ("87 plain", lambda r, t: any(x[0] == 87 and not x[2] for x in ltvs(r))),
        ("no 93", lambda r, t: all(x[0] != 93 for x in ltvs(r))),
    ],
))

cases.append(run(
    "135초과 없음",
    base(area=140),
    [("no promo", lambda r, t: r and "한도프로모션" not in t)],
))

cases.append(run(
    "499세대 없음",
    base(household_count=499),
    [("no promo", lambda r, t: r and "한도프로모션" not in t and any(x[0] == 90 for x in ltvs(r)))],
))

cases.append(run(
    "선순위 없음",
    base(mortgages=[]),
    [("primary", lambda r, t: r and any(x[0] == 90 and not x[2] for x in ltvs(r)) and "한도프로모션" not in t)],
))

cases.append(run(
    "6등급 없음",
    base(credit_score=720),
    [("no promo", lambda r, t: r and "한도프로모션" not in t)],
))

cases.append(run(
    "수지 있음 기흥 없음",
    base(region="경기도용인시수지구", address="경기도 용인시 수지구 10층"),
    [("promo", lambda r, t: "한도프로모션" in t)],
))
cases.append(run(
    "기흥 없음",
    base(region="경기도용인시기흥구", address="경기도 용인시 기흥구 10층"),
    [("no", lambda r, t: r and "한도프로모션" not in t)],
))

cases.append(run(
    "1층 하한가 없음",
    base(address="서울특별시 강남구 역삼동 1층", kb_price_raw="일반 53,000만원 하한 50,000만원"),
    [("no", lambda r, t: r and "한도프로모션" not in t and any(x[0] == 90 for x in ltvs(r)))],
))

cases.append(run(
    "한국부동산원 없음",
    base(kb_price=None, kb_price_raw=None, special_notes="한국부동산원 시세: 53,000만원"),
    [("no promo", lambda r, t: r and any(x[0] == 90 for x in ltvs(r)) and "한도프로모션" not in t)],
))

cases.append(run(
    "만75세 없음",
    base(age=75),
    [("no", lambda r, t: r and "한도프로모션" not in t)],
))
cases.append(run(
    "1952년생 있음",
    base(birth_year=1952),
    [("yes", lambda r, t: "한도프로모션" in t)],
))
cases.append(run(
    "1951년생 없음",
    base(birth_year=1951),
    [("no", lambda r, t: r and "한도프로모션" not in t)],
))

cases.append(run(
    "대지권미등기 없음",
    base(property_type="아파트(대지권 미등기)"),
    [("no", lambda r, t: r and "한도프로모션" not in t and any(x[0] == 90 for x in ltvs(r)))],
))

cases.append(run(
    "주상복합 5층 없음 11층 있음",
    base(property_type="주상복합", address="서울특별시 강남구 역삼동 5층", kb_price_raw="일반 53,000만원 하한 50,000만원"),
    [("no", lambda r, t: r and "한도프로모션" not in t)],
))
cases.append(run(
    "주상복합 11층 있음",
    base(property_type="주상복합", address="서울특별시 강남구 역삼동 11층"),
    [("yes", lambda r, t: "한도프로모션" in t)],
))

cases.append(run(
    "점수없음 4등급 93",
    base(credit_score=None),
    [
        ("93", lambda r, t: any(x[0] == 93 and x[1] == 10.62 and x[2] == "한도프로모션" for x in ltvs(r))),
        ("label", lambda r, t: "4등급기준" in t and "한도프로모션" in t),
    ],
))

cases.append(run(
    "합계 딱 5억이면 93 유지",
    base(kb_price=64520, kb_price_raw="일반 64,520만원"),
    [("93", lambda r, t: any(x[0] == 93 and x[2] == "한도프로모션" for x in ltvs(r)))],
))

print("ALL OK" if all(cases) else "SOME FAILED")
sys.exit(0 if all(cases) else 1)
