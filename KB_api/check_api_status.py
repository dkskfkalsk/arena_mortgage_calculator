# -*- coding: utf-8 -*-
"""
KB 시세 API 상태 확인 스크립트
API가 정상 작동하는지 확인합니다.
"""

import requests
import json
from typing import Dict, Any


def check_api_health():
    """KB API 기본 상태 확인"""
    print("=" * 60)
    print("🔍 KB 시세 API 상태 확인")
    print("=" * 60)
    print()
    
    base_url = "https://api.kbland.kr"
    
    # 테스트용 법정동코드 (서울 강남구 대치동)
    test_dongcode = "1168010600"
    
    # 1. 단지 목록 조회 API 테스트
    print("1️⃣ 단지 목록 조회 API 테스트")
    print("-" * 60)
    
    url1 = f"{base_url}/land-price/price/fastPriceInfo"
    params1 = {
        "법정동코드": test_dongcode,
        "유형": "1",  # 아파트
        "거래유형": "0"  # 매매
    }
    
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'ko-KR,ko;q=0.9',
        'Cache-Control': 'no-cache',
        'Origin': 'https://kbland.kr',
        'Referer': 'https://kbland.kr/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        print(f"📡 요청 URL: {url1}")
        print(f"📋 파라미터: {params1}")
        print(f"🔗 헤더: {json.dumps(headers, indent=2, ensure_ascii=False)}")
        print()
        
        response = requests.get(url1, params=params1, headers=headers, timeout=10)
        
        print(f"📊 응답 상태 코드: {response.status_code}")
        print(f"📝 응답 헤더:")
        for key, value in response.headers.items():
            if key.lower() in ['content-type', 'content-length', 'server', 'date']:
                print(f"   {key}: {value}")
        print()
        
        if response.status_code == 200:
            try:
                data = response.json()
                print("✅ API 응답 성공!")
                print(f"📦 응답 데이터 구조:")
                print(f"   - 최상위 키: {list(data.keys())}")
                
                if 'dataBody' in data:
                    data_body = data['dataBody']
                    print(f"   - dataBody 키: {list(data_body.keys()) if isinstance(data_body, dict) else 'N/A'}")
                    
                    if 'data' in data_body:
                        complexes = data_body['data']
                        if isinstance(complexes, list):
                            print(f"   - 단지 개수: {len(complexes)}개")
                            if len(complexes) > 0:
                                print(f"   - 첫 번째 단지 예시:")
                                first_complex = complexes[0]
                                for key, value in list(first_complex.items())[:5]:
                                    print(f"     {key}: {value}")
                        else:
                            print(f"   - data 타입: {type(complexes)}")
                            print(f"   - data 내용: {complexes}")
                
                # 전체 응답 일부 출력
                print()
                print("📄 응답 데이터 (처음 500자):")
                response_text = json.dumps(data, ensure_ascii=False, indent=2)
                print(response_text[:500])
                if len(response_text) > 500:
                    print("... (생략)")
                
                return True, data
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON 파싱 실패: {e}")
                print(f"📄 응답 텍스트 (처음 500자):")
                print(response.text[:500])
                return False, None
        else:
            print(f"❌ API 응답 실패: HTTP {response.status_code}")
            print(f"📄 응답 내용:")
            print(response.text[:500])
            return False, None
            
    except requests.exceptions.Timeout:
        print("❌ 요청 타임아웃 (10초 초과)")
        return False, None
    except requests.exceptions.ConnectionError as e:
        print(f"❌ 연결 오류: {e}")
        print("   - 네트워크 연결을 확인하세요")
        print("   - KB API 서버가 다운되었을 수 있습니다")
        return False, None
    except requests.exceptions.RequestException as e:
        print(f"❌ 요청 오류: {e}")
        return False, None
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def check_complex_price_api(complex_id: str = None):
    """단지 시세 조회 API 테스트"""
    print()
    print("=" * 60)
    print("2️⃣ 단지 시세 조회 API 테스트")
    print("=" * 60)
    print()
    
    if not complex_id:
        # 테스트용 단지 ID (대치아이파크)
        complex_id = "341954"
        print(f"⚠️ 단지 ID가 제공되지 않아 테스트 ID 사용: {complex_id}")
    
    base_url = "https://api.kbland.kr"
    url = f"{base_url}/land-complex/complex/mpriByType"
    params = {
        "단지기본일련번호": complex_id
    }
    
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Origin': 'https://kbland.kr',
        'Referer': 'https://kbland.kr/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        print(f"📡 요청 URL: {url}")
        print(f"📋 파라미터: {params}")
        print()
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        print(f"📊 응답 상태 코드: {response.status_code}")
        print()
        
        if response.status_code == 200:
            try:
                data = response.json()
                print("✅ API 응답 성공!")
                print(f"📦 응답 데이터 구조:")
                print(f"   - 최상위 키: {list(data.keys())}")
                
                if 'dataBody' in data:
                    data_body = data['dataBody']
                    if 'data' in data_body:
                        prices = data_body['data']
                        if isinstance(prices, list):
                            print(f"   - 시세 타입 개수: {len(prices)}개")
                            if len(prices) > 0:
                                print(f"   - 첫 번째 시세 예시:")
                                first_price = prices[0]
                                for key, value in list(first_price.items())[:5]:
                                    print(f"     {key}: {value}")
                
                return True, data
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON 파싱 실패: {e}")
                print(f"📄 응답 텍스트 (처음 500자):")
                print(response.text[:500])
                return False, None
        else:
            print(f"❌ API 응답 실패: HTTP {response.status_code}")
            print(f"📄 응답 내용:")
            print(response.text[:500])
            return False, None
            
    except Exception as e:
        print(f"❌ 오류 발생: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def check_network_connectivity():
    """네트워크 연결 확인"""
    print()
    print("=" * 60)
    print("3️⃣ 네트워크 연결 확인")
    print("=" * 60)
    print()
    
    test_urls = [
        ("KB API 기본 도메인", "https://api.kbland.kr"),
        ("KB 부동산 웹사이트", "https://kbland.kr"),
        ("일반 인터넷 연결", "https://www.google.com"),
    ]
    
    for name, url in test_urls:
        try:
            print(f"🔍 {name} 연결 확인: {url}")
            response = requests.get(url, timeout=5)
            print(f"   ✅ 연결 성공 (상태 코드: {response.status_code})")
        except requests.exceptions.Timeout:
            print(f"   ⏱️ 타임아웃")
        except requests.exceptions.ConnectionError:
            print(f"   ❌ 연결 실패")
        except Exception as e:
            print(f"   ❌ 오류: {e}")
        print()


def main():
    """메인 함수"""
    print()
    print("🚀 KB 시세 API 상태 확인 시작")
    print()
    
    # 네트워크 연결 확인
    check_network_connectivity()
    
    # API 상태 확인
    success1, data1 = check_api_health()
    
    # 단지 시세 API 확인
    if success1 and data1:
        # 첫 번째 단지 ID 추출 시도
        complex_id = None
        try:
            if 'dataBody' in data1 and 'data' in data1['dataBody']:
                complexes = data1['dataBody']['data']
                if isinstance(complexes, list) and len(complexes) > 0:
                    complex_id = complexes[0].get('단지기본일련번호') or complexes[0].get('id')
        except:
            pass
        
        check_complex_price_api(complex_id)
    
    # 최종 요약
    print()
    print("=" * 60)
    print("📋 최종 요약")
    print("=" * 60)
    print()
    
    if success1:
        print("✅ 단지 목록 조회 API: 정상 작동")
    else:
        print("❌ 단지 목록 조회 API: 오류 발생")
        print()
        print("💡 문제 해결 방법:")
        print("   1. 네트워크 연결 확인")
        print("   2. KB API 서버 상태 확인 (https://kbland.kr)")
        print("   3. 방화벽/프록시 설정 확인")
        print("   4. API 엔드포인트 변경 여부 확인")
        print("   5. CORS 정책 변경 여부 확인 (서버 환경에서 실행 권장)")
    
    print()


if __name__ == "__main__":
    main()
