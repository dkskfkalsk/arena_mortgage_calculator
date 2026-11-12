# 금융사 조견 통합 적용 계획

> **문서 성격**: 내부 개발 로드맵 (아직 전면 적용 전)  
> **목표**: 조견 JSON만 수정하면 모든 금융사에 동일 규칙이 적용되도록 스키마·config 플래그 통합

현재 운영 조견은 `data/banks/*.json`에 금융사별 키가 혼재합니다.  
이 문서는 `calculator/base_calculator.py`의 금융사명 분기를 줄이기 위한 설계안입니다.

---

## 0. 적용 완료: 조건별 LTV 조정 (`ltv_adjustments`)

조건이 맞으면 최대 LTV를 고정·상향·차감·상한하는 규칙은 모두 금융사 JSON의 `ltv_adjustments` 배열 하나로 통일했습니다.
조건 키·동작·프리셋·적용 순서 정의는 `data/common/ltv_adjustments.json`에 있습니다 (`data/banks`·`data/loan` 밖이어야 금융사로 로드되지 않음).

```json
"ltv_adjustments": [
  { "preset": "household_under", "when": { "household_count_lt": 100 }, "value": 5 },
  { "preset": "area_over", "when": { "area_gt": 135 }, "value": 5 },
  { "action": "cap", "when": { "priority": "subordinate", "property_type_in": ["residential_commercial"] }, "value": 80 },
  { "action": "note", "when": { "region_grade_in": [4] }, "message": "안내 문구" }
]
```

- 동작: `set`(고정) → `raise`(상향) → `reduce`(차감) → `cap`(상한) 순서로 적용, `note`는 멘트만 추가
- 적용 위치: 급지·신용·선후순위·면적 매트릭스로 기본 최대 LTV를 정한 뒤, 지분조건 50% 상한 전
- `message`는 한도 아래 멘트, `no_limit_message`는 그 차감·상한 때문에만 한도가 사라질 때 회신 문구

| 이전 키 (제거됨) | 금융사 | `ltv_adjustments` |
|------------------|--------|-------------------|
| `household_ltv_reduction` | 솔브레인, 애큐온저축 | `household_under` reduce |
| `property_type_ltv_reduction` | 애큐온저축 | `officetel` reduce |
| `tenant_ltv_reduction` (미구현이었음) | 애큐온저축 | `tenant` reduce |
| `primary_ltv_adjustments` | 키움 | `priority: primary` reduce 2건 |
| `subordinate_ltv_restrictions` (미구현이었음) | 키움 | `priority: subordinate` cap 3건 |
| `max_ltv_by_property_type` | 한투저축, JB | `property_type_cap` cap |
| `area_limit.max_ltv_when_exceeded` | 이음-하이론 | `area_over_cap` cap |
| `ltv_when_household_gte` | 드림에셋 아파트 | set |
| `ltv_100_conditions` | OK | raise 100 |
| (코드 고정) 가계자금 70% | OK | `product_type: household` set |
| `premium_property_conditions` | 애큐온저축 | note |
| `household_condition_lt` | IM 주택론 | note |

`area_limit`(면적 초과 취급 불가, BNK)과 `ltv_kb_price_override`(GM, LTV 단계까지 바꿈)는 성격이 달라 그대로 둡니다.

---

## 1. 현재 문제점

### 1.1 코드에 금융사명 하드코딩 (약 40곳)

| 분기 조건 | 사용 위치 | 대체 방안 |
|-----------|-----------|------------|
| `is_ok_bank` | 10곳+ | `config.support_household_business: true` |
| `is_mg_capital` | 8곳+ | `config.refinance_ltv_search_mode: "step_down_0.1"` |
| `is_bnk` | 4곳 | `config.calculation_mode: "ltv_grade"` |
| `is_acuon` | 5곳+ | `config.calculation_mode: "region_group"` |
| `is_jb` | 4곳 | `config.calculation_mode: "region_credit_grade"` |
| ~~`is_kiwoom_retail`~~ | 제거됨 | `ltv_adjustments`로 이전 (아래 0절) |

### 1.2 조견 키 불일치 (금융사마다 다른 키 사용)

