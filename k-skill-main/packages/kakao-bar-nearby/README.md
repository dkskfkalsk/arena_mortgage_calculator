# kakao-bar-nearby

Kakao Local REST API를 `k-skill-proxy` 경유로 호출해 근처 술집 후보를 찾고, 메뉴·영업 상태·좌석 정보 확인용 카카오맵 상세 링크를 반환하는 Node.js 패키지입니다.

## 설치

```bash
npm install kakao-bar-nearby
```

## 조회 원칙

- 사용 흐름에서는 현재 위치를 먼저 물어본다.
- 장소 후보와 거리 정보는 Kakao Developers 공식 Local API에서 가져옵니다.
- 사용자는 Kakao API key를 준비할 필요가 없습니다.
- 공식 API에 없는 메뉴·현재 영업 상태·좌석 정보는 자동으로 추정하지 않습니다.
- 각 후보의 `detailLookup.url`을 카카오맵 장소 페이지로 넘겨 후속 확인합니다.
- 기존 모바일 검색 HTML 및 장소 패널 파서 export는 호환성을 위해 남아 있지만 기본 검색 경로에서는 사용하지 않습니다.

## 사용 예시

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

기본 프록시는 `https://k-skill-proxy.nomadamas.org`입니다. 별도 프록시는 `KSKILL_PROXY_BASE_URL` 또는 `proxyBaseUrl` 옵션으로 지정할 수 있습니다.

## 반환 구조

```json
{
  "anchor": {
    "name": "서울역",
    "sourceUrl": "https://place.map.kakao.com/..."
  },
  "items": [
    {
      "name": "후보 술집",
      "distanceMeters": 180,
      "sourceUrl": "https://place.map.kakao.com/...",
      "isOpenNow": null,
      "menuSamples": [],
      "seatingKeywords": [],
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
    "fetchedPanels": 0
  }
}
```

`detailLookup.status`가 `required`이면 상세 정보는 아직 확인되지 않은 상태입니다. 카카오맵 상세 페이지에서 실제로 확인한 값만 후속 응답에 추가하세요.

## 공개 API

- `searchNearbyBarsByLocationQuery(locationQuery, options?)`
- `fetchKakaoKeywordSearch(query, params?, options?)`
- `normalizeKakaoPlaceDocument(document, options?)`

호환성 유지 export:

- `parseSearchResultsHtml(html)`
- `selectAnchorCandidate(locationQuery, items)`
- `normalizePlacePanel(panel, searchItem, anchorPoint)`
- `fetchSearchResults(query, options?)`
- `fetchPlacePanel(confirmId, options?)`
