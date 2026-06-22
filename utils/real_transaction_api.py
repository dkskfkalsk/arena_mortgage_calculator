# -*- coding: utf-8 -*-
"""
공공데이터포털 국토교통부 아파트 매매 실거래가 API
- KB 시세 없을 때 실거래가를 대체 정보로 표시
- 환경변수 REAL_ESTATE_API_KEY 필요
"""

import os
import re
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode
import requests
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# 공공데이터포털 아파트 매매 실거래가 API (개발계정)
API_BASE = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev"
API_PATH = "/getRTMSDataSvcAptTradeDev"


def _get_service_key() -> Optional[str]:
    """환경변수에서 인증키 로드"""
    key = os.environ.get("REAL_ESTATE_API_KEY") or os.environ.get("REAL_ESTATE_API_KEY_ENC")
    return key.strip() if key and str(key).strip() else None


def _extract_complex_name_from_address(address: str) -> Optional[str]:
    """주소에서 단지명 추출 (KB API와 동일한 패턴)"""
    if not address or not address.strip():
        return None
    addr = address.strip()
    complex_patterns = [
        r'\d+(?:-\d+)?\s+([가-힣]+?)(?=\s+제\d+동|\s+제\d+층|\s+제\d+호|$)',
        r'([가-힣]+)오피스텔',
        r'([가-힣]+)아파트',
        r'([가-힣]+)빌라',
        r'([가-힣]+마을)',
        r'([가-힣]+단지)',
        r'([가-힣]+(?:아이파크|래미안|자이|힐스테이트|푸르지오|센트럴|팰리스|월드|우방|아이유쉘))',
    ]
    for pattern in complex_patterns:
        match = re.search(pattern, addr)
        if match:
            name = match.group(1).strip()
            if len(name) >= 2 and name not in ('동', '구', '시', '군', '읍', '면', '필지'):
                return name
    return None


def _match_complex(item_apt: str, item_road: str, search_name: str) -> bool:
    """실거래가 항목의 아파트명/도로명이 검색 단지명과 매칭되는지"""
    if not search_name or len(search_name) < 2:
        return True  # 단지명 없으면 모두 매칭
    search_clean = search_name.replace(" ", "").replace("(", "").replace(")", "")
    for field in (item_apt or "", item_road or ""):
        if not field:
            continue
        field_clean = field.replace(" ", "").replace("(", "").replace(")", "")
        if search_clean in field_clean or field_clean in search_clean:
            return True
        # 부분 매칭 (거제코아루 vs 거제코아루파크드림)
        if len(search_clean) >= 3 and search_clean[:3] in field_clean:
            return True
    return False


def _format_price_manwon(price_str: str) -> str:
    """거래금액(만원)을 '1억5,000만' 형식으로 포맷"""
    try:
        price = int(str(price_str).replace(",", "").strip())
        if price >= 10000:
            eok = price // 10000
            man = price % 10000
            if man == 0:
                return f"{eok}억"
            return f"{eok}억{man:,}만"
        return f"{price:,}만"
    except (ValueError, TypeError):
        return str(price_str)


