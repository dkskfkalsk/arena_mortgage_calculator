# KB 시세 API 직접 호출 URL

## 주소: 경기도 수원시 권선구 곡반정동 654 수원하늘채더퍼스트2단지 제217동 제11층 제1105호

### 1단계: 법정동코드 찾기

법정동코드를 찾기 위해 아래 스크립트를 실행하세요:

```bash
python KB_api/generate_api_url.py "경기도 수원시 권선구 곡반정동 654"
```

### 2단계: API URL (예시)

**참고**: 곡반정동의 정확한 법정동코드를 찾아야 합니다. 
일반적으로 권선구의 법정동코드는 `41113`으로 시작합니다.

#### 예시 URL (권선구 - 당수동 기준):
```
https://api.kbland.kr/land-price/price/fastPriceInfo?법정동코드=4111314100&유형=1&거래유형=0
```

#### 곡반정동 법정동코드 찾기:
1. 행정표준코드관리시스템 (code.go.kr)에서 조회
2. 또는 아래 스크립트로 자동 찾기:
   ```python
   from KB_api.kb_price_api import KBPriceAPI
   api = KBPriceAPI()
   dongcode = api.find_dongcode("경기도 수원시 권선구 곡반정동")
   print(f"법정동코드: {dongcode}")
   ```

### 3단계: 브라우저에서 테스트

법정동코드를 찾은 후, 아래 형식으로 URL을 만들어 브라우저에서 테스트하세요:

```
https://api.kbland.kr/land-price/price/fastPriceInfo?법정동코드=[법정동코드]&유형=1&거래유형=0
```

### 주의사항

- '제217동', '제1105호', '제11층' 같은 상세 주소는 법정동코드 찾기에 필요 없습니다.
- 법정동코드는 "경기도 수원시 권선구 곡반정동"까지만 필요합니다.
- 코드에서 자동으로 '제'가 붙은 부분을 제거합니다.
