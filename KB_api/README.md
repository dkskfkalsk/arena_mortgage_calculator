# KB 시세 API 모듈 사용 가이드

## 개요

`kb_price_api.py`는 등기부에서 추출한 주소와 면적을 기반으로 KB 부동산 시세를 자동으로 조회하는 모듈입니다.

이 모듈은 다른 코드와 **독립적으로 작동**하며, 기존 코드에 영향을 주지 않습니다.

## 설치

```bash
pip install requests
```

또는

```bash
pip install -r requirements.txt
```

## 기본 사용법

### 1. 간단한 사용 (편의 함수)

```python
from KB_api.kb_price_api import get_kb_price_from_registry

# 등기부에서 추출한 주소와 면적
address = "서울특별시 강남구 대치동 123"
area = "84.93㎡"  # 또는 "84.93"

# KB 시세 조회
result = get_kb_price_from_registry(address, area)

if result:
    print(f"KB시세: {result['kb_price_raw']}")  # "125,000만원"
    print(f"단지명: {result['complex_name']}")
    print(f"면적: {result['area']}m²")
    print(f"평수: {result['pyeong']}평")
    print(f"타입: {result['type']}")
```

### 2. 상세 사용 (KBPriceAPI 클래스)

```python
from KB_api.kb_price_api import KBPriceAPI

# API 인스턴스 생성
api = KBPriceAPI()

# KB 시세 조회
result = api.get_kb_price(
    address="서울특별시 강남구 대치동",
    area=84.93,  # m² 단위
    complex_name="대치아이파크"  # 선택사항, 있으면 더 정확
)

if result:
    kb_price_manwon = result['kb_price']  # 만원 단위 숫자
    print(f"KB시세: {kb_price_manwon:,.0f}만원")
```

## 등기부 파서와 연동

```python
from parsers.registry_parser import RegistryParser
from KB_api.kb_price_api import get_kb_price_from_registry

# 등기부 파싱
parser = RegistryParser()
doc = parser.parse("등기부.pdf")

# 등기부에서 추출한 정보로 KB 시세 조회
if doc.부동산_주소 and doc.면적:
    result = get_kb_price_from_registry(doc.부동산_주소, doc.면적)
    
    if result:
        # KB 시세를 사용할 수 있음
        kb_price = result['kb_price']  # 만원 단위
        print(f"KB시세: {kb_price:,.0f}만원")
```

## 반환값 구조

```python
{
    "kb_price": 125000,           # 만원 단위 숫자
    "kb_price_raw": "125,000만원", # 포맷된 문자열
    "complex_name": "대치아이파크", # 단지명
    "area": 84.93,                 # m² 단위
    "pyeong": "25.7",              # 평수 (문자열)
    "type": "84A형"                # 주택 타입
}
```

조회 실패 시 `None`을 반환합니다.

## 주요 기능

### 1. 주소 파싱
- 주소에서 시/도, 구/군, 동/읍/면 자동 추출
- 약칭 자동 변환 (예: "서울" → "서울특별시")

### 2. 법정동코드 찾기
- 법정동코드 데이터 파일 자동 로드
- 주소를 기반으로 법정동코드 자동 매칭

### 3. 단지 목록 조회
- 법정동코드로 해당 지역의 단지 목록 조회
- KB 부동산 API 직접 호출

### 4. 시세 조회
- 단지별 평형별 상세 시세 조회
- 면적에 맞는 시세 자동 매칭 (허용 오차: 5m²)

## 테스트

```bash
# 전체 테스트
python KB_api/test.py

# 특정 테스트만 실행
python KB_api/test.py --test parse    # 주소 파싱 테스트
python KB_api/test.py --test lookup   # 시세 조회 테스트
python KB_api/test.py --test registry  # 등기부 연동 테스트
```

## API 상태 확인

KB 시세가 가져와지지 않을 때 API가 정상 작동하는지 확인:

```bash
# API 상태 확인 (네트워크, 응답, 오류 등 상세 확인)
python KB_api/check_api_status.py
```

이 스크립트는 다음을 확인합니다:
- 네트워크 연결 상태
- KB API 엔드포인트 응답
- API 응답 데이터 구조
- 오류 메시지 및 원인

## 예제 코드

더 자세한 예제는 `KB_api/usage_example.py`를 참고하세요.

## 주의사항

1. **법정동코드 데이터 파일 필요**
   - `kbland_price-main/static/combined_dongcode_data.json` 파일이 필요합니다
   - 없으면 자동으로 서울/경기도 개별 파일을 찾습니다

2. **API 호출 제한**
   - KB 부동산 API는 CORS 제한이 있을 수 있습니다
   - 서버 환경에서 실행하는 것을 권장합니다

3. **면적 매칭**
   - 면적에 맞는 시세를 찾지 못하면 가장 가까운 시세를 반환합니다
   - 허용 오차는 기본 5m²입니다

## 문제 해결

### 법정동코드를 찾을 수 없음
- 주소 형식 확인 (시/도, 구/군, 동이 모두 포함되어야 함)
- 법정동코드 데이터 파일 경로 확인

### API 호출 실패
- 네트워크 연결 확인
- KB 부동산 API 서버 상태 확인
- CORS 문제인 경우 서버 환경에서 실행

### 시세를 찾을 수 없음
- 해당 지역에 단지가 없을 수 있음
- 면적이 너무 특이한 경우 매칭 실패 가능

## 독립성

이 모듈은 다음 특징으로 다른 코드와 간섭 없이 작동합니다:

1. **독립적인 폴더**: `KB_api/` 폴더에 모든 파일 포함
2. **선택적 사용**: 필요할 때만 import하여 사용
3. **기존 코드 수정 불필요**: 기존 파서나 계산기는 그대로 사용 가능
4. **반환값 표준화**: 딕셔너리 형태로 일관된 반환값 제공

## 파일 구조

```
KB_api/
├── kb_price_api.py      # 메인 API 모듈
├── test.py              # 테스트 스크립트
├── usage_example.py     # 사용 예제
└── README.md            # 이 파일
```
