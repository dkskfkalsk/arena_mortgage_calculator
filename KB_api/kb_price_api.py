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
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)

# Vercel 환경 로그
if is_vercel:
    logger.info("🔵 Vercel 환경 감지 - 로그는 Vercel 대시보드에서 확인하세요")


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
        # 시/군을 먼저 찾고, 그 다음 구를 찾아야 함
        # 패턴: "경기도 부천시 원미구" -> "부천시" 추출
        district_patterns = [
            r'(?:시|도)\s+([가-힣]+시)\s+[가-힣]+구',  # "경기도 부천시 원미구" -> "부천시" (우선)
            r'(?:시|도)\s+([가-힣]+시|[가-힣]+군)',  # "경기도 수원시" -> "수원시"
        ]
        
        for pattern in district_patterns:
            match = re.search(pattern, address)
            if match:
                result["district"] = match.group(1)
                logger.debug(f"   구/시/군 추출: {match.group(1)}")
                break
        
        # 동/읍/면 추출 (제217동, 제1105호 같은 '제' 제거)
        # 전국 데이터 구조: "권선구 곡반정동" 형식으로 저장됨
        # "경기도 수원시 권선구 곡반정동" -> dong="권선구 곡반정동"으로 추출
        # "서울특별시 종로구 청운동" -> dong="청운동"으로 추출
        
        # 패턴 1: "경기도 수원시 권선구 곡반정동" -> "권선구 곡반정동" 추출
        # 패턴 2: "서울특별시 종로구 청운동" -> "청운동" 추출
        dong_patterns = [
            r'(?:시|도)\s+[가-힣]+(?:시|구|군)\s+([가-힣]+(?:구|군|시)\s+[가-힣]+(?:동|읍|면))',  # "원미구 중동", "권선구 곡반정동" 형식
            r'(?:구|군|시)\s+([가-힣]+(?:구|군|시)?\s*[가-힣]+(?:동|읍|면))',  # "원미구 중동", "권선구 곡반정동" 같은 경우
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
                result["dong"] = dong_cleaned
                logger.debug(f"   동 추출: {dong_raw} -> {dong_cleaned}")
                dong_found = True
                break
        
        if not dong_found:
            logger.warning(f"⚠️ 동/읍/면을 찾을 수 없음: {address}")
        
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
        
        logger.debug(f"   파싱된 주소 정보: region={region}, district={district}, dong={dong}")
        
        if not all([region, district, dong]):
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
            # 유사 구/시/군명 찾기 시도
            for key in districts.keys():
                if district in key or key in district:
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
        else:
            logger.warning(f"법정동코드를 찾을 수 없음: {region} {district} {dong}")
            return None
    
    def get_complex_list(self, dongcode: str) -> List[Dict[str, Any]]:
        """
        법정동코드로 단지 목록 조회
        
        Args:
            dongcode: 법정동코드 (10자리)
        
        Returns:
            단지 목록 리스트
        """
        url = f"{self.base_url}/land-price/price/fastPriceInfo"
        params = {
            "법정동코드": dongcode,
            "유형": "1",  # 아파트
            "거래유형": "0"  # 매매
        }
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=15)
                response.raise_for_status()
                data = response.json()
                complexes = data.get("dataBody", {}).get("data", [])
                print(f"[OK] 단지 목록 조회 성공: {len(complexes)}개 단지")
                return complexes
            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                if attempt < max_retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                print(f"[X] 단지 목록 조회 실패(연결 끊김): {e}")
                return []
            except requests.exceptions.RequestException as e:
                print(f"[X] 단지 목록 조회 실패: {e}")
                return []
            except Exception as e:
                print(f"[X] 단지 목록 조회 오류: {e}")
                return []
        return []
    
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
        
        # 1. 법정동코드 찾기
        logger.debug("1단계: 법정동코드 찾기")
        dongcode = self.find_dongcode(address)
        if not dongcode:
            logger.error("❌ 법정동코드를 찾을 수 없어 시세 조회 불가")
            print("[X] 법정동코드를 찾을 수 없어 시세 조회 불가")
            return None
        
        logger.info(f"✅ 법정동코드: {dongcode}")
        
        # 2. 단지 목록 조회
        logger.debug("2단계: 단지 목록 조회")
        complexes = self.get_complex_list(dongcode)
        if not complexes:
            logger.error("❌ 단지 목록을 찾을 수 없음")
            print("[X] 단지 목록을 찾을 수 없음")
            return None
        
        logger.info(f"✅ 단지 목록 조회 성공: {len(complexes)}개 단지")
        
        # 3. 단지 선택 (단지명이 있으면 우선 매칭)
        logger.debug("3단계: 단지 선택")
        selected_complex = None
        
        # 주소에서 번지수 추출 (예: "1180-1", "1180")
        lot_number = None
        lot_match = re.search(r'(\d+(?:-\d+)?)', address)
        if lot_match:
            lot_number = lot_match.group(1)
            logger.debug(f"   주소에서 번지수 추출: {lot_number}")
        
        if complex_name:
            logger.debug(f"   단지명으로 매칭 시도: {complex_name}")
            # 단지명 매칭 우선순위: 정확 매칭 > 부분 매칭 (앞부분) > 부분 매칭 (뒷부분)
            best_match = None
            best_score = 0
            
            for i, complex in enumerate(complexes):
                complex_name_from_api = complex.get("단지명") or complex.get("name", "")
                complex_address_from_api = complex.get("주소", "")
                logger.debug(f"   [{i+1}] {complex_name_from_api} (주소: {complex_address_from_api})")
                
                # 정확 매칭
                if complex_name == complex_name_from_api:
                    selected_complex = complex
                    logger.info(f"✅ 단지명 정확 매칭: {complex_name_from_api}")
                    print(f"[OK] 단지명 정확 매칭: {complex_name_from_api}")
                    break
                
                # 부분 매칭 점수 계산 (더 긴 매칭이 우선)
                # 예: "미리내마을" in "미리내마을(롯데2)" -> True
                score = 0
                if complex_name in complex_name_from_api:
                    # 매칭 비율 계산 (추출한 단지명이 API 단지명에 포함된 비율)
                    score = len(complex_name) / len(complex_name_from_api.replace('(', '').replace(')', ''))
                    # 괄호 안 내용이 있어도 매칭되면 점수 보정
                    if '(' in complex_name_from_api:
                        base_name = complex_name_from_api.split('(')[0]
                        if complex_name == base_name or complex_name in base_name:
                            score = 0.9  # 높은 점수 부여
                elif complex_name_from_api in complex_name:
                    score = len(complex_name_from_api) / len(complex_name)
                
                # 번지수 매칭 보너스 (번지수가 일치하면 점수 증가)
                if lot_number and lot_number in complex_address_from_api:
                    score += 0.2  # 번지수 일치 시 보너스
                    logger.debug(f"      번지수 일치 보너스: {lot_number}")
                
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
        
        # 단지명 매칭 실패 시 첫 번째 단지 사용
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
        if not prices and complex_id is not None:
            logger.info("   fastPriceInfo에 매매 없음 → get_complex_price 호출")
            print("[*] 단지 시세 별도 조회 중...")
            prices = self.get_complex_price(str(complex_id))
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
        # find_matching_price에서 이미 가장 가까운 면적을 찾아서 반환하므로
        # 여기서는 None인 경우만 처리
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
        }
        
        # 7. 재건축·세대수: 단지 목록 → get_complex_info → /c/ 스크래퍼 순으로 세대수/동수 채우기
        result["redevelop_stages"] = []
        result["households"] = None
        result["buildings"] = None
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
            # /c/ 스크래퍼: 재건축이면 단계+세대수·동수, 일반 단지면 세대수·동수만 (아직 None일 때)
            extra = get_complex_extra_info(complex_id)
            if result["redevelop_yn"]:
                result["redevelop_stages"] = extra.get("redevelop_stages") or []
                if extra.get("households") is not None:
                    result["households"] = extra["households"]
                if extra.get("buildings") is not None:
                    result["buildings"] = extra["buildings"]
                if extra.get("error"):
                    result["redevelop_error"] = extra["error"]
            else:
                # 일반 단지: 스크래퍼에서 세대수·동수만 채우기 (API에 없을 때)
                if result["households"] is None and extra.get("households") is not None:
                    result["households"] = extra["households"]
                    logger.info(f"✅ 스크래퍼에서 세대수 추출: {result['households']}")
                if result["buildings"] is None and extra.get("buildings") is not None:
                    result["buildings"] = extra["buildings"]
                    logger.info(f"✅ 스크래퍼에서 동수 추출: {result['buildings']}")
        
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
    
    # 면적에서 숫자만 추출
    area_match = re.search(r'([\d.]+)', str(area))
    if not area_match:
        logger.error(f"⚠️ 면적 파싱 실패: {area}")
        print(f"[!] 면적 파싱 실패: {area}")
        return None
    
    try:
        area_float = float(area_match.group(1))
        logger.debug(f"   추출된 면적: {area_float}m²")
    except ValueError:
        logger.error(f"⚠️ 면적 변환 실패: {area}")
        print(f"[!] 면적 변환 실패: {area}")
        return None
    
    # 주소에서 단지명 추출 (예: "미리내마을", "수원하늘채더퍼스트2단지")
    # 패턴: 주소 중간에 있는 단지명 패턴 찾기
    complex_name = None
    # "미리내마을", "수원하늘채더퍼스트2단지" 같은 패턴 찾기
    complex_patterns = [
        r'([가-힣]+마을)',  # "미리내마을", "꿈마을"
        r'([가-힣]+단지)',  # "수원하늘채더퍼스트2단지"
        r'([가-힣]+아파트)',  # "대치아이파크아파트"
        r'([가-힣]+힐스|힐스테이트)',  # "힐스테이트중동"
        r'([가-힣]+(?:아이파크|래미안|자이|힐스테이트|푸르지오|센트럴|팰리스|월드|뉴|더|디|엘|리|그린|보람|연화|은하|중흥|한라|포도|무지개|꿈|덕유|설악|복사골|금강|동원|대신|범양|영안|현대|형진|풍남))',  # 주요 단지명 키워드
    ]
    
    for pattern in complex_patterns:
        match = re.search(pattern, address)
        if match:
            complex_name = match.group(1)
            logger.info(f"✅ 주소에서 단지명 추출: {complex_name}")
            break
    
    # 단지명이 없으면 주소에서 번지수 앞의 단어를 단지명으로 추출 시도
    # 예: "중동 1180-1 미리내마을" -> "미리내마을"
    if not complex_name:
        # 번지수 패턴: 숫자-숫자 또는 숫자만
        lot_pattern = r'(\d+(?:-\d+)?)\s+([가-힣]+(?:마을|단지|아파트)?)'
        match = re.search(lot_pattern, address)
        if match:
            potential_name = match.group(2)
            # 너무 짧거나 일반적인 단어는 제외
            if len(potential_name) >= 2 and potential_name not in ['동', '구', '시', '군', '읍', '면']:
                complex_name = potential_name
                logger.info(f"✅ 주소에서 단지명 추출 (번지수 기준): {complex_name}")
    
    # KB 시세 조회
    api = KBPriceAPI()
    return api.get_kb_price(address, area_float, complex_name=complex_name)
