# -*- coding: utf-8 -*-
"""
_next/data JSON 방식으로 사용승인일·재건축·세대수 추출 (Next.js 사이트용)

※ kbland.kr은 Vue.js SPA로 _next/data가 없어 본 모듈 적용 불가.
   kbland에서는 Playwright/Chromium 스크래핑 필요.
"""
import os
import re
import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:
    requests = None

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://kbland.kr/",
    "Origin": "https://kbland.kr",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
}


def _fetch_html(url: str) -> Optional[str]:
    if not requests:
        return None
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.warning("kb_next_data HTML fetch 실패 %s: %s", url, e)
        return None


def _extract_build_id(html: str) -> Optional[str]:
    """HTML에서 Next.js buildId 추출"""
    if not html:
        return None
    # __NEXT_DATA__ 스크립트
    m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>([^<]+)</script>', html, re.I)
    if m:
        try:
            data = json.loads(m.group(1))
            bid = data.get("buildId")
            if bid and isinstance(bid, str):
                return bid
        except json.JSONDecodeError:
            pass
    # 대체 패턴
    m = re.search(r'"buildId"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'/_next/static/([a-zA-Z0-9_-]+)/', html)
    if m:
        return m.group(1)
    return None


def _fetch_next_data_json(build_id: str, complex_id: str) -> Optional[dict]:
    if not requests:
        return None
    url = f"https://kbland.kr/_next/data/{build_id}/c/{complex_id}.json"
    try:
        r = requests.get(
            url,
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15,
        )
        if r.ok:
            return r.json()
    except Exception as e:
        logger.warning("kb_next_data JSON fetch 실패: %s", e)
    return None


def _extract_from_json(data: dict) -> Dict[str, Any]:
    """JSON/객체에서 사용승인일, 재건축, 세대수 추출"""
    result = {
        "approval_date": None,
        "years_since_completion": None,
        "redevelop_stages": [],
        "households": None,
        "buildings": None,
        "redevelop_yn": False,
    }
    if not data:
        return result

    json_str = json.dumps(data, ensure_ascii=False)

    # 사용승인일: 사용승인일 1987.08.03(40년차)
    m = re.search(
        r"사용\s*승인\s*일\s*(\d{4}[.-]\d{2}[.-]\d{2})\s*(?:\(\s*(\d+)\s*년\s*차\s*\))?",
        json_str,
    )
    if m:
        result["approval_date"] = m.group(1).replace("-", ".")
        if m.group(2):
            result["years_since_completion"] = int(m.group(2))

    # 재건축 단계: 4단계추진위원회승인'2025.08.18
    seen_steps = set()
    for m in re.finditer(
        r"(\d+)단계\s*([가-힣]+)['\s]*(\d{4}\.\d{2}\.\d{2})",
        json_str,
    ):
        step = int(m.group(1))
        if step not in seen_steps:
            seen_steps.add(step)
            result["redevelop_stages"].append({
                "step": step,
                "name": m.group(2),
                "date": m.group(3),
            })
    result["redevelop_stages"].sort(key=lambda x: x["step"])
    result["redevelop_yn"] = len(result["redevelop_stages"]) > 0

    # 세대수: 재귀 검색
    def find_num(obj, keys: List[str], max_val: int = 200000):
        if obj is None:
            return None
        if isinstance(obj, dict):
            for k in keys:
                v = obj.get(k)
                if v is not None and str(v).strip():
                    try:
                        n = int(float(str(v).replace(",", "")))
                        if 1 <= n <= max_val:
                            return n
                    except (ValueError, TypeError):
                        pass
            for v in obj.values():
                r = find_num(v, keys, max_val)
                if r is not None:
                    return r
        elif isinstance(obj, list):
            for item in obj:
                r = find_num(item, keys, max_val)
                if r is not None:
                    return r
        return None

    result["households"] = find_num(
        data, ["세대수", "총세대수", "총호수", "호수", "households"], 200000
    )
    result["buildings"] = find_num(
        data, ["동수", "총동수", "개동", "buildings"], 10000
    )

    return result


def get_complex_info_via_next_data(complex_id: str) -> Dict[str, Any]:
    """
    _next/data JSON으로 단지 정보 조회 (Chromium 없이)
    Vercel 서버리스에서 사용 가능.
    """
    empty = {
        "approval_date": None,
        "years_since_completion": None,
        "redevelop_stages": [],
        "households": None,
        "buildings": None,
        "redevelop_yn": False,
        "error": None,
    }
    if not complex_id or not str(complex_id).strip():
        empty["error"] = "complex_id 필요"
        return empty

    cid = str(complex_id).strip()

    # 1) /c/ 페이지 먼저 (단지 상세 - 사용승인일 등 있을 가능성)
    html = _fetch_html(f"https://kbland.kr/c/{cid}")
    build_id = _extract_build_id(html) if html else None

    if not build_id and html and len(html) < 5000:
        # /c/ 페이지가 짧으면(리다이렉트 등) 메인 페이지 시도
        html_main = _fetch_html("https://kbland.kr/")
        if html_main and len(html_main) > len(html or ""):
            html = html_main
        build_id = _extract_build_id(html) if html else None

    if not build_id:
        # __NEXT_DATA__가 HTML에 있으면 그대로 파싱 (SSR 페이지)
        if html:
            m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>([^<]+)</script>', html, re.I)
            if m:
                try:
                    next_data = json.loads(m.group(1))
                    extracted = _extract_from_json(next_data)
                    extracted["error"] = None
                    logger.info("kb_next_data: __NEXT_DATA__ 직접 파싱 성공")
                    return extracted
                except json.JSONDecodeError:
                    pass
            # HTML 본문에서 직접 사용승인일·세대수 패턴 검색 (JS 미렌더링 시)
            extracted = _extract_from_json({"raw": html})
            if extracted.get("approval_date") or extracted.get("households"):
                extracted["error"] = None
                logger.info("kb_next_data: HTML 본문에서 직접 파싱 성공")
                return extracted
        # 디버그: HTML 샘플 저장 (KB_NEXT_DATA_DEBUG=1 시)
        if os.environ.get("KB_NEXT_DATA_DEBUG") and html:
            try:
                with open("kb_next_data_debug.html", "w", encoding="utf-8") as f:
                    f.write(html[:15000])
                logger.info("kb_next_data: debug HTML 저장됨 (kb_next_data_debug.html)")
            except Exception:
                pass
        empty["error"] = "buildId 추출 실패"
        return empty

    # 2) _next/data JSON fetch
    next_data = _fetch_next_data_json(build_id, cid)
    if not next_data:
        empty["error"] = "_next/data fetch 실패"
        return empty

    extracted = _extract_from_json(next_data)
    extracted["error"] = None
    logger.info(
        "kb_next_data 성공: approval_date=%s, households=%s",
        extracted["approval_date"],
        extracted["households"],
    )
    return extracted
