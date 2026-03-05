# -*- coding: utf-8 -*-
"""
KB 부동산 시세 API 호출 모듈
등기부에서 추출한 주소와 면적을 기반으로 KB 시세를 자동으로 조회합니다.
"""

import json
import os
import re
import time
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
        
        # 주소에서 번지수 추출 (예: "1180-1", "1180", "1588")
        lot_number = None
        lot_match = re.search(r'(\d+(?:-\d+)?)', address)
        if lot_match:
            lot_number = lot_match.group(1)
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
                # API 단지명 공백 제거 (ex: "천안역 우방 아이유쉘" vs "천안역우방아이유쉘")
                api_name_nospace = (complex_name_from_api or "").replace(" ", "")
                
                # 정확 매칭 (공백 무시 포함)
                if complex_name == complex_name_from_api or (api_name_nospace and complex_name == api_name_nospace):
                    selected_complex = complex
                    logger.info(f"✅ 단지명 정확 매칭: {complex_name_from_api}")
                    print(f"[OK] 단지명 정확 매칭: {complex_name_from_api}")
                    break
                
                # 부분 매칭 점수 계산 (더 긴 매칭이 우선)
                # 예: "미리내마을" in "미리내마을(롯데2)" -> True
                score = 0
                base_api = (complex_name_from_api or "").replace(" ", "").replace("(", "").replace(")", "")
                if complex_name in complex_name_from_api or (base_api and complex_name in base_api):
                    denom = len(base_api) or 1
                    score = len(complex_name) / denom
                    if '(' in (complex_name_from_api or ""):
                        base_name = (complex_name_from_api.split('(')[0] or "").replace(" ", "")
                        if base_name and (complex_name == base_name or complex_name in base_name):
                            score = 0.9
                elif complex_name_from_api in complex_name or (base_api and base_api in complex_name):
                    score = len(base_api or complex_name_from_api or "") / len(complex_name)
                
                # 번지수 매칭 보너스 (번지수가 일치하면 점수 증가)
                if lot_number and lot_number in complex_address_from_api:
                    score += 0.2  # 번지수 일치 시 보너스
                    logger.debug(f"      번지수 일치 보너스: {lot_number}")
                # 동+번지 매칭 보너스: 단지명이 비슷한 후보가 여러 개일 때,
                # API 단지 주소에 "관양동"과 "1588"이 둘 다 들어 있으면 그 단지를 더 우선 선택
                if dong_name and lot_number and dong_name in complex_address_from_api and lot_number in complex_address_from_api:
                    score += 0.35
                    logger.debug(f"      동+번지 매칭 보너스: {dong_name} {lot_number}")
                
                if score > best_score:
                    best_score = score
                    best_match = complex
                    logger.debug(f"      매칭 발견: {complex_name_from_api} (점수: {score:.2f})")
            
            # 부분 매칭 결과 사용
            if not selected_complex and best_match:
                selected_complex = best_match
                complex_name_from_api = selected_complex.get('단지명', '알 수 없음')
                logger.info(f"✅ 단지명 부분 매칭: {complex_name_from_api} (점수: {best_score:.2f})")
                print(f"[OK] 단지명 부분 매칭: {complex_name_from_api}")
        
        # 단지명 없을 때: 동+번지로 단지 선택 (예: 관양동 1588 직접 검색)
        if not selected_complex and dong_name and lot_number:
            for complex in complexes:
                complex_address_from_api = (complex.get("주소") or "").strip()
                if dong_name in complex_address_from_api and lot_number in complex_address_from_api:
                    selected_complex = complex
                    logger.info(f"✅ 동+번지 매칭: {dong_name} {lot_number} → {complex.get('단지명', '')} (주소: {complex_address_from_api})")
                    print(f"[OK] 동+번지 매칭: {dong_name} {lot_number} → {complex.get('단지명', '')}")
                    break
        
        # 단지명/동+번지 매칭 실패 시: 주소에서 단지명이 추출된 경우 잘못된 단지 사용 금지
        # (예: 거제코아루파크드림인데 지세포골드캐슬 시세 표시 방지)
        if not selected_complex:
            if complex_name:
                logger.warning(f"⚠️ 단지명 '{complex_name}' 매칭 실패. 잘못된 시세 표시 방지를 위해 KB 시세 생략")
                print(f"[!] 단지명 '{complex_name}' 매칭 실패. KB 시세 없이 다른 정보만 추출합니다.")
                return None
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
            logger.error(f"❌ 시세 가격 정보가 없음. 매칭된 데이터: {matched_price}")
            print("[X] 시세 가격 정보가 없음")
            return None
        
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
        
        if price_num is None:
            print(f"[X] 시세 가격 파싱 실패: {price_value}")
            return None
        
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
            "kb_price_raw": f"{price_num:,.0f}만원",
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
        
        price_info = f"{result['kb_price']:,.0f}만원"
        if price_min_num:
            price_info += f" (하한: {price_min_num:,.0f}만원)"
        
        # 면적 차이 경고
        if area_diff and area_diff > 5.0:
            logger.warning(f"[!] 면적 차이: {area_diff:.2f}m² (요청: {area}m², 매칭: {matched_area_val}m²)")
            print(f"[!] 면적 차이: {area_diff:.2f}m² (요청: {area}m², 매칭: {matched_area_val}m²)")
        
        logger.info(f"✅ KB 시세 조회 완료: {price_info} ({result['complex_name']})")
        logger.debug(f"   최종 결과: {result}")
        print(f"[OK] KB 시세 조회 완료: {price_info} ({result['complex_name']})")
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
    
    # 주소에서 단지명 추출 (예: "미리내마을", "천안역우방아이유쉘")
    # KB 사이트는 "성우아뜨리움"처럼 접미사 없이 표기하는 경우가 많음 → 접미사 제거하여 매칭
    complex_name = None
    complex_patterns = [
        r'([가-힣]+)오피스텔',   # 성우아뜨리움오피스텔 → 성우아뜨리움 (KB: 성우아뜨리움)
        r'([가-힣]+)아파트',    # 성우아파트 → 성우
        r'([가-힣]+)빌라',      # OO빌라 → OO
        r'([가-힣]+)다가구',    # OO다가구 또는 다가구
        r'([가-힣]+마을)',
        r'([가-힣]+단지)',
        r'([가-힣]+(?:힐스|힐스테이트))',
        r'([가-힣]+(?:아이파크|래미안|자이|힐스테이트|푸르지오|센트럴|팰리스|월드|뉴|더|디|엘|리|그린|보람|연화|은하|중흥|한라|포도|무지개|꿈|덕유|설악|복사골|금강|동원|대신|범양|영안|현대|형진|풍남|우방|아이유쉘|유쉘))',
    ]
    for pattern in complex_patterns:
        match = re.search(pattern, address)
        if match:
            complex_name = match.group(1)
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
                if len(complex_name) >= 2:
                    logger.info(f"✅ 주소에서 단지명 추출 (필지+이름): {complex_name}")
    
    # 번지수 + 한글 단지명 (제N동/제N층/제N호 앞까지) ex: "1562 천안역우방아이유쉘 제104동"
    if not complex_name:
        lot_name_pattern = r'\d+(?:-\d+)?\s+([가-힣]+?)(?=\s+제\d+동|\s+제\d+층|\s+제\d+호|$)'
        match = re.search(lot_name_pattern, address)
        if match:
            potential_name = match.group(1).strip()
            if len(potential_name) >= 2 and potential_name not in ('동', '구', '시', '군', '읍', '면'):
                complex_name = potential_name
                logger.info(f"✅ 주소에서 단지명 추출 (번지+이름): {complex_name}")
    
    # 기존: 번지수 + (마을|단지|아파트) ex: "1180-1 미리내마을"
    if not complex_name:
        lot_pattern = r'(\d+(?:-\d+)?)\s+([가-힣]+(?:마을|단지|아파트)?)'
        match = re.search(lot_pattern, address)
        if match:
            potential_name = match.group(2)
            if len(potential_name) >= 2 and potential_name not in ('동', '구', '시', '군', '읍', '면'):
                complex_name = potential_name
                logger.info(f"✅ 주소에서 단지명 추출 (번지수 기준): {complex_name}")
    
    # KB 시세 조회
    api = KBPriceAPI()
    return api.get_kb_price(address, area_float, complex_name=complex_name)
