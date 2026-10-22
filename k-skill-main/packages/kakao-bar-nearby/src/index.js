const {
  isAnchorLikePlace,
  isBarPanel,
  normalizePlacePanel,
  parseSearchResultsHtml,
  selectAnchorCandidate
} = require("./parse");

const DEFAULT_PROXY_BASE_URL = "https://k-skill-proxy.nomadamas.org";
const KAKAO_KEYWORD_SEARCH_PATH = "/v1/kakao-map/search/keyword";
const DEFAULT_SEARCH_RADIUS = 3000;
const DEFAULT_SEARCH_SIZE = 15;
const DEFAULT_ANCHOR_SIZE = 8;
const DETAIL_LOOKUP_FIELDS = [
  "openStatus",
  "menuSamples",
  "seatingKeywords",
  "capacityHint"
];

// Legacy exports remain available for existing consumers, but the main search
// workflow no longer calls either mobile HTML or the internal panel endpoint.
const SEARCH_VIEW_URL = "https://m.map.kakao.com/actions/searchView";
const PLACE_PANEL_URL_BASE = "https://place-api.map.kakao.com/places/panel3";
const DEFAULT_PANEL_LIMIT = 8;
const STATIONISH_CATEGORY_PATTERN = /(기차역|전철역|지하철역|환승역|수도권\d+호선|역)$/u;
const DEFAULT_BROWSER_HEADERS = {
  accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  "accept-language": "ko,en-US;q=0.9,en;q=0.8",
  "user-agent":
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
};

async function requestLegacySurface(url, options = {}, responseType = "text") {
  const fetchImpl = options.fetchImpl || global.fetch;

  if (typeof fetchImpl !== "function") {
    throw new Error("A fetch implementation is required.");
  }

  const response = await fetchImpl(url, {
    headers: {
      ...DEFAULT_BROWSER_HEADERS,
      ...(options.headers || {})
    },
    signal: options.signal
  });

  if (!response.ok) {
    throw new Error(`Kakao bar lookup request failed with ${response.status} for ${url}`);
  }

  return responseType === "json" ? response.json() : response.text();
}

async function fetchSearchResults(query, options = {}) {
  const url = new URL(SEARCH_VIEW_URL);
  url.searchParams.set("q", String(query || "").trim());
  return requestLegacySurface(url.toString(), options, "text");
}

async function fetchPlacePanel(confirmId, options = {}) {
  return requestLegacySurface(`${PLACE_PANEL_URL_BASE}/${confirmId}`, options, "json");
}

function resolveProxyBaseUrl(options = {}) {
  return String(
    options.proxyBaseUrl ||
    process.env.KSKILL_PROXY_BASE_URL ||
    DEFAULT_PROXY_BASE_URL
  ).replace(/\/+$/u, "");
}

async function fetchKakaoKeywordSearch(query, params = {}, options = {}) {
  const fetchImpl = options.fetchImpl || global.fetch;

  if (typeof fetchImpl !== "function") {
    throw new Error("A fetch implementation is required.");
  }

  const url = new URL(`${resolveProxyBaseUrl(options)}${KAKAO_KEYWORD_SEARCH_PATH}`);
  url.searchParams.set("q", String(query || "").trim());

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  const response = await fetchImpl(url, {
    headers: {
      accept: "application/json",
      ...(options.headers || {})
    },
    signal: options.signal
  });

  let body;
  try {
    body = await response.json();
  } catch (_error) {
    body = null;
  }

  if (!response.ok) {
    const detail = body?.message || body?.error || "Unknown proxy error.";
    throw new Error(`Kakao Map proxy request failed with ${response.status}: ${detail}`);
  }

  if (!body || !Array.isArray(body.documents)) {
    throw new Error("Kakao Map proxy returned an invalid keyword-search response.");
  }

  return body;
}

