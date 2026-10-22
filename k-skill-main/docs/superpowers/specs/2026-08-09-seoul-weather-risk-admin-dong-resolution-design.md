# Seoul Weather Risk 행정동 입력 해석 설계

## 목적

사용자가 `place_id`를 알지 못해도 `행정동 이름 + 자연어 질문`으로 `seoul-weather-risk`를 사용할 수 있게 한다. Skill helper가 행정동 이름을 ASK Seoul의 정규 `place_id`로 결정적으로 변환한 뒤 기존 hosted proxy의 읽기 전용 data 경로를 호출한다.

## 변경하지 않는 경계

- 대상 제품은 `weather_place_risk_window` 하나로 유지한다.
- hosted proxy의 인증·scope·단일 제품 allowlist 경계를 넓히지 않는다.
- D1, Worker, Publisher, dbt 모델 및 Marketplace 데이터 계약은 변경하지 않는다.
- 임의 SQL, fuzzy search, 좌표 geocoding, 실시간 위치 추론을 추가하지 않는다.
- 기존 `--filter place_id=...` 고급 사용 경로는 하위 호환을 위해 유지한다.

## 기준 데이터와 버전

- 기준 원천: ASAC-DBT `weather_place_grid_mapping.csv`
- 기준 버전: `mapping_method=kma_admin_dong_grid_20260325`
- 스냅샷 규모: 서울 행정동 427개, 고유 `place_id` 427개
- `place_id` 형식: `seoul_admd_<10자리 행정동 코드>`
- 이름 중복: `신사동` 1건의 동명이명 집합(강남구/관악구)

Skill에는 실행 시점의 외부 저장소나 API에 의존하지 않는 버전 고정 JSON reference를 포함한다. reference에는 `mapping_version`, `source`, `generated_at`, 그리고 `admin_dong`, `gu`, `place_id`의 최소 필드만 저장한다.

## 입력 계약

`query` 명령에 아래 선택지를 추가한다.

- `--admin-dong <행정동명>`: 일반 사용자용 기본 위치 입력
- `--gu <자치구명>`: 동명이명 해소용 선택 입력. `--admin-dong`과 함께만 허용
- 기존 `--filter place_id=<정규 ID>`: 고급 사용자와 기존 호출의 호환 경로

위치 입력은 정확히 한 방식만 허용한다. `--admin-dong`과 `place_id` 필터를 동시에 주면 `conflicting_location_input`으로 실패한다. `--gu`만 주면 `invalid_location_input`으로 실패한다.

## 정규화와 해석 규칙

1. Unicode NFC 정규화
2. 앞뒤 공백 제거
3. 연속 공백을 한 칸으로 축약
4. 정규화된 문자열의 정확 일치만 허용

접미사 제거, 초성 검색, 유사 문자열, 자동 오타 보정은 하지 않는다. 잘못된 지역으로 조회하는 것보다 안전한 실패를 우선한다.

해석 결과는 다음과 같다.

- 후보 1개: 해당 `place_id`로 변환
- 후보 여러 개, `--gu` 없음: `ambiguous_admin_dong`과 후보 자치구 목록 반환
- 후보 여러 개, `--gu`로 1개 확정: 해당 `place_id`로 변환
- 후보 없음: `unknown_admin_dong`
- 알려지지 않은 `--gu`: `unknown_gu`

## 실행 흐름

1. helper가 기존처럼 bundle과 product metadata 계약을 검증한다.
2. `--admin-dong`을 로컬 reference에서 해석한다.
3. 변환된 `place_id`를 기존 공개 projection 필터로 검증한다.
4. proxy에는 `place_id`, 시간 범위, limit, cursor만 전송한다.
5. 응답 행은 기존 data 계약으로 검증하고 그대로 출력한다.

따라서 proxy와 ASK Seoul 서비스는 행정동 문자열 해석 책임을 갖지 않으며, 사용자 API Key가 필요 없는 현재 보안 모델도 유지된다.

## 문서·에이전트 동작

- 기본 예시는 `--admin-dong 잠실본동`처럼 사람이 읽는 이름을 사용한다.
- 자연어 질문에서 행정동 이름을 찾으면 helper의 `--admin-dong`에 전달한다.
- `신사동`처럼 모호하면 자치구를 한 번 질문하고, 답을 받은 뒤 `--gu`와 함께 재호출한다.
- 응답 설명에서는 내부 `place_id`보다 사용자가 입력한 행정동과 제품의 예보 시각·위험 근거를 우선한다.

## 오류 계약

새 오류 코드는 모두 exit code 2의 기존 JSON 오류 envelope을 사용한다.

- `invalid_location_input`
- `conflicting_location_input`
- `unknown_admin_dong`
- `ambiguous_admin_dong` (`details.candidates`에 자치구와 `place_id` 포함)
- `unknown_gu`
- `location_mapping_invalid` (reference 누락·중복 ID·스키마 오류)

## 검증 계획

1. `잠실본동`이 정규 `place_id`로 변환되어 proxy data query에 전달되는지 확인
2. 앞뒤/연속 공백과 Unicode NFC 정규화 확인
3. `신사동` 단독 입력이 후보 자치구를 포함해 실패하는지 확인
4. `신사동 + 강남구`가 한 ID로 확정되는지 확인
5. 미등록 동, 잘못된 구, 충돌 위치 입력이 typed error인지 확인
6. 기존 `place_id` 필터 호출이 동일하게 동작하는지 회귀 확인
7. reference의 427행·고유 ID·버전·필수 필드 invariant 확인
8. source와 CLI bundled copy의 완전 동기화 및 전체 `npm run ci` 확인

## 완료 조건

- 사용자가 행정동 이름만으로 비모호 위치의 기상 위험 데이터를 조회할 수 있다.
- 동명이명은 자치구 없이 임의 선택되지 않는다.
- proxy에 새 query field나 사용자 credential이 추가되지 않는다.
- 생성 스텁, CLI 번들, 단위 테스트 및 전체 CI가 통과한다.
