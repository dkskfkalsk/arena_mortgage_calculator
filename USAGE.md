# 사용 가이드

## 프로젝트 구조 설명

### 1. 금융사 추가하기

새로운 금융사를 추가하려면:

1. **설정 파일 생성**: `data/banks/새금융사_config.json` 파일 생성
   - `bnk_config.json` 파일을 참고하여 작성
   - 금융사별 모든 정보를 한 파일에 작성:
     - `bank_name`: 금융사명
     - `target_regions`: 대상 지역 리스트
     - `region_grades`: 지역별 급지 매핑 (금융사별로 다를 수 있음)
     - `max_ltv_by_grade`: 급지별 최대 LTV
     - `ltv_steps`: 계산할 LTV 단계
     - `interest_rates_by_ltv`: LTV별 신용등급별 금리
     - `credit_score_to_grade`: 신용점수→등급 매핑
     - `conditions`: 특이 조건 리스트
   
   **자동 등록**: JSON 파일만 추가하면 자동으로 계산기에 등록됩니다!
   Python 클래스를 만들 필요가 없습니다.

### 2. 설정 파일 수정하기

각 금융사의 조건이 변경되면 `data/banks/` 폴더의 해당 JSON 파일을 수정하면 됩니다.

주요 설정 항목 (모두 한 파일에 관리):
- `bank_name`: 금융사명
- `target_regions`: 대상 지역 리스트
- `region_grades`: 지역별 급지 매핑 (금융사별로 다를 수 있음)
- `max_ltv_by_grade`: 급지별 최대 LTV
- `ltv_steps`: 계산할 LTV 단계
- `interest_rates_by_ltv`: LTV별 신용등급별 금리
- `credit_score_to_grade`: 신용점수→등급 매핑
- `conditions`: 특이 조건 리스트

### 3. 대환 여부 판단 로직 추가

현재는 `parsers/message_parser.py`의 `_parse_mortgage_line()` 메서드에서 대환 여부를 판단하지 못합니다.

추가할 위치:
- `parsers/message_parser.py` 파일의 `_parse_mortgage_line()` 메서드
- `# TODO: 대환 여부 판단 로직` 주석이 있는 부분

예시:
```python
# 메시지에서 "대환" 키워드 확인
is_refinance = "대환" in line or "대환대출" in line
```

### 4. 텔레그램 봇 설정

1. `@BotFather`에서 봇 생성 및 토큰 발급
2. `config/telegram_config.py` 파일에서 `TELEGRAM_BOT_TOKEN` 설정
3. 로컬 실행: `python main.py`
4. Vercel 배포: Webhook 방식 사용

### 5. Vercel 배포

1. GitHub에 프로젝트 업로드
2. Vercel에 프로젝트 연결
3. 환경 변수에 `TELEGRAM_BOT_TOKEN` 설정
4. Webhook URL을 텔레그램에 등록

## 메시지 형식

텔레그램 메시지는 다음과 같은 형식을 따라야 합니다:

```
성   명 : 정종민 (68)
직   업 : 직장인(사업자보유)
신용점수 : X
거주여부 : 비거주(전세미동의)
소유현황 : 단독소유
주   소 : 서울특별시광진구자양동842-1미산빌5차동 3층 301호
면   적 : 25.95㎡
세대수 : 16세대 (1개동)
구   분 : 빌라
KB시세 : 시세없음
=========설정내역=========
1순위 : 전세입자
           27,000 (27,000)만원
2순위 : 보성새마을금고
           10,800 (9,000)만원
========================
특이사항 : *하우스머치 59,400(25.11.01) / 월250만 / 즉발보유
요청사항 : *사업자 보유 부가세누락 신고조건 / 세입자 미동의 조건 / 3순위 확인부탁드립니다
```

## 주의사항

- KB시세가 없으면 산출이 불가능합니다
- 신용점수가 없으면 금리 범위로 표시됩니다
- UTF-8 인코딩을 사용합니다