| 기능 | MG캐피탈 | 키움 | BNK | JB | 애큐온캐 | 애큐온저 | OK |
|------|----------|------|-----|-----|----------|----------|-----|
| LTV 단계 | `ltv_steps` | `ltv_steps_primary`/`_subordinate` | `ltv_steps` | `ltv_steps` | `ltv_steps` | `ltv_steps_primary`/`_subordinate` | `ltv_steps` |
| 최대 LTV | `max_ltv_by_grade` | `max_ltv_primary`/`_subordinate` | `max_ltv_by_grade` | `max_ltv_by_region_credit_grade` | `max_ltv_by_region_credit_grade` | `max_ltv_primary`/`_subordinate` | `max_ltv_by_grade` |
| 금리 테이블 | `primary_*`/`subordinate_*` | 동일 | `interest_rate_by_ltv_grade` | `primary_*` | `interest_rates_by_region_group_*` | `subordinate_*_by_region` | `business_*`/`household_*` |

### 1.3 정의만 있고 미구현

- ~~`subordinate_ltv_restrictions` (키움저축)~~ → `ltv_adjustments` cap 규칙으로 이전 완료
- `price_application_rules` (키움저축) → 미구현 (`lower_bound_price`와 중복)

---

## 2. 통합 스키마 설계

### 2.1 계산 모드 플래그 (config 기반 분기)

```json
{
  "calculation_mode": "primary_subordinate",
  "refinance_ltv_search_mode": null,
  "support_household_business": false
}
```

| `calculation_mode` | 설명 | 적용 금융사 |
|-------------------|------|-------------|
| `primary_subordinate` | 선순위/후순위 분리, `primary_*`/`subordinate_*` | MG, 키움, 페퍼, 애큐온저축 |
| `ltv_grade` | LTV·등급별 단일 테이블 | BNK |
| `region_credit_grade` | 지역·신용등급별 LTV | JB, 애큐온캐피탈 |
| `cofix_plus_spread` | COFIX 기반 가산금리 | OK저축 |

| `refinance_ltv_search_mode` | 설명 | 적용 금융사 |
|-----------------------------|------|-------------|
| `null` | 기본 (ltv_steps만 사용) | 대부분 |
| `"step_down_0.1"` | max_ltv부터 0.1%씩 감소 탐색 | MG캐피탈 |

| `support_household_business` | 설명 | 적용 금융사 |
|------------------------------|------|-------------|
| `true` | 가계자금·사업자금 둘 다 계산 | OK저축 |
| `false` | 사업자금만 | 그 외 |

### 2.2 LTV/금리 키 통합

**통일된 키 구조 (선택적 사용)**

```json
{
  "ltv": {
    "steps": [90, 85, 80, 75, 70],
    "steps_primary": [90, 85, 80, 75, 70],
    "steps_subordinate": [90, 85, 80, 75, 70],
    "max_by_grade": { "1": 90, "9": 0 },
    "max_primary": 90,
    "max_subordinate": 90,
    "restrictions": {
      "subordinate": {
        "small_apartment_max_ltv": 100,
        "small_apartment_conditions": ["1개동", "200세대 이하"],
        "residential_commercial_max_ltv": 100
      }
    }
  },
  "interest_rates": {
    "primary_by_ltv": { "70": { "1": 5.69, ... }, ... },
    "subordinate_by_ltv": { ... },
    "by_ltv_grade": { "92": { "1": 4.91, ... }, ... },
    "by_region_group_priority": { ... }
  }
}
```

- 금융사별로 필요한 블록만 정의
- `calculation_mode`에 따라 사용할 블록 결정

### 2.3 공통 기본값 스키마 (config_defaults.json)

```json
{
  "product_type": "business",
  "min_amount": 3000,
  "min_kb_price": null,
  "min_credit_score": null,
  "max_age": null,
  "max_amount": null,
  "price_sources": {
    "kb_price": 1,
    "kb_ai_price": 0,
    "bank_appraisal_price": 0,
    "realestatetech_price": 0,
    "korea_realestate_price": 0,
    "housematch_price": 0
  },
  "business_property_types": {
    "apartment": 1,
    "apartment_no_land_registry": 1,
    "residential_commercial": 1,
    "villa": 0,
    "officetel": 0,
    "detached_house": 0,
    "multi_family_house": 0
  },
  "validation_rules": {
    "enabled": true,
    "occupation_requirements": {},
    "restricted_keywords": {},
    "complex_rules": []
  },
  "lower_bound_price": { "enabled": false },
  "conditions": []
}
```

---

## 3. 변경 작업 단계

### Phase 1: 기본값 병합 로직 추가 (코드 1곳)

