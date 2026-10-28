# -*- coding: utf-8 -*-
"""
등기부 면적과 정확히 같은 면적의 최근 매매 실거래가 1건 조회.

국토교통부 실거래가 신고 데이터를 k-skill-proxy(`/v1/real-estate/...`)로 받는다.
API 키가 필요 없다. 자세한 설명은 같은 폴더의 README_real_estate_search.md 참고.
"""

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterator, List, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_PROXY_BASE_URL = "https://k-skill-proxy.nomadamas.org"
MAX_MONTHS = 60
MONTHS_PER_BATCH = 12
REQUEST_TIMEOUT_SEC = 10

ASSET_BY_PROPERTY_TYPE = {
    "아파트": "apartment",
    "주상복합": "apartment",
    "오피스텔": "officetel",
    "연립/다세대": "villa",
    "연립": "villa",
    "다세대": "villa",
}


class RealEstateLookupError(RuntimeError):
    """프록시 호출 실패 또는 응답 형식 오류"""


def _proxy_base_url() -> str:
    return (os.environ.get("REAL_ESTATE_PROXY_BASE_URL") or DEFAULT_PROXY_BASE_URL).rstrip("/")


def parse_exclusive_area(area: Any) -> Optional[Decimal]:
    """등기부 면적 문자열 → Decimal. "51㎡/37.85㎡"처럼 공급/전용이면 전용(두 번째) 사용."""
    numbers = re.findall(r"\d+(?:\.\d+)?", str(area or ""))
    if not numbers:
        return None
    try:
        return Decimal(numbers[1] if "/" in str(area) and len(numbers) >= 2 else numbers[0])
    except InvalidOperation:
        return None


def _normalize_name(name: str) -> str:
    return re.sub(r"[\s()（）]|아파트$", "", name or "")


def _same_complex(item_name: str, complex_name: str) -> bool:
    a, b = _normalize_name(item_name), _normalize_name(complex_name)
    return bool(a and b) and (a == b or a in b or b in a)


def _same_area(item_area: Any, registry_area: Decimal) -> bool:
    try:
        return Decimal(str(item_area)) == registry_area
    except InvalidOperation:
        return False


def _months_back(n: int, now: Optional[datetime] = None) -> Iterator[str]:
    now = now or datetime.now()
    y, m = now.year, now.month
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        yield f"{y}{m:02d}"


def _fetch_month(lawd_cd: str, asset: str, deal_ymd: str) -> List[Dict[str, Any]]:
    try:
        resp = requests.get(
            f"{_proxy_base_url()}/v1/real-estate/{asset}/trade",
            params={"lawd_cd": lawd_cd, "deal_ymd": deal_ymd, "num_of_rows": 1000},
            timeout=REQUEST_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        return resp.json().get("items") or []
    except (requests.RequestException, ValueError) as e:
        raise RealEstateLookupError(f"{asset}/trade {lawd_cd} {deal_ymd}: {e}") from e


def find_same_area_trade(
    lawd_cd: str,
    complex_name: str,
    registry_area: Decimal,
    asset: str = "apartment",
    max_months: int = MAX_MONTHS,
) -> Optional[Dict[str, Any]]:
    """같은 단지·같은 면적의 가장 최근 매매 1건. max_months 안에 없으면 None.

    최근 1년치씩 병렬 조회하고, 동일 면적이 나오면 더 과거는 조회하지 않는다.
    """
    months = list(_months_back(max_months))
    with ThreadPoolExecutor(max_workers=MONTHS_PER_BATCH) as pool:
        for start in range(0, len(months), MONTHS_PER_BATCH):
            batch = months[start:start + MONTHS_PER_BATCH]
            matches = [
                item
                for items in pool.map(lambda ymd: _fetch_month(lawd_cd, asset, ymd), batch)
                for item in items
                if _same_complex(item.get("name", ""), complex_name)
                and _same_area(item.get("area_m2"), registry_area)
            ]
            if matches:
                return max(matches, key=lambda item: item.get("deal_date", ""))
    return None


def _format_price_10k(price_10k: int) -> str:
    eok, man = divmod(int(price_10k), 10000)
    if not eok:
        return f"{man:,}만"
    return f"{eok}억" + (f"{man:,}만" if man else "")


def format_trade_line(trade: Optional[Dict[str, Any]], max_months: int = MAX_MONTHS) -> str:
    """텔레그램 응답용 한 줄. 예: "실거래가 : 27억8,000만 26.05.04 24층 49.593㎡" """
    if not trade:
        return f"실거래가 : 동일면적 거래 없음 (최근 {max_months // 12}년)"
    deal_date = str(trade.get("deal_date", ""))[2:].replace("-", ".")
    return (
        f"실거래가 : {_format_price_10k(trade['price_10k'])} {deal_date} "
        f"{trade.get('floor', '')}층 {trade.get('area_m2')}㎡"
    )


def lookup_registry_trade_line(
    address: str,
    area: Any,
    complex_name: Optional[str] = None,
    property_type: Optional[str] = None,
) -> Optional[str]:
    """등기부 주소·면적으로 실거래가 한 줄을 만든다. 단지명이나 법정동코드를 못 찾으면 None."""
    registry_area = parse_exclusive_area(area)
    if not address or registry_area is None:
        return None

    from KB_api.kb_price_api import KBPriceAPI
    from utils.real_transaction_api import _extract_complex_name_from_address

    complex_name = complex_name or _extract_complex_name_from_address(address)
    dongcode = KBPriceAPI().find_dongcode(address)
    if not complex_name or not dongcode:
        logger.info("실거래가 조회 생략 (단지명=%s, 법정동코드=%s)", complex_name, dongcode)
        return None

    asset = ASSET_BY_PROPERTY_TYPE.get((property_type or "").strip(), "apartment")
    try:
        trade = find_same_area_trade(dongcode[:5], complex_name, registry_area, asset=asset)
    except RealEstateLookupError as e:
        logger.warning("실거래가 조회 실패: %s", e)
        return "실거래가 : 조회 실패"
    return format_trade_line(trade)
