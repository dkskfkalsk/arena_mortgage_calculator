# seoul-weather-risk fast path 설계

## 목적

일반 사용자의 오늘 기상 위험 질문에서 반복되는 bundle·product metadata 조회를 생략해 hosted proxy 왕복을 줄인다. 등록 전 local-direct나 사용자 API key 경로는 다시 추가하지 않는다.

## 동작

- `query --fast`는 정규 product ID, 행정동 매핑, 자치구 모호성, 날짜 범위, limit, cursor를 로컬에서 검증한다.
- fast path는 `/v1/ask-seoul/weather-risk/data`만 호출하고 응답 계약(`bundle_id`, `product_id`, `publication_id`, page fields)을 검증한다.
- `--fast`에서는 metadata가 필요한 임의 `--filter`를 거부한다. 필터나 게시 계약 확인이 필요하면 기존 full-contract query와 `catalog`/`describe` 진단을 사용한다.
- `product_not_ready`·계약 오류를 fixture나 추정값으로 대체하지 않는다.

## 사용자 흐름

일반 질문은 `query --fast` 한 번으로 처리하고, 오류 또는 readiness 점검 시에만 `preflight → catalog → describe`를 실행한다. 이로써 기본 CLI 실행 수와 live GET 수를 줄이면서 진단 경로와 기존 full-contract 동작은 보존한다.

## 검증

- fast query가 data route만 호출하고 Authorization 헤더를 보내지 않는 회귀 테스트
- 기존 full-contract query, 행정동 매핑, 오류 계약 테스트 전체 통과
- source instruction과 CLI 번들·스냅샷 동기화 검사
