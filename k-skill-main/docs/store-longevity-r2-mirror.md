# Store longevity R2 mirror operations

`store-longevity-radar`는 공공데이터포털 원본을 먼저 직접 호출한다. 원본이 특정
egress에서 timeout되면 검증된 R2 객체를 fallback으로 사용한다. 이 미러는
`k-skill-proxy` API route가 아니라 공개 파일의 정적 객체 미러다.

## 비용

2026-08 기준 예상 비용은 월 **$0**이다.

- 저장 대상은 분기당 약 341 MB다.
- R2 Standard 무료 구간은 월 10 GB-month, Class A 100만 회, Class B 1,000만 회다.
- R2 인터넷 egress는 무료다.
- 저장본을 삭제하지 않아도 약 7년간 분기 스냅샷을 보관해야 10 GB에 접근한다.
- 이 저장소는 public repository이므로 표준 GitHub-hosted Actions 사용료가 없다.

공식 가격:

- <https://developers.cloudflare.com/r2/pricing/>
- <https://docs.github.com/en/billing/concepts/product-billing/github-actions>

## R2 준비

Cloudflare 계정에서 Standard storage bucket을 하나 만든다. 예시 bucket 이름:

```bash
npx -y wrangler@4.118.0 r2 bucket create k-skill-public-data
```

현재 managed public URL은
`https://pub-c974105a1e4840bcaa264cb2a55d99a1.r2.dev`다. 필요하면 이후
`k-skill-data.nomadamas.org` custom domain을 연결할 수 있다.

GitHub Actions API token은 해당 Cloudflare account의 R2 object read/write만
허용하도록 최소 권한으로 만든다.

## GitHub 설정

Actions secrets:

```text
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
```

Actions variables:

```text
STORE_LONGEVITY_R2_BUCKET=k-skill-public-data
STORE_LONGEVITY_R2_PUBLIC_BASE_URL=https://pub-c974105a1e4840bcaa264cb2a55d99a1.r2.dev
```

설정 예시:

```bash
gh secret set CLOUDFLARE_ACCOUNT_ID --repo NomaDamas/k-skill
gh secret set CLOUDFLARE_API_TOKEN --repo NomaDamas/k-skill
gh variable set STORE_LONGEVITY_R2_BUCKET --body k-skill-public-data --repo NomaDamas/k-skill
gh variable set STORE_LONGEVITY_R2_PUBLIC_BASE_URL \
  --body https://pub-c974105a1e4840bcaa264cb2a55d99a1.r2.dev \
  --repo NomaDamas/k-skill
```

시크릿 값은 shell argument에 넣지 말고 위 명령의 stdin prompt로 입력한다.

## 최신본 확인 계약

`.github/workflows/store-longevity-r2-mirror.yml`이 매일 실행된다.

1. 공공데이터포털 HTML에서 `FILE_*` ID를 찾는다.
2. 직접 HTML 접근 실패 시 Jina Reader rendered HTML을 discovery fallback으로 쓴다.
   두 경로 모두 robot-limit HTML을 반환하면 수동 실행의 `source_file_id` input으로
   `FILE_<digits>` 값을 전달한다. helper가 strict pattern으로 검증한다.
3. 공개 `latest.json`의 `source_file_id`가 같으면 아무 것도 다운로드하지 않는다.
4. 새 ID면 원본 ZIP을 임시 경로에 내려받는다.
5. ZIP CRC, CSV 존재, 필수 헤더, 파일 크기, SHA-256을 검증한다.
6. `objects/<FILE_ID>.zip`과 `manifests/<FILE_ID>.json`을 immutable object로 올린다.
7. 마지막에만 `latest.json`을 교체한다.

오래된 immutable object는 당장 삭제하지 않는다. 분기 파일 크기 기준 무료 저장
구간을 수년간 넘지 않으며, 이전 manifest를 본 클라이언트와의 race도 방지한다.

## 수동 실행

```bash
gh workflow run store-longevity-r2-mirror.yml \
  --repo NomaDamas/k-skill \
  -f force=true \
  -f source_file_id=FILE_000000003676619
```

실행 후 확인:

```bash
curl -fsSL https://pub-c974105a1e4840bcaa264cb2a55d99a1.r2.dev/store-longevity-radar/latest.json
```
