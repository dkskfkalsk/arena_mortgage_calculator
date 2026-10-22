# 멀티에셋 모닝 브리핑

`multi-asset-morning-briefing`은 가장 최근 완료된 미국·한국 세션을 독립적으로 확인하고 글로벌 주식·금리·외환·원자재·변동성과 한국시장 전달 경로, 향후 5개 한국 거래일 일정을 7개 섹션으로 작성하는 조회·리서치 스킬이다.

## 데이터 경로

helper는 Python 표준 라이브러리만 사용하며 로그인·API 키·프록시가 필요 없다.

| 원천 | 용도 | 기준 |
| --- | --- | --- |
| U.S. Treasury daily par yield curve CSV | 2Y·10Y·30Y, 2s10s, 일간 bp 변화 | 미국 세션과 같은 관측일만 사용 |
| Cboe VIX History CSV | 미국 최근 완료 세션 판별, VIX 종가 | `pt`, close |
| ECB Data API EXR CSV | EUR/USD·USD/JPY·GBP/USD 교차환율 | reference rate, 통화쌍별 단위 |
| 한국은행 ECOS `802Y001` | 한국 최근 완료 세션 판별, KOSPI·KOSDAQ | `pt`, close |

FRED `series` 명령은 발표 지연을 명시하는 보조 fallback으로 유지한다. `stale: true` 또는 `lag_days > 0`인 값은 목표 세션 값으로 쓰지 않는다.

## 사용 예시

```bash
npx -y @nomadamas/k-skill@0 exec multi-asset-morning-briefing scripts/market_data.py -- snapshot --briefing-date 2026-09-17
npx -y @nomadamas/k-skill@0 exec multi-asset-morning-briefing scripts/market_data.py -- yields --last 5 --session 2026-09-16
npx -y @nomadamas/k-skill@0 exec multi-asset-morning-briefing scripts/market_data.py -- cboe-vix --last 5 --session 2026-09-16
npx -y @nomadamas/k-skill@0 exec multi-asset-morning-briefing scripts/market_data.py -- ecb-fx --last 5 --session 2026-09-16
```

`snapshot`은 `sessions`, `items`, `warnings`, `failures`를 반환한다. 각 item에는 `symbol`, `section`, `value`, `unit`, `observed`, `session`, `basis`, `source_name`, `source_url`이 들어간다. 한 원천이 실패해도 다른 원천은 계속 수집한다.

## 브리핑 계약

첫 줄은 `YYYY.MM.DD Morning Market Briefing`, 본문은 다음 7개 섹션이다.

1. Summary
2. Rates
3. FX
4. Commodity
5. Equity, Vol
6. 한국 증시
7. 주요 일정

각 bullet은 사실·수치·해석을 직접 뒷받침하는 Markdown 링크로 끝나며 리서치 메모형 종결을 사용한다. 결과는 대화에만 출력하고 파일을 만들지 않는다.

일정은 브리핑일부터 향후 5개 한국 거래일을 대상으로 Fed·BLS·BEA·Treasury·ECB·BOJ·한국은행·통계청·기업 IR 등 공식 발표 일정을 우선한다. 이용약관과 HTML 구조에 취약한 Investing.com 자동 파서는 사용하지 않는다.

뉴스는 제목 부분 문자열로 자동 분류하지 않는다. 원문에서 자산과 촉매를 확인하고 기본 `07:00 KST` cutoff 이후 기사는 제외한다.

## 안전·실패 처리

- 원격 응답은 8 MiB로 제한하고 `Content-Length`와 스트리밍 양쪽을 검사한다.
- JSON/CSV 파싱 오류는 typed failure로 반환한다.
- 원천별 실패를 `failures[]`에 격리한다.
- 세션 불일치·stale·출처 충돌은 추정이나 보간 없이 해당 값만 제외한다.

## 테스트

```bash
python -m unittest discover -s multi-asset-morning-briefing/tests -p "test_*.py"
```

오프라인 테스트가 공식 원천 파서, ZIP 병합, curve 산술, 단위, 독립 세션, source failure 격리, 비정상 JSON, 응답 크기 제한과 실제 완성 브리핑 fixture의 제목·7개 섹션·링크·문체 계약을 검증한다.
