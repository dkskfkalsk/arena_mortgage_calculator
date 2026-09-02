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

# 빌라·다세대 빠른시세(AI시세)는 api.kbland.kr 가 아니라 data-api 허브에 있다.
_DATA_API_BASE = "https://data-api.kbland.kr"

# KB API 요청 시 브라우저로 보이도록 (User-Agent 미설정 시 연결 끊김 발생 가능)
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Cache-Control": "no-cache",
    "Origin": "https://kbland.kr",
    "Referer": "https://kbland.kr/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# KB 조회는 한 건에 4~8회 요청이 나가는데, 매번 새 연결을 맺으면 요청당 TLS 핸드셰이크에
# 250ms 이상을 쓴다. Session으로 커넥션을 재사용하면 은마 기준 3.3초 → 1.0초.
_SESSION = requests.Session()
_SESSION.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=8))

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
_HO_FROM_ADDRESS_RE = re.compile(r"제\s*(\d{1,4})\s*호|(?:^|[^\d])(\d{1,4})\s*호(?:\s|$)")
_FLOOR_FROM_ADDRESS_RE = re.compile(r"제\s*(\d{1,3})\s*층|(?:^|[^\d])(\d{1,3})\s*층")
# kbland 검색창 autoKywrSerch 파라미터 (웹 JS 번들과 동일)
_KB_AUTO_KYWR_COLLECTION = (
    "COL_AT_JUSO:100;COL_AT_SCHOOL:100;COL_AT_SUBWAY:100;COL_AT_HSCM:100;COL_AT_VILLA:100"
)

# kbland 검색 엔진(intgraSerch/autoKywrSerch) 서킷 브레이커.
# 이 엔진은 rc=33500 "throw error"로 전면 장애가 나는 경우가 있는데, 폴백 검색은
# 키워드 조합마다 호출하므로 장애 시 한 건당 十수 회를 헛돌며 응답이 수 초씩 늘어난다.
# 연속 실패가 임계치를 넘으면 쿨다운 동안 호출을 건너뛴다 (성공 시 즉시 복구).
_KB_SEARCH_FAIL_THRESHOLD = 2
_KB_SEARCH_COOLDOWN_SEC = 300
_KB_SEARCH_TIMEOUT_SEC = 6
_KB_SEARCH_STATE: Dict[str, float] = {"fails": 0.0, "disabled_until": 0.0}

# KB '동일시세 전용면적'(BasePrcInfoNew의 기타전용면적) 캐시. 타입별로 1회씩 호출하므로
# 타입이 많은 단지에서 호출이 불어나는 것을 막는다.
_SAME_PRICE_AREA_CACHE: Dict[Tuple[str, str], List[str]] = {}
_SAME_PRICE_AREA_MAX_LOOKUP = 8


def _kb_search_available() -> bool:
    """검색 엔진 호출 가능 여부 (쿨다운 중이면 False)."""
    until = _KB_SEARCH_STATE.get("disabled_until", 0.0)
    if until and time.time() < until:
        return False
    if until:
        # 쿨다운 종료 → 재시도 허용
        _KB_SEARCH_STATE["disabled_until"] = 0.0
        _KB_SEARCH_STATE["fails"] = 0.0
    return True


def _kb_search_note_failure(reason: str) -> None:
    _KB_SEARCH_STATE["fails"] = _KB_SEARCH_STATE.get("fails", 0.0) + 1
    if _KB_SEARCH_STATE["fails"] >= _KB_SEARCH_FAIL_THRESHOLD:
        _KB_SEARCH_STATE["disabled_until"] = time.time() + _KB_SEARCH_COOLDOWN_SEC
        logger.warning(
            "KB 검색 엔진 연속 실패(%s) → %d초간 검색 폴백 건너뜀",
            reason, _KB_SEARCH_COOLDOWN_SEC,
        )
        print(f"[!] KB 검색 엔진 장애({reason}) → {_KB_SEARCH_COOLDOWN_SEC}초간 검색 폴백 생략")


def _kb_search_note_success() -> None:
    if _KB_SEARCH_STATE.get("fails"):
        _KB_SEARCH_STATE["fails"] = 0.0
    _KB_SEARCH_STATE["disabled_until"] = 0.0


# 등기부 건물내역에 "오피스텔"이라는 단어가 없어도 업무시설/숙박시설(주로 오피스텔)이면
# KB 유형=2(오피스텔) 목록도 함께 조회하기 위한 키워드
_OFFICETEL_BUILDING_USE_KEYWORDS = ("업무시설", "숙박시설")


def _text_indicates_officetel(text: Optional[str]) -> bool:
    """주소·등기부 원문에 '오피스텔' 또는 업무시설/숙박시설 용도가 있으면 True."""
    if not text:
        return False
    if "오피스텔" in text:
        return True
    return any(kw in text for kw in _OFFICETEL_BUILDING_USE_KEYWORDS)


def _text_indicates_villa_or_multi(text: Optional[str]) -> bool:
    """등기 건물내역·주소가 다세대·연립·빌라면 True. 아파트 단지는 제외."""
    if not text:
        return False
    compact = re.sub(r"\s+", "", text)
    if "아파트" in compact and "다세대" not in compact and "연립" not in compact:
        return False
    return any(kw in compact for kw in ("다세대", "연립주택", "연립/다세대", "빌라"))


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


def _extract_registry_building_dong(address: str) -> Optional[str]:
    """등기부 주소의 제N동 건물동 번호 (예: 제200동 → '200')."""
    if not address:
        return None
    m = re.search(r"제(\d{2,4})동", address)
    return m.group(1) if m else None


def _complex_name_has_building_dong_label(api_name: str, building_dong: str) -> bool:
    """
    KB 단지명에 건물동 번호가 단지 식별자로 붙어 있는지.
    예) 개포현대(200동), 개포현대200동 — 일반 101동·102동 대단지와 구분.
    """
    if not api_name or not building_dong:
        return False
    norm = re.sub(r"\s+", "", api_name)
    patterns = (
        rf"\({building_dong}동\)",
        rf"\({building_dong}\)",
        rf"{building_dong}동(?:\)|$)",
    )
    return any(re.search(p, norm) for p in patterns)


def _expand_complex_name_search_variants(
    name: str, address: Optional[str] = None
) -> List[str]:
    """검색용 단지명 후보: 원문 + 알파벳 음차 변환본 + (가능 시) 한글 꼬리 + 제N동 변형."""
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
    building_dong = _extract_registry_building_dong(address or "")
    if building_dong:
        base = _strip_complex_name_decorations(raw) or raw
        for fmt in (
            f"{base}({building_dong}동)",
            f"{base}{building_dong}동",
            f"{base} {building_dong}동",
        ):
            if fmt and fmt not in variants:
                variants.append(fmt)
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


def _strip_complex_name_decorations(name: str) -> str:
    """
    단지명 장식 제거 → 코어명.
    예) 대림아파트 → 대림, 대림(1차) → 대림, 힐스테이트리버시티1단지 → 힐스테이트리버시티
    """
    s = re.sub(r"[\s\-_·&]+", "", (name or "").strip())
    if not s:
        return s
    # (1차) (제2차) 등
    s = re.sub(r"\((?:제)?\d+차\)", "", s)
    s = re.sub(r"[()\[\]{}]", "", s)
    # 끝의 1차/2차/1단지
    s = re.sub(r"(?:제)?\d+차$", "", s)
    s = re.sub(r"\d+단지$", "", s)
    for suf in (
        "아파트형공장",
        "도시형생활주택",
        "오피스텔",
        "아파트",
        "연립주택",
        "다세대",
        "빌라",
        "연립",
    ):
        if s.endswith(suf) and len(s) - len(suf) >= 2:
            s = s[: -len(suf)]
            break
    return s


def _complex_name_core(name: str) -> str:
    """매칭용 코어 단지명 (장식 제거 + 알파벳 음차 정규화)."""
    s = _strip_complex_name_decorations(name)
    if not s:
        return ""
    converted = _hangul_letter_prefix_to_latin_name(s)
    if converted:
        s = converted
    if re.search(r"[A-Za-z]", s):
        return s.lower()
    return s


def _normalize_kb_complex_name_for_match(name: str) -> str:
    """단지명 매칭용: 장식 제거·알파벳 음차→영문·영문 소문자."""
    return _complex_name_core(name)


# 포함 관계 remainder가 이 패턴이면 같은 단지 장식(1차, 200동)으로 본다.
_SAFE_NAME_REMAINDER_RE = re.compile(r"^(?:제)?\d+(?:차|단지|동)?$")


def _is_safe_name_containment(shorter: str, longer: str) -> bool:
    """
    shorter ⊂ longer를 같은 단지로 볼 수 있는지.
    remainder가 1차/200동 같은 장식일 때만 True.
    '꿈마을' ⊂ '꿈마을동아'처럼 시공사명이 붙으면 False.
    """
    if not shorter or not longer:
        return False
    if shorter == longer:
        return True
    if shorter not in longer:
        return False
    remainder = re.sub(r"[\s,·_\-]+", "", longer.replace(shorter, "", 1))
    if not remainder:
        return True
    return bool(_SAFE_NAME_REMAINDER_RE.fullmatch(remainder))


