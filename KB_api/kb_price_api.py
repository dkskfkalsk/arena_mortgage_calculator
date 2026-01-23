# -*- coding: utf-8 -*-
"""
KB 부동산 시세 API 호출 모듈
등기부에서 추출한 주소와 면적을 기반으로 KB 시세를 자동으로 조회합니다.
"""

import json
import os
import re
import requests
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path


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
            # 자동으로 찾기 (KB_api 폴더 기준으로 상위 폴더에서 찾기)
            current_dir = Path(__file__).parent
            project_root = current_dir.parent
            possible_paths = [
                project_root / "kbland_price-main" / "static" / "combined_dongcode_data.json",
                project_root / "kbland_price-main" / "static" / "서울_dongcode_data.json",
                project_root / "kbland_price-main" / "static" / "경기도_dongcode_data.json",
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
                    print(f"✅ 법정동코드 데이터 로드 완료: {data_path}")
            except Exception as e:
                print(f"⚠️ 법정동코드 데이터 로드 실패: {e}")
                self.dongcode_data = {}
        else:
            print("⚠️ 법정동코드 데이터 파일을 찾을 수 없습니다.")
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
        if not address:
            return {}
        
        # 주소 정규화 (공백 정리)
        address = re.sub(r'\s+', ' ', address.strip())
        
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
        district_pattern = r'(?:시|도)\s+([가-힣]+(?:시|구|군))'
        match = re.search(district_pattern, address)
        if match:
            result["district"] = match.group(1)
        
        # 동/읍/면 추출
        dong_pattern = r'(?:구|군|시)\s+([가-힣]+(?:동|읍|면))'
        match = re.search(dong_pattern, address)
        if match:
            result["dong"] = match.group(1)
        
        # 상세 주소 (나머지)
        if result.get("dong"):
            detail_start = address.find(result["dong"]) + len(result["dong"])
            result["detail"] = address[detail_start:].strip()
        
        return result
    
    def find_dongcode(self, address: str) -> Optional[str]:
        """
        주소에서 법정동코드 찾기
        
        Args:
            address: 주소 문자열
        
        Returns:
            법정동코드 (10자리 문자열) 또는 None
        """
        if not self.dongcode_data:
            print("⚠️ 법정동코드 데이터가 로드되지 않았습니다.")
            return None
        
        parsed = self.parse_address(address)
        region = parsed.get("region")
        district = parsed.get("district")
        dong = parsed.get("dong")
        
        if not all([region, district, dong]):
            print(f"⚠️ 주소 파싱 실패: {address}")
            return None
        
        # 데이터에서 찾기
        region_data = self.dongcode_data.get(region, {})
        districts = region_data.get("districts", {})
        district_data = districts.get(district, {})
        dongs = district_data.get("dongs", {})
        dong_data = dongs.get(dong, {})
        
        dongcode = dong_data.get("code")
        
        if dongcode:
            print(f"✅ 법정동코드 찾음: {dongcode} ({region} {district} {dong})")
            return dongcode
        else:
            print(f"⚠️ 법정동코드를 찾을 수 없음: {region} {district} {dong}")
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
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ko-KR,ko;q=0.9',
            'Cache-Control': 'no-cache',
            'Origin': 'https://kbland.kr',
            'Referer': 'https://kbland.kr/'
        }
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            complexes = data.get("dataBody", {}).get("data", [])
            
            print(f"✅ 단지 목록 조회 성공: {len(complexes)}개 단지")
            return complexes
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 단지 목록 조회 실패: {e}")
            return []
        except Exception as e:
            print(f"❌ 단지 목록 조회 오류: {e}")
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
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Origin': 'https://kbland.kr',
            'Referer': 'https://kbland.kr/'
        }
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            prices = data.get("dataBody", {}).get("data", [])
            
            print(f"✅ 단지 시세 조회 성공: {len(prices)}개 타입")
            return prices
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 단지 시세 조회 실패: {e}")
            return []
        except Exception as e:
            print(f"❌ 단지 시세 조회 오류: {e}")
            return []
    
    def find_matching_price(self, prices: List[Dict[str, Any]], area: float, 
                           tolerance: float = 5.0) -> Optional[Dict[str, Any]]:
        """
        면적에 맞는 시세 찾기
        
        Args:
            prices: 평형별 시세 리스트
            area: 전용면적 (m²)
            tolerance: 허용 오차 (m², 기본 5.0)
        
        Returns:
            가장 가까운 시세 정보 또는 None
        """
        if not prices or area <= 0:
            return None
        
        best_match = None
        min_diff = float('inf')
        
        for price_info in prices:
            # 공급면적 추출
            supply_area_str = price_info.get("공급면적") or price_info.get("면적", "")
            if not supply_area_str:
                continue
            
            try:
                supply_area = float(str(supply_area_str).strip())
            except (ValueError, TypeError):
                continue
            
            # 면적 차이 계산
            diff = abs(supply_area - area)
            
            # 허용 오차 내이고 가장 가까운 것 선택
            if diff <= tolerance and diff < min_diff:
                min_diff = diff
                best_match = price_info
        
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
                "kb_price": 125000,  # 만원 단위
                "kb_price_raw": "125,000만원",
                "complex_name": "대치아이파크",
                "area": 84.93,
                "pyeong": 25.7,
                "type": "84A형"
            } 또는 None
        """
        print(f"\n🔍 KB 시세 조회 시작")
        print(f"   주소: {address}")
        print(f"   면적: {area}m²")
        
        # 1. 법정동코드 찾기
        dongcode = self.find_dongcode(address)
        if not dongcode:
            print("❌ 법정동코드를 찾을 수 없어 시세 조회 불가")
            return None
        
        # 2. 단지 목록 조회
        complexes = self.get_complex_list(dongcode)
        if not complexes:
            print("❌ 단지 목록을 찾을 수 없음")
            return None
        
        # 3. 단지 선택 (단지명이 있으면 우선 매칭)
        selected_complex = None
        if complex_name:
            for complex in complexes:
                complex_name_from_api = complex.get("단지명") or complex.get("name", "")
                if complex_name in complex_name_from_api or complex_name_from_api in complex_name:
                    selected_complex = complex
                    print(f"✅ 단지명으로 매칭: {complex_name_from_api}")
                    break
        
        # 단지명 매칭 실패 시 첫 번째 단지 사용
        if not selected_complex:
            selected_complex = complexes[0]
            print(f"⚠️ 단지명 매칭 실패, 첫 번째 단지 사용: {selected_complex.get('단지명', '알 수 없음')}")
        
        complex_id = selected_complex.get("단지기본일련번호") or selected_complex.get("id")
        if not complex_id:
            print("❌ 단지 ID를 찾을 수 없음")
            return None
        
        # 4. 단지 시세 조회
        prices = self.get_complex_price(str(complex_id))
        if not prices:
            print("❌ 시세 정보를 찾을 수 없음")
            return None
        
        # 5. 면적에 맞는 시세 찾기
        matched_price = self.find_matching_price(prices, area)
        if not matched_price:
            print(f"⚠️ 면적 {area}m²에 맞는 시세를 찾을 수 없음 (허용 오차: 5m²)")
            # 가장 가까운 것이라도 반환
            if prices:
                matched_price = prices[0]
                print(f"⚠️ 첫 번째 시세 사용: {matched_price.get('공급면적', 'N/A')}m²")
        
        # 6. 결과 구성
        price_value = matched_price.get("매매일반거래가") or matched_price.get("매매가") or matched_price.get("매매평균가")
        if not price_value:
            print("❌ 시세 가격 정보가 없음")
            return None
        
        # 가격을 숫자로 변환 (만원 단위)
        try:
            if isinstance(price_value, str):
                price_value = price_value.replace(",", "").replace("만원", "").strip()
            price_num = float(price_value)
        except (ValueError, TypeError):
            print(f"❌ 시세 가격 파싱 실패: {price_value}")
            return None
        
        result = {
            "kb_price": price_num,  # 만원 단위
            "kb_price_raw": f"{price_num:,.0f}만원",
            "complex_name": selected_complex.get("단지명") or selected_complex.get("name", "알 수 없음"),
            "area": float(matched_price.get("공급면적") or area),
            "pyeong": matched_price.get("공급면적평N") or matched_price.get("평수", ""),
            "type": matched_price.get("주택형타입내용") or matched_price.get("타입", ""),
        }
        
        print(f"✅ KB 시세 조회 완료: {result['kb_price']:,.0f}만원 ({result['complex_name']})")
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
    # 면적에서 숫자만 추출
    area_match = re.search(r'([\d.]+)', str(area))
    if not area_match:
        print(f"⚠️ 면적 파싱 실패: {area}")
        return None
    
    try:
        area_float = float(area_match.group(1))
    except ValueError:
        print(f"⚠️ 면적 변환 실패: {area}")
        return None
    
    # KB 시세 조회
    api = KBPriceAPI()
    return api.get_kb_price(address, area_float)
