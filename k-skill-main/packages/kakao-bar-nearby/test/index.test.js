const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const {
  normalizePlacePanel,
  parseSearchResultsHtml,
  searchNearbyBarsByLocationQuery,
  selectAnchorCandidate
} = require("../src/index");

const fixturesDir = path.join(__dirname, "fixtures");
const anchorSearchHtml = fs.readFileSync(path.join(fixturesDir, "anchor-search.html"), "utf8");
const barSearchHtml = fs.readFileSync(path.join(fixturesDir, "bar-search.html"), "utf8");
const openBarPanel = JSON.parse(fs.readFileSync(path.join(fixturesDir, "open-bar-panel.json"), "utf8"));

test("parseSearchResultsHtml keeps the legacy Kakao mobile card parser compatible", () => {
  const items = parseSearchResultsHtml(barSearchHtml);

  assert.equal(items.length, 3);
  assert.deepEqual(items[0], {
    id: "2001",
    name: "데이브루펍",
    category: "맥주,호프",
    address: "서울 중구 칠패로 31",
    phone: "02-1111-2222",
    openStatusLabel: "영업중",
    openStatusText: "영업시간 12:00 ~ 23:30"
  });
});

test("selectAnchorCandidate keeps the legacy normalized candidate contract", () => {
  const anchor = selectAnchorCandidate("서울역", parseSearchResultsHtml(anchorSearchHtml));

  assert.equal(anchor.id, "1001");
  assert.equal(anchor.name, "서울역");
  assert.equal(anchor.category, "기차역");
});

test("normalizePlacePanel keeps the legacy detail-panel normalizer compatible", () => {
  const item = normalizePlacePanel(openBarPanel, {
    id: "2001",
    phone: "02-1111-2222",
    openStatusLabel: "영업중",
    openStatusText: "영업시간 12:00 ~ 23:30"
  }, {
    latitude: 37.55472,
    longitude: 126.97068
  });

  assert.equal(item.id, "2001");
  assert.equal(item.name, "데이브루펍");
  assert.equal(item.isOpenNow, true);
  assert.deepEqual(item.menuSamples, ["수제맥주 샘플러", "감바스", "페퍼로니 피자"]);
  assert.deepEqual(item.seatingKeywords, ["단체석", "바테이블"]);
});

test("searchNearbyBarsByLocationQuery uses official Kakao Local proxy results and returns detail handoffs", async () => {
  const calls = [];
  const result = await searchNearbyBarsByLocationQuery("서울역", {
    limit: 5,
    radius: 2500,
    fetchImpl: async (url) => {
      const parsed = new URL(String(url));
      calls.push(parsed);

      if (parsed.searchParams.get("q") === "서울역") {
        return makeJsonResponse({
          documents: [
            kakaoDocument({
              id: "1001",
              name: "서울역",
              category: "교통,수송 > 기차역 > 서울역",
              longitude: 126.97068,
              latitude: 37.55472,
              url: "https://place.map.kakao.com/1001"
            })
          ],
          meta: { total_count: 1 }
        });
      }

      if (parsed.searchParams.get("q") === "서울역 술집") {
        assert.equal(parsed.searchParams.get("x"), "126.97068");
        assert.equal(parsed.searchParams.get("y"), "37.55472");
        assert.equal(parsed.searchParams.get("radius"), "2500");
        assert.equal(parsed.searchParams.get("sort"), "distance");

        return makeJsonResponse({
          documents: [
            kakaoDocument({
              id: "2001",
              name: "데이브루펍",
              category: "음식점 > 술집 > 맥주,호프",
              distance: "180",
              url: "https://place.map.kakao.com/2001"
            }),
            kakaoDocument({
              id: "2002",
              name: "밤산책와인바",
              category: "음식점 > 술집 > 와인바",
              distance: "90",
              url: "http://place.map.kakao.com/2002"
            }),
            kakaoDocument({
              id: "2003",
              name: "서울역국밥",
              category: "음식점 > 한식",
              distance: "50",
              url: "https://place.map.kakao.com/2003"
            })
          ],
          meta: { total_count: 3 }
        });
      }

      throw new Error(`unexpected url: ${parsed}`);
    }
  });

  assert.equal(result.anchor.name, "서울역");
  assert.equal(result.anchor.sourceUrl, "https://place.map.kakao.com/1001");
  assert.deepEqual(result.items.map((item) => item.name), ["밤산책와인바", "데이브루펍"]);
  assert.deepEqual(result.items[0].detailLookup, {
    status: "required",
    url: "https://place.map.kakao.com/2002",
    fields: ["openStatus", "menuSamples", "seatingKeywords", "capacityHint"]
  });
  assert.equal(result.items[0].isOpenNow, null);
  assert.equal(result.items[0].openStatus, null);
  assert.deepEqual(result.items[0].menuSamples, []);
  assert.deepEqual(result.items[0].seatingKeywords, []);
  assert.equal(result.meta.source, "kakao-local-rest-api");
  assert.equal(result.meta.detailLookupRequiredCount, 2);
  assert.equal(result.meta.fetchedPanels, 0);
  assert.equal(result.meta.openNowCount, null);
  assert.equal(calls.length, 2);
  assert.ok(calls.every((url) => url.origin === "https://k-skill-proxy.nomadamas.org"));
  assert.ok(calls.every((url) => url.pathname === "/v1/kakao-map/search/keyword"));
});