def _complex_names_equivalent(a: str, b: str) -> bool:
    """단지명 동일 여부 (띄어쓰기·영문·알파벳 음차·아파트/(N차) 장식 무시). 시공사명 형제는 False."""
    na = _normalize_kb_complex_name_for_match(a)
    nb = _normalize_kb_complex_name_for_match(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if _is_safe_name_containment(na, nb) or _is_safe_name_containment(nb, na):
        return True
    # 숫자+단지 변형: 리버시티1단지 vs 리버시티 (장식 제거 후에도 남을 경우)
    base_a = re.sub(r"\d+단지$", "", na)
    base_b = re.sub(r"\d+단지$", "", nb)
    if base_a and base_b:
        if base_a == base_b or _is_safe_name_containment(base_a, base_b) or _is_safe_name_containment(base_b, base_a):
            return True
    # 공통 한글 꼬리 (충분히 길 때만) — 양쪽 모두 영문/음차 접두가 있을 때
    tail_a = _complex_name_hangul_tail(a)
    tail_b = _complex_name_hangul_tail(b)
    if tail_a and tail_b and len(tail_a) >= 4 and len(tail_b) >= 4:
        if tail_a == tail_b or _is_safe_name_containment(tail_a, tail_b) or _is_safe_name_containment(tail_b, tail_a):
            la, _ = _parse_hangul_letter_prefix(a)
            lb, _ = _parse_hangul_letter_prefix(b)
            if (la and len(la) >= 2) and (lb and len(lb) >= 2):
                return True
    return False


def _complex_names_related(a: str, b: str) -> bool:
    """시공사만 다른 형제 단지 후보 (꿈마을 vs 꿈마을(동아)). 확정은 번지/면적으로."""
    if _complex_names_equivalent(a, b):
        return True
    na = _normalize_kb_complex_name_for_match(a)
    nb = _normalize_kb_complex_name_for_match(b)
    if not na or not nb or min(len(na), len(nb)) < 3:
        return False
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return shorter in longer


def _complex_names_core_equal(a: str, b: str) -> bool:
    """코어명 완전 일치 (대림아파트 ↔ 대림(1차)). 부분문자열 아님."""
    ca = _complex_name_core(a)
    cb = _complex_name_core(b)
    return bool(ca and cb and len(ca) >= 2 and ca == cb)


def _score_complex_name_similarity(target: str, api_name: str) -> float:
    """단지명 유사도 0~1 (영문·혼합·알파벳 음차·공통 한글 꼬리)"""
    if _complex_names_equivalent(target, api_name):
        return 1.0
    nt = _normalize_kb_complex_name_for_match(target)
    na = _normalize_kb_complex_name_for_match(api_name)
    if not nt or not na:
        return 0.0
    if nt in na:
        ratio = len(nt) / max(len(na), 1)
        # 시공사 형제(꿈마을 ⊂ 꿈마을동아)는 부분매칭 임계(0.8) 아래로 묶어 단독 확정하지 않음
        if _is_safe_name_containment(nt, na):
            return min(0.95, ratio)
        return min(0.72, ratio)
    if na in nt:
        ratio = len(na) / max(len(nt), 1)
        if _is_safe_name_containment(na, nt):
            return min(0.95, ratio)
        return min(0.72, ratio)

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
    """추출된 단지명 후처리: 동번호·행정구역·번지 오탐 제거"""
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
    # 해운대구좌동1396대림아파트 → 대림아파트
    # ※ '시' 단독 접미 제거 금지 (클라시스 → 스 오절단)
    s = re.sub(r"^(?:[가-힣]+구)", "", s)
    s = re.sub(r"^(?:[가-힣]+군)", "", s)
    s = re.sub(r"^[가-힣]+동", "", s)
    s = re.sub(r"^\d+(?:-\d+)?", "", s)
    s = re.sub(r"^(?:[가-힣]+구)", "", s)
    s = re.sub(r"^[가-힣]+동", "", s)
    s = re.sub(r"^\d+(?:-\d+)?", "", s)
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

    # 번지 뒤 띄어쓰기 단지명: "606 송파 레이크힐 제1501동"
    # 접미사(아파트/단지)가 없으면 기존 패턴이 '송파'만 잘라 KB 매칭이 실패한다.
    m = re.search(
        r"\d+(?:-\d+)?\s+([가-힣]+(?:\s+[가-힣]+)+)\s*(?=제\s*\d+(?:동|층|호)|$)",
        address,
    )
    if m:
        raw = m.group(1).strip()
        if not re.search(r"(?:구역|사업|블럭|블록|롯트|필지)", raw):
            candidate = _clean_extracted_complex_name(raw)
            if len(candidate) >= 4 and not _is_invalid_complex_name(candidate):
                return candidate

    return None


def _extract_eup_myeon_from_address(address: str) -> Optional[str]:
    """주소에서 읍/면 이름 추출 (예: '남양주시 별내면 청학리 419' → '별내면')."""
    if not address:
        return None
    m = re.search(r"(?:시|군|구)\s+([가-힣]+(?:읍|면))(?:\s|$)", address)
    return m.group(1) if m else None


def _strip_admin_prefix_for_complex_name(address: str) -> str:
    """
    단지명 추출용: 읍/면/리 주소에서 단지명 앞의 행정구역·지번을 잘라낸다.

    등기부는 '별내면 청학리 419 청학주공아파트'처럼 리(里)와 번지가 단지명 앞에 붙는데,
    단지명 추출 패턴이 이를 통째로 잡아 '별내면청학리419청학주공아파트'가 되어 매칭에 실패한다.
    읍/면이 없는 동 단위 주소는 원본을 그대로 반환하므로 기존 동작에 영향이 없다.
    """
    addr = re.sub(r"\s+", " ", (address or "").strip())
    if not addr:
        return addr
    patterns = (
        r"[가-힣]+(?:읍|면)\s+[가-힣]+리\s+\d+(?:-\d+)?(?:\s*외\s*\d+\s*필지)?\s+(?=\S)",  # 면+리+지번
        r"[가-힣]+(?:읍|면)\s+[가-힣0-9]+(?:로|길)\s+\d+(?:-\d+)?,?\s+(?=\S)",  # 면+도로명+건물번호
        r"[가-힣]+(?:읍|면)\s+\d+(?:-\d+)?(?:\s*외\s*\d+\s*필지)?\s+(?=\S)",  # 면+지번 (리 생략)
    )
    for pattern in patterns:
        m = re.search(pattern, addr)
        if m:
            rest = addr[m.end():].strip()
            if len(rest) >= 2:
                return rest
    return addr


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


def _extract_kbland_complex_id(text: Optional[str]) -> Optional[str]:
    """캡션·등기 원문의 kbland.kr/c/{id} 단지 ID."""
    if not text:
        return None
    m = _KBLAND_COMPLEX_PATH_RE.search(text)
    return m.group(1) if m else None


def _extract_ho_name_from_address(address: str) -> Optional[str]:
    """등기 주소에서 호수 (제301호, 301호)."""
    if not address:
        return None
    m = _HO_FROM_ADDRESS_RE.search(address)
    if not m:
        return None
    return (m.group(1) or m.group(2) or "").lstrip("0") or (m.group(1) or m.group(2))


def _extract_floor_from_address(address: str) -> Optional[int]:
    """등기 주소에서 층 (제3층, 3층)."""
    if not address:
        return None
    m = _FLOOR_FROM_ADDRESS_RE.search(address)
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _normalize_ho_name(ho_name: Any) -> str:
    digits = re.sub(r"\D", "", str(ho_name or ""))
    if not digits:
        return ""
    stripped = digits.lstrip("0")
    return stripped or digits


def _ho_matches_floor(ho_name: Any, floor: Optional[int]) -> bool:
    """301호 → 3층처럼 호수의 백의 자리가 층과 같은지."""
    if floor is None:
        return False
    digits = re.sub(r"\D", "", str(ho_name or ""))
    if len(digits) < 3:
        return False
    try:
        return int(digits) // 100 == int(floor)
    except (TypeError, ValueError):
        return False


def _parse_sale_price_man(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").replace("만원", "").strip()
        num = float(value)
        return num if num > 0 else None
    except (TypeError, ValueError):
        return None


def _kb_data_api_get(path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """kbland data-api GET. 성공 시 dataBody.data, 실패 시 None."""
    try:
        response = _SESSION.get(
            f"{_DATA_API_BASE}{path}",
            params=params or {},
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        body = response.json() or {}
        data_body = body.get("dataBody") or {}
        return data_body.get("data")
    except Exception as e:
        logger.debug("data-api GET %s 실패: %s", path, e)
        return None


def _extract_road_name_and_number(address: str) -> Optional[Tuple[str, str]]:
    """도로명+건물번호 추출 (예: 언주로 105, 선릉로18길 12)."""
    if not address:
        return None
    m = re.search(
        r"([가-힣]+(?:로|길)(?:\d+길)?)\s*(\d+(?:-\d+)?)",
        address,
    )
    if m:
        return m.group(1), m.group(2)
    return None


def _score_road_address_match(address: str, api_address: str) -> float:
    """등기 도로명·건물번호가 KB 단지 주소와 일치하면 1.0."""
    road = _extract_road_name_and_number(address)
    if not road or not api_address:
        return 0.0
    road_name, road_num = road
    norm_api = re.sub(r"\s+", "", api_address)
    norm_road = re.sub(r"\s+", "", road_name)
    if norm_road in norm_api and road_num in norm_api:
        return 1.0
    return 0.0


def _select_complex_by_dong_and_lot(
    complexes: List[Dict[str, Any]],
    dong_name: str,
    lot_number: str,
) -> Optional[Dict[str, Any]]:
    """법정동+번지로 단지 1건 확정 (이름 무관)."""
    if not dong_name or not lot_number:
        return None
    hits = [
        c
        for c in complexes
        if dong_name in (c.get("주소") or "")
        and _lot_matches_complex_address(lot_number, c.get("주소") or "")
    ]
    if len(hits) == 1:
        return hits[0]
    return None


def _parse_area_number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).strip().replace(",", "").replace("㎡", "").replace("m²", ""))
    except (ValueError, TypeError):
        return None


def _complex_has_exact_area(
    complex_item: Dict[str, Any],
    area: float,
    tolerance: float = 0.01,
) -> Optional[bool]:
    """
    fastPriceInfo 매매 배열에 등기 면적이 정확히 있는지.
    시세 배열이 없으면 None(모름), 있으면 True/False.
    """
    if area is None or area <= 0:
        return None
    prices = complex_item.get("매매") or complex_item.get("매매가") or []
    if not isinstance(prices, list) or not prices:
        return None
    for price_info in prices:
        dedicated = _parse_area_number(price_info.get("전용면적"))
        supply = _parse_area_number(price_info.get("공급면적") or price_info.get("면적"))
        if dedicated is not None and abs(dedicated - area) <= tolerance:
            return True
        if dedicated is None and supply is not None and abs(supply - area) <= tolerance:
            return True
    return False


def _disambiguate_complex_candidates(
    pool: List[Dict[str, Any]],
    dong_name: str,
    lot_number: Optional[str],
    area: Optional[float],
    complex_name: Optional[str],
) -> Optional[Dict[str, Any]]:
    """이름 동률 후보를 동+번지 → 정확 면적 → 코어 완전일치 순으로 1건 확정. 못 가리면 None."""
    if not pool:
        return None
    remaining = list(pool)
    if dong_name and lot_number:
        lot_hits = [
            c for c in remaining
            if dong_name in (c.get("주소") or "")
            and _lot_matches_complex_address(lot_number, c.get("주소") or "")
        ]
        if len(lot_hits) == 1:
            return lot_hits[0]
        if lot_hits:
            remaining = lot_hits
    if area is not None and area > 0:
        area_hits = [c for c in remaining if _complex_has_exact_area(c, area) is True]
        if len(area_hits) == 1:
            return area_hits[0]
        if area_hits:
            remaining = area_hits
    if len(remaining) == 1:
        return remaining[0]
    if complex_name:
        core_hits = [
            c for c in remaining
            if _complex_names_core_equal(complex_name, c.get("단지명") or c.get("name") or "")
        ]
        if len(core_hits) == 1:
            return core_hits[0]
    return None


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
        # 이름만으로 캐시하면 '꿈마을'이 건영서안/동아를 서로 덮어쓴다. 주소 단위만 저장.
        keys = []
        if address:
            keys.append(f"addr::{self._normalize_text(address)}")
        if address and complex_name:
            keys.append(f"pair::{self._normalize_text(address)}::{self._normalize_text(complex_name)}")
        return keys

    def _kb_intgra_search_hscm(self, keyword: str, count: int = 2) -> List[Dict[str, Any]]:
        """kbland 내부 통합검색(intgraSerch)으로 단지 후보 조회."""
        kw = (keyword or "").strip()
        if not kw or not _kb_search_available():
            return []
        params = {
            "검색대상구분": "SRC_HSCM",
            "검색키워드": kw,
            "결과개수": count,
            "페이지번호": 1,
        }
        try:
            response = _SESSION.get(
                f"{self.base_url}/land-complex/serch/intgraSerch",
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=_KB_SEARCH_TIMEOUT_SEC,
            )
            response.raise_for_status()
            body = response.json().get("dataBody", {}) or {}
            rc = body.get("resultCode")
            if rc not in (None, 11000):
                logger.debug(
                    "intgraSerch 오류(keyword=%s): rc=%s msg=%s",
                    kw[:40], rc, body.get("message"),
                )
                _kb_search_note_failure(f"intgraSerch rc={rc}")
                return []
            _kb_search_note_success()
            outer = body.get("data")
            if not isinstance(outer, dict):
                return []
            inner = outer.get("data")
            if isinstance(inner, dict) and inner.get("resultCode") not in (None, 11000):
                logger.debug(
                    "intgraSerch 엔진 오류(keyword=%s): %s",
                    kw[:40], inner.get("message"),
                )
                _kb_search_note_failure("intgraSerch 엔진 오류")
                return []
            hscm = (inner or {}).get("HSCM") if isinstance(inner, dict) else {}
            items = (hscm or {}).get("data") or []
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.debug("intgraSerch 실패(keyword=%s): %s", kw[:40], e)
            _kb_search_note_failure("intgraSerch 예외")
            return []

    def _kb_auto_keyword_hscm(self, keyword: str) -> List[Dict[str, Any]]:
        """kbland 자동완성(autoKywrSerch)으로 단지명 후보 확장."""
        kw = (keyword or "").strip()
        if not kw or not _kb_search_available():
            return []
        params = {
            "컬렉션비중설정": _KB_AUTO_KYWR_COLLECTION,
            "검색키워드": kw,
        }
        try:
            response = _SESSION.get(
                f"{self.base_url}/land-complex/serch/autoKywrSerch",
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=_KB_SEARCH_TIMEOUT_SEC,
            )
            response.raise_for_status()
            body = response.json().get("dataBody", {}) or {}
            rc = body.get("resultCode")
            if rc not in (None, 11000):
                _kb_search_note_failure(f"autoKywrSerch rc={rc}")
                return []
            _kb_search_note_success()
            data = body.get("data") or []
            if isinstance(data, list) and data:
                items = data[0].get("COL_AT_HSCM") or []
                return items if isinstance(items, list) else []
        except Exception as e:
            logger.debug("autoKywrSerch 실패(keyword=%s): %s", kw[:40], e)
            _kb_search_note_failure("autoKywrSerch 예외")
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
            if not _kb_search_available():  # 엔진 장애 → 남은 키워드 조합 생략
                return candidates[:head_limit]
            _add_from_intgra(self._kb_intgra_search_hscm(kw, count=10))
            if len(candidates) >= head_limit:
                return candidates[:head_limit]

        for kw in unique_keywords[:4]:
            if not _kb_search_available():
                return candidates[:head_limit]
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
            response = _SESSION.get(
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
                r = _SESSION.get(path, headers=DEFAULT_HEADERS, timeout=12)
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

        cand_addr = f"{page_info.get('road_address', '')} {page_info.get('jibun_address', '')}"
        target_nums = set(_KBLAND_NUM_RE.findall(target_address or ""))
        cand_nums = set(_KBLAND_NUM_RE.findall(cand_addr))
        if target_nums and cand_nums and target_nums.intersection(cand_nums):
            score += 1.0

        target_lot = _extract_lot_number_from_address(target_address)
        if target_lot:
            if _lot_matches_complex_address(target_lot, cand_addr):
                score += 2.0
            else:
                cand_lot = _extract_lot_number_from_address(
                    page_info.get("jibun_address") or page_info.get("road_address") or ""
                )
                if cand_lot and cand_lot != target_lot:
                    score -= 2.5

        if target_complex_name:
            name_norm = self._normalize_text(target_complex_name)
            name_match = _normalize_kb_complex_name_for_match(target_complex_name)
            title_match = _normalize_kb_complex_name_for_match(page_info.get("title", ""))
            title_raw = page_info.get("title", "") or ""
            if _complex_names_equivalent(target_complex_name, title_raw):
                score += 2.0
            elif name_match and title_match and (
                _is_safe_name_containment(name_match, title_match)
                or _is_safe_name_containment(title_match, name_match)
            ):
                score += 2.0
            elif _complex_names_related(target_complex_name, title_raw):
                score += 0.8
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
            building_dong = _extract_registry_building_dong(target_address)
            if building_dong and _complex_name_has_building_dong_label(title_raw, building_dong):
                score += 1.5

        road_score = _score_road_address_match(
            target_address, f"{page_info.get('road_address', '')} {page_info.get('jibun_address', '')}"
        )
        if road_score > 0:
            score += road_score * 1.5

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

        # 원문 + 알파벳 음차 변환본(DMC…) + 한글 꼬리 + 제N동 변형 dual query
        name_variants = _expand_complex_name_search_variants(complex_name, address)
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
        # 양평동3가, 보문동6가 등 "동+숫자+가"를 일반 동명보다 먼저 매칭해야 한다.
        # 뒤에 두면 "특별시 성북구 보문동6가"가 패턴4에 걸려 dong="성북구 보문동"이 되고
        # 법정동코드가 성북동(1129010100)으로 떨어져 보문파크뷰자이(29858)를 못 찾는다.
        dong_patterns = [
            r'(?:구|군|시)\s+([가-힣]+(?:동|읍|면)\s*\d+가)',  # 보문동6가, 양평동3가, 양평동 3가
            r'(?:시|도)\s+[가-힣]+(?:시|구|군)\s+([가-힣]+(?:구|군|시)\s+[가-힣]+(?:동|읍|면))(?!\s*\d+가)',  # "원미구 중동", "권선구 곡반정동" 형식
            r'(?:구|군|시)\s+[가-힣]+(?:읍|면)\s+([가-힣]+리)',  # "김포시 고촌읍 향산리" -> "향산리"
            r'(?:구|군|시)\s+([가-힣]+면\s+[가-힣]+리)',  # "거제시 일운면 지세포리" -> "일운면 지세포리" (면+리 우선)
            r'(?:구|군|시)\s+([가-힣]+(?:구|군|시)?\s*[가-힣]+(?:동|읍|면))(?!\s*\d+가)',  # "원미구 중동", "권선구 곡반정동"
            r'(?:구|군|시)\s+([가-힣]+(?:동|읍|면))(?!\s*\d+가)',  # 일반 동명 (예: 곡반정동, 청운동, 중동)
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

        # 세종특별자치시처럼 구/군이 없는 시/도: parse는 district=None.
        # JSON은 districts["세종특별자치시"].dongs["집현동"] 또는
        # districts["조치원읍"].dongs["원리"] 형태이므로, 동이 들어 있는 district 키를 채운다.
        if region and dong and not district:
            preview_districts = ((self.dongcode_data.get(region) or {}).get("districts") or {})
            if region in preview_districts:
                dongs_under_region = (preview_districts.get(region) or {}).get("dongs") or {}
                if dong in dongs_under_region:
                    district = region
                else:
                    for dist_key, dist_val in preview_districts.items():
                        dongs = (dist_val or {}).get("dongs") or {}
                        if dong in dongs:
                            district = dist_key
                            break
                    if not district:
                        district = region
            elif len(preview_districts) == 1:
                district = next(iter(preview_districts))
            if district:
                logger.debug("   구 없는 시/도 → district=%s (dong=%s)", district, dong)
        
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
                    response = _SESSION.get(url, params=params, headers=DEFAULT_HEADERS, timeout=15)
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
        # hscmList는 여기서 붙이지 않는다. fastPriceInfo로 단지를 확정하면 생략하고,
        # 매칭 실패 시에만 get_kb_price에서 _merge_hscm_into_complex_list를 호출한다.
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
            response = _SESSION.get(url, params=params, headers=DEFAULT_HEADERS, timeout=15)
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
    
    # kbland 재건축 절차 9단계 ↔ rcnsInfo 날짜 필드
    _RCNS_STAGE_FIELDS = (
        (1, "기본계획수립", "기본계획수립일"),
        (2, "재건축진단", "안전진단일"),
        (3, "정비구역지정", "정비구역지정일"),
        (4, "추진위원회승인", "추진위원회승인일"),
        (5, "조합설립인가", "조합설립인가일"),
        (6, "사업시행인가", "사업시행인가일"),
        (7, "관리처분인가", "관리처분인가일"),
        (8, "이주 및 철거", "철거신고일"),
        (9, "일반분양", "분양일"),
    )

    def get_complex_main(self, complex_id: str) -> Optional[Dict[str, Any]]:
        """단지 상세 기본정보 (complexMain). 총세대수·총동수·준공년월일·매물종별구분명 등."""
        if not complex_id:
            return None
        try:
            response = _SESSION.get(
                f"{self.base_url}/land-complex/complex/complexMain",
                params={"단지기본일련번호": complex_id},
                headers=DEFAULT_HEADERS,
                timeout=10,
            )
            response.raise_for_status()
            return (response.json().get("dataBody") or {}).get("data")
        except Exception as e:
            logger.debug("get_complex_main 실패: %s", e)
            return None

    def get_complex_extra_via_api(self, complex_id: str) -> Dict[str, Any]:
        """
        세대수·동수·사용승인일·단지유형·재건축단계를 KB API로 조회 (Playwright 대체).

        /c/ 페이지 스크래핑은 Chromium을 띄워 메모리·시간을 크게 쓰는데,
        같은 값이 complexMain(+재건축은 rcnsInfo)에 그대로 있어 API를 먼저 쓴다.
        반환 형태는 kb_complex_scraper.get_complex_extra_info와 동일하다.
        """
        out: Dict[str, Any] = {
            "redevelop_stages": [],
            "households": None,
            "buildings": None,
            "approval_date": None,
            "years_since_completion": None,
            "redevelop_yn": False,
            "complex_name": None,
            "complex_type": None,
            "source_url": f"https://kbland.kr/c/{complex_id}" if complex_id else None,
            "error": None,
        }

        def to_int(value, max_val):
            try:
                num = int(float(str(value).replace(",", "").strip()))
            except (ValueError, TypeError, AttributeError):
                return None
            return num if 1 <= num <= max_val else None

        main = self.get_complex_main(str(complex_id))
        if not main:
            out["error"] = "complexMain 조회 실패"
            return out

        out["complex_name"] = main.get("단지명")
        out["households"] = to_int(main.get("총세대수"), 100000)
        out["buildings"] = to_int(main.get("총동수"), 10000)
        out["complex_type"] = main.get("매물종별구분명") or None

        # 준공년월일 19790830 → 사용승인일 1979.08.30 (KB 페이지의 '사용승인일'과 같은 값)
        ymd = re.sub(r"\D", "", str(main.get("준공년월일") or ""))
        if len(ymd) == 8:
            out["approval_date"] = f"{ymd[:4]}.{ymd[4:6]}.{ymd[6:]}"
        out["years_since_completion"] = to_int(main.get("준공년수"), 200)

        if str(main.get("재건축여부")) == "1":
            out["redevelop_yn"] = True
            out["redevelop_stages"] = self.stages_from_rcns(self.get_rcns_info(str(complex_id)))

        logger.info(
            "✅ KB API 단지정보: 세대수=%s 동수=%s 사용승인=%s(%s년차) 유형=%s 재건축단계=%d개",
            out["households"], out["buildings"], out["approval_date"],
            out["years_since_completion"], out["complex_type"], len(out["redevelop_stages"]),
        )
        return out

    def get_villa_dong_list(self, dongcode: str) -> List[Dict[str, Any]]:
        """법정동 빌라·다세대 동(건물) 목록 (지번·단지ID 매칭용)."""
        payload = _kb_data_api_get(
            "/common/quick-price-check/villas",
            {"legalCode": dongcode},
        )
        if not payload:
            return []
        if isinstance(payload, dict):
            dongs = payload.get("dongs") or []
        elif isinstance(payload, list):
            dongs = payload
        else:
            dongs = []
        return [d for d in dongs if isinstance(d, dict)]

    def get_villa_hos(self, dong_id: str) -> List[Dict[str, Any]]:
        """빌라 동 호실 목록 (hoId, hoName)."""
        if not dong_id:
            return []
        payload = _kb_data_api_get(f"/common/quick-price-check/villas/{dong_id}/hos")
        if isinstance(payload, dict):
            hos = payload.get("hos") or []
        elif isinstance(payload, list):
            hos = payload
        else:
            hos = []
        return [h for h in hos if isinstance(h, dict)]

    def get_villa_ho_areas(self, dong_id: str) -> List[Dict[str, Any]]:
        """호별 전용면적 (호수 미기재 시 면적 매칭용)."""
        if not dong_id:
            return []
        payload = _kb_data_api_get(f"/common/opinion/hoList/{dong_id}")
        rows = []
        if isinstance(payload, dict):
            rows = payload.get("data") or payload.get("hos") or []
        elif isinstance(payload, list):
            rows = payload
        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ho_id = row.get("건물호일련번호") or row.get("hoId")
            ho_name = row.get("호명") or row.get("hoName")
            area = row.get("전용면적") or row.get("area")
            if ho_id is None:
                continue
            try:
                area_f = float(area) if area is not None else None
            except (TypeError, ValueError):
                area_f = None
            out.append({"hoId": ho_id, "hoName": ho_name, "area": area_f})
        return out

    def get_villa_ho_price(self, dong_id: str, ho_id: Any) -> Optional[Dict[str, Any]]:
        """호별 KB AI시세 (만원)."""
        if not dong_id or ho_id is None:
            return None
        payload = _kb_data_api_get(
            f"/common/quick-price-check/villas/{dong_id}/hos/{ho_id}/price"
        )
        if not isinstance(payload, dict):
            return None
        dongs = payload.get("dongs") or []
        for dong in dongs:
            for ho in (dong.get("hoPrices") or []):
                if str(ho.get("hoId")) == str(ho_id):
                    return ho
            prices = dong.get("hoPrices") or []
            if len(prices) == 1:
                return prices[0]
        return None

    def _select_villa_dong(
        self,
        dongs: List[Dict[str, Any]],
        address: str,
        complex_name: Optional[str] = None,
        complex_id_hint: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """지번·단지ID·건물명·도로명으로 빌라 동을 확정. 후보가 여러 개면 추측하지 않음."""
        if not dongs:
            return None

        pool = dongs
        if complex_id_hint:
            hint = str(complex_id_hint).strip()
            id_hits = [
                d for d in dongs
                if d.get("complexId") is not None and str(d.get("complexId")) == hint
            ]
            if len(id_hits) == 1:
                return id_hits[0]
            if id_hits:
                pool = id_hits

        lot = _extract_lot_number_from_address(address)
        lot_hits: List[Dict[str, Any]] = []
        if lot:
            for d in pool:
                land = d.get("landAddress") or ""
                road = d.get("roadAddress") or ""
                if _lot_matches_complex_address(lot, land) or _lot_matches_complex_address(lot, road):
                    lot_hits.append(d)
        if len(lot_hits) == 1:
            return lot_hits[0]
        candidates = lot_hits or pool

        if complex_name:
            name_hits = [
                d for d in candidates
                if _complex_names_related(
                    complex_name,
                    d.get("buildingName") or d.get("dongName") or "",
                )
            ]
            if len(name_hits) == 1:
                return name_hits[0]
            if len(name_hits) > 1 and lot_hits:
                # 같은 지번에 이름이 비슷한 동이 여러 개면 단지ID 있는 쪽
                with_id = [d for d in name_hits if d.get("complexId")]
                if len(with_id) == 1:
                    return with_id[0]
            if len(name_hits) == 1:
                return name_hits[0]
            if lot_hits and len(name_hits) > 1:
                return None

        road_hits = [
            d for d in candidates
            if _score_road_address_match(address, d.get("roadAddress") or "") >= 1.0
        ]
        if len(road_hits) == 1:
            return road_hits[0]

        if len(lot_hits) == 1:
            return lot_hits[0]
        return None

    def _select_villa_ho(
        self,
        hos: List[Dict[str, Any]],
        address: str,
        area: float,
        dong_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """호명 우선, 없으면 전용면적(+층)으로 호실 확정."""
        if not hos:
            return None
        ho_name = _extract_ho_name_from_address(address)
        if ho_name:
            target = _normalize_ho_name(ho_name)
            name_hits = [
                h for h in hos
                if _normalize_ho_name(h.get("hoName") or h.get("호명")) == target
            ]
            if len(name_hits) == 1:
                return name_hits[0]
            if name_hits:
                return name_hits[0]

        floor = _extract_floor_from_address(address)
        area_rows = self.get_villa_ho_areas(dong_id) if dong_id and area and area > 0 else []
        area_by_id = {str(r["hoId"]): r.get("area") for r in area_rows}
        area_hits: List[Dict[str, Any]] = []
        if area and area > 0:
            for h in hos:
                ho_area = area_by_id.get(str(h.get("hoId")))
                if ho_area is None:
                    continue
                if abs(float(ho_area) - float(area)) <= 0.51:
                    area_hits.append(h)
        if floor is not None and area_hits:
            floor_hits = [h for h in area_hits if _ho_matches_floor(h.get("hoName"), floor)]
            if len(floor_hits) == 1:
                return floor_hits[0]
            if len(floor_hits) > 1:
                return None
        if len(area_hits) == 1:
            return area_hits[0]
        return None

    def get_villa_kb_ai_price(
        self,
        address: str,
        area: float,
        complex_name: Optional[str] = None,
        hint_text: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        빌라·다세대 주소 매칭 후 KB AI시세 + 단지 기본정보.
        공식 KB시세(kb_price)는 채우지 않는다.
        """
        dongcode = self.find_dongcode(address)
        if not dongcode:
            address_attached = _make_attached_address(address)
            if address_attached != address:
                dongcode = self.find_dongcode(address_attached)
        if not dongcode:
            logger.info("빌라 AI시세: 법정동코드를 찾지 못해 생략")
            return None

        dongs = self.get_villa_dong_list(dongcode)
        if not dongs:
            logger.info("빌라 AI시세: 해당 동 빌라 목록 없음 (%s)", dongcode)
            return None

        complex_id_hint = _extract_kbland_complex_id(hint_text)
        selected = self._select_villa_dong(
            dongs, address, complex_name=complex_name, complex_id_hint=complex_id_hint
        )
        if not selected:
            logger.info(
                "빌라 AI시세: 주소 매칭 실패 (dongcode=%s, lot=%s, name=%s, hint_id=%s)",
                dongcode,
                _extract_lot_number_from_address(address),
                complex_name,
                complex_id_hint,
            )
            return None

        dong_id = selected.get("dongId")
        building_name = selected.get("buildingName") or selected.get("dongName") or complex_name
        complex_id = selected.get("complexId")
        logger.info(
            "✅ 빌라 동 매칭: %s (dongId=%s, complexId=%s, %s)",
            building_name, dong_id, complex_id, selected.get("landAddress"),
        )
        print(f"[OK] 빌라 동 매칭: {building_name} (id={complex_id})")

        result: Dict[str, Any] = {
            "kb_price": None,
            "kb_price_min": None,
            "kb_price_raw": None,
            "kb_price_min_raw": None,
            "kb_ai_price": None,
            "kb_ai_price_min": None,
            "kb_ai_price_max": None,
            "complex_name": building_name,
            "area": area,
            "area_requested": area,
            "area_diff": 0.0,
            "pyeong": "",
            "type": "",
            "dongcode": dongcode,
            "complex_id": str(complex_id) if complex_id is not None else None,
            "same_price_area_matched": False,
            "redevelop_stages": [],
            "households": None,
            "buildings": None,
            "approval_date": None,
            "years_since_completion": None,
            "complex_type": "연립/다세대",
            "redevelop_yn": False,
            "villa_dong_id": dong_id,
            "villa_ho_name": None,
        }

        hos = self.get_villa_hos(str(dong_id)) if dong_id else []
        selected_ho = self._select_villa_ho(hos, address, area, dong_id=str(dong_id) if dong_id else None)
        if selected_ho and dong_id:
            ho_id = selected_ho.get("hoId")
            ho_name = selected_ho.get("hoName")
            price_row = self.get_villa_ho_price(str(dong_id), ho_id)
            avg = _parse_sale_price_man((price_row or {}).get("averageSalePrice"))
            lower = _parse_sale_price_man((price_row or {}).get("lowerSalePrice"))
            upper = _parse_sale_price_man((price_row or {}).get("upperSalePrice"))
            ho_area = (price_row or {}).get("area")
            try:
                ho_area_f = float(ho_area) if ho_area is not None else None
            except (TypeError, ValueError):
                ho_area_f = None
            result["villa_ho_name"] = str(ho_name) if ho_name is not None else None
            if ho_area_f:
                result["area"] = ho_area_f
                result["area_diff"] = abs(ho_area_f - area) if area else 0.0
                try:
                    result["pyeong"] = f"{ho_area_f / 3.3058:.1f}"
                except Exception:
                    pass
            if avg:
                result["kb_ai_price"] = avg
                result["kb_ai_price_min"] = lower
                result["kb_ai_price_max"] = upper
                logger.info(
                    "✅ 빌라 KB AI시세: 일반 %s만원 하한 %s만원 (%s %s호)",
                    f"{avg:,.0f}", f"{lower:,.0f}" if lower else "-", building_name, ho_name,
                )
                print(f"[OK] 빌라 KB AI시세: 일반 {avg:,.0f}만원 ({building_name} {ho_name}호)")
            else:
                logger.info("빌라 호실 매칭은 됐으나 AI시세 금액 없음 (hoId=%s)", ho_id)
        else:
            logger.info("빌라 단지 식별 완료, 호실 미확정 → AI시세 생략 (단지정보만)")
            print("[!] 빌라 호실을 특정하지 못해 AI시세는 생략, 단지 정보만 반환")

        if complex_id is not None:
            extra = self.get_complex_extra_via_api(str(complex_id))
            for key in (
                "households", "buildings", "approval_date", "years_since_completion",
                "complex_type", "complex_name",
            ):
                if extra.get(key) is not None:
                    result[key] = extra[key]
            if extra.get("redevelop_yn"):
                result["redevelop_yn"] = True
                result["redevelop_stages"] = extra.get("redevelop_stages") or []
            if extra.get("source_url"):
                result["source_url"] = extra["source_url"]
        if not result.get("source_url") and result.get("complex_id"):
            result["source_url"] = f"https://kbland.kr/c/{result['complex_id']}"

        return result

    def get_rcns_info(self, complex_id: str) -> Optional[Dict[str, Any]]:
        """단지 재건축/정비사업 정보 (kbland complex/rcnsInfo). Playwright 없이 단계·인가일 확보."""
        if not complex_id:
            return None
        try:
            response = _SESSION.get(
                f"{self.base_url}/land-complex/complex/rcnsInfo",
                params={"단지기본일련번호": complex_id},
                headers=DEFAULT_HEADERS,
                timeout=10,
            )
            response.raise_for_status()
            return (response.json().get("dataBody") or {}).get("data")
        except Exception as e:
            logger.debug("get_rcns_info 실패: %s", e)
            return None

    def stages_from_rcns(self, rcns: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """rcnsInfo 응답을 스크래퍼와 같은 {step, name, date} 목록으로 변환. 날짜 있는 단계만."""
        if not rcns or not isinstance(rcns, dict):
            return []
        stages: List[Dict[str, Any]] = []
        for step, name, field in self._RCNS_STAGE_FIELDS:
            date_val = str(rcns.get(field) or "").strip()
            if re.match(r"^\d{4}\.\d{2}\.\d{2}$", date_val):
                stages.append({"step": step, "name": name, "date": date_val})
        # 날짜 필드는 비었지만 현재 단계명만 있는 경우(드묾)는 날짜 없이 넣지 않는다.
        # 웹훅 출력은 날짜가 있는 단계만 사용한다.
        return stages
    
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

    def get_same_price_areas(self, complex_id: str, area_seq: Any) -> List[str]:
        """
        KB '동일시세 전용면적' 목록 조회 (kbland 단지 상세의 동일 버튼과 같은 데이터).

        BasePrcInfoNew 응답의 '기타전용면적' 필드로, 한 시세 타입에 묶인 전용면적들이
        쉼표로 나열된다. 1980년 전후 구축은 등기부 전유면적에 발코니가 포함돼 KB 전용면적과
        다르므로(은마 등기 94.76 ↔ KB 전용 76.79), 이 목록이 등기부 면적 → 시세 타입을
        잇는 KB 공식 대응표 역할을 한다.
        """
        if area_seq is None:
            return []
        cache_key = (str(complex_id), str(area_seq))
        if cache_key in _SAME_PRICE_AREA_CACHE:
            return _SAME_PRICE_AREA_CACHE[cache_key]

        areas: List[str] = []
        try:
            response = _SESSION.get(
                f"{self.base_url}/land-price/price/BasePrcInfoNew",
                params={"단지기본일련번호": complex_id, "면적일련번호": area_seq},
                headers=DEFAULT_HEADERS,
                timeout=10,
            )
            response.raise_for_status()
            rows = (response.json().get("dataBody", {}) or {}).get("data", {}) or {}
            for row in rows.get("시세") or []:
                for token in str(row.get("기타전용면적") or "").split(","):
                    token = token.strip()
                    if token:
                        areas.append(token)
        except Exception as e:
            logger.debug("동일시세 전용면적 조회 실패(단지 %s, 면적일련번호 %s): %s", complex_id, area_seq, e)

        _SAME_PRICE_AREA_CACHE[cache_key] = areas
        return areas

    def find_price_by_same_price_area(self, complex_id: str, prices: List[Dict[str, Any]],
                                      area: float) -> Optional[Dict[str, Any]]:
        """
        전용/공급면적 정확 매칭이 실패했을 때, KB '동일시세 전용면적' 목록으로 타입을 찾는다.

        구축 아파트는 등기부 전유면적이 발코니를 포함해 KB 전용면적과 다르지만,
        KB가 해당 면적을 동일 시세 타입으로 묶어 두었기 때문에 목록에 정확히 있으면 확정할 수 있다.
        후보가 2개 이상이면 어느 타입인지 단정할 수 없으므로 포기한다(가까운 면적 대체 금지).
        """
        if not prices or area <= 0 or complex_id is None:
            return None

        target = f"{area:.2f}"

        def to_float(value):
            try:
                return float(str(value).strip())
            except (ValueError, TypeError, AttributeError):
                return None

        # 등기면적이 전용~공급면적 구간(±10%) 안에 드는 타입만 조회해 API 호출 수를 억제
        candidates = []
        for price_info in prices:
            dedicated = to_float(price_info.get("전용면적"))
            supply = to_float(price_info.get("공급면적") or price_info.get("면적"))
            low = (dedicated or supply or 0) * 0.9
            high = (supply or dedicated or 0) * 1.1
            if low <= area <= high:
                candidates.append(price_info)
        if not candidates:
            candidates = list(prices)
        candidates = candidates[:_SAME_PRICE_AREA_MAX_LOOKUP]

        matched = []
        for price_info in candidates:
            same_areas = self.get_same_price_areas(complex_id, price_info.get("면적일련번호"))
            if not same_areas:
                continue
            if any(f"{v:.2f}" == target for v in (to_float(a) for a in same_areas) if v is not None):
                matched.append((price_info, same_areas))

        if len(matched) != 1:
            if matched:
                logger.warning(
                    "⚠️ 동일시세 전용면적에 %s㎡가 여러 타입(%d개)에 있어 타입 확정 불가 → KB 시세 생략",
                    target, len(matched),
                )
            return None

        price_info, same_areas = matched[0]
        logger.info(
            "✅ KB 동일시세 전용면적에서 %s㎡ 확인 → 전용 %s㎡ / 공급 %s㎡ 타입 적용 (목록: %s)",
            target, price_info.get("전용면적"), price_info.get("공급면적"), ", ".join(same_areas),
        )
        print(f"[OK] KB 동일시세 전용면적 매칭: 등기 {target}㎡ → 공급 {price_info.get('공급면적')}㎡ 타입")
        return price_info

    def _select_complex_from_list(
        self,
        complexes: List[Dict[str, Any]],
        address: str,
        complex_name: Optional[str],
        area: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """fastPriceInfo/hscm 목록에서 등기 주소·단지명으로 단지를 고른다. 못 찾으면 None."""
        if not complexes:
            return None

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
        # KB 단지 주소는 리(里)를 생략하기도 한다 (등기 '별내면 청학리 419' ↔ KB '남양주시 별내면 419').
        # 단지 목록 어디에도 리 이름이 없을 때만 읍/면 이름으로 대조 (리를 쓰는 지역은 기존대로).
        if dong_name.endswith("리") and not any(
            dong_name in (c.get("주소") or "") for c in complexes
        ):
            eup_myeon = _extract_eup_myeon_from_address(address)
            if eup_myeon and any(eup_myeon in (c.get("주소") or "") for c in complexes):
                logger.info(f"   KB 단지 주소에 '{dong_name}' 없음 → 읍/면 '{eup_myeon}' 기준으로 대조")
                print(f"[KB] KB 단지 주소에 '{dong_name}' 없음 → '{eup_myeon}' 기준 매칭")
                dong_name = eup_myeon
        if dong_name and lot_number:
            logger.debug(f"   동+번지 매칭 키: {dong_name} {lot_number}")

        building_dong = _extract_registry_building_dong(address)
        if building_dong:
            logger.debug(f"   등기 건물동 번호: {building_dong}")

        # 동+번지가 단지 1건으로 확정되면 이름보다 우선 (중동 1103 → 꿈마을(동아))
        if dong_name and lot_number:
            lot_unique = _select_complex_by_dong_and_lot(complexes, dong_name, lot_number)
            if lot_unique:
                selected_complex = lot_unique
                logger.info(
                    "✅ 동+번지 우선 확정: %s (%s %s)",
                    selected_complex.get("단지명"),
                    dong_name,
                    lot_number,
                )
                print(
                    f"[OK] 동+번지 우선 확정: "
                    f"{selected_complex.get('단지명')} ({dong_name} {lot_number})"
                )

        if not selected_complex and complex_name:
            logger.debug(f"   단지명으로 매칭 시도: {complex_name}")
            # 단지명 매칭: 동등 후보 + 시공사 형제 후보 → 동·번지·면적으로 확정
            exact_matches: List[Dict[str, Any]] = []
            related_matches: List[Dict[str, Any]] = []
            best_match = None
            best_score = 0.0

            for i, complex in enumerate(complexes):
                complex_name_from_api = complex.get("단지명") or complex.get("name", "")
                complex_address_from_api = complex.get("주소", "")
                logger.debug(f"   [{i+1}] {complex_name_from_api} (주소: {complex_address_from_api})")

                # 정확/코어 매칭 (대림아파트 ↔ 대림(1차) 포함)
                name_equiv = _complex_names_equivalent(complex_name, complex_name_from_api)
                # 제N동 변형 매칭 (개포현대아파트 + 제200동 ↔ 개포현대(200동))
                if not name_equiv and building_dong:
                    for variant in _expand_complex_name_search_variants(complex_name, address):
                        if variant != complex_name and _complex_names_equivalent(
                            variant, complex_name_from_api
                        ):
                            name_equiv = True
                            break
                if name_equiv:
                    exact_matches.append(complex)
                    related_matches.append(complex)
                    logger.debug(f"      동등/코어 후보: {complex_name_from_api}")
                    continue

                if _complex_names_related(complex_name, complex_name_from_api):
                    related_matches.append(complex)
                    logger.debug(f"      형제 단지 후보: {complex_name_from_api}")

                # 부분/유사 매칭 점수 (영문·혼합 단지명 포함)
                score = _score_complex_name_similarity(complex_name, complex_name_from_api)
                name_related = score >= 0.5
                if (
                    building_dong
                    and name_related
                    and _complex_name_has_building_dong_label(complex_name_from_api, building_dong)
                ):
                    score += 0.4
                    logger.debug(f"      건물동 단지명 보너스: {building_dong}동")
                road_bonus = _score_road_address_match(address, complex_address_from_api)
                if name_related and road_bonus > 0:
                    score += road_bonus * 0.35
                    logger.debug(f"      도로명+번호 보너스")
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

            name_pool = exact_matches or related_matches
            if name_pool:
                picked = _disambiguate_complex_candidates(
                    name_pool, dong_name, lot_number, area, complex_name
                )
                if picked:
                    selected_complex = picked
                    picked_name = selected_complex.get("단지명", "알 수 없음")
                    picked_addr = (selected_complex.get("주소") or "").strip()
                    if len(exact_matches) == 1 and selected_complex in exact_matches:
                        logger.info(f"✅ 단지명 정확 매칭: {picked_name}")
                        print(f"[OK] 단지명 정확 매칭: {picked_name}")
                    elif dong_name and lot_number and dong_name in picked_addr and _lot_matches_complex_address(lot_number, picked_addr):
                        logger.info(
                            "✅ 이름 동률 → 동+번지 확정: %s (%s %s)",
                            picked_name, dong_name, lot_number,
                        )
                        print(
                            f"[OK] 이름 동률 → 동+번지 확정: "
                            f"{picked_name} ({dong_name} {lot_number})"
                        )
                    elif area and _complex_has_exact_area(selected_complex, area) is True:
                        logger.info("✅ 이름 동률 → 정확 면적으로 확정: %s (%.2f㎡)", picked_name, area)
                        print(f"[OK] 이름 동률 → 정확 면적 확정: {picked_name} ({area}㎡)")
                    else:
                        logger.info(f"✅ 단지명 매칭: {picked_name}")
                        print(f"[OK] 단지명 매칭: {picked_name}")
                else:
                    logger.warning(
                        "⚠️ 단지명 후보 %d개이나 동+번지/면적으로 확정 불가 → 추가 매칭 시도",
                        len(name_pool),
                    )

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

        # 단지명 코어는 맞지만 위 단계에서 미확정 → 동+번지로 코어 후보만 재확정
        if not selected_complex and complex_name and dong_name and lot_number:
            core_lot_hits = []
            for complex in complexes:
                api_name = complex.get("단지명") or complex.get("name") or ""
                api_addr = (complex.get("주소") or "").strip()
                if not _complex_names_core_equal(complex_name, api_name):
                    continue
                if dong_name in api_addr and _lot_matches_complex_address(lot_number, api_addr):
                    core_lot_hits.append(complex)
            if len(core_lot_hits) == 1:
                selected_complex = core_lot_hits[0]
                logger.info(
                    "✅ 코어명+동·번지 매칭: %s (%s %s)",
                    selected_complex.get("단지명"),
                    dong_name,
                    lot_number,
                )
                print(
                    f"[OK] 코어명+동·번지 매칭: "
                    f"{selected_complex.get('단지명')} ({dong_name} {lot_number})"
                )
        # 이름은 맞았으나 번지 불일치 등으로 미확정 → 동+번지만으로 재검색
        if not selected_complex and dong_name and lot_number:
            lot_hit = _select_complex_by_dong_and_lot(complexes, dong_name, lot_number)
            if lot_hit:
                selected_complex = lot_hit
                logger.info(
                    "✅ 동+번지 단독 매칭: %s (%s %s)",
                    selected_complex.get("단지명"),
                    dong_name,
                    lot_number,
                )
                print(
                    f"[OK] 동+번지 단독 매칭: "
                    f"{selected_complex.get('단지명')} ({dong_name} {lot_number})"
                )
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

        return selected_complex

    def get_kb_price(self, address: str, area: float, 
                     complex_name: Optional[str] = None,
                     force_officetel: bool = False) -> Optional[Dict[str, Any]]:
        """
        주소와 면적을 기반으로 KB 시세 조회 (메인 함수)
        
        Args:
            address: 부동산 주소
            area: 전용면적 (m²)
            complex_name: 단지명 (선택사항, 있으면 더 정확한 매칭)
            force_officetel: True면 주소에 "오피스텔" 문구가 없어도 KB 유형=2(오피스텔)
                목록을 함께 조회 (등기부 건물내역이 업무시설/숙박시설인 경우 등)
        
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
        
        # 2. 단지 목록 조회 (오피스텔 주소·업무시설/숙박시설 등기부면 유형 2도 조회하여 병합)
        logger.debug("2단계: 단지 목록 조회")
        is_officetel_hint = force_officetel or _text_indicates_officetel(address)
        property_type_hint = "오피스텔" if is_officetel_hint else None
        if force_officetel and "오피스텔" not in (address or ""):
            logger.info("   등기부 건물내역(업무시설/숙박시설 등)으로 오피스텔 유형 조회 강제 적용")
            print("[KB] 등기부 건물내역(업무시설/숙박시설)으로 오피스텔 유형(2) 조회 추가")
        complexes = self.get_complex_list(dongcode, property_type_hint=property_type_hint)
        logger.info(f"✅ 단지 목록 조회 성공: {len(complexes)}개 단지")

        # 3. 단지 선택. hscmList는 fastPriceInfo로 못 찾을 때만 붙인다.
        logger.debug("3단계: 단지 선택")
        selected_complex = self._select_complex_from_list(complexes, address, complex_name, area=area)
        if not selected_complex:
            seen_ids = {
                c.get("단지기본일련번호")
                for c in complexes
                if c.get("단지기본일련번호") is not None
            }
            hscm_added = self._merge_hscm_into_complex_list(complexes, seen_ids, dongcode)
            if hscm_added:
                print(f"[OK] hscmList 병합(매칭 실패 후): +{hscm_added}개 → 총 {len(complexes)}개")
                logger.info("hscmList 병합(매칭 실패 후): +%d개 (총 %d개)", hscm_added, len(complexes))
                selected_complex = self._select_complex_from_list(complexes, address, complex_name, area=area)
            elif not complexes:
                logger.error("❌ 단지 목록을 찾을 수 없음")
                print("[X] 단지 목록을 찾을 수 없음")
                return None

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
            # 단지를 확정하지 못하면 조회를 포기한다.
            # 예전에는 목록의 첫 번째 단지를 그냥 썼는데, 단지명 없는 빌라 등기가 같은 읍/면의
            # 무관한 아파트 시세를 가져오는 오조회가 발생할 수 있어 제거함.
            if not selected_complex:
                logger.warning(
                    f"⚠️ 단지를 확정하지 못함 → KB 시세 생략 (후보: {[c.get('단지명', 'N/A') for c in complexes[:5]]})"
                )
                print("[!] 단지를 확정하지 못해 KB 시세를 사용하지 않습니다.")
                return None
        
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
        # 시세 배열이 없어도 단지가 확정됐으면 세대수·구분은 이어서 채운다.
        if not prices:
            logger.warning(f"⚠️ 해당 단지에 매매 시세 정보가 없음: {selected_complex.get('단지명')} → 단지 정보만 반환")
            print("[!] 해당 단지에 매매 시세 정보가 없음 → 단지 정보만 반환")
        else:
            logger.info(f"✅ 단지에서 시세 정보 추출: {len(prices)}개 타입")
            logger.debug(f"   시세 타입별 면적: {[p.get('공급면적', 'N/A') for p in prices[:5]]}")
            print(f"[OK] 단지에서 시세 정보 추출: {len(prices)}개 타입")
        
        # 5. 면적에 맞는 시세 찾기
        logger.debug(f"5단계: 면적 매칭 (목표 면적: {area}m²)")
        logger.info(f"   사용 가능한 시세 면적: {[p.get('공급면적', 'N/A') for p in prices[:10]]}")
        matched_price = self.find_matching_price(prices, area) if prices else None
        # 면적 미제공(0)이면 해당 단지의 첫 번째 시세 타입을 폴백으로 사용
        if not matched_price and area <= 0 and prices:
            matched_price = prices[0]
            logger.warning(f"⚠️ 면적 미제공(0) → 해당 단지 첫 번째 타입 적용: {matched_price.get('공급면적', 'N/A')}㎡ 등")
            print(f"[!] 면적 미제공 → 해당 단지 첫 번째 시세 타입 적용")

        # 전용/공급면적이 안 맞으면 mpriByType으로 정확 매칭 후, KB '동일시세 전용면적' 목록으로 재시도.
        # fastPriceInfo 매매 배열은 시세미제공 타입을 빼는 경우가 있어(장미 123.53㎡),
        # mpriByType에 같은 면적이 있으면 그 타입을 먼저 쓴다.
        # 1980년 전후 구축은 등기부 전유면적에 발코니가 포함돼 KB 전용면적과 다르다
        # (은마 등기 94.76㎡ ↔ KB 전용 76.79㎡). KB가 두 면적을 같은 시세로 묶어두므로
        # 목록에 정확히 있을 때만 확정한다.
        same_price_area_used = False
        if not matched_price and area > 0 and complex_id is not None:
            if not prices_from_mpri:
                logger.info("   면적 불일치 → mpriByType 조회로 재시도")
                mpri_prices = self.get_complex_price(str(complex_id))
            else:
                mpri_prices = prices
            if mpri_prices:
                prices = mpri_prices
                prices_from_mpri = True
                matched_price = self.find_matching_price(prices, area)
            if not matched_price:
                fallback = self.find_price_by_same_price_area(str(complex_id), mpri_prices, area)
                if fallback:
                    matched_price = fallback
                    same_price_area_used = True

        # 고른 단지에 면적이 없고, 번지로 확정되지 않았을 때만
        # 같은 이름 형제 단지 중 정확 면적 1건으로 재선택 (꿈마을 시공사 형제)
        if not matched_price and area > 0 and complex_name:
            target_lot = _extract_lot_number_from_address(address)
            selected_addr = selected_complex.get("주소") or ""
            lot_confirmed = bool(
                target_lot and _lot_matches_complex_address(target_lot, selected_addr)
            )
            if not lot_confirmed:
                selected_id = selected_complex.get("단지기본일련번호")
                related_hits = []
                for c in complexes:
                    if c.get("단지기본일련번호") == selected_id:
                        continue
                    api_name = c.get("단지명") or c.get("name") or ""
                    if not _complex_names_related(complex_name, api_name):
                        continue
                    if _complex_has_exact_area(c, area) is True:
                        related_hits.append(c)
                if len(related_hits) == 1:
                    selected_complex = related_hits[0]
                    complex_id = selected_complex.get("단지기본일련번호")
                    logger.info(
                        "✅ 면적 교차검증으로 단지 재선택: %s (id=%s, %.2f㎡)",
                        selected_complex.get("단지명"), complex_id, area,
                    )
                    print(f"[OK] 면적 교차검증 재선택: {selected_complex.get('단지명')} ({area}㎡)")
                    prices = selected_complex.get("매매") or selected_complex.get("매매가") or []
                    prices_from_mpri = False
                    if not prices and complex_id is not None:
                        prices = self.get_complex_price(str(complex_id))
                        prices_from_mpri = True
                    matched_price = self.find_matching_price(prices, area)

        # 면적이 정확히 일치하는 타입이 없으면 시세는 쓰지 않는다 (가까운 면적으로 대체 금지).
        # 다만 단지는 이미 확정됐으므로 세대수·구분·참고링크는 이어서 채운다.
        if not matched_price:
            logger.warning(f"⚠️ 면적 {area}m²에 맞는 시세를 찾을 수 없음 → 단지 정보만 반환")
            print(f"[!] 면적 {area}m²에 맞는 시세를 찾을 수 없음 → 단지 정보만 반환")
            if prices:
                logger.warning(f"⚠️ 사용 가능한 면적: {[p.get('공급면적', 'N/A') for p in prices[:10]]}")
                print(f"[!] 사용 가능한 면적: {[p.get('공급면적', 'N/A') for p in prices[:10]]}")
            matched_price = {}

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
            # 등기부 면적이 KB 전용면적과 달라 '동일시세 전용면적' 목록으로 매칭했는지 (구축)
            "same_price_area_matched": same_price_area_used,
        }
        
        # 7. 재건축·세대수·사용승인일: 단지 목록 → complexMain/rcnsInfo → /c/ 스크래퍼 순으로 채우기
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
            # 단지 부가정보(세대수·동수·사용승인일·유형·재건축단계)는 KB API 우선.
            # complexMain 하나에 재건축여부·총세대수·총동수·준공일·유형이 모두 있어
            # complex/info는 따로 부르지 않는다(응답 필드가 전부 중복이라 호출만 늘어남).
            # /c/ 스크래퍼(Playwright)는 Chromium을 띄워 메모리·시간을 크게 쓰므로
            # API로 채우지 못한 항목이 있을 때만 보조로 호출한다.
            extra = self.get_complex_extra_via_api(str(complex_id))
            if extra.get("households") is None or extra.get("approval_date") is None:
                logger.info("   KB API로 단지정보 부족(세대수/사용승인일) → /c/ 스크래퍼 보조 호출")
                scraped = get_complex_extra_info(complex_id)
                for key in (
                    "households", "buildings", "approval_date", "years_since_completion",
                    "complex_type", "complex_name",
                ):
                    if extra.get(key) is None and scraped.get(key) is not None:
                        extra[key] = scraped[key]
                if not extra.get("redevelop_stages") and scraped.get("redevelop_stages"):
                    extra["redevelop_stages"] = scraped["redevelop_stages"]
                if scraped.get("redevelop_yn"):
                    extra["redevelop_yn"] = True
                if scraped.get("error"):
                    extra["error"] = scraped["error"]
            else:
                logger.debug("   KB API로 단지정보 확보 → Playwright 스크래핑 생략")
            if extra.get("approval_date") is not None:
                result["approval_date"] = extra["approval_date"]
                logger.info(f"✅ 사용승인일: {result['approval_date']}")
            if extra.get("years_since_completion") is not None:
                result["years_since_completion"] = extra["years_since_completion"]
                logger.info(f"✅ 년차: {result['years_since_completion']}년차")
            # 단지유형 (주상복합, 아파트, 오피스텔 등)
            if extra.get("complex_type") is not None:
                result["complex_type"] = extra["complex_type"]
                logger.info(f"✅ 단지유형: {result['complex_type']}")

            # 세대수·동수: 단지 총세대수(임대 포함)를 시세 타입별 세대수 합산보다 우선
            if extra.get("households") is not None:
                result["households"] = extra["households"]
                logger.info(f"✅ 세대수: {result['households']}세대")
            elif result["households"] is None:
                mpri_prices = prices if prices_from_mpri else self.get_complex_price(str(complex_id))
                if mpri_prices:
                    h_sum = sum(int(p.get("세대수") or 0) for p in mpri_prices)
                    if h_sum > 0:
                        result["households"] = h_sum
                        logger.info(f"✅ mpriByType 세대수 합산(fallback): {result['households']}")
            if extra.get("buildings") is not None:
                result["buildings"] = extra["buildings"]
                logger.info(f"✅ 동수: {result['buildings']}개동")

            # 재건축: 단계 목록이 있으면 재건축으로 간주 (complex/info의 재건축여부도 함께 반영)
            if extra.get("redevelop_yn") or extra.get("redevelop_stages"):
                result["redevelop_yn"] = True
            if result["redevelop_yn"]:
                result["redevelop_stages"] = extra.get("redevelop_stages") or []
                if not result["redevelop_stages"]:
                    # info만 재건축=1인 경우(단계 미확보) rcnsInfo로 한 번 더 시도
                    result["redevelop_stages"] = self.stages_from_rcns(self.get_rcns_info(str(complex_id)))
                if result["redevelop_stages"]:
                    print("[OK] 재건축 단계: %s" % ", ".join(
                        f"{s['step']}단계{s['name']}'{s['date']}" for s in result["redevelop_stages"]
                    ))
                logger.info(f"✅ 재건축 단계: {len(result['redevelop_stages'])}개")
                if extra.get("error"):
                    result["redevelop_error"] = extra["error"]
        
        if result["kb_price"] is not None:
            price_info = f"{result['kb_price']:,.0f}만원"
            if price_min_num:
                price_info += f" (하한: {price_min_num:,.0f}만원)"
        else:
            price_info = "시세없음"
        
        # 면적 차이 경고 (동일시세 전용면적 매칭은 KB가 같은 시세로 묶은 면적이므로 경고 아님)
        if area_diff and area_diff > 5.0:
            if same_price_area_used:
                logger.info(
                    f"   구축 등기면적 {area}m² → KB 동일시세 전용면적 {matched_area_val}m² 타입 적용"
                )
            else:
                logger.warning(f"[!] 면적 차이: {area_diff:.2f}m² (요청: {area}m², 매칭: {matched_area_val}m²)")
                print(f"[!] 면적 차이: {area_diff:.2f}m² (요청: {area}m², 매칭: {matched_area_val}m²)")
        
        logger.info(f"✅ KB 시세 조회 완료: {price_info} ({result['complex_name']})")
        logger.debug(f"   최종 결과: {result}")
        if result["kb_price"] is not None:
            print(f"[OK] KB 시세 조회 완료: {price_info} ({result['complex_name']})")
        else:
            print(f"[OK] KB 단지 식별 완료(시세없음): {result['complex_name']} / id={result.get('complex_id')}")
        return result


def get_kb_price_from_registry(address: str, area: str, registry_text: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    등기부 정보로 KB 시세 조회 (편의 함수)
    
    Args:
        address: 등기부에서 추출한 주소
        area: 등기부에서 추출한 면적 (문자열, 예: "84.93㎡" 또는 "84.93")
        registry_text: 등기부 원문 전체(선택). 주소에 "오피스텔"이 없어도
            표제부 건물내역에 업무시설/숙박시설이 있으면 KB 오피스텔 유형으로도 조회
    
    Returns:
        KB 시세 정보 딕셔너리 또는 None
    """
    logger.info(f"📄 등기부 정보로 KB 시세 조회 시작")
    logger.info(f"   등기부 주소: {address}")
    logger.info(f"   등기부 면적: {area}")

    force_officetel = _text_indicates_officetel(registry_text)
    if force_officetel and not _text_indicates_officetel(address):
        logger.info("   등기부 원문에 업무시설/숙박시설 문구 발견 → 오피스텔 유형 조회 강제")
    
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
    
    # 읍/면/리 주소는 행정구역·지번이 단지명 앞에 붙어 패턴에 통째로 잡히므로 앞부분을 잘라낸다
    # (동 단위 주소는 원본 그대로 → 기존 동작 불변)
    name_source = _strip_admin_prefix_for_complex_name(address)
    if name_source != address:
        logger.info(f"   읍/면/리 주소 → 단지명 추출 대상: {name_source}")

    # 주소에서 단지명 추출 (예: "미리내마을", "천안역우방아이유쉘", "힐스테이트 리버시티 1단지")
    complex_name = _extract_complex_name_from_address(name_source)
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
        match = re.search(pattern, name_source)
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
    
    # 번지수 + 한글 단지명 (제N동/제N층/제N호 앞까지)
    # 띄어쓰기 허용: "606 송파 레이크힐 제1501동" → 송파 레이크힐 (기존은 송파만 캡처)
    if not complex_name:
        lot_name_pattern = r'\d+(?:-\d+)?\s+([가-힣]+(?:\s+[가-힣]+)*)(?=\s+제\d+동|\s+제\d+층|\s+제\d+호|$)'
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
    
    # KB 시세 조회.
    # 다세대·연립·빌라 힌트가 있으면 아파트 목록(온천동 100여 개 + hscmList)을
    # 먼저 훑지 않고 빌라 AI시세·단지정보를 바로 가져온다.
    api = KBPriceAPI()
    villa = None
    villa_tried = False
    villa_hint = _text_indicates_villa_or_multi(registry_text) or _text_indicates_villa_or_multi(address)
    if villa_hint:
        logger.info("   다세대/연립/빌라 힌트 → 빌라 AI시세 경로 우선")
        villa = api.get_villa_kb_ai_price(
            address, area_float, complex_name=complex_name, hint_text=registry_text
        )
        villa_tried = True
        if villa and (villa.get("kb_ai_price") or villa.get("complex_id")):
            return villa

    result = api.get_kb_price(
        address, area_float, complex_name=complex_name, force_officetel=force_officetel
    )
    if result and result.get("kb_price"):
        return result

    if not villa_tried:
        villa = api.get_villa_kb_ai_price(
            address, area_float, complex_name=complex_name, hint_text=registry_text
        )
    if not villa:
        return result
    if not result:
        return villa

    # 공식시세는 없지만 아파트 단지가 이미 식별된 경우:
    # 같은 단지일 때만 AI시세를 얹고, 다른 단지면 아파트 식별 결과를 유지한다.
    result_cid = str(result.get("complex_id") or "")
    villa_cid = str(villa.get("complex_id") or "")
    if result_cid and villa_cid and result_cid != villa_cid:
        logger.info(
            "빌라 AI시세 단지가 기존 식별 단지와 다름 → AI시세 생략 (apt=%s, villa=%s)",
            result_cid, villa_cid,
        )
        return result
    for key, value in villa.items():
        if key.startswith("kb_ai") or key.startswith("villa_"):
            result[key] = value
        elif result.get(key) in (None, "", [], False) and value not in (None, "", []):
            result[key] = value
    return result
