# -*- coding: utf-8 -*-
"""
KB 부동산 시세 API 호출 모듈
등기부에서 추출한 주소와 면적을 기반으로 KB 시세를 자동으로 조회합니다.
"""

import json
import os
import re
import time
import html
import requests
import logging
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from .kb_complex_scraper import get_complex_extra_info

# KB API 요청 시 브라우저로 보이도록 (User-Agent 미설정 시 연결 끊김 발생 가능)
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Cache-Control": "no-cache",
    "Origin": "https://kbland.kr",
    "Referer": "https://kbland.kr/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# 도로명주소 API (행정안전부 실시간 주소정보조회)
# https://www.data.go.kr/data/15057017/openapi.do / juso.go.kr 신청 후 confmKey 발급
JUSO_API_URL = "https://www.juso.go.kr/addrlink/addrLinkApi.do"

# parse_address 결과(강원도, 전라북도 등) → dongcode_data 실제 키(강원특별자치도, 전북특별자치도) 매핑
_REGION_LOOKUP_MAP = {
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
    "제주도": "제주특별자치도",
}

# 도로명 등으로 동/읍/면을 찾지 못할 때 사용하는 보조 매핑 (키워드→법정동코드)
# (시/군 키워드, 도로명·단지 키워드) → 법정동코드. 주소에 키워드가 모두 포함되면 사용.
_ROAD_FALLBACK_DONGCODES = [
    # 도로명주소로만 표기된 경우 (동/읍/면 파싱 실패 케이스)
    (["김포", "양도로"], "4157025600"),   # 경기 김포시 양촌읍 (양도로, 양도마을서해아파트)
    (["김포", "양도마을"], "4157025600"),
]


def _try_road_fallback_dongcode(address: str) -> Optional[str]:
    """도로명/키워드 보조 매핑으로 법정동코드 반환. 매칭 없으면 None."""
    addr = (address or "").strip()
    for keywords, code in _ROAD_FALLBACK_DONGCODES:
        if all(kw in addr for kw in keywords):
            return code
    return None


def _make_attached_address(address: str) -> str:
    """
    1차 조회 실패 시 재시도용: 주소 일부를 붙여서 검색 (공백 제거).
    - 안양시 동안구 → 안양시동안구
    - 김포시 양촌읍 → 김포시양촌읍
    법정동코드/검색 API가 붙어 있는 형태로만 인식하는 경우 대응.
    """
    if not address or not address.strip():
        return address or ""
    addr = re.sub(r"\s+", " ", address.strip())
    # "한글시 공백 한글구" → "한글시한글구" (시+구)
    addr = re.sub(r"([가-힣]+시)\s+([가-힣]+구)", r"\1\2", addr)
    # "한글시 공백 한글군" → "한글시한글군" (시+군)
    addr = re.sub(r"([가-힣]+시)\s+([가-힣]+군)", r"\1\2", addr)
    # "한글시 공백 한글읍" → "한글시한글읍" (시+읍)
    addr = re.sub(r"([가-힣]+시)\s+([가-힣]+읍)", r"\1\2", addr)
    # "한글시 공백 한글면" → "한글시한글면" (시+면)
    addr = re.sub(r"([가-힣]+시)\s+([가-힣]+면)", r"\1\2", addr)
    return addr


def _make_juso_search_keyword(address: str) -> Optional[str]:
    """API 검색용 키워드 생성. 도로명+번지 위주로 앞부분만 사용 (최대 50자)."""
    if not address or not address.strip():
        return None
    addr = re.sub(r"\s+", " ", address.strip())
    # 제N동, 제N층, 제N호 제거
    addr = re.sub(r"\s+제\d+동", "", addr)
    addr = re.sub(r"\s+제\d+층", "", addr)
    addr = re.sub(r"\s+제\d+호", "", addr)
    addr = re.sub(r"\s+제\d+번지", "", addr)
    addr = addr.strip()
    if len(addr) > 50:
        addr = addr[:50].rstrip()
    return addr if addr else None


def _get_dongcode_from_juso_api(address: str) -> Optional[str]:
    """
    행정안전부 도로명주소 API로 주소 검색 후 행정구역코드(10자리) 반환.
    환경변수 JUSO_API_KEY(또는 JUSO_CONFM_KEY)가 설정된 경우에만 호출.
    """
    key = os.environ.get("JUSO_API_KEY") or os.environ.get("JUSO_CONFM_KEY")
    if not key or not key.strip():
        return None
    keyword = _make_juso_search_keyword(address)
    if not keyword:
        return None
    try:
        resp = requests.post(
            JUSO_API_URL,
            data={
                "confmKey": key.strip(),
                "keyword": keyword,
                "resultType": "json",
                "countPerPage": 1,
                "currentPage": 1,
            },
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MortgageBot/1.0)"},
        )
        resp.raise_for_status()
        data = resp.json()
        # 응답 구조: results.juso (배열) 또는 results 내 첫 요소
        juso_list = None
        if isinstance(data, dict):
            results = data.get("results") or data.get("result")
            if isinstance(results, dict):
                juso_list = results.get("juso")
                if not juso_list and "common" in results:
                    error_code = (results.get("common") or {}).get("errorCode") or ""
                    if error_code and error_code != "0":
                        logger.debug(f"도로명주소 API 오류: {results.get('common')}")
                        return None
            elif isinstance(results, list) and results:
                first_el = results[0]
                juso_list = first_el.get("juso") if isinstance(first_el, dict) else results
        if not juso_list or not isinstance(juso_list, list) or len(juso_list) == 0:
            return None
        first = juso_list[0]
        if not isinstance(first, dict):
            return None
        # 행정구역코드: admCd (10자리 법정동코드)
        adm_cd = first.get("admCd") or first.get("행정구역코드") or ""
        if isinstance(adm_cd, str) and re.match(r"^\d{10}$", adm_cd.strip()):
            return adm_cd.strip()
        return None
    except Exception as e:
        logger.debug(f"도로명주소 API 조회 실패: {e}")
        return None


# 로깅 설정
# Vercel 환경에서는 파일 로깅이 제한적이므로 stdout/stderr 사용
# 로컬에서는 파일 로깅도 함께 사용
import sys
import os

# Vercel 환경 확인 (Vercel은 VERCEL 환경변수를 설정함)
is_vercel = os.getenv('VERCEL') == '1' or os.getenv('VERCEL_ENV') is not None

handlers = [logging.StreamHandler(sys.stderr)]  # Vercel에서 확인 가능한 stderr 사용

# 로컬 환경에서만 파일 로깅 추가
if not is_vercel:
    try:
        handlers.append(logging.FileHandler('kb_price_api_debug.log', encoding='utf-8'))
    except Exception:
        # 파일 로깅 실패해도 계속 진행
        pass

logging.basicConfig(
    level=logging.INFO if is_vercel else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)
if is_vercel:
    logger.setLevel(logging.INFO)

_KBLAND_COMPLEX_PATH_RE = re.compile(r"https?://(?:www\.)?kbland\.kr/(?:se/)?c/(\d+)")
_KBLAND_NUM_RE = re.compile(r"(\d+(?:-\d+)?)")
# kbland 검색창 autoKywrSerch 파라미터 (웹 JS 번들과 동일)
_KB_AUTO_KYWR_COLLECTION = (
    "COL_AT_JUSO:100;COL_AT_SCHOOL:100;COL_AT_SUBWAY:100;COL_AT_HSCM:100;COL_AT_VILLA:100"
)


def _is_invalid_complex_name(name: str) -> bool:
    """
    단지명 후보가 행정구역명으로 오탐된 경우 제외.
    예) 지세포리, 관양동, 일운면 ...
    """
    s = (name or "").strip()
    if len(s) < 2:
        return True
    # 행정구역 접미사로 끝나는 단독 지명은 단지명으로 취급하지 않음
    if re.search(r"(동|리|면|읍|시|군|구)$", s):
        return True
    return False


# 영문 알파벳 한글 글자명 → 라틴 (긴 음절 우선 매칭)
_LETTER_NAME_TO_LATIN: Tuple[Tuple[str, str], ...] = tuple(
    sorted(
        [
            ("더블유", "W"),
            ("에이치", "H"),
            ("에프", "F"),
            ("엑스", "X"),
            ("제트", "Z"),
            ("에이", "A"),
            ("비", "B"),
            ("씨", "C"),
            ("시", "C"),
            ("디", "D"),
            ("이", "E"),
            ("지", "G"),
            ("아이", "I"),
            ("제이", "J"),
            ("케이", "K"),
            ("엘", "L"),
            ("엠", "M"),
            ("엔", "N"),
            ("오", "O"),
            ("피", "P"),
            ("큐", "Q"),
            ("알", "R"),
            ("에스", "S"),
            ("티", "T"),
            ("유", "U"),
            ("브이", "V"),
            ("와이", "Y"),
        ],
        key=lambda x: (-len(x[0]), x[0]),
    )
)

# 글자명으로 오인하기 쉬운 외래어·일반어 접두 (시+티 → CT 등)
_LETTER_PREFIX_HANGUL_BLOCKLIST = frozenset(
    {
        "시티",
        "씨티",
        "센트",
        "스타",
        "스마트",
        "스카이",
        "파크",
        "타워",
        "빌리지",
        "플라자",
        "하우스",
        "미니",
        "슈퍼",
    }
)

# 브랜드 접미사 (추출·꼬리 판별 공용)
_COMPLEX_BRAND_SUFFIXES = (
    "힐스테이트",
    "아이파크",
    "아이유쉘",
    "푸르지오",
    "래미안",
    "자이",
    "센트럴",
    "팰리스",
    "유쉘",
    "월드",
    "보람",
    "연화",
    "은하",
    "중흥",
    "한라",
    "포도",
    "무지개",
    "덕유",
    "설악",
    "복사골",
    "금강",
    "동원",
    "대신",
    "범양",
    "영안",
    "현대",
    "형진",
    "풍남",
    "우방",
    "그린",
    "힐스",
    "꿈",
    "뉴",
    "더",
    "디",
    "엘",
    "리",
)


def _parse_hangul_letter_prefix(name: str) -> Tuple[str, str]:
    """
    단지명 앞의 영문 알파벳 한글 글자명 접두를 파싱.
    Returns: (라틴접두 or '', 나머지)
    예) 디엠씨래미안클라시스 → ('DMC', '래미안클라시스')
    """
    s = re.sub(r"[\s\-_·&]+", "", (name or "").strip())
    if not s:
        return "", ""
    # 이미 라틴으로 시작하면 접두 분리만
    m = re.match(r"^([A-Za-z0-9]+)(.*)$", s)
    if m:
        return m.group(1).upper(), m.group(2)

    latin_parts: List[str] = []
    rest = s
    consumed = ""
    while rest:
        matched = False
        for hangul, latin in _LETTER_NAME_TO_LATIN:
            if rest.startswith(hangul):
                latin_parts.append(latin)
                consumed += hangul
                rest = rest[len(hangul) :]
                matched = True
                break
        if not matched:
            break

    if len(latin_parts) < 2:
        return "", s
    if consumed in _LETTER_PREFIX_HANGUL_BLOCKLIST:
        return "", s
    # 블록리스트 접두로 시작하면 변환 안 함 (시티자이 등)
    for blocked in _LETTER_PREFIX_HANGUL_BLOCKLIST:
        if s.startswith(blocked):
            return "", s
    return "".join(latin_parts), rest


