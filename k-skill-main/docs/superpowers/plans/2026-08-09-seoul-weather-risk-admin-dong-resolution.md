# Seoul Weather Risk Admin Dong Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 서울 행정동 이름과 자연어 질문만으로 `weather_place_risk_window`를 조회할 수 있도록 행정동을 정규 `place_id`로 안전하게 변환한다.

**Architecture:** ASAC-DBT의 `weather_place_grid_mapping.csv`를 427행의 최소 JSON reference로 고정하고, Python helper가 proxy 호출 전에 로컬에서 정확 일치 해석을 수행한다. hosted proxy와 ASK Seoul에는 기존과 동일하게 `place_id`만 전달해 인증·allowlist·단일 제품 경계를 유지한다.

**Tech Stack:** Python 3 표준 라이브러리(`argparse`, `json`, `pathlib`, `unicodedata`), `unittest`, Node.js 기반 k-skill asset sync/CI

## Global Constraints

- 대상 제품은 `weather_place_risk_window` 하나다.
- 기준 매핑은 `mapping_method=kma_admin_dong_grid_20260325`, 427행, 고유 `place_id` 427개다.
- 정확 일치만 허용하며 fuzzy search, 자동 오타 보정, 좌표 geocoding을 추가하지 않는다.
- `신사동`은 강남구와 관악구 중 하나를 임의 선택하지 않고 `--gu`를 요구한다.
- proxy에는 새 query field와 사용자 credential을 추가하지 않는다.
- `skill.json`과 `instruction.md`가 원본이며 `SKILL.md`와 CLI copy는 생성·동기화한다.
- 기존 `--filter place_id=...` 호출은 유지한다.

---

### Task 1: 버전 고정 행정동 reference와 검증 계약

**Files:**
- Create: `seoul-weather-risk/references/admin-dong-place-map.json`
- Modify: `seoul-weather-risk/tests/test_seoul_weather_risk.py`

**Interfaces:**
- Consumes: ASAC-DBT `domains/traffic_weather/seeds/weather/weather_place_grid_mapping.csv`
- Produces: `{mapping_version: str, source: str, generated_at: str, locations: list[{admin_dong: str, gu: str, place_id: str}]}`

- [ ] **Step 1: Write the failing reference invariant test**

```python
def test_admin_dong_reference_has_expected_version_and_unique_place_ids(self):
    payload = json.loads((ROOT / "seoul-weather-risk" / "references" / "admin-dong-place-map.json").read_text(encoding="utf-8"))
    self.assertEqual(payload["mapping_version"], "kma_admin_dong_grid_20260325")
    self.assertEqual(len(payload["locations"]), 427)
    self.assertEqual(len({row["place_id"] for row in payload["locations"]}), 427)
    self.assertEqual(
        sorted(row["gu"] for row in payload["locations"] if row["admin_dong"] == "신사동"),
        ["강남구", "관악구"],
    )
```

- [ ] **Step 2: Run the focused test and observe RED**

Run: `python -m unittest seoul-weather-risk.tests.test_seoul_weather_risk.LocationMappingTests.test_admin_dong_reference_has_expected_version_and_unique_place_ids -v`

Expected: FAIL because `references/admin-dong-place-map.json` does not exist.

- [ ] **Step 3: Add the minimal reference snapshot**

Create UTF-8 JSON from the canonical CSV, retaining only `admin_dong`, `gu`, and `place_id`, sorted by `place_id`. Set `mapping_version` to `kma_admin_dong_grid_20260325`, `source` to the canonical ASAC-DBT seed path, and `generated_at` to `2026-08-09`.

- [ ] **Step 4: Run the focused test and observe GREEN**

Run: `python -m unittest seoul-weather-risk.tests.test_seoul_weather_risk.LocationMappingTests.test_admin_dong_reference_has_expected_version_and_unique_place_ids -v`

Expected: PASS with 427 locations and 427 unique IDs.

### Task 2: 행정동 해석과 typed error

**Files:**
- Modify: `seoul-weather-risk/scripts/seoul_weather_risk.py`
- Modify: `seoul-weather-risk/tests/test_seoul_weather_risk.py`

**Interfaces:**
- Consumes: `admin-dong-place-map.json`
- Produces: `_normalize_location_name(value: str) -> str`, `_load_location_mapping(path: pathlib.Path = LOCATION_MAPPING_PATH) -> tuple[str, list[dict[str, str]]]`, `_resolve_admin_dong(admin_dong: str, gu: str | None = None) -> dict[str, str]`