test("searchNearbyBarsByLocationQuery retries a station query through the official API", async () => {
  const queries = [];
  const result = await searchNearbyBarsByLocationQuery("사당", {
    proxyBaseUrl: "https://proxy.example.test/",
    limit: 1,
    fetchImpl: async (url) => {
      const parsed = new URL(String(url));
      const query = parsed.searchParams.get("q");
      queries.push(query);

      if (query === "사당") {
        return makeJsonResponse({
          documents: [
            kakaoDocument({
              id: "1100",
              name: "사당한우",
              category: "음식점 > 한식 > 육류,고기",
              url: "https://place.map.kakao.com/1100"
            })
          ]
        });
      }

      if (query === "사당역") {
        return makeJsonResponse({
          documents: [
            kakaoDocument({
              id: "1200",
              name: "사당역",
              category: "교통,수송 > 지하철,전철 > 수도권2호선",
              longitude: 126.98163,
              latitude: 37.47659,
              url: "https://place.map.kakao.com/1200"
            })
          ]
        });
      }

      if (query === "사당 술집") {
        assert.equal(parsed.origin, "https://proxy.example.test");
        return makeJsonResponse({
          documents: [
            kakaoDocument({
              id: "2200",
              name: "사당포차",
              category: "음식점 > 술집 > 포장마차",
              distance: "140",
              url: ""
            })
          ]
        });
      }

      throw new Error(`unexpected url: ${parsed}`);
    }
  });

  assert.deepEqual(queries, ["사당", "사당역", "사당 술집"]);
  assert.equal(result.anchor.name, "사당역");
  assert.equal(result.items[0].sourceUrl, "https://place.map.kakao.com/2200");
  assert.equal(result.items[0].detailLookup.url, "https://place.map.kakao.com/2200");
});

test("searchNearbyBarsByLocationQuery surfaces official proxy failures without scraping fallback", async () => {
  await assert.rejects(
    searchNearbyBarsByLocationQuery("서울역", {
      fetchImpl: async () => makeJsonResponse({
        error: "upstream_not_configured",
        message: "KAKAO_REST_API_KEY is not configured."
      }, 503)
    }),
    /Kakao Map proxy request failed with 503.*KAKAO_REST_API_KEY is not configured/u
  );
});

test("searchNearbyBarsByLocationQuery rejects unrelated results for an explicit station query", async () => {
  const queries = [];

  await assert.rejects(
    searchNearbyBarsByLocationQuery("사당역", {
      fetchImpl: async (url) => {
        const query = new URL(String(url)).searchParams.get("q");
        queries.push(query);
        return makeJsonResponse({
          documents: [
            kakaoDocument({
              id: "3300",
              name: "사당역맥주집",
              category: "음식점 > 술집 > 맥주,호프",
              url: "https://place.map.kakao.com/3300"
            })
          ]
        });
      }
    }),
    /No usable Kakao Local place candidate was available for 사당역/u
  );

  assert.deepEqual(queries, ["사당역"]);
});

function makeJsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json"
    }
  });
}

function kakaoDocument({
  id,
  name,
  category,
  address = "서울 중구 세종대로 1",
  phone = "02-1111-2222",
  longitude = 126.971,
  latitude = 37.555,
  distance = "",
  url
}) {
  return {
    id,
    place_name: name,
    category_name: category,
    address_name: address,
    road_address_name: address,
    phone,
    x: String(longitude),
    y: String(latitude),
    distance,
    place_url: url
  };
}
