# 근처 술집 조회 가이드

## 이 기능으로 할 수 있는 일

- 서울역/강남/사당/논현 같은 위치 질의를 Kakao Local 공식 API 검색으로 변환
- 기준 장소 좌표를 중심으로 술집 후보를 거리순 조회
- 술집명, 카테고리, 주소, 전화번호, 거리, 카카오맵 장소 링크 제공
- 공식 API에 없는 현재 영업 상태, 대표 메뉴, 좌석 옵션은 장소 링크에서 후속 확인

## 가장 먼저 할 일

이 기능은 **반드시 현재 위치를 먼저 물어본 뒤** 실행합니다.

권장 질문 예시:

```text
현재 위치를 알려주세요. 서울역/강남/사당 같은 역명이나 동네명으로 보내주시면 카카오맵 기준 근처 술집을 찾아볼게요.
```

위치가 넓거나 애매하면 가까운 역명이나 동 이름으로 한 번 더 좁힙니다.

## 기본 조회 경로

### 후보 검색

- Kakao Developers Local REST API
- proxy route: `https://k-skill-proxy.nomadamas.org/v1/kakao-map/search/keyword`
- 사용자 API key: 필요 없음

`kakao-bar-nearby` 패키지는 먼저 위치 anchor를 검색한 뒤, 해당 좌표를 중심으로 `<location> 술집`을 거리순 조회합니다.

### 상세 정보 핸드오프

- Kakao Map 장소 페이지: `https://place.map.kakao.com/<id>`
- 반환 필드: `items[].detailLookup.url`

메뉴·현재 영업 상태·좌석 옵션은 Kakao Local 공식 API 응답에 포함되지 않습니다. 이 정보는 상위 후보의 `detailLookup.url`을 브라우저로 열어 실제로 보이는 값만 확인합니다.

모바일 검색 HTML과 내부 `place-api.map.kakao.com/places/panel3` JSON은 기본 검색 경로로 사용하지 않습니다.

## Node.js 예시

```js
const { searchNearbyBarsByLocationQuery } = require("kakao-bar-nearby");

async function main() {
  const result = await searchNearbyBarsByLocationQuery("서울역", {
    limit: 5,
    radius: 3000
  });

  for (const item of result.items) {
    console.log(item.name, item.distanceMeters, item.detailLookup.url);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
```

## 공식 API 단계의 반환 계약

```json
{
  "anchor": {
    "name": "서울역",
    "sourceUrl": "https://place.map.kakao.com/..."
  },
  "items": [
    {
      "name": "후보 술집",
      "phone": "02-0000-0000",
      "distanceMeters": 180,
      "sourceUrl": "https://place.map.kakao.com/...",
      "isOpenNow": null,
      "openStatus": null,
      "menuSamples": [],
      "seatingKeywords": [],
      "capacityHint": null,
      "detailLookup": {
        "status": "required",
        "url": "https://place.map.kakao.com/...",
        "fields": [
          "openStatus",
          "menuSamples",
          "seatingKeywords",
          "capacityHint"
        ]
      }
    }
  ],
  "meta": {
    "source": "kakao-local-rest-api",
    "fetchedPanels": 0,
    "detailLookupRequiredCount": 1
  }
}
```

`detailLookup.status`가 `required`이면 영업·메뉴·좌석 정보가 아직 확인되지 않은 상태입니다.

## 상세 페이지에서 확인할 항목

1. 장소명이 API 후보와 일치하는지 확인
2. 현재 영업 상태와 오늘 영업시간
3. 대표 메뉴 2~3개
4. 단체석, 룸, 바테이블, 혼술 등 좌석/인원 힌트
5. 상세 페이지에 표시된 전화번호

페이지에 없는 값은 추정하지 않고 `상세 정보 미확인`으로 표시합니다.

## 실패 모드

- `429 rate_limited`: 반복 호출하지 말고 잠시 후 재시도
- `502 upstream_error` / `503 upstream_not_configured`: Kakao 공식 API 프록시 상태를 그대로 안내
- 기준 장소가 모호함: 가까운 역명이나 동 이름을 다시 질문
- 후보 없음: 반경을 넓히거나 `와인바`, `이자카야`, `호프`처럼 키워드 구체화
- 상세 페이지 차단/CAPTCHA/빈 화면: 우회하지 않고 API 후보와 장소 링크까지만 제공

## 주의할 점

- Kakao Local 검색 결과와 거리는 조회 시점에 따라 바뀔 수 있습니다.
- 상세 페이지의 메뉴와 영업시간도 수시로 변경될 수 있습니다.
- 좌석 수를 정확히 제공하지 않으면 `단체 방문 가능` 같은 보수적인 힌트만 사용합니다.
- 공식 API에서 확인한 값과 상세 페이지에서 확인한 값을 구분해 표시합니다.