**위치**: `BaseCalculator.__init__` 또는 config 로드 시점

```python
# config 로드 후
DEFAULTS = load_json("data/config_defaults.json")
self.config = deep_merge(DEFAULTS, config)
```

- `deep_merge`: 기본값 위에 금융사 config 덮어쓰기
- 금융사 JSON에는 **변경된 값만** 기재

### Phase 2: 금융사명 분기 → config 플래그로 교체

| 기존 코드 | 변경 후 |
|-----------|---------|
| `if is_ok_bank:` | `if self.config.get("support_household_business"):` |
| `if is_mg_capital and is_refinance:` | `if self.config.get("refinance_ltv_search_mode") == "step_down_0.1" and is_refinance:` |
| ~~`if is_kiwoom_retail:`~~ | 완료 — `ltv_adjustments` (0절) |
| `if is_acuon_capital_no_credit:` | `if self.config.get("calculation_mode") == "region_credit_grade" and credit_grade is None:` |
| `if is_jb_per_grade:` | `if self.config.get("calculation_mode") == "region_credit_grade":` |
| `if is_bnk:` | `if self.config.get("calculation_mode") == "ltv_grade":` |

### Phase 3: LTV/금리 키 통합 (fallback 체인)

```python
# LTV 단계
ltv_steps = (
    self.config.get("ltv", {}).get("steps") or
    self.config.get("ltv_steps_primary") or  # 하위호환
    self.config.get("ltv_steps") or
    [90, 85, 80, 75, 70]
)
```

- 기존 키 유지(하위호환) + 새 통합 키 우선
- 점진적 마이그레이션 가능

### Phase 4: subordinate_ltv_restrictions 구현 — 완료

`ltv_adjustments` cap 규칙으로 이전 (0절 참고).

### Phase 5: price_application_rules 정리

- `price_application_rules`는 `lower_bound_price`와 역할 중복
- **권장**: `price_application_rules` 제거, `lower_bound_price`만 사용
- 또는 `lower_bound_price`를 `price_application_rules` 구조로 통일 후 기존 `price_application_rules` 제거

---

## 4. 금융사별 config 변경 예시

### 4.1 MG캐피탈 (1_MGcapital.json)

**추가할 키**:
```json
{
  "calculation_mode": "primary_subordinate",
  "refinance_ltv_search_mode": "step_down_0.1",
  "support_household_business": false,
  "min_kb_price": 10000
}
```

**제거 가능**: (기존 키 유지해도 동작)

### 4.2 키움저축-리테일 (2_kiwoomretail.json)

**추가/유지**:
```json
{
  "calculation_mode": "primary_subordinate"
}
```

LTV 차감·후순위 상한은 `ltv_adjustments`로 이전 완료 (0절 참고).

**제거**: `price_application_rules` (미사용)

### 4.3 OK저축은행 (6_ok_config.json)

**추가**:
```json
{
  "calculation_mode": "cofix_plus_spread",
  "support_household_business": true
}
```

### 4.4 BNK캐피탈 (4_bnk_config.json)

**추가**:
```json
{
  "calculation_mode": "ltv_grade",
  "min_kb_price": 20000
}
```

---

## 5. 적용 후 기대 효과

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 신규 금융사 추가 | 코드 수정 + JSON 작성 | JSON만 추가 |
| 조견 변경 | JSON 수정 (일부는 코드 수정 필요) | JSON만 수정 |
| 금융사별 분기 | `bank_name` 문자열 비교 | `config` 플래그/모드 |
| 미구현 조건 | `subordinate_ltv_restrictions` 등 | 모두 config 기반으로 동작 |

---

## 6. 작업 순서 요약

1. **config_defaults.json** 생성 및 `deep_merge` 로직 추가
2. **calculation_mode**, **refinance_ltv_search_mode**, **support_household_business** 도입 후 금융사명 분기 제거
3. LTV/금리 키 fallback 체인 정리 (하위호환 유지)
4. **subordinate_ltv_restrictions** 구현
5. **price_application_rules** 제거 또는 `lower_bound_price`로 통합
6. 각 금융사 JSON에 새 플래그 추가 및 검증

---

## 7. 주의사항

- **하위호환**: 기존 JSON은 수정 없이 동작하도록 fallback 유지
- **점진적 적용**: Phase별로 나누어 적용 후 테스트
- **테스트**: 기존 케이스로 리그레션 확인 필수