def _hangul_letter_prefix_to_latin_name(name: str) -> Optional[str]:
    """
    앞쪽 알파벳 음차를 영문으로 바꾼 단지명 변형.
    2글자 이상 변환될 때만 반환. 예) 디엠씨래미안클라시스 → DMC래미안클라시스
    """
    latin, rest = _parse_hangul_letter_prefix(name)
    if not latin or len(latin) < 2:
        return None
    # 순수 한글 입력이 아닐 때(이미 영문)는 변형 불필요
    raw = re.sub(r"[\s\-_·&]+", "", (name or "").strip())
    if re.match(r"^[A-Za-z0-9]", raw or ""):
        return None
    converted = f"{latin}{rest}"
    if converted == raw:
        return None
    return converted


def _expand_complex_name_search_variants(name: str) -> List[str]:
    """검색용 단지명 후보: 원문 + 알파벳 음차 변환본 + (가능 시) 한글 꼬리."""
    variants: List[str] = []
    raw = (name or "").strip()
    if not raw:
        return variants
    variants.append(raw)
    converted = _hangul_letter_prefix_to_latin_name(raw)
    if converted and converted not in variants:
        variants.append(converted)
    tail = _complex_name_hangul_tail(raw)
    if tail and len(tail) >= 4 and tail not in variants:
        # 꼬리만으로는 오탐 가능 → dual query 보조로만, 원문과 다를 때
        if tail != raw and (converted is None or tail != converted):
            variants.append(tail)
    return variants


def _complex_name_hangul_tail(name: str) -> str:
    """
    영문/알파벳음차 접두를 벗긴 공통 한글 꼬리.
    접두가 실제로 있을 때만 반환 (순수 한글 전체명은 빈 문자열).
    예) DMC래미안클라시스 / 디엠씨래미안클라시스 → 래미안클라시스
    """
    latin, rest = _parse_hangul_letter_prefix(name)
    if latin and len(latin) >= 2 and rest and re.match(r"^[가-힣]", rest):
        return rest
    s = re.sub(r"[\s\-_·&]+", "", (name or "").strip())
    m = re.match(r"^([A-Za-z0-9]+)([가-힣].*)$", s)
    if m:
        return m.group(2)
    return ""


def _normalize_kb_complex_name(name: str) -> str:
    """KB 단지명 비교용 공백 제거"""
    return re.sub(r"\s+", "", (name or "").strip())


def _normalize_kb_complex_name_for_match(name: str) -> str:
    """단지명 매칭용: 공백·하이픈 제거, 앞쪽 알파벳 음차→영문, 영문 소문자."""
    s = re.sub(r"[\s\-_·&]+", "", (name or "").strip())
    if not s:
        return s
    converted = _hangul_letter_prefix_to_latin_name(s)
    if converted:
        s = converted
    if re.search(r"[A-Za-z]", s):
        return s.lower()
    return s


