const crypto = require("node:crypto");
const { fetchWithRetry } = require("./fetch-with-retry");

const COUPANG_API_BASE_URL = "https://api-gateway.coupang.com";
const COUPANG_PRODUCTS_SEARCH_PATH =
  "/v2/providers/affiliate_open_api/apis/openapi/v1/products/search";
const DEFAULT_LIMIT = 10;
const MAX_LIMIT = 10;

function trimOrNull(value) {
  if (value === undefined || value === null) {
    return null;
  }
  const trimmed = String(value).trim();
  return trimmed ? trimmed : null;
}

function parseInteger(value, fallback) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizeCoupangProductSearchQuery(query = {}) {
  const keyword = trimOrNull(query.keyword ?? query.q ?? query.query);
  if (!keyword || keyword.length < 2) {
    throw new Error("Provide keyword/q/query with at least 2 characters.");
  }
  if (keyword.length > 100) {
    throw new Error("keyword must be at most 100 characters.");
  }

  const limit = Math.min(Math.max(parseInteger(query.limit, DEFAULT_LIMIT), 1), MAX_LIMIT);
  const subId = trimOrNull(query.subId ?? query.sub_id);
  if (subId && subId.length > 100) {
    throw new Error("subId must be at most 100 characters.");
  }

  return { keyword, limit, subId };
}

function buildCoupangSignedDate(now = new Date()) {
  return now
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}Z$/, "Z")
    .slice(2);
}

function buildCoupangAuthorization({
  accessKey,
  secretKey,
  method,
  pathWithQuery,
  signedDate
}) {
  const [path, query = ""] = pathWithQuery.split("?", 2);
  const message = `${signedDate}${method.toUpperCase()}${path}${query}`;
  const signature = crypto
    .createHmac("sha256", secretKey)
    .update(message, "utf8")
    .digest("hex");
  return (
    `CEA algorithm=HmacSHA256, access-key=${accessKey}, ` +
    `signed-date=${signedDate}, signature=${signature}`
  );
}

function normalizeCoupangProducts(payload) {
  const data = payload && typeof payload === "object" ? payload.data : null;
  const rawItems = Array.isArray(data)
    ? data
    : Array.isArray(data?.productData)
      ? data.productData
      : Array.isArray(data?.products)
        ? data.products
        : Array.isArray(payload?.productData)
          ? payload.productData
          : [];

  return rawItems.map((item, index) => ({
    rank: index + 1,
    product_id: item?.productId == null ? null : String(item.productId),
    title: item?.productName || null,
    price: item?.productPrice == null ? null : Number(item.productPrice),
    price_text: item?.productPrice == null ? null : `${Number(item.productPrice).toLocaleString("ko-KR")}원`,
    url: item?.productUrl || null,
    image_url: item?.productImage || item?.productImageUrl || null,
    mall_name: item?.vendorName || null,
    review_count: item?.reviewCount == null ? null : Number(item.reviewCount),
    score: item?.ratingAverage == null ? null : Number(item.ratingAverage),
    is_rocket: Boolean(item?.isRocket),
    is_free_shipping: Boolean(item?.isFreeShipping)
  }));
}

async function searchCoupangProducts({
  keyword,
  limit,
  subId,
  accessKey,
  secretKey,
  baseUrl = COUPANG_API_BASE_URL,
  fetchImpl = globalThis.fetch,
  now = () => new Date()
}) {
  if (!accessKey || !secretKey) {
    const error = new Error("COUPANG_ACCESS_KEY and COUPANG_SECRET_KEY are required.");
    error.code = "upstream_not_configured";
    error.statusCode = 503;
    throw error;
  }

  const params = new URLSearchParams({ keyword, limit: String(limit) });
  if (subId) {
    params.set("subId", subId);
  }
  const pathWithQuery = `${COUPANG_PRODUCTS_SEARCH_PATH}?${params.toString()}`;
  const signedDate = buildCoupangSignedDate(now());
  const authorization = buildCoupangAuthorization({
    accessKey,
    secretKey,
    method: "GET",
    pathWithQuery,
    signedDate
  });

  let response;
  try {
    response = await fetchWithRetry(`${baseUrl}${pathWithQuery}`, {
      fetchImpl,
      method: "GET",
      headers: {
        Authorization: authorization,
        "Content-Type": "application/json"
      }
    });
  } catch (cause) {
    const error = new Error(`Coupang upstream request failed: ${cause.message}`);
    error.code = "upstream_unavailable";
    error.statusCode = 502;
    throw error;
  }

  const rawBody = await response.text();
  let body;
  try {
    body = rawBody ? JSON.parse(rawBody) : null;
  } catch {
    const error = new Error("Coupang upstream returned invalid JSON.");
    error.code = "upstream_invalid_response";
    error.statusCode = 502;
    throw error;
  }

  if (!response.ok) {
    const error = new Error(`Coupang upstream returned HTTP ${response.status}.`);
    error.code = response.status === 401 || response.status === 403
      ? "upstream_forbidden"
      : "upstream_error";
    error.statusCode = 502;
    error.upstreamStatusCode = response.status;
    error.upstreamBodySnippet = rawBody.slice(0, 500);
    throw error;
  }

  return {
    items: normalizeCoupangProducts(body),
    upstream: {
      provider: "coupang-partners-api",
      response_code: body?.rCode ?? body?.code ?? null
    }
  };
}

module.exports = {
  COUPANG_API_BASE_URL,
  COUPANG_PRODUCTS_SEARCH_PATH,
  buildCoupangAuthorization,
  buildCoupangSignedDate,
  normalizeCoupangProductSearchQuery,
  normalizeCoupangProducts,
  searchCoupangProducts
};