- [ ] **Step 1: Write failing resolver tests**

```python
def test_resolve_admin_dong_returns_canonical_place_id(self):
    resolved = seoul_weather_risk._resolve_admin_dong("  잠실본동  ")
    self.assertEqual(resolved["admin_dong"], "잠실본동")
    self.assertRegex(resolved["place_id"], r"^seoul_admd_\d{10}$")

def test_resolve_admin_dong_requires_gu_for_duplicate_name(self):
    with self.assertRaises(seoul_weather_risk.SkillError) as raised:
        seoul_weather_risk._resolve_admin_dong("신사동")
    self.assertEqual(raised.exception.code, "ambiguous_admin_dong")
    self.assertEqual([item["gu"] for item in raised.exception.details["candidates"]], ["강남구", "관악구"])

def test_resolve_admin_dong_uses_gu_to_disambiguate(self):
    resolved = seoul_weather_risk._resolve_admin_dong("신사동", "강남구")
    self.assertEqual(resolved["gu"], "강남구")
```

- [ ] **Step 2: Run resolver tests and observe RED**

Run: `python -m unittest seoul-weather-risk.tests.test_seoul_weather_risk.LocationMappingTests -v`

Expected: FAIL because resolver functions are undefined.

- [ ] **Step 3: Implement schema validation, normalization, and resolution**

```python
LOCATION_MAPPING_PATH = pathlib.Path(__file__).resolve().parents[1] / "references" / "admin-dong-place-map.json"

def _normalize_location_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).strip().split())

def _resolve_admin_dong(admin_dong: str, gu: str | None = None) -> dict[str, str]:
    normalized_dong = _normalize_location_name(admin_dong)
    normalized_gu = _normalize_location_name(gu) if gu is not None else None
    _version, locations = _load_location_mapping()
    candidates = [row for row in locations if _normalize_location_name(row["admin_dong"]) == normalized_dong]
    if not candidates:
        raise SkillError("unknown_admin_dong", f"지원하는 서울 행정동이 아닙니다: {normalized_dong}")
    if normalized_gu is not None:
        known_gus = {_normalize_location_name(row["gu"]) for row in locations}
        if normalized_gu not in known_gus:
            raise SkillError("unknown_gu", f"지원하는 서울 자치구가 아닙니다: {normalized_gu}")
        candidates = [row for row in candidates if _normalize_location_name(row["gu"]) == normalized_gu]
        if not candidates:
            raise SkillError("unknown_admin_dong", f"{normalized_gu}의 지원 행정동이 아닙니다: {normalized_dong}")
    if len(candidates) > 1:
        raise SkillError("ambiguous_admin_dong", "동명이므로 자치구를 함께 입력해야 합니다.", {"candidates": sorted(candidates, key=lambda item: item["gu"])})
    return candidates[0]
```

`_load_location_mapping`은 JSON object/schema, 매핑 버전, 427행, 필수 문자열 필드, 고유 `place_id`를 확인하고 위반 시 `location_mapping_invalid`를 발생시킨다.

- [ ] **Step 4: Run resolver tests and observe GREEN**

Run: `python -m unittest seoul-weather-risk.tests.test_seoul_weather_risk.LocationMappingTests -v`

Expected: PASS for normal, normalized, ambiguous, disambiguated, unknown-dong, unknown-gu, and corrupt-reference cases.

### Task 3: query CLI에 자연어 위치 입력 연결

**Files:**
- Modify: `seoul-weather-risk/scripts/seoul_weather_risk.py`
- Modify: `seoul-weather-risk/tests/test_seoul_weather_risk.py`

**Interfaces:**
- Consumes: `_resolve_admin_dong(admin_dong, gu)`
- Produces: `query --admin-dong <name> [--gu <name>]`, while preserving `query --filter place_id=<id>`

- [ ] **Step 1: Write failing request-contract tests**

```python
def test_query_maps_admin_dong_to_place_id_before_proxy_request(self):
    code = seoul_weather_risk.run(["query", "--product-id", PRODUCT_ID, "--admin-dong", "잠실본동", "--limit", "1"])
    self.assertEqual(code, 0)
    query = self.api.requests[-1]["query"]
    self.assertEqual(query["limit"], ["1"])
    self.assertRegex(query["place_id"][0], r"^seoul_admd_\d{10}$")
    self.assertNotIn("admin_dong", query)
    self.assertNotIn("gu", query)
```