function numberOrNull(value) {
  if (value === undefined || value === null || value === "") {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeKakaoPlaceDocument(document, { detailHandoff = false } = {}) {
  const id = String(document?.id || "").trim();
  const providedUrl = String(document?.place_url || "").trim();
  const sourceUrl = providedUrl
    ? providedUrl.replace(/^http:\/\/place\.map\.kakao\.com\//u, "https://place.map.kakao.com/")
    : (id ? `https://place.map.kakao.com/${id}` : null);
  const item = {
    id,
    name: String(document?.place_name || "").trim(),
    category: String(document?.category_name || "").trim(),
    address: String(document?.road_address_name || document?.address_name || "").trim(),
    phone: String(document?.phone || "").trim() || null,
    latitude: numberOrNull(document?.y),
    longitude: numberOrNull(document?.x),
    distanceMeters: numberOrNull(document?.distance),
    sourceUrl
  };

  if (!detailHandoff) {
    return item;
  }

  return {
    ...item,
    isOpenNow: null,
    openStatus: null,
    menuSamples: [],
    seatingKeywords: [],
    capacityHint: null,
    tags: [],
    summary: null,
    detailLookup: {
      status: "required",
      url: sourceUrl,
      fields: [...DETAIL_LOOKUP_FIELDS]
    }
  };
}

function isUsableAnchor(anchor) {
  return Boolean(
    anchor?.sourceUrl &&
    Number.isFinite(anchor?.latitude) &&
    Number.isFinite(anchor?.longitude)
  );
}

function normalizeQueryText(value) {
  return String(value || "")
    .replace(/[\s\p{P}\p{S}]+/gu, "")
    .toLowerCase();
}

function matchesAnchorQueryPrefix(query, anchor) {
  const normalizedQuery = normalizeQueryText(query);
  const normalizedName = normalizeQueryText(anchor?.name);
  return Boolean(normalizedQuery && normalizedName.startsWith(normalizedQuery));
}

function shouldAcceptAnchor(query, anchor) {
  if (!isUsableAnchor(anchor)) {
    return false;
  }

  if (!/역$/u.test(query)) {
    return true;
  }

  return (
    matchesAnchorQueryPrefix(query, anchor) &&
    (STATIONISH_CATEGORY_PATTERN.test(anchor.category) || isAnchorLikePlace(anchor))
  );
}

function shouldRetryWithStationQuery(query, anchor) {
  return (
    !/역$/u.test(query) &&
    (!isUsableAnchor(anchor) ||
      (!STATIONISH_CATEGORY_PATTERN.test(anchor.category) && !isAnchorLikePlace(anchor)))
  );
}

async function resolveAnchor(query, options = {}) {
  const response = await fetchKakaoKeywordSearch(query, {
    size: DEFAULT_ANCHOR_SIZE
  }, options);
  const anchorCandidates = response.documents.map((document) =>
    normalizeKakaoPlaceDocument(document)
  );
  const selected = selectAnchorCandidate(query, anchorCandidates);
  const rankedCandidates = selected
    ? [selected, ...anchorCandidates.filter((candidate) => candidate.id !== selected.id)]
    : anchorCandidates;
  const anchor = rankedCandidates.find((candidate) => shouldAcceptAnchor(query, candidate));

  if (!anchor) {
    throw new Error(`No usable Kakao Local place candidate was available for ${query}.`);
  }

  return {
    anchor,
    anchorCandidates
  };
}

function normalizeRadius(value) {
  const radius = value === undefined ? DEFAULT_SEARCH_RADIUS : Number(value);

  if (!Number.isInteger(radius) || radius < 0 || radius > 20000) {
    throw new Error("radius must be an integer between 0 and 20000.");
  }

  return radius;
}

function sortBars(items) {
  return [...items].sort((left, right) => {
    const leftDistance = left.distanceMeters ?? Number.POSITIVE_INFINITY;
    const rightDistance = right.distanceMeters ?? Number.POSITIVE_INFINITY;

    if (leftDistance !== rightDistance) {
      return leftDistance - rightDistance;
    }

    return left.name.localeCompare(right.name, "ko");
  });
}

async function searchNearbyBarsByLocationQuery(locationQuery, options = {}) {
  const query = String(locationQuery || "").trim();

  if (!query) {
    throw new Error("locationQuery is required.");
  }

  let { anchor, anchorCandidates } = await resolveAnchor(query, options);
  let anchorFallbackUsed = false;

  if (shouldRetryWithStationQuery(query, anchor)) {
    try {
      const stationResolution = await resolveAnchor(`${query}역`, options);
      anchor = stationResolution.anchor;
      anchorCandidates = stationResolution.anchorCandidates;
      anchorFallbackUsed = true;
    } catch (_error) {
      // Keep the original official API anchor when the station fallback is unavailable.
    }
  }

  const radius = normalizeRadius(options.radius);
  const response = await fetchKakaoKeywordSearch(`${query} 술집`, {
    x: anchor.longitude,
    y: anchor.latitude,
    radius,
    sort: "distance",
    size: DEFAULT_SEARCH_SIZE
  }, options);
  const normalizedItems = sortBars(
    response.documents
      .map((document) => normalizeKakaoPlaceDocument(document, { detailHandoff: true }))
      .filter((item) => isBarPanel({}, item))
  );
  const limit = Math.max(1, Number(options.limit ?? 5));
  const items = normalizedItems.slice(0, limit);

  return {
    anchor,
    anchorCandidates,
    items,
    meta: {
      evaluatedAt: new Date().toISOString(),
      source: "kakao-local-rest-api",
      totalSearchResults: numberOrNull(response.meta?.total_count) ?? response.documents.length,
      openNowCount: null,
      fetchedPanels: 0,
      detailLookupRequiredCount: items.length,
      anchorFallbackUsed,
      radiusMeters: radius
    }
  };
}

module.exports = {
  DEFAULT_ANCHOR_SIZE,
  DEFAULT_PANEL_LIMIT,
  DEFAULT_PROXY_BASE_URL,
  DEFAULT_SEARCH_RADIUS,
  DEFAULT_SEARCH_SIZE,
  DETAIL_LOOKUP_FIELDS,
  KAKAO_KEYWORD_SEARCH_PATH,
  PLACE_PANEL_URL_BASE,
  SEARCH_VIEW_URL,
  fetchKakaoKeywordSearch,
  fetchPlacePanel,
  fetchSearchResults,
  normalizeKakaoPlaceDocument,
  normalizePlacePanel,
  parseSearchResultsHtml,
  searchNearbyBarsByLocationQuery,
  selectAnchorCandidate
};