def get_real_transactions(
    address: str,
    dongcode_10: str,
    complex_name_hint: Optional[str] = None,
    area_hint: Optional[float] = None,
    max_items: int = 5,
) -> List[Dict[str, Any]]:
    """
    공공데이터포털 실거래가 API로 최근 매매 실거래가 조회

    Args:
        address: 등기부 주소
        dongcode_10: 10자리 법정동코드 (앞 5자리 사용)
        complex_name_hint: 단지명 (없으면 주소에서 추출 시도)
        area_hint: 면적(m²) - 유사 면적 필터링용 (선택)
        max_items: 반환할 최대 건수

    Returns:
        [{"price_display": "1억5,000만", "date": "26.2.25", "floor": "7", "area": 84.88}, ...]
    """
    service_key = _get_service_key()
    if not service_key:
        logger.warning("REAL_ESTATE_API_KEY 환경변수 미설정. 실거래가 조회 생략.")
        return []

    lawd_cd = dongcode_10[:5] if dongcode_10 and len(dongcode_10) >= 5 else None
    if not lawd_cd:
        logger.warning("법정동코드 5자리 추출 실패")
        return []

    complex_name = complex_name_hint or _extract_complex_name_from_address(address)
    now = datetime.now()
    results = []

    # 최근 3개월 조회 (실거래가는 2개월 후 공개되므로)
    for month_offset in range(3, 0, -1):
        target = now
        for _ in range(month_offset):
            if target.month == 1:
                target = target.replace(year=target.year - 1, month=12)
            else:
                target = target.replace(month=target.month - 1)
        deal_ymd = target.strftime("%Y%m")

        params = {
            "serviceKey": service_key,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": deal_ymd,
            "pageNo": 1,
            "numOfRows": 100,
        }

        try:
            url = f"{API_BASE}{API_PATH}"
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("실거래가 API 호출 실패: %s", e)
            continue

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            logger.warning("실거래가 XML 파싱 실패: %s", e)
            continue

        # 에러 체크 (header/resultCode)
        header = root.find("header") or root.find(".//header")
        if header is not None:
            result_code = header.findtext("resultCode")
            if result_code and str(result_code).strip() not in ("00", "0"):
                logger.debug("실거래가 API 에러: %s", header.findtext("resultMsg") or result_code)
                continue

        # 응답 구조: response > body > items > item (공공데이터포털)
        body = root.find("body") or root.find(".//body")
        if body is None:
            body = root
        items = body.find("items") or body.find(".//items")
        if items is None:
            # 결과 없음 (해당 월에 거래 없음)
            continue

        item_list = items.findall("item")

        for item in item_list:
            apt_name = (
                item.findtext("아파트명")
                or item.findtext("aptNm")
                or item.findtext("아파트")
                or ""
            ).strip()
            road_name = (item.findtext("도로명") or item.findtext("roadName") or "").strip()

            if not _match_complex(apt_name, road_name, complex_name):
                continue

            price_str = item.findtext("거래금액") or item.findtext("dealAmount") or "0"
            year = item.findtext("년") or item.findtext("dealYear") or ""
            month = item.findtext("월") or item.findtext("dealMonth") or ""
            day = item.findtext("일") or item.findtext("dealDay") or ""
            floor = item.findtext("층") or item.findtext("floor") or ""
            area_str = item.findtext("전용면적") or item.findtext("area") or ""

            try:
                area_val = float(str(area_str).strip()) if area_str else None
            except (ValueError, TypeError):
                area_val = None

            # 면적 필터 (유사 ±10㎡)
            if area_hint and area_val is not None:
                if abs(area_val - area_hint) > 15:
                    continue

            # 날짜 포맷: 26.2.25
            try:
                y = int(year) % 100 if year else 0
                m = int(month) if month else 0
                d = int(day) if day else 0
                date_display = f"{y:02d}.{m}.{d}" if y and m and d else ""
            except (ValueError, TypeError):
                date_display = ""

            price_display = _format_price_manwon(price_str)

            results.append({
                "price_display": price_display,
                "price_manwon": int(str(price_str).replace(",", "")) if price_str else 0,
                "date": date_display,
                "floor": str(floor).strip() if floor else "",
                "area": area_val,
                "apt_name": apt_name or road_name,
            })

            if len(results) >= max_items:
                break

        if len(results) >= max_items:
            break

    return results[:max_items]


def format_real_transactions_display(transactions: List[Dict[str, Any]]) -> str:
    """
    실거래가 목록을 "1억5,000만 26.2.25 7층" 형식 문자열로 변환
    """
    if not transactions:
        return ""
    parts = []
    for t in transactions:
        p = t.get("price_display", "")
        d = t.get("date", "")
        f = t.get("floor", "")
        line = p
        if d:
            line += f" {d}"
        if f:
            line += f" {f}층"
        parts.append(line.strip())
    return "\n".join(parts)