Add explicit tests for `--gu` without `--admin-dong`, `--admin-dong` together with a `place_id` filter, and the existing `place_id` request.

- [ ] **Step 2: Run focused CLI tests and observe RED**

Run: `python -m unittest seoul-weather-risk.tests.test_seoul_weather_risk.ApiClientTests.test_query_maps_admin_dong_to_place_id_before_proxy_request -v`

Expected: parser exits because `--admin-dong` is not defined.

- [ ] **Step 3: Add CLI flags and conflict validation**

```python
query.add_argument("--admin-dong")
query.add_argument("--gu")
```

After parsing filters, reject `--gu` without `--admin-dong`; reject `--admin-dong` with any `place_id` filter; otherwise resolve the name and set `filters["place_id"]` to the resolved canonical ID. Do not add `admin_dong` or `gu` to `request_query`.

- [ ] **Step 4: Run all skill unit tests and observe GREEN**

Run: `python -m unittest discover -s seoul-weather-risk/tests -p 'test_seoul_weather_risk.py' -v`

Expected: all existing and new tests PASS.

### Task 4: 사용 지침·메타데이터·배포 asset 동기화

**Files:**
- Modify: `seoul-weather-risk/instruction.md`
- Modify: `seoul-weather-risk/skill.json`
- Modify: `docs/features/seoul-weather-risk.md`
- Generate: `seoul-weather-risk/SKILL.md`
- Generate: `packages/k-skill-cli/skills/seoul-weather-risk/**`

**Interfaces:**
- Consumes: final CLI/error contract
- Produces: natural-language-first workflow and synchronized CLI package assets

- [ ] **Step 1: Update source instructions**

Make `--admin-dong 잠실본동` the primary query example, document optional `--gu`, the `신사동` ambiguity flow, exact matching, typed failures, and the retained advanced `place_id` route.

- [ ] **Step 2: Update skill discovery text**

Change `skill.json` description/frontmatter so the trigger includes 서울 행정동 이름 기반 기상 위험 질문 without claiming fuzzy or real-time location support.

- [ ] **Step 3: Generate and sync assets**

Run: `npm run generate:skill-stubs`

Run: `npm run sync:cli-skills`

Expected: the top-level stub and `packages/k-skill-cli/skills/seoul-weather-risk` contain the updated instruction, helper, tests-excluded asset set, and reference JSON.

- [ ] **Step 4: Sync the current skill to global development locations**

Respect existing symlinks and mirror the top-level `seoul-weather-risk` directory to `~/.agents/skills/seoul-weather-risk` and `~/.claude/skills/seoul-weather-risk` without creating repo-local skill directories.

### Task 5: 전체 검증, 커밋, PR #552 갱신

**Files:**
- Modify: PR #552 body on GitHub

**Interfaces:**
- Consumes: all source/generated files and tests
- Produces: pushed PR head with reproducible verification evidence

- [ ] **Step 1: Run source and bundle consistency checks**

Run: `npm run generate:skill-stubs -- --check`

Run: `npm run sync:cli-skills -- --check`

Run: `git diff --check`

Expected: all exit 0.

- [ ] **Step 2: Run full repository verification**

Run: `npm run ci`

Expected: lint, unit/workspace tests, skill validation, and manifest check all exit 0.

- [ ] **Step 3: Run installed-skill smoke**

Run the globally synchronized helper with `preflight`, then run the local mock-backed unit suite. Confirm no user API Key appears in stdout/stderr and the generated proxy request contains only canonical `place_id` plus bounded paging/time fields.

- [ ] **Step 4: Commit exact files and push to the existing PR branch**

Stage only the design/plan, skill source, generated stub, reference, tests, feature doc, and CLI synchronized files. Push `HEAD` to `origin/feat/546-seoul-weather-risk` as a fast-forward update.

- [ ] **Step 5: Update and verify PR #552**

Add a concise section describing 행정동 입력, ambiguity handling, unchanged proxy boundary, mapping provenance/version, and exact test/CI results. Verify title/body/head/base and rendered UTF-8 content with `gh pr view 552`.
