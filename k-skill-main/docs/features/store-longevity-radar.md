# 장수 점포 레이더 (store-longevity-radar)

`store-longevity-radar` 스킬은 공공데이터포털 **「소상공인시장진흥공단_상가(상권)정보」** 공개 파일(비회원 다운로드)을 이용해, 업종·상호 키워드에 맞는 전국 점포 전수를 뽑고 과거 스냅샷과 매칭해 **"과거에도 존재했고 지금도 존재하는" 장수 점포**를 추출한다.

## 제공 기능

- `current` — 최신 분기 스냅샷(전국 17개 시도 zip, 무인증)에서 상권업종소분류코드/상호 키워드로 점포 전수 추출 (상호·업종·주소·행정동·경위도)
- `match` — 사용자가 보유한 과거 스냅샷 CSV와 ① 상가업소번호 ② 정규화 상호+좌표(기본 150m) 순으로 매칭해 장수 점포 추출
- 기본 업종은 문구·완구(`G21302`, `G21306`)이며 `--code`/`--keyword`로 어떤 업종이든 지정 가능

## 인증/시크릿

없다. 무인증 공개 파일을 사용자 머신에서 먼저 직접 받는다. 직접 경로가 timeout/차단되면 GitHub Actions가 원본 ZIP의 CRC·필수 CSV 헤더·SHA-256을 검증한 뒤 R2에 저장한 공개 객체 미러를 fallback으로 사용한다. helper는 stdlib만 쓴다. 최신 zip(수백 MB)은 1일 로컬 캐시(`~/.cache/k-skill/store-longevity-radar/`)한다.

## 정직한 한계 (사용자 고지 필수)

- 자료에 **사업자등록번호·개업일이 없다.** 산출값은 "최초 관측 시점 하한"이지 개업일이 아니다.
- 상호 변경·이전 점포는 매칭에서 빠진다(과소집계). 동명 상호는 좌표 거리로 구분하되 동일성을 단정하지 않는다.
- 과거 스냅샷은 공공데이터포털에서 최신 분기만 배포되므로 사용자가 별도 보유분을 제공해야 한다.
- 폐업 확정은 `nts-business-registration`(사업자번호 필요), 인허가 업종 업력은 `localdata-business-status`, 전화번호·현재 등재 확인은 `kakao-map`과 조합한다.

## 예시

```bash
# 전국 문구·완구 현재 전수
npx -y @nomadamas/k-skill@0 exec store-longevity-radar scripts/store_longevity_radar.py -- \
  current --out 전국_문구완구.csv

# 서울·부산 × 2019 스냅샷 매칭 → 장수 점포
npx -y @nomadamas/k-skill@0 exec store-longevity-radar scripts/store_longevity_radar.py -- \
  match --sido 서울 --sido 부산 --old-csv 상가업소정보_201912_01.csv --out 장수점포.csv
```

## 입력

- `--code`: 상권업종소분류코드 (반복, 기본 `G21302` `G21306`). 다른 업종을 `match`할 때 코드체계가 바뀌었다면 현재 코드와 과거 코드를 모두 반복 지정
- `--keyword`: 상호 키워드 (반복, 기본 문구/문방구/완구/장난감)
- `--sido`: 시도명 필터 (생략 시 전국)
- `--zip`: 기존 zip 재사용 / `--old-csv`: 과거 CSV (`match` 필수, 구분자 자동 감지)
- `--max-dist`: 동일 상호 허용 좌표 거리(m), 기본 150
- `--out`, `--format`: 출력 파일/형식
- `KSKILL_STORE_LONGEVITY_MIRROR_MANIFEST_URL`: 검증 미러 manifest URL override

## 실패 모드

- 데이터셋 페이지에서 파일 ID 발견 실패 → `unavailable` + 수동 확인 URL
- 공공데이터포털 접속/다운로드 timeout 또는 HTTP 실패 → 검증 미러 fallback
- 미러 manifest/ZIP 접근 실패, 크기·SHA-256 불일치, ZIP 손상 → 캐시 미승격 + `unavailable`
- 다운로드 중단 → `.part` 잔존, 캐시 미승격, 재실행 시 재다운로드
- 0건: 코드체계 불일치 가능(기본 문구·완구의 2022년 이전 코드는 자동 포함, 다른 업종은 현재/과거 코드를 모두 `--code`로 지정) — `--keyword` 위주로 재시도