def _complex_names_equivalent(a: str, b: str) -> bool:
    """단지명 동일 여부 (띄어쓰기·영문 대소문자·알파벳 음차·e-편한세상 등 무시)"""
    na = _normalize_kb_complex_name_for_match(a)
    nb = _normalize_kb_complex_name_for_match(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    # 숫자+단지 변형: 리버시티1단지 vs 리버시티
    base_a = re.sub(r"\d+단지$", "", na)
    base_b = re.sub(r"\d+단지$", "", nb)
    if base_a and base_b and (base_a == base_b or base_a in base_b or base_b in base_a):
        return True
    # 공통 한글 꼬리 (충분히 길 때만) — 양쪽 모두 영문/음차 접두가 있을 때
    tail_a = _complex_name_hangul_tail(a)
    tail_b = _complex_name_hangul_tail(b)
    if tail_a and tail_b and len(tail_a) >= 4 and len(tail_b) >= 4:
        if tail_a == tail_b or tail_a in tail_b or tail_b in tail_a:
            la, _ = _parse_hangul_letter_prefix(a)
            lb, _ = _parse_hangul_letter_prefix(b)
            if (la and len(la) >= 2) and (lb and len(lb) >= 2):
                return True
    return False


def _score_complex_name_similarity(target: str, api_name: str) -> float:
    """단지명 유사도 0~1 (영문·혼합·알파벳 음차·공통 한글 꼬리)"""
    if _complex_names_equivalent(target, api_name):
        return 1.0
    nt = _normalize_kb_complex_name_for_match(target)
    na = _normalize_kb_complex_name_for_match(api_name)
    if not nt or not na:
        return 0.0
    if nt in na:
        return min(0.95, len(nt) / len(na))
    if na in nt:
        return min(0.95, len(na) / len(nt))

    # 공통 한글 꼬리 점수 (래미안클라시스 등)
    tail_t = _complex_name_hangul_tail(target)
    tail_a = _complex_name_hangul_tail(api_name)
    # 한쪽만 접두가 있으면 다른 쪽 전체 한글과 꼬리 비교
    core_t = tail_t or re.sub(r"[\s\-_·&]+", "", (target or "").strip())
    core_a = tail_a or re.sub(r"[\s\-_·&]+", "", (api_name or "").strip())
    if (tail_t or tail_a) and core_t and core_a and len(core_t) >= 4 and len(core_a) >= 4:
        if core_t == core_a:
            return 0.88
        if core_t in core_a or core_a in core_t:
            shorter, longer = (core_t, core_a) if len(core_t) <= len(core_a) else (core_a, core_t)
            return min(0.85, 0.7 + 0.15 * (len(shorter) / max(len(longer), 1)))

    def _tokens(s: str) -> set:
        return set(re.findall(r"[가-힣]+|[a-z0-9]+", s.lower()))

    t_tok, a_tok = _tokens(nt), _tokens(na)
    if t_tok and a_tok:
        # 영문 약어(DMC 등)만 겹치는 경우는 제외 — 한글 토큰 교집합 필요
        hangul_t = {t for t in t_tok if re.search(r"[가-힣]", t)}
        hangul_a = {t for t in a_tok if re.search(r"[가-힣]", t)}
        if hangul_t and hangul_a and not (hangul_t & hangul_a):
            return 0.0
        overlap = len(t_tok & a_tok) / max(len(t_tok), len(a_tok))
        if overlap >= 0.5:
            return 0.65 + overlap * 0.25
    return 0.0


def _extract_address_match_tokens(address: str) -> List[str]:
    """단지명 없을 때 KB 단지 주소와 대조할 키워드 (블럭/롯트/지구 등)"""
    if not address:
        return []
    tokens: List[str] = []
    patterns = [
        r"[A-Za-z]?\d+\s*(?:블럭|블록|BL)\s*\d*\s*(?:롯트|로트)?",
        r"[A-Za-z]\d*BL",
        r"[가-힣]+(?:지구|구역)",
        r"[가-힣A-Za-z0-9]+(?:단지|타운|빌리지|시티)",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, address, re.IGNORECASE):
            tok = _normalize_kb_complex_name_for_match(m.group(0))
            if len(tok) >= 3 and tok not in tokens:
                tokens.append(tok)
    return tokens


def _score_address_token_match(tokens: List[str], api_address: str) -> float:
    """등기부 주소 토큰이 KB 단지 주소에 얼마나 겹치는지"""
    if not tokens or not api_address:
        return 0.0
    norm_addr = _normalize_kb_complex_name_for_match(api_address)
    hits = sum(1 for t in tokens if t in norm_addr)
    return hits / len(tokens) if tokens else 0.0


def _clean_extracted_complex_name(name: str) -> str:
    """추출된 단지명 후처리: 동번호·행정구역 오탐 제거"""
    s = _normalize_kb_complex_name(name)
    if not s:
        return s
    # 끝의 동번호(101동→101) 제거 — 센트럴파크101 → 센트럴파크
    if not s.endswith("단지"):
        s = re.sub(r"\d{2,4}동?$", "", s)
    # 영문 단지명 앞에 붙은 행정구역 접두 제거
    s = re.sub(
        r"^(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)"
        r"(?:특별시|광역시|특별자치시|도)?"
        r"(?:[가-힣]+(?:시|군|구))+(?:[가-힣]+(?:동|읍|면|리))*",
        "",
        s,
    )
    return s.strip()


def _extract_complex_name_from_address(address: str) -> Optional[str]:
    """
    등기부 주소에서 KB 단지명 추출.
    '힐스테이트 리버시티 1단지'처럼 띄어쓰기가 있는 브랜드 단지명도 처리.
    """
    if not address:
        return None

    # 브랜드 + 단지명 (띄어쓰기 허용) — 영문/혼합보다 먼저
    spaced_brand_patterns = [
        r"((?:힐스테이트|힐스)\s+[가-힣]+(?:\s*\d+)?\s*단지)",
        r"((?:래미안|자이|푸르지오|아이파크|e편한세상|이편한세상)\s+[가-힣]+(?:\s*\d+)?\s*단지)",
        r"((?:힐스테이트|래미안|자이|힐스)\s+[가-힣]+(?:\s*\d+)?\s*단지)",
    ]
    for pattern in spaced_brand_patterns:
        m = re.search(pattern, address, re.IGNORECASE)
        if m:
            candidate = _normalize_kb_complex_name(m.group(1))
            if len(candidate) >= 4 and not _is_invalid_complex_name(candidate):
                return candidate

    # 혼합(한글+영문) 브랜드 단지명: e편한세상, THE HILL, Songdo Central Park 등
    mixed_patterns = [
        r"((?:e|E)[\s\-]?편한세상\s+[가-힣A-Za-z0-9]+(?:\s*\d+)?\s*(?:단지)?)",
        r"((?:THE|the)\s+[가-힣A-Za-z0-9]+(?:\s+[가-힣A-Za-z0-9]+)*)",
        r"([A-Za-z][A-Za-z0-9]*(?:\s+[A-Za-z][A-Za-z0-9]*)+(?:\s*\d+)?\s*단지)",
        r"([A-Za-z][A-Za-z0-9]*(?:\s+[A-Za-z][A-Za-z0-9]*)+)",
        r"([가-힣A-Za-z0-9]+(?:\s+[가-힣A-Za-z0-9]+){0,3}\s*\d+\s*(?:단지|타운|빌리지|시티|아파트|오피스텔))",
        r"([가-힣]{2,}(?:앤|&)[가-힣]{2,}(?:시티|파크)?)",
    ]
    for pattern in mixed_patterns:
        m = re.search(pattern, address, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            if re.search(r"(?:구역|사업|블럭|블록|롯트|필지|도시개발)", raw):
                continue
            candidate = _clean_extracted_complex_name(raw)
            if len(candidate) >= 3 and not _is_invalid_complex_name(candidate):
                return candidate

    # 일반 띄어쓰기 단지명 (도시개발구역/블럭/롯트 키워드 제외)
    m = re.search(r"([가-힣]+(?:\s+[가-힣]+){1,4}\s*\d*\s*단지)", address)
    if m:
        raw = m.group(1).strip()
        if not re.search(r"(?:구역|사업|블럭|블록|롯트|필지)", raw):
            candidate = _normalize_kb_complex_name(raw)
            if len(candidate) >= 4 and not _is_invalid_complex_name(candidate):
                return candidate

    return None


def _extract_lot_number_from_address(address: str) -> Optional[str]:
    """
    동+번지 매칭용 번지수 추출.
    '에이1블럭1롯트'의 1처럼 블록/롯트 번호는 제외한다.
    """
    if not address:
        return None

    addr = re.sub(r"\s+제\d+동", "", address)
    addr = re.sub(r"\s+제\d+층", "", addr)
    addr = re.sub(r"\s+제\d+호", "", addr)
    addr = re.sub(r"\s+", " ", addr).strip()

    # 법정 리/동 + 번지: 신곡리 1110, 향산리 123-1
    m = re.search(r"([가-힣]+(?:리|동))\s+(\d{2,}(?:-\d+)?)", addr)
    if m:
        return m.group(2)

    # 리/동/번지 뒤 번지
    m = re.search(r"(?:리|동|번지)\s+(\d{2,}(?:-\d+)?)", addr)
    if m:
        return m.group(1)

    # 독립 3자리 이상 번지 (도로명 번지 등)
    m = re.search(r"(?:^|[^가-힣0-9])(\d{3,}(?:-\d+)?)(?:\s*(?:번지)?(?:\s|$)|$)", addr)
    if m:
        return m.group(1)

    return None


def _lot_matches_complex_address(lot: str, complex_address: str) -> bool:
    """번지가 단지 주소에 정확히 포함되는지 확인 ('1' in '1110' 오매칭 방지)"""
    if not lot or not complex_address:
        return False
    ca = complex_address.strip()
    patterns = [
        rf"(?:리|동)\s+{re.escape(lot)}(?:\s|$|-)",
        rf"(?:^|\s){re.escape(lot)}(?:\s|$|-)",
        rf"(?:^|\s){re.escape(lot)}(?:번지)",
    ]
    return any(re.search(p, ca) for p in patterns)


class KBPriceAPI:
    """KB 부동산 시세 API 클라이언트"""
    
    def __init__(self, dongcode_data_path: Optional[str] = None):
        """
        초기화
        
        Args:
            dongcode_data_path: 법정동코드 데이터 JSON 파일 경로
                                None이면 자동으로 찾음
        """
        self.base_url = "https://api.kbland.kr"
        self.dongcode_data = None
        self.dongcode_data_path = dongcode_data_path
        
        # 법정동코드 데이터 로드
        self._load_dongcode_data()
    
    def _load_dongcode_data(self):
        """법정동코드 데이터 로드"""
        if self.dongcode_data_path and os.path.exists(self.dongcode_data_path):
            data_path = self.dongcode_data_path
        else:
            # 자동으로 찾기 (KB_api 폴더 내에서 찾기)
            current_dir = Path(__file__).parent
            possible_paths = [
                current_dir / "전국_dongcode_data.json",  # 전국 데이터 (필수)
            ]
            
            data_path = None
            for path in possible_paths:
                if path.exists():
                    data_path = str(path)
                    break
        
        if data_path and os.path.exists(data_path):
            try:
                with open(data_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.dongcode_data = data.get('regions', {})
                    file_name = os.path.basename(data_path)
                    total_regions = len(self.dongcode_data)
                    logger.info(f"법정동코드 데이터 로드 완료: {file_name} (시/도: {total_regions}개)")
            except Exception as e:
                logger.error(f"법정동코드 데이터 로드 실패: {e}")
                self.dongcode_data = {}
        else:
            logger.warning("법정동코드 데이터 파일을 찾을 수 없습니다.")
            self.dongcode_data = {}

    def _cache_file_path(self) -> Path:
        return Path(__file__).parent / "kb_complex_id_cache.json"

    def _load_complex_id_cache(self) -> Dict[str, str]:
        p = self._cache_file_path()
        if not p.exists():
            return {}
        try:
            with p.open("r", encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, dict):
                return {str(k): str(v) for k, v in obj.items() if str(v).strip().isdigit()}
        except Exception as e:
            logger.debug("kb_complex_id_cache 로드 실패: %s", e)
        return {}

    def _save_complex_id_cache(self, cache: Dict[str, str]) -> None:
        p = self._cache_file_path()
        try:
            with p.open("w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("kb_complex_id_cache 저장 실패: %s", e)

    @staticmethod
    def _normalize_text(value: str) -> str:
        v = (value or "").strip()
        v = re.sub(r"\s+", "", v)
        v = re.sub(r"[()\-_,./]", "", v)
        return v

    def _build_cache_keys(self, address: str, complex_name: Optional[str]) -> List[str]:
        keys = []
        if complex_name:
            keys.append(f"name::{self._normalize_text(complex_name)}")
        if address:
            keys.append(f"addr::{self._normalize_text(address)}")
        if address and complex_name:
            keys.append(f"pair::{self._normalize_text(address)}::{self._normalize_text(complex_name)}")
        return keys

    def _kb_intgra_search_hscm(self, keyword: str, count: int = 2) -> List[Dict[str, Any]]:
        """kbland 내부 통합검색(intgraSerch)으로 단지 후보 조회."""
        kw = (keyword or "").strip()
        if not kw:
            return []
        params = {
            "검색대상구분": "SRC_HSCM",
            "검색키워드": kw,
            "결과개수": count,
            "페이지번호": 1,
        }
        try:
            response = requests.get(
                f"{self.base_url}/land-complex/serch/intgraSerch",
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=12,
            )
            response.raise_for_status()
            body = response.json().get("dataBody", {}) or {}
            rc = body.get("resultCode")
            if rc not in (None, 11000):
                logger.debug(
                    "intgraSerch 오류(keyword=%s): rc=%s msg=%s",
                    kw[:40], rc, body.get("message"),
                )
                return []
            outer = body.get("data")
            if not isinstance(outer, dict):
                return []
            inner = outer.get("data")
            if isinstance(inner, dict) and inner.get("resultCode") not in (None, 11000):
                logger.debug(
                    "intgraSerch 엔진 오류(keyword=%s): %s",
                    kw[:40], inner.get("message"),
                )
                return []
            hscm = (inner or {}).get("HSCM") if isinstance(inner, dict) else {}
            items = (hscm or {}).get("data") or []
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.debug("intgraSerch 실패(keyword=%s): %s", kw[:40], e)
            return []

    def _kb_auto_keyword_hscm(self, keyword: str) -> List[Dict[str, Any]]:
        """kbland 자동완성(autoKywrSerch)으로 단지명 후보 확장."""
        kw = (keyword or "").strip()
        if not kw:
            return []
        params = {
            "컬렉션비중설정": _KB_AUTO_KYWR_COLLECTION,
            "검색키워드": kw,
        }
        try:
            response = requests.get(
                f"{self.base_url}/land-complex/serch/autoKywrSerch",
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=12,
            )
            response.raise_for_status()
            body = response.json().get("dataBody", {}) or {}
            rc = body.get("resultCode")
            if rc not in (None, 11000):
                return []
            data = body.get("data") or []
            if isinstance(data, list) and data:
                items = data[0].get("COL_AT_HSCM") or []
                return items if isinstance(items, list) else []
        except Exception as e:
            logger.debug("autoKywrSerch 실패(keyword=%s): %s", kw[:40], e)
        return []

    @staticmethod
    def _intgra_item_to_page_info(item: Dict[str, Any]) -> Dict[str, str]:
        """intgraSerch 단지 항목 → _score_complex_match 입력 형식."""
        cid = str(item.get("COMPLEX_NO") or "").strip()
        return {
            "url": f"https://kbland.kr/c/{cid}" if cid else "",
            "title": (item.get("HSCM_NM_EXT") or item.get("HSCM_NM") or "").strip(),
            "road_address": (item.get("NEWADDRESS") or "").strip(),
            "jibun_address": (item.get("JUSO_ARNO") or item.get("ARNO") or "").strip(),
        }

    def _collect_kb_search_candidates(
        self,
        keywords: List[str],
        head_limit: int = 12,
    ) -> List[Tuple[str, Dict[str, str]]]:
        """
        kbland 내부 검색 API로 complex_id 후보 수집.
        intgraSerch 우선, 부족 시 autoKywrSerch로 검색어 확장.
        """
        seen_ids: set = set()
        candidates: List[Tuple[str, Dict[str, str]]] = []

        def _add_from_intgra(items: List[Dict[str, Any]]) -> None:
            for item in items:
                cid = str(item.get("COMPLEX_NO") or "").strip()
                if not cid or cid in seen_ids:
                    continue
                seen_ids.add(cid)
                candidates.append((cid, self._intgra_item_to_page_info(item)))
                if len(candidates) >= head_limit:
                    return

        unique_keywords: List[str] = []
        for kw in keywords:
            k = (kw or "").strip()
            if k and k not in unique_keywords:
                unique_keywords.append(k)

        for kw in unique_keywords:
            _add_from_intgra(self._kb_intgra_search_hscm(kw, count=10))
            if len(candidates) >= head_limit:
                return candidates[:head_limit]

        for kw in unique_keywords[:4]:
            for ac in self._kb_auto_keyword_hscm(kw):
                for search_kw in (
                    (ac.get("textTemp") or "").strip(),
                    (ac.get("text") or "").strip(),
                ):
                    if not search_kw:
                        continue
                    _add_from_intgra(self._kb_intgra_search_hscm(search_kw, count=5))
                    if len(candidates) >= head_limit:
                        return candidates[:head_limit]

        return candidates[:head_limit]

    def _fetch_hscm_list(self, dongcode: str) -> List[Dict[str, Any]]:
        """법정동코드 기준 단지 목록(hscmList) — fastPriceInfo 보조."""
        try:
            response = requests.get(
                f"{self.base_url}/land-complex/complexComm/hscmList",
                params={"법정동코드": dongcode},
                headers=DEFAULT_HEADERS,
                timeout=15,
            )
            response.raise_for_status()
            items = response.json().get("dataBody", {}).get("data", [])
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.debug("hscmList 조회 실패(dongcode=%s): %s", dongcode, e)
            return []

    def _merge_hscm_into_complex_list(
        self,
        merged: List[Dict[str, Any]],
        seen_ids: set,
        dongcode: str,
    ) -> int:
        """hscmList 항목을 fastPriceInfo 목록에 병합. 추가된 개수 반환."""
        added = 0
        for item in self._fetch_hscm_list(dongcode):
            cid = item.get("단지기본일련번호")
            if cid is None or cid in seen_ids:
                continue
            seen_ids.add(cid)
            merged.append({
                "단지기본일련번호": cid,
                "단지명": item.get("단지명") or "",
                "주소": item.get("주소") or "",
            })
            added += 1
        return added

    def _fetch_kbland_page_info(self, complex_id: str) -> Optional[Dict[str, str]]:
        for path in (f"https://kbland.kr/se/c/{complex_id}", f"https://kbland.kr/c/{complex_id}"):
            try:
                r = requests.get(path, headers=DEFAULT_HEADERS, timeout=12)
                if r.status_code >= 400:
                    continue
                text = html.unescape(r.text or "")
                compact = re.sub(r"\s+", " ", text)

                title_match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else ""

                # meta keywords에 주소가 가장 잘 들어옴 (SSR)
                keywords_match = re.search(r'<meta[^>]+name="keywords"[^>]+content="([^"]+)"', text, re.IGNORECASE)
                keyword_text = keywords_match.group(1) if keywords_match else ""
                compact_kw = re.sub(r"\s+", " ", html.unescape(keyword_text))

                # 도로명 패턴 예: 거제시 일운면 지세포1길 27
                road_match = re.search(
                    r"((?:[가-힣]+도\s+)?[가-힣]+시(?:\s+[가-힣]+(?:구|군))?\s+[가-힣]+(?:동|읍|면)\s+[가-힣0-9]+(?:로|길)\s*\d+(?:-\d+)?)",
                    compact_kw or compact,
                )
                # 지번 패턴 예: 경상남도 거제시 일운면 지세포리 1412
                jibun_match = re.search(
                    r"((?:[가-힣]+도\s+)?[가-힣]+시(?:\s+[가-힣]+(?:구|군))?\s+[가-힣]+(?:동|읍|면)\s+[가-힣0-9]+(?:리|동)\s*\d+(?:-\d+)?)",
                    compact_kw or compact,
                )
                return {
                    "url": path,
                    "title": title,
                    "road_address": road_match.group(1).strip() if road_match else "",
                    "jibun_address": jibun_match.group(1).strip() if jibun_match else "",
                }
            except Exception:
                continue
        return None

    def _score_complex_match(
        self,
        target_address: str,
        target_complex_name: Optional[str],
        page_info: Dict[str, str],
    ) -> float:
        score = 0.0
        addr = self._normalize_text(target_address)
        road = self._normalize_text(page_info.get("road_address", ""))
        jibun = self._normalize_text(page_info.get("jibun_address", ""))
        title = self._normalize_text(page_info.get("title", ""))
        cand = f"{road}{jibun}{title}"

        if addr and cand and (addr in cand or cand in addr):
            score += 2.0

        parsed = self.parse_address(target_address)
        for key in ("district", "dong"):
            token = self._normalize_text(parsed.get(key, ""))
            if token and token in cand:
                score += 1.0

        target_nums = set(_KBLAND_NUM_RE.findall(target_address or ""))
        cand_nums = set(_KBLAND_NUM_RE.findall(f"{page_info.get('road_address','')} {page_info.get('jibun_address','')}"))
        if target_nums and cand_nums and target_nums.intersection(cand_nums):
            score += 1.0

        if target_complex_name:
            name_norm = self._normalize_text(target_complex_name)
            name_match = _normalize_kb_complex_name_for_match(target_complex_name)
            title_match = _normalize_kb_complex_name_for_match(page_info.get("title", ""))
            title_raw = page_info.get("title", "") or ""
            if name_norm and name_norm in title:
                score += 2.0
            elif name_match and title_match and (name_match in title_match or title_match in name_match):
                score += 2.0
            elif _complex_names_equivalent(target_complex_name, title_raw):
                score += 2.0
            else:
                tail_t = _complex_name_hangul_tail(target_complex_name)
                tail_title = _complex_name_hangul_tail(title_raw) or title_match
                if tail_t and len(tail_t) >= 4 and tail_title and (
                    tail_t == tail_title or tail_t in tail_title or tail_title in tail_t
                ):
                    score += 1.5
                elif name_norm and (name_norm in cand or cand.find(name_norm[:3]) >= 0):
                    score += 0.8
                elif name_match and _normalize_kb_complex_name_for_match(cand).find(name_match[:4]) >= 0:
                    score += 0.8

        return score

    def resolve_complex_id_by_search(
        self,
        address: str,
        complex_name: Optional[str],
        dongcode: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        """
        fastPriceInfo 매칭 실패 시, kbland 내부 검색 API(intgraSerch)로 후보를 수집하고
        단지 주소/단지명을 등기부 주소와 대조해 complex_id를 확정한다.
        """
        if not address:
            return None
        if not complex_name:
            # 단지명 없으면 주소 토큰(블럭/롯트/지구)으로 검색어 구성
            addr_tokens = _extract_address_match_tokens(address)
            if addr_tokens:
                complex_name = addr_tokens[0]
            else:
                return None

        cache = self._load_complex_id_cache()
        for k in self._build_cache_keys(address, complex_name):
            cid = cache.get(k)
            if cid:
                info = self._fetch_kbland_page_info(cid)
                if info and self._score_complex_match(address, complex_name, info) >= 3.0:
                    logger.info("✅ KB 캐시 ID 사용: %s (%s)", cid, info.get("url"))
                    return {"complex_id": cid, "complex_name": complex_name}

        # 원문 + 알파벳 음차 변환본(DMC…) + 한글 꼬리 dual query
        name_variants = _expand_complex_name_search_variants(complex_name)
        keyword_candidates: List[str] = list(name_variants)
        parsed = self.parse_address(address)
        for variant in name_variants:
            if parsed.get("dong"):
                keyword_candidates.append(f"{variant} {parsed.get('dong')}")
            if parsed.get("district"):
                keyword_candidates.append(f"{variant} {parsed.get('district')}")
            if dongcode:
                keyword_candidates.append(f"{variant} {dongcode}")

        search_candidates = self._collect_kb_search_candidates(keyword_candidates, head_limit=12)

        if not search_candidates:
            logger.info("KB 내부 검색 후보 없음 (keyword=%s)", complex_name)
            return None

        best = None
        best_score = -1.0
        for cid, info in search_candidates:
            score = self._score_complex_match(address, complex_name, info)
            logger.info(
                "KB 내부 검색 후보 검증: id=%s score=%.2f road=%s jibun=%s title=%s",
                cid, score, info.get("road_address"), info.get("jibun_address"), info.get("title"),
            )
            if score > best_score:
                best_score = score
                best = (cid, info)

        if not best or best_score < 3.0:
            logger.info("KB ID 확정 실패: 최고 점수 %.2f", best_score)
            return None

        resolved_id, resolved_info = best
        # 성공 시 캐시 저장
        for k in self._build_cache_keys(address, complex_name):
            cache[k] = resolved_id
        self._save_complex_id_cache(cache)
        logger.info("✅ KB ID 확정(내부검색): %s (%s)", resolved_id, resolved_info.get("url"))
        return {"complex_id": resolved_id, "complex_name": complex_name}
    
    def parse_address(self, address: str) -> Dict[str, str]:
        """
        주소를 파싱하여 지역 정보 추출
        
        Args:
            address: 주소 문자열 (예: "서울특별시 강남구 대치동 123")
        
        Returns:
            {
                "region": "서울특별시",
                "district": "강남구",
                "dong": "대치동",
                "detail": "123"
            }
        """
        logger.debug(f"🔍 주소 파싱 시작: {address}")
        
        if not address:
            logger.warning("⚠️ 주소가 비어있음")
            return {}
        
        # 원본 주소 저장
        original_address = address
        
        # 주소 정규화 (공백 정리)
        address = re.sub(r'\s+', ' ', address.strip())
        logger.debug(f"   정규화된 주소: {address}")
        
        # '제217동', '제1105호' 같은 상세 주소 제거 (법정동명 찾기 전에 제거)
        # 법정동명은 "곡반정동" 같은 형태이므로, "제숫자동", "제숫자호" 같은 패턴 제거
        address_cleaned = re.sub(r'\s+제\d+동', '', address)  # " 제217동" 제거
        address_cleaned = re.sub(r'\s+제\d+호', '', address_cleaned)  # " 제1105호" 제거
        address_cleaned = re.sub(r'\s+제\d+층', '', address_cleaned)  # " 제11층" 제거
        address_cleaned = re.sub(r'\s+제\d+번지', '', address_cleaned)  # " 제123번지" 제거
        
        if address_cleaned != address:
            logger.debug(f"   상세 주소 제거: '{address}' -> '{address_cleaned}'")
            address = address_cleaned
        
        result = {}
        
        # 시/도 추출
        region_patterns = [
            r'(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|경기도|강원도|충청북도|충청남도|전라북도|전라남도|경상북도|경상남도|제주특별자치도)',
            r'(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)',
        ]
        
        for pattern in region_patterns:
            match = re.search(pattern, address)
            if match:
                region = match.group(1)
                # 약칭을 정식명으로 변환
                region_map = {
                    "서울": "서울특별시",
                    "부산": "부산광역시",
                    "대구": "대구광역시",
                    "인천": "인천광역시",
                    "광주": "광주광역시",
                    "대전": "대전광역시",
                    "울산": "울산광역시",
                    "세종": "세종특별자치시",
                    "경기": "경기도",
                    "강원": "강원도",
                    "충북": "충청북도",
                    "충남": "충청남도",
                    "전북": "전라북도",
                    "전남": "전라남도",
                    "경북": "경상북도",
                    "경남": "경상남도",
                    "제주": "제주특별자치도",
                }
                result["region"] = region_map.get(region, region)
                break
        
        # 구/시/군 추출
        # "경기도 수원시 권선구" -> district="수원시"
        # "경기도 부천시 원미구" -> district="부천시"
        # "서울특별시 구로구" -> district="구로구"
        # "부산광역시 동래구" -> district="동래구"
        # 시/군을 먼저 찾고, 그 다음 구를 찾아야 함
        district_patterns = [
            r'(?:시|도)\s+([가-힣]+시)\s+[가-힣]+구',  # "경기도 부천시 원미구" -> "부천시" (우선)
            r'(?:시|도)\s+([가-힣]+시|[가-힣]+군)',  # "경기도 수원시" -> "수원시"
            r'(?:특별시|광역시)\s+([가-힣]+구)',  # "서울특별시 구로구" -> "구로구", "부산광역시 동래구" -> "동래구"
        ]
        
        for pattern in district_patterns:
            match = re.search(pattern, address)
            if match:
                result["district"] = match.group(1)
                logger.debug(f"   구/시/군 추출: {match.group(1)}")
                break
        
        # 도로명주소: 맨 앞에 시/군만 있는 경우 (예: "원주시 장막2길 12") - region 없이 district만
        if not result.get("district"):
            lead_match = re.match(r'^([가-힣]+(?:시|군))\s', address)
            if lead_match:
                cand = lead_match.group(1)
                # 시/도급(특별시, 광역시, 도)이면 district로 사용하지 않음
                if not any(x in cand for x in ("특별", "광역", "특별자치", "도")):
                    result["district"] = cand
                    logger.debug(f"   구/시/군 추출(도로명 선행): {cand}")
        
        # 동/읍/면 추출 (제217동, 제1105호 같은 '제' 제거)
        # 전국 데이터 구조: "권선구 곡반정동" 형식으로 저장됨
        # "경기도 수원시 권선구 곡반정동" -> dong="권선구 곡반정동"으로 추출
        # "서울특별시 종로구 청운동" -> dong="청운동"으로 추출
        
        # 패턴 1: "경기도 수원시 권선구 곡반정동" -> "권선구 곡반정동" 추출
        # 패턴 2: "서울특별시 종로구 청운동" -> "청운동" 추출
        # 패턴 2-1: "거제시 일운면 지세포리" -> "일운면 지세포리" (면+리, 법정동코드 데이터 키와 일치)
        # 양평동3가, 영등포동1가 등 "동+숫자+가"를 먼저 매칭 (법정동코드 데이터 키와 일치)
        dong_patterns = [
            r'(?:시|도)\s+[가-힣]+(?:시|구|군)\s+([가-힣]+(?:구|군|시)\s+[가-힣]+(?:동|읍|면))',  # "원미구 중동", "권선구 곡반정동" 형식
            r'(?:구|군|시)\s+[가-힣]+(?:읍|면)\s+([가-힣]+리)',  # "김포시 고촌읍 향산리" -> "향산리"
            r'(?:구|군|시)\s+([가-힣]+면\s+[가-힣]+리)',  # "거제시 일운면 지세포리" -> "일운면 지세포리" (면+리 우선)
            r'(?:구|군|시)\s+([가-힣]+(?:구|군|시)?\s*[가-힣]+(?:동|읍|면))',  # "원미구 중동", "권선구 곡반정동" 같은 경우
            r'(?:구|군|시)\s+([가-힣]+(?:동|읍|면)\s*\d+가)',  # 양평동3가, 양평동 3가(공백) 등 (일반 동명보다 우선)
            r'(?:구|군|시)\s+([가-힣]+(?:동|읍|면))',  # 일반 동명 (예: 곡반정동, 청운동, 중동)
            r'(?:구|군|시)\s+제?(\d+동)',  # 제가 붙은 동 (예: 제217동)
        ]
        
        dong_found = False
        for pattern in dong_patterns:
            match = re.search(pattern, address)
            if match:
                dong_raw = match.group(1)
                # '제' 제거 및 정리
                dong_cleaned = re.sub(r'^제', '', dong_raw).strip()
                # "양평동 3가" → "양평동3가" (법정동코드 데이터 키는 공백 없음)
                dong_cleaned = re.sub(r'(동|읍|면)\s+(\d+가)', r'\1\2', dong_cleaned)
                result["dong"] = dong_cleaned
                logger.debug(f"   동 추출: {dong_raw} -> {dong_cleaned}")
                dong_found = True
                break
        
        if not dong_found:
            logger.warning(f"⚠️ 동/읍/면을 찾을 수 없음: {address}")
        
        # 도로명 패턴 추출 (~로, ~길) - find_dongcode에서 시/군/구 기반 검색 시 활용
        # "장막2길", "양도로", "테스트로 123" 등 지원
        road_match = re.search(r'([가-힣]+(?:\d)*(?:로|길)\s*\d*)', address)
        if road_match:
            result["road_name"] = road_match.group(1).strip()  # 예: "장막2길", "양도로"
            logger.debug(f"   도로명 추출: {result['road_name']}")
        
        # 상세 주소 (나머지)
        if result.get("dong"):
            detail_start = address.find(result["dong"]) + len(result["dong"])
            result["detail"] = address[detail_start:].strip()
            logger.debug(f"   상세 주소: {result.get('detail', '')}")
        
        logger.debug(f"✅ 주소 파싱 결과: {result}")
        return result
    
    def find_dongcode(self, address: str) -> Optional[str]:
        """
        주소에서 법정동코드 찾기
        
        Args:
            address: 주소 문자열
        
        Returns:
            법정동코드 (10자리 문자열) 또는 None
        """
        logger.debug(f"🔍 법정동코드 찾기 시작: {address}")
        
        if not self.dongcode_data:
            logger.error("법정동코드 데이터가 로드되지 않았습니다.")
            return None
        
        parsed = self.parse_address(address)
        region = parsed.get("region")
        district = parsed.get("district")
        dong = parsed.get("dong")
        
        # 강원도→강원특별자치도, 전라북도→전북특별자치도 등 dongcode_data 키로 매핑
        if region and region in _REGION_LOOKUP_MAP:
            region = _REGION_LOOKUP_MAP[region]
            logger.debug(f"   region 매핑 적용: {parsed.get('region')} → {region}")
        
        logger.debug(f"   파싱된 주소 정보: region={region}, district={district}, dong={dong}")
        
        # [방안 A] district는 있는데 region 없음 → dongcode_data에서 해당 district를 가진 region 추론
        if district and not region:
            for reg_key, reg_val in (self.dongcode_data or {}).items():
                districts_in_reg = (reg_val or {}).get("districts", {})
                if district in districts_in_reg:
                    region = reg_key
                    logger.info(f"   region 추론(시/군 기반): {district} → {region}")
                    break
        
        # [방안 A] region·district 있으나 dong 없음 + 도로명 있음 → district 하위 dongs에서 도로명 stem 매칭
        road_name = parsed.get("road_name")
        if region and district and not dong and road_name:
            road_stem = re.sub(r'\d*(로|길)\s*\d*$', '', road_name).strip()  # "장막2길"→"장막", "양도로"→"양도"
            if len(road_stem) >= 2:
                region_data = self.dongcode_data.get(region, {})
                district_data = (region_data.get("districts", {}) or {}).get(district, {})
                dongs = (district_data or {}).get("dongs", {})
                for dong_key, dong_val in dongs.items():
                    if road_stem in dong_key and isinstance(dong_val, dict):
                        code = dong_val.get("code")
                        if code and re.match(r'^\d{10}$', str(code)):
                            logger.info(f"   도로명 기반 동 매칭: {road_stem} in '{dong_key}' → {code}")
                            return str(code)
        
        logger.debug(f"   파싱된 주소 정보(추론 후): region={region}, district={district}, dong={dong}")
        
        if not all([region, district, dong]):
            fallback = _try_road_fallback_dongcode(address)
            if fallback:
                logger.info(f"도로명/키워드 보조 매핑으로 법정동코드 사용: {fallback} (동/읍/면 파싱 실패)")
                return fallback
            api_code = _get_dongcode_from_juso_api(address)
            if api_code:
                logger.info(f"도로명주소 API로 법정동코드 조회: {api_code} (동/읍/면 파싱 실패)")
                return api_code
            logger.warning(f"주소 파싱 실패: {address} -> {parsed}")
            return None
        
        # 데이터에서 찾기
        region_data = self.dongcode_data.get(region, {})
        logger.debug(f"   지역 데이터 존재: {bool(region_data)}")
        
        if not region_data:
            logger.warning(f"⚠️ 지역 데이터 없음: {region}")
            # 유사 지역명 찾기 시도
            for key in self.dongcode_data.keys():
                if region in key or key in region:
                    logger.debug(f"   유사 지역 발견: {key}")
                    region_data = self.dongcode_data.get(key, {})
                    region = key
                    break
        
        districts = region_data.get("districts", {})
        logger.debug(f"   구/시/군 목록: {list(districts.keys())[:5]}...")
        
        district_data = districts.get(district, {})
        logger.debug(f"   구/시/군 데이터 존재: {bool(district_data)}")
        
        if not district_data:
            logger.warning(f"⚠️ 구/시/군 데이터 없음: {district}")
            # 유사 구/시/군명 찾기: district가 "안양시"일 때 "안양시 동안구" 등 시작하는 키 시도
            for key in districts.keys():
                if key.startswith(district) or district in key or key in district:
                    logger.debug(f"   유사 구/시/군 발견: {key}")
                    district_data = districts.get(key, {})
                    district = key
                    break
        
        dongs = district_data.get("dongs", {})
        logger.debug(f"   동 목록: {list(dongs.keys())[:5]}...")
        
        # 동 단위 데이터 찾기
        dong_data = dongs.get(dong, {})
        logger.debug(f"   동 데이터 존재: {bool(dong_data)}")
        
        if not dong_data:
            logger.warning(f"⚠️ 동 데이터 없음: {dong}")
            # 유사 동명 찾기 시도 (전국 데이터 구조에 맞게)
            for key in dongs.keys():
                # 정확한 매칭
                if dong == key:
                    logger.debug(f"   정확한 동명 매칭: {key}")
                    dong_data = dongs.get(key, {})
                    dong = key
                    break
                
                # "권선구 곡반정동" 같은 경우도 매칭
                # 예: dong="권선구 곡반정동", key="권선구 곡반정동" -> 매칭
                if dong in key or key in dong or key.endswith(dong):
                    logger.debug(f"   유사 동명 발견: {key}")
                    dong_data = dongs.get(key, {})
                    dong = key
                    break
                
                # "권선구 곡반정동"에서 "곡반정동"만 추출해서 매칭
                # 예: dong="곡반정동", key="권선구 곡반정동" -> 매칭
                if ' ' in key:
                    key_dong_only = key.split()[-1]  # 마지막 부분이 동명
                    if dong == key_dong_only:
                        logger.debug(f"   동명만으로 매칭: {key} (추출된 동명: {key_dong_only})")
                        dong_data = dongs.get(key, {})
                        dong = key
                        break
        
        dongcode = dong_data.get("code")
        
        # 동 단위 코드를 찾지 못한 경우, 구 단위 코드 사용 시도
        # (수원시처럼 구 단위만 있는 경우)
        if not dongcode and dongs:
            logger.info(f"💡 동 단위 코드 없음. 구 단위 코드 사용 시도...")
            # 구 단위 코드가 있는지 확인 (dongs의 키가 구 이름인 경우)
            # 예: "권선구"가 dongs의 키로 있고, 그 안에 code가 있음
            for key, value in dongs.items():
                if isinstance(value, dict) and "code" in value:
                    dongcode = value.get("code")
                    logger.info(f"구 단위 법정동코드 사용: {dongcode} ({region} {district} - {key})")
                    return dongcode
        
        if dongcode:
            logger.info(f"법정동코드 찾음: {dongcode} ({region} {district} {dong})")
            return dongcode
        fallback = _try_road_fallback_dongcode(address)
        if fallback:
            logger.info(f"도로명/키워드 보조 매핑으로 법정동코드 사용: {fallback} (동 데이터 없음)")
            return fallback
        api_code = _get_dongcode_from_juso_api(address)
        if api_code:
            logger.info(f"도로명주소 API로 법정동코드 조회: {api_code} (동 데이터 없음)")
            return api_code
        logger.warning(f"법정동코드를 찾을 수 없음: {region} {district} {dong}")
        return None
    
    def get_complex_list(self, dongcode: str, property_type_hint: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        법정동코드로 단지 목록 조회
        
        Args:
            dongcode: 법정동코드 (10자리)
            property_type_hint: 주소 기반 유형 힌트 ("오피스텔" 등). 오피스텔이면 유형 2도 조회하여 병합
        
        Returns:
            단지 목록 리스트
        """
        url = f"{self.base_url}/land-price/price/fastPriceInfo"
        # 유형: 1=아파트, 2=오피스텔 (KB API)
        type_codes = ["1"]  # 기본: 아파트
        if property_type_hint and "오피스텔" in property_type_hint:
            type_codes = ["2", "1"]  # 오피스텔 우선, 아파트 fallback
        seen_ids = set()
        merged = []
        for type_code in type_codes:
            params = {
                "법정동코드": dongcode,
                "유형": type_code,
                "거래유형": "0"  # 매매
            }
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=15)
                    response.raise_for_status()
                    data = response.json()
                    complexes = data.get("dataBody", {}).get("data", [])
                    for c in complexes:
                        cid = c.get("단지기본일련번호")
                        if cid is not None and cid not in seen_ids:
                            seen_ids.add(cid)
                            merged.append(c)
                    type_name = "오피스텔" if type_code == "2" else "아파트"
                    print(f"[OK] 단지 목록 조회 성공 (유형:{type_name}): {len(complexes)}개 → 병합:{len(merged)}개")
                    break
                except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                    if attempt < max_retries - 1:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    print(f"[X] 단지 목록 조회 실패(연결 끊김): {e}")
                    break
                except requests.exceptions.RequestException as e:
                    print(f"[X] 단지 목록 조회 실패: {e}")
                    break
                except Exception as e:
                    print(f"[X] 단지 목록 조회 오류: {e}")
                    break
        hscm_added = self._merge_hscm_into_complex_list(merged, seen_ids, dongcode)
        if hscm_added:
            print(f"[OK] hscmList 병합: +{hscm_added}개 → 총 {len(merged)}개")
            logger.info("hscmList 병합: +%d개 (총 %d개)", hscm_added, len(merged))
        return merged
    
    def get_complex_price(self, complex_id: str) -> List[Dict[str, Any]]:
        """
        단지별 상세 시세 조회
        
        Args:
            complex_id: 단지기본일련번호
        
        Returns:
            평형별 시세 리스트
        """
        url = f"{self.base_url}/land-complex/complex/mpriByType"
        params = {
            "단지기본일련번호": complex_id
        }
        try:
            response = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            prices = data.get("dataBody", {}).get("data", [])
            
            print(f"[OK] 단지 시세 조회 성공: {len(prices)}개 타입")
            return prices
            
        except requests.exceptions.RequestException as e:
            print(f"[X] 단지 시세 조회 실패: {e}")
            return []
        except Exception as e:
            print(f"[X] 단지 시세 조회 오류: {e}")
            return []
    
    def get_complex_info(self, complex_id: str) -> Optional[Dict[str, Any]]:
        """
        단지 기본정보 조회 (재건축여부 등)
        
        Args:
            complex_id: 단지기본일련번호
        
        Returns:
            dataBody.data (단지명, 재건축여부, 법정동코드 등) 또는 None
        """
        url = f"{self.base_url}/land-complex/complex/info"
        params = {"단지기본일련번호": complex_id}
        try:
            response = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=15)
            response.raise_for_status()
            data = response.json()
            return data.get("dataBody", {}).get("data")
        except Exception as e:
            logger.debug("get_complex_info 실패: %s", e)
            return None
    
    def find_matching_price(self, prices: List[Dict[str, Any]], area: float, 
                           tolerance: float = 0.0) -> Optional[Dict[str, Any]]:
        """
        면적에 맞는 시세 찾기 (정확히 일치하는 면적만)
        
        Args:
            prices: 평형별 시세 리스트
            area: 전용면적 (m²)
            tolerance: 허용 오차 (m², 기본 0.0 = 정확히 일치만)
        
        Returns:
            정확히 일치하는 시세 정보 또는 None (일치하는 것이 없으면 None)
        """
        logger.debug(f"   면적 매칭 시작: 목표 면적={area}m², 허용 오차={tolerance}m² (정확 매칭), 후보 수={len(prices)}")
        
        if not prices or area <= 0:
            logger.warning(f"⚠️ 면적 매칭 불가: prices={len(prices) if prices else 0}, area={area}")
            return None
        
        best_match = None
        min_diff = float('inf')
        
        for i, price_info in enumerate(prices):
            # 전용면적을 우선적으로 비교 (등기부 면적은 전용면적에 가까움)
            def parse_area(s):
                if not s: return None
                try: return float(str(s).strip())
                except (ValueError, TypeError): return None
            dedicated = parse_area(price_info.get("전용면적", ""))
            supply = parse_area(price_info.get("공급면적") or price_info.get("면적", ""))
            
            if dedicated is None and supply is None:
                logger.debug(f"   [{i+1}] 면적 정보 없음, 스킵")
                continue
            
            # 전용면적을 우선 사용, 없으면 공급면적 사용
            if dedicated is not None:
                used_val, diff, used_key = dedicated, abs(dedicated - area), "전용면적"
            else:
                used_val, diff, used_key = supply, abs(supply - area), "공급면적"
            
            logger.debug(f"   [{i+1}] {used_key}={used_val}m², 차이={diff:.2f}m²")
            
            # 정확히 일치하는 면적만 선택 (부동소수점 오차 고려하여 0.01㎡ 이내)
            if diff <= tolerance + 0.01:  # 부동소수점 오차 허용
                if diff < min_diff:
                    min_diff = diff
                    best_match = price_info
                    logger.debug(f"   정확 매칭 발견: {used_key}={used_val}m² (차이: {diff:.2f}m²)")
        
        if best_match:
            matched_area = best_match.get("전용면적") or best_match.get("공급면적") or best_match.get("면적", "N/A")
            logger.info(f"면적 정확 매칭 성공: {matched_area}m² (차이: {min_diff:.2f}m²)")
        else:
            logger.warning(f"⚠️ 정확히 일치하는 면적 없음: {area}m²")
            logger.debug(f"   사용 가능한 면적: {[p.get('전용면적') or p.get('공급면적') or 'N/A' for p in prices[:10]]}")
        
        return best_match
    
    def get_kb_price(self, address: str, area: float, 
                     complex_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        주소와 면적을 기반으로 KB 시세 조회 (메인 함수)
        
        Args:
            address: 부동산 주소
            area: 전용면적 (m²)
            complex_name: 단지명 (선택사항, 있으면 더 정확한 매칭)
        
        Returns:
            {
                "kb_price": 125000,  # 일반 매매가 (만원 단위)
                "kb_price_min": 120000,  # 하한 매매가 (만원 단위, 없으면 None)
                "kb_price_raw": "125,000만원",
                "kb_price_min_raw": "120,000만원",  # 하한 매매가 문자열 (없으면 None)
                "complex_name": "대치아이파크",
                "area": 84.93,
                "pyeong": 25.7,
                "type": "84A형",
                "dongcode": "1168010100",
                "complex_id": "12345",   # 단지기본일련번호 → kbland.kr/c/{id} 참고 링크용
                "redevelop_stages": [],   # 재건축 단계 (재건축여부=1이고 스크래퍼 성공 시)
                "households": None,       # 세대수 (재건축 단지 스크래핑 시)
                "buildings": None,        # 동수 (재건축 단지 스크래핑 시)
                "redevelop_yn": False,    # 재건축 단지 여부
                "redevelop_error": None,  # 스크래퍼 오류 시 메시지 (선택)
            } 또는 None
        """
        logger.info(f"\n🔍 KB 시세 조회 시작")
        logger.info(f"   주소: {address}")
        logger.info(f"   면적: {area}m²")
        print(f"\n[KB] KB 시세 조회 시작")
        print(f"   주소: {address}")
        print(f"   면적: {area}m²")
        
        # 1. 법정동코드 찾기 (1차: 원본 주소, 없으면 2차: 주소 붙여서 재시도, 예: 안양시 동안구 → 안양시동안구)
        logger.debug("1단계: 법정동코드 찾기 (1차: 원본 주소)")
        dongcode = self.find_dongcode(address)
        if not dongcode:
            address_attached = _make_attached_address(address)
            if address_attached != address:
                logger.info("   1차 실패 → 주소 붙여서 2차 시도: %s", address_attached[:60])
                print("[KB] 1차 실패 → 주소 붙여서 2차 시도 (예: 안양시 동안구 → 안양시동안구)")
                dongcode = self.find_dongcode(address_attached)
                if dongcode:
                    logger.info("✅ 법정동코드 찾음(붙인 주소 2차 시도): %s", dongcode)
        if not dongcode:
            logger.error("❌ 법정동코드를 찾을 수 없어 시세 조회 불가")
            print("[X] 법정동코드를 찾을 수 없어 시세 조회 불가")
            return None

        logger.info(f"✅ 법정동코드: {dongcode}")
        
        # 2. 단지 목록 조회 (오피스텔 주소면 유형 2도 조회하여 병합)
        logger.debug("2단계: 단지 목록 조회")
        property_type_hint = address if "오피스텔" in (address or "") else None
        complexes = self.get_complex_list(dongcode, property_type_hint=property_type_hint)
        if not complexes:
            logger.error("❌ 단지 목록을 찾을 수 없음")
            print("[X] 단지 목록을 찾을 수 없음")
            return None
        
        logger.info(f"✅ 단지 목록 조회 성공: {len(complexes)}개 단지")
        
        # 3. 단지 선택 (단지명 우선, 없으면 동+번지로 매칭 예: 관양동 1588)
        logger.debug("3단계: 단지 선택")
        selected_complex = None
        
        # 주소에서 번지수 추출 (블록/롯트 번호 오매칭 제외)
        lot_number = _extract_lot_number_from_address(address)
        if lot_number:
            logger.debug(f"   주소에서 번지수 추출: {lot_number}")
        
        # 주소에서 동명 추출 (동+번지 매칭용, 예: 관양동 1588)
        parsed_addr = self.parse_address(address)
        dong_name = (parsed_addr.get("dong") or "").strip()
        if dong_name and " " in dong_name:
            # "동안구 관양동" -> "관양동"만 사용 (동 단위, API 주소에 "관양동 1588" 형태로 나옴)
            parts = dong_name.split()
            if parts and parts[-1][-1] in "동읍면":
                dong_name = parts[-1]
        if not dong_name:
            dong_name = ""
        if dong_name and lot_number:
            logger.debug(f"   동+번지 매칭 키: {dong_name} {lot_number}")
        
        if complex_name:
            logger.debug(f"   단지명으로 매칭 시도: {complex_name}")
            # 단지명 매칭 우선순위: 정확 매칭 > 부분 매칭 (앞부분) > 부분 매칭 (뒷부분)
            best_match = None
            best_score = 0
            
            for i, complex in enumerate(complexes):
                complex_name_from_api = complex.get("단지명") or complex.get("name", "")
                complex_address_from_api = complex.get("주소", "")
                logger.debug(f"   [{i+1}] {complex_name_from_api} (주소: {complex_address_from_api})")
                
                # 정확 매칭 (공백·영문 대소문자 무시)
                if _complex_names_equivalent(complex_name, complex_name_from_api):
                    selected_complex = complex
                    logger.info(f"✅ 단지명 정확 매칭: {complex_name_from_api}")
                    print(f"[OK] 단지명 정확 매칭: {complex_name_from_api}")
                    break
                
                # 부분/유사 매칭 점수 (영문·혼합 단지명 포함)
                score = _score_complex_name_similarity(complex_name, complex_name_from_api)
                name_related = score >= 0.5
                if name_related and lot_number and _lot_matches_complex_address(lot_number, complex_address_from_api):
                    score += 0.2
                    logger.debug(f"      번지수 일치 보너스: {lot_number}")
                if (
                    name_related and dong_name and lot_number
                    and dong_name in complex_address_from_api
                    and _lot_matches_complex_address(lot_number, complex_address_from_api)
                ):
                    score += 0.35
                    logger.debug(f"      동+번지 매칭 보너스: {dong_name} {lot_number}")
                # KB 단지 주소 토큰 일치 보너스 (A1블럭1롯트 등)
                addr_tokens = _extract_address_match_tokens(address)
                if name_related and addr_tokens:
                    token_score = _score_address_token_match(addr_tokens, complex_address_from_api)
                    if token_score > 0:
                        score += token_score * 0.3
                        logger.debug(f"      주소 토큰 보너스: {token_score:.2f}")
                
                if score > best_score:
                    best_score = score
                    best_match = complex
                    logger.debug(f"      매칭 발견: {complex_name_from_api} (점수: {score:.2f})")
            
            # 부분 매칭 결과 사용 (영문·알파벳음차 변환 가능 시 임계값 완화)
            has_latinish = bool(re.search(r"[A-Za-z]", complex_name or "")) or (
                _hangul_letter_prefix_to_latin_name(complex_name or "") is not None
            )
            min_partial_score = 0.65 if has_latinish else 0.8
            if not selected_complex and best_match and best_score >= min_partial_score:
                selected_complex = best_match
                complex_name_from_api = selected_complex.get('단지명', '알 수 없음')
                logger.info(f"✅ 단지명 부분 매칭: {complex_name_from_api} (점수: {best_score:.2f})")
                print(f"[OK] 단지명 부분 매칭: {complex_name_from_api}")
        
        # 단지명 없을 때: 주소 토큰(블럭/롯트/지구)으로 단지 선택
        if not selected_complex and not complex_name:
            addr_tokens = _extract_address_match_tokens(address)
            if addr_tokens:
                best_token_match = None
                best_token_score = 0.0
                for complex in complexes:
                    api_addr = (complex.get("주소") or "").strip()
                    api_name = (complex.get("단지명") or complex.get("name") or "").strip()
                    token_score = _score_address_token_match(addr_tokens, api_addr)
                    # 단지명에도 토큰이 있으면 가산
                    if api_name:
                        token_score = max(token_score, _score_address_token_match(addr_tokens, api_name) * 0.9)
                    if token_score > best_token_score:
                        best_token_score = token_score
                        best_token_match = complex
                if best_token_match and best_token_score >= 0.5:
                    selected_complex = best_token_match
                    logger.info(
                        "✅ 주소 토큰 매칭: %s (점수: %.2f)",
                        selected_complex.get("단지명", ""),
                        best_token_score,
                    )
                    print(f"[OK] 주소 토큰 매칭: {selected_complex.get('단지명', '')}")
        
        # 단지명이 없을 때만: 동+번지로 단지 선택 (예: 관양동 1588 직접 검색)
        # 단지명이 있는데도 동+번지를 허용하면 도로명 숫자(예: 지세포1길)로 오매칭될 수 있음
        if not selected_complex and (not complex_name) and dong_name and lot_number:
            for complex in complexes:
                complex_address_from_api = (complex.get("주소") or "").strip()
                if dong_name in complex_address_from_api and _lot_matches_complex_address(lot_number, complex_address_from_api):
                    selected_complex = complex
                    logger.info(f"✅ 동+번지 매칭: {dong_name} {lot_number} → {complex.get('단지명', '')} (주소: {complex_address_from_api})")
                    print(f"[OK] 동+번지 매칭: {dong_name} {lot_number} → {complex.get('단지명', '')}")
                    break
        
        # 단지명/동+번지/주소토큰 매칭 실패 시: 검색-검증 폴백
        if not selected_complex:
            if complex_name:
                logger.warning(f"⚠️ 단지명 '{complex_name}' 매칭 실패. KB 내부 검색 폴백 시도")
                print(f"[!] 단지명 '{complex_name}' fastPriceInfo 매칭 실패 → KB 내부 검색 시도")
                resolved = self.resolve_complex_id_by_search(address=address, complex_name=complex_name, dongcode=dongcode)
                if resolved and resolved.get("complex_id"):
                    selected_complex = {
                        "단지기본일련번호": resolved["complex_id"],
                        "단지명": resolved.get("complex_name") or complex_name,
                        "주소": address,
                    }
                    logger.info("✅ KB 내부 검색으로 complex_id 확정: %s", resolved["complex_id"])
                    print(f"[OK] KB 내부 검색으로 complex_id 확정: {resolved['complex_id']}")
                else:
                    logger.warning(f"⚠️ 단지명 '{complex_name}' 매칭/검색 모두 실패. KB 시세 생략")
                    print(f"[!] 단지명 '{complex_name}' 매칭 실패. KB 시세 없이 다른 정보만 추출합니다.")
                    return None
            elif _extract_address_match_tokens(address):
                logger.warning("⚠️ 단지명 없음 → 주소 토큰으로 KB 내부 검색 시도")
                print("[!] 단지명 없음 → 주소 토큰으로 KB 내부 검색 시도")
                resolved = self.resolve_complex_id_by_search(address=address, complex_name=None, dongcode=dongcode)
                if resolved and resolved.get("complex_id"):
                    selected_complex = {
                        "단지기본일련번호": resolved["complex_id"],
                        "단지명": resolved.get("complex_name") or "",
                        "주소": address,
                    }
                    logger.info("✅ 주소 토큰 KB 내부 검색으로 complex_id 확정: %s", resolved["complex_id"])
                    print(f"[OK] KB 내부 검색으로 complex_id 확정: {resolved['complex_id']}")
            if not selected_complex:
                selected_complex = complexes[0]
                complex_name_from_api = selected_complex.get('단지명', '알 수 없음')
                logger.warning(f"⚠️ 단지명 매칭 실패, 첫 번째 단지 사용: {complex_name_from_api}")
                logger.debug(f"   사용 가능한 단지 목록: {[c.get('단지명', 'N/A') for c in complexes[:5]]}")
                print(f"[!] 단지명 매칭 실패, 첫 번째 단지 사용: {complex_name_from_api}")
        
        # 4. 단지 데이터에서 매매 시세 정보 추출
        # fastPriceInfo API에 매매 배열이 있으면 사용, 없으면 get_complex_price(단지기본일련번호) 호출
        complex_id = selected_complex.get("단지기본일련번호")
        logger.debug("4단계: 매매 시세 정보 추출")
        prices = selected_complex.get("매매", []) or selected_complex.get("매매가", [])
        prices_from_mpri = False
        if not prices and complex_id is not None:
            logger.info("   fastPriceInfo에 매매 없음 → get_complex_price 호출")
            print("[*] 단지 시세 별도 조회 중...")
            prices = self.get_complex_price(str(complex_id))
            prices_from_mpri = True
        if not prices:
            logger.error(f"❌ 해당 단지에 매매 시세 정보가 없음: {selected_complex.get('단지명')}")
            print("[X] 해당 단지에 매매 시세 정보가 없음")
            return None

        logger.info(f"✅ 단지에서 시세 정보 추출: {len(prices)}개 타입")
        logger.debug(f"   시세 타입별 면적: {[p.get('공급면적', 'N/A') for p in prices[:5]]}")
        print(f"[OK] 단지에서 시세 정보 추출: {len(prices)}개 타입")
        
        # 5. 면적에 맞는 시세 찾기
        logger.debug(f"5단계: 면적 매칭 (목표 면적: {area}m²)")
        logger.info(f"   사용 가능한 시세 면적: {[p.get('공급면적', 'N/A') for p in prices[:10]]}")
        matched_price = self.find_matching_price(prices, area)
        # 면적 미제공(0)이면 해당 단지의 첫 번째 시세 타입을 폴백으로 사용
        if not matched_price and area <= 0 and prices:
            matched_price = prices[0]
            logger.warning(f"⚠️ 면적 미제공(0) → 해당 단지 첫 번째 타입 적용: {matched_price.get('공급면적', 'N/A')}㎡ 등")
            print(f"[!] 면적 미제공 → 해당 단지 첫 번째 시세 타입 적용")
        # 정확 매칭 없으면 가장 가까운 면적 타입 사용 (예: 37.85㎡ 요청 시 51.46㎡ 등 가장 가까운 타입)
        if not matched_price and area > 0 and prices:
            def _area_val(p):
                v = p.get("전용면적") or p.get("공급면적") or p.get("면적")
                try:
                    return float(str(v).replace(",", "").strip()) if v is not None else None
                except (ValueError, TypeError):
                    return None
            nearest = None
            min_diff = float("inf")
            for p in prices:
                v = _area_val(p)
                if v is not None and 10 <= v <= 300:
                    d = abs(v - area)
                    if d < min_diff:
                        min_diff = d
                        nearest = p
            if nearest:
                matched_price = nearest
                near_area = _area_val(nearest)
                logger.warning(f"⚠️ {area}m²와 동일 타입 없음 → 가장 가까운 면적 적용: {near_area}m² (차이: {min_diff:.1f}m²)")
                print(f"[!] {area}m² 동일 타입 없음 → 가장 가까운 면적 {near_area}m² 적용")
        if not matched_price:
            logger.error(f"❌ 면적 {area}m²에 맞는 시세를 찾을 수 없음")
            print(f"[X] 면적 {area}m²에 맞는 시세를 찾을 수 없음")
            if prices:
                logger.warning(f"⚠️ 사용 가능한 면적: {[p.get('공급면적', 'N/A') for p in prices[:10]]}")
                print(f"[!] 사용 가능한 면적: {[p.get('공급면적', 'N/A') for p in prices[:10]]}")
            return None

        # 6. 결과 구성
        logger.debug("6단계: 결과 구성")
        # 실제 API 응답에서는 "일반평균" 필드에 일반 매매가, "하위평균"에 하한 매매가가 있음
        price_value = matched_price.get("일반평균") or matched_price.get("매매일반거래가") or matched_price.get("매매가") or matched_price.get("매매평균가")
        price_min_value = matched_price.get("하위평균") or matched_price.get("매매하한가")
        
        logger.debug(f"   일반 매매가 필드: {price_value}")
        logger.debug(f"   하한 매매가 필드: {price_min_value}")
        logger.debug(f"   매칭된 시세 데이터 키: {list(matched_price.keys())}")
        
        if not price_value:
            logger.warning(f"⚠️ 시세 가격 정보가 없음(단지 식별 정보만 반환). 매칭된 데이터: {matched_price}")
            print("[!] 시세 가격 정보 없음 → 단지 식별 정보만 반환")
        
        # 가격을 숫자로 변환 (만원 단위)
        def parse_price(value):
            if not value:
                return None
            try:
                if isinstance(value, str):
                    value = value.replace(",", "").replace("만원", "").strip()
                return float(value)
            except (ValueError, TypeError):
                return None
        
        price_num = parse_price(price_value)
        price_min_num = parse_price(price_min_value)
        # KB에서 시세 미제공 단지는 0으로 내려오기도 함 (시세없음 처리)
        if price_num is not None and price_num <= 0:
            price_num = None
        if price_min_num is not None and price_min_num <= 0:
            price_min_num = None
        
        # 매칭된 면적과 원본 면적의 차이 계산
        matched_area_val = float(matched_price.get("전용면적") or matched_price.get("공급면적") or matched_price.get("면적") or area)
        area_diff = abs(matched_area_val - area)
        
        # 평수 계산 (전용면적을 평수로 변환: 1평 = 3.3058m²)
        pyeong_value = matched_price.get("전용면적") or matched_price.get("공급면적") or area
        try:
            pyeong_float = float(pyeong_value) / 3.3058
            pyeong_str = f"{pyeong_float:.1f}"
        except:
            pyeong_str = matched_price.get("공급면적평N") or matched_price.get("평수", "")
        
        result = {
            "kb_price": price_num,  # 일반 매매가 (만원 단위)
            "kb_price_min": price_min_num,  # 하한 매매가 (만원 단위, 없으면 None)
            "kb_price_raw": f"{price_num:,.0f}만원" if price_num is not None else None,
            "kb_price_min_raw": f"{price_min_num:,.0f}만원" if price_min_num else None,
            "complex_name": selected_complex.get("단지명") or selected_complex.get("name", "알 수 없음"),
            "area": matched_area_val,  # 매칭된 면적
            "area_requested": area,  # 요청한 면적 (등기부 면적)
            "area_diff": area_diff,  # 면적 차이 (m²)
            "pyeong": pyeong_str,
            "type": matched_price.get("주택형타입내용") or matched_price.get("타입", ""),
            "dongcode": dongcode,
            "complex_id": str(complex_id) if complex_id is not None else None,  # 단지기본일련번호 → kbland.kr/c/{id}
        }
        
        # 7. 재건축·세대수·사용승인일: 단지 목록 → get_complex_info → /c/ 스크래퍼 순으로 채우기
        result["redevelop_stages"] = []
        result["households"] = None
        result["buildings"] = None
        result["approval_date"] = None   # 사용승인일 YYYY.MM.DD (기본정보)
        result["years_since_completion"] = None  # N년차 (기본정보)
        result["complex_type"] = None  # 주상복합, 아파트, 오피스텔 등
        result["redevelop_yn"] = False
        # fastPriceInfo 단지 항목에 세대수/동수 필드가 있으면 우선 사용
        for key in ("세대수", "총세대수", "총호수", "호수"):
            val = selected_complex.get(key)
            if val is not None and str(val).strip() != "":
                try:
                    result["households"] = int(float(str(val).replace(",", "")))
                    break
                except (ValueError, TypeError):
                    pass
        for key in ("동수", "총동수", "개동"):
            val = selected_complex.get(key)
            if val is not None and str(val).strip() != "":
                try:
                    result["buildings"] = int(float(str(val).replace(",", "")))
                    break
                except (ValueError, TypeError):
                    pass
        if complex_id is not None:
            info = self.get_complex_info(str(complex_id))
            redevelop_flag = (info or {}).get("재건축여부")
            if str(redevelop_flag) == "1":
                result["redevelop_yn"] = True
            # API 응답에서 세대수/동수 필드 시도 (KB API 필드명이 있을 수 있음)
            if info:
                for key in ("세대수", "총세대수", "총호수", "호수"):
                    val = info.get(key)
                    if val is not None and str(val).strip() != "":
                        try:
                            result["households"] = int(float(str(val).replace(",", "")))
                            logger.info(f"✅ API에서 세대수 추출: {result['households']} (필드: {key})")
                            break
                        except (ValueError, TypeError):
                            pass
                for key in ("동수", "총동수", "개동"):
                    val = info.get(key)
                    if val is not None and str(val).strip() != "":
                        try:
                            result["buildings"] = int(float(str(val).replace(",", "")))
                            logger.info(f"✅ API에서 동수 추출: {result['buildings']} (필드: {key})")
                            break
                        except (ValueError, TypeError):
                            pass
            # 세대수는 스크래핑에서 우선 가져오기 (API는 fallback)
            # /c/ 스크래퍼: 재건축이면 단계+세대수·동수, 일반 단지면 세대수·동수·사용승인일
            extra = get_complex_extra_info(complex_id)
            if extra.get("approval_date") is not None:
                result["approval_date"] = extra["approval_date"]
                logger.info(f"✅ 스크래퍼(기본정보)에서 사용승인일 추출: {result['approval_date']}")
            if extra.get("years_since_completion") is not None:
                result["years_since_completion"] = extra["years_since_completion"]
                logger.info(f"✅ 스크래퍼(기본정보)에서 년차 추출: {result['years_since_completion']}년차")
            # 단지유형 (주상복합, 아파트, 오피스텔 등)
            if extra.get("complex_type") is not None:
                result["complex_type"] = extra["complex_type"]
                logger.info(f"✅ 스크래퍼에서 단지유형 추출: {result['complex_type']}")
            # 스크래퍼에서 재건축 단계를 찾으면 재건축으로 간주 (API 재건축여부 없어도)
            if extra.get("redevelop_yn") or (extra.get("redevelop_stages") and len(extra["redevelop_stages"]) > 0):
                result["redevelop_yn"] = True
            # 세대수/동수는 스크래핑 우선 (API는 fallback)
            if extra.get("households") is not None:
                result["households"] = extra["households"]
                logger.info(f"✅ 스크래퍼에서 세대수 추출: {result['households']}세대")
            elif result["households"] is None and complex_id is not None:
                # 스크래핑 실패 시 API fallback
                mpri_prices = prices if prices_from_mpri else self.get_complex_price(str(complex_id))
                if mpri_prices:
                    h_sum = sum(int(p.get("세대수") or 0) for p in mpri_prices)
                    if h_sum > 0:
                        result["households"] = h_sum
                        logger.info(f"✅ mpriByType API 세대수 합산 (fallback): {result['households']}")
            
            if extra.get("buildings") is not None:
                result["buildings"] = extra["buildings"]
                logger.info(f"✅ 스크래퍼에서 동수 추출: {result['buildings']}개동")
            
            if result["redevelop_yn"]:
                result["redevelop_stages"] = extra.get("redevelop_stages") or []
                logger.info(f"✅ 재건축 단계: {len(result['redevelop_stages'])}개")
                if extra.get("error"):
                    result["redevelop_error"] = extra["error"]
            else:
                # 일반 단지: 기본정보(스크래퍼) 세대수·동수를 API보다 우선 사용
                # API는 분양/매매 세대만(618) 반환하는 경우가 있어, 기본정보 "783세대(임대165)" 총 세대수를 사용
                if extra.get("households") is not None:
                    result["households"] = extra["households"]
                    logger.info(f"✅ 스크래퍼(기본정보)에서 세대수 추출: {result['households']}")
                elif result["households"] is None:
                    pass  # API에서만 채우기 (이미 위에서 시도함)
                if extra.get("buildings") is not None:
                    result["buildings"] = extra["buildings"]
                    logger.info(f"✅ 스크래퍼에서 동수 추출: {result['buildings']}")
                elif result["buildings"] is None:
                    pass
        
        if result["kb_price"] is not None:
            price_info = f"{result['kb_price']:,.0f}만원"
            if price_min_num:
                price_info += f" (하한: {price_min_num:,.0f}만원)"
        else:
            price_info = "시세없음"
        
        # 면적 차이 경고
        if area_diff and area_diff > 5.0:
            logger.warning(f"[!] 면적 차이: {area_diff:.2f}m² (요청: {area}m², 매칭: {matched_area_val}m²)")
            print(f"[!] 면적 차이: {area_diff:.2f}m² (요청: {area}m², 매칭: {matched_area_val}m²)")
        
        logger.info(f"✅ KB 시세 조회 완료: {price_info} ({result['complex_name']})")
        logger.debug(f"   최종 결과: {result}")
        if result["kb_price"] is not None:
            print(f"[OK] KB 시세 조회 완료: {price_info} ({result['complex_name']})")
        else:
            print(f"[OK] KB 단지 식별 완료(시세없음): {result['complex_name']} / id={result.get('complex_id')}")
        return result


def get_kb_price_from_registry(address: str, area: str) -> Optional[Dict[str, Any]]:
    """
    등기부 정보로 KB 시세 조회 (편의 함수)
    
    Args:
        address: 등기부에서 추출한 주소
        area: 등기부에서 추출한 면적 (문자열, 예: "84.93㎡" 또는 "84.93")
    
    Returns:
        KB 시세 정보 딕셔너리 또는 None
    """
    logger.info(f"📄 등기부 정보로 KB 시세 조회 시작")
    logger.info(f"   등기부 주소: {address}")
    logger.info(f"   등기부 면적: {area}")
    
    # 면적 파싱: "51㎡/37.85㎡" 또는 "51/37.85" → 전용면적(두 번째) 사용, KB 시세는 전용면적 기준
    area_str = str(area).strip()
    area_float = None
    slash_match = re.search(r'(\d+\.?\d*)\s*[㎡m²]?\s*/\s*(\d+\.?\d*)\s*[㎡m²]?', area_str, re.IGNORECASE)
    if slash_match:
        try:
            first_num = float(slash_match.group(1))
            second_num = float(slash_match.group(2))
            # 두 번째가 전용면적(보통 더 작음), 10~300 범위면 사용
            if 10 <= second_num <= 300:
                area_float = second_num
                logger.info(f"   공급/전용 면적에서 전용면적 사용: {second_num}m² (공급: {first_num}m²)")
            elif 10 <= first_num <= 300:
                area_float = first_num
        except ValueError:
            pass
    if area_float is None:
        area_match = re.search(r'([\d.]+)', area_str)
        if area_match:
            try:
                area_float = float(area_match.group(1))
                if not (10 <= area_float <= 300):
                    area_float = None
            except ValueError:
                pass
    if area_float is None:
        logger.error(f"⚠️ 면적 파싱 실패: {area}")
        print(f"[!] 면적 파싱 실패: {area}")
        return None
    logger.debug(f"   추출된 면적(전용): {area_float}m²")
    
    # 주소에서 단지명 추출 (예: "미리내마을", "천안역우방아이유쉘", "힐스테이트 리버시티 1단지")
    complex_name = _extract_complex_name_from_address(address)
    if complex_name:
        logger.info(f"✅ 주소에서 단지명 추출 (띄어쓰기/브랜드): {complex_name}")

    # 브랜드 접미사: 브랜드 뒤 한글(클라시스 등)까지 포함. 짧은 1글자 접미(디/엘/리)는 제외해 과매칭 방지
    _brand_alt = "|".join(
        re.escape(b)
        for b in _COMPLEX_BRAND_SUFFIXES
        if len(b) >= 2 and b not in ("뉴", "더", "디", "엘", "리", "꿈")
    )
    complex_patterns = [
        r'([가-힣A-Za-z0-9]+(?:\s+[가-힣A-Za-z0-9]+){0,3}\s*\d*\s*(?:단지|타운|빌리지|시티|아파트|오피스텔))',
        r'((?:e|E)[\s\-]?편한세상\s*[가-힣A-Za-z0-9]+)',
        r'((?:THE|the)\s+[가-힣A-Za-z0-9]+(?:\s+[가-힣A-Za-z0-9]+)*)',
        r'([가-힣]+)오피스텔',   # 성우아뜨리움오피스텔 → 성우아뜨리움 (KB: 성우아뜨리움)
        r'([가-힣]+)아파트',    # 성우아파트 → 성우
        r'([가-힣]+)빌라',      # OO빌라 → OO
        r'([가-힣]+)다가구',    # OO다가구 또는 다가구
        r'([가-힣]+마을)',
        r'([가-힣]+단지)',
        r'([가-힣]+(?:힐스|힐스테이트)[가-힣]*)',
        # 디엠씨래미안클라시스처럼 브랜드 앞·뒤 한글까지 한 덩어리로 추출
        rf'([가-힣A-Za-z0-9]*(?:{_brand_alt})[가-힣A-Za-z0-9]*)',
    ]
    for pattern in complex_patterns:
        if complex_name:
            break
        match = re.search(pattern, address)
        if match:
            candidate = _clean_extracted_complex_name(match.group(1).strip())
            if _is_invalid_complex_name(candidate):
                logger.debug(f"단지명 후보 제외(행정구역 오탐): {candidate}")
                continue
            complex_name = _clean_extracted_complex_name(candidate)
            logger.info(f"✅ 주소에서 단지명 추출: {complex_name}")
            break
    
    # 필지 + 단지명 (1314외 3필지 성우아뜨리움오피스텔 제2층)
    if not complex_name:
        lot_name_pattern = r'(?:필지|외)\s+([가-힣]+?)(?=\s+제\d+동|\s+제\d+층|\s+제\d+호|$)'
        match = re.search(lot_name_pattern, address)
        if match:
            potential_name = match.group(1).strip()
            if len(potential_name) >= 2 and potential_name not in ('동', '구', '시', '군', '읍', '면', '필지'):
                complex_name = potential_name
                # 접미사 제거 (KB는 "성우아뜨리움" 형태로 표기)
                for suffix in ('오피스텔', '아파트', '빌라', '다가구'):
                    if complex_name.endswith(suffix):
                        complex_name = complex_name[:-len(suffix)]
                        break
                if len(complex_name) >= 2 and not _is_invalid_complex_name(complex_name):
                    logger.info(f"✅ 주소에서 단지명 추출 (필지+이름): {complex_name}")
                else:
                    complex_name = None
    
    # 번지수 + 한글 단지명 (제N동/제N층/제N호 앞까지) ex: "1562 천안역우방아이유쉘 제104동"
    if not complex_name:
        lot_name_pattern = r'\d+(?:-\d+)?\s+([가-힣]+?)(?=\s+제\d+동|\s+제\d+층|\s+제\d+호|$)'
        match = re.search(lot_name_pattern, address)
        if match:
            potential_name = match.group(1).strip()
            if len(potential_name) >= 2 and potential_name not in ('동', '구', '시', '군', '읍', '면'):
                if not _is_invalid_complex_name(potential_name):
                    complex_name = potential_name
                    logger.info(f"✅ 주소에서 단지명 추출 (번지+이름): {complex_name}")
    
    # 기존: 번지수 + (마을|단지|아파트) ex: "1180-1 미리내마을"
    if not complex_name:
        lot_pattern = r'(\d+(?:-\d+)?)\s+([가-힣]+(?:마을|단지|아파트)?)'
        match = re.search(lot_pattern, address)
        if match:
            potential_name = match.group(2)
            if len(potential_name) >= 2 and potential_name not in ('동', '구', '시', '군', '읍', '면'):
                if not _is_invalid_complex_name(potential_name):
                    complex_name = potential_name
                    logger.info(f"✅ 주소에서 단지명 추출 (번지수 기준): {complex_name}")
    
    # KB 시세 조회
    api = KBPriceAPI()
    return api.get_kb_price(address, area_float, complex_name=complex_name)
