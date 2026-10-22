const ASK_SEOUL_SKILL_BUNDLE_ID = "seoul-weather-risk";
const ASK_SEOUL_WEATHER_RISK_PRODUCT_ID = "weather_place_risk_window";
const ASK_SEOUL_WEATHER_RISK_PATHS = Object.freeze({
  bundle: `/skill/v1/bundles/${ASK_SEOUL_SKILL_BUNDLE_ID}`,
  product: `/skill/v1/products/${ASK_SEOUL_WEATHER_RISK_PRODUCT_ID}`,
  data: `/skill/v1/products/${ASK_SEOUL_WEATHER_RISK_PRODUCT_ID}/data`
});

const DATA_QUERY_FIELDS = new Set([
  "product_row_id",
  "place_id",
  "forecast_at",
  "risk_labels",
  "from",
  "to",
  "limit",
  "cursor"
]);
const DEFAULT_LIMIT = 100;
const MAX_LIMIT = 500;
const MAX_VALUE_LENGTH = 1024;

function queryValue(query, name) {
  const value = query[name];
  if (Array.isArray(value)) throw new Error(`${name} must be provided once.`);
  if (value === undefined || value === null) return null;
  const text = String(value);
  if (!text || text.length > MAX_VALUE_LENGTH) throw new Error(`${name} has an invalid length.`);
  return text;
}

function normalizeLimit(value) {
  if (value === null) return String(DEFAULT_LIMIT);
  if (!/^[1-9][0-9]*$/.test(value)) throw new Error("limit must be an integer from 1 through 500.");
  const limit = Number(value);
  if (limit > MAX_LIMIT) throw new Error("limit must be an integer from 1 through 500.");
  return String(limit);
}

function normalizeAskSeoulWeatherRiskQuery(operation, query = {}) {
  if (!Object.hasOwn(ASK_SEOUL_WEATHER_RISK_PATHS, operation)) {
    throw new Error("That ASK Seoul weather-risk operation is not exposed by this proxy.");
  }

  const keys = Object.keys(query);
  if (operation !== "data") {
    if (keys.length) throw new Error(`${operation} does not accept query parameters.`);
    return {};
  }

  for (const key of keys) {
    if (!DATA_QUERY_FIELDS.has(key)) throw new Error(`${key} is not exposed by this proxy.`);
  }

  const normalized = { limit: normalizeLimit(queryValue(query, "limit")) };
  for (const key of DATA_QUERY_FIELDS) {
    if (key === "limit") continue;
    const value = queryValue(query, key);
    if (value !== null) normalized[key] = value;
  }
  return normalized;
}

function configuredBaseUrl(baseUrl) {
  if (!baseUrl || !String(baseUrl).trim()) return null;
  try {
    const parsed = new URL(String(baseUrl).trim());
    if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.pathname !== "/" || parsed.search || parsed.hash) {
      return null;
    }
    return parsed.origin;
  } catch {
    return null;
  }
}

function proxyFailure(statusCode, error, message) {
  return {
    statusCode,
    contentType: "application/json; charset=utf-8",
    body: JSON.stringify({ error, message })
  };
}

function isExpectedAskSeoulWeatherRiskSuccess(operation, response) {
  if (response.statusCode !== 200 || !/^application\/json(?:\s*;|$)/i.test(response.contentType)) {
    return false;
  }

  try {
    const payload = JSON.parse(response.body);
    if (!payload || Array.isArray(payload) || typeof payload !== "object" || payload.error) return false;
    if (payload.bundle_id !== ASK_SEOUL_SKILL_BUNDLE_ID) return false;
    return operation === "bundle" || payload.product_id === ASK_SEOUL_WEATHER_RISK_PRODUCT_ID;
  } catch {
    return false;
  }
}

async function proxyAskSeoulWeatherRiskRequest({
  operation,
  params = {},
  baseUrl,
  apiKey,
  fetchImpl = global.fetch
}) {
  const configuredOrigin = configuredBaseUrl(baseUrl);
  if (!configuredOrigin || !apiKey) {
    return proxyFailure(
      503,
      "upstream_not_configured",
      "ASK Seoul weather-risk proxy credentials are not configured on the proxy server."
    );
  }

  const path = ASK_SEOUL_WEATHER_RISK_PATHS[operation];
  if (!path) {
    return proxyFailure(400, "bad_request", "That ASK Seoul weather-risk operation is not exposed by this proxy.");
  }

  const url = new URL(path, configuredOrigin);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);

  try {
    const response = await fetchImpl(url.toString(), {
      headers: {
        accept: "application/json",
        authorization: `Bearer ${apiKey}`,
        "user-agent": "k-skill-proxy/ask-seoul-weather-risk"
      },
      redirect: "error",
      signal: AbortSignal.timeout(20000)
    });
    return {
      statusCode: response.status,
      contentType: response.headers.get("content-type") || "application/json; charset=utf-8",
      body: await response.text()
    };
  } catch {
    return proxyFailure(502, "upstream_unavailable", "ASK Seoul weather-risk upstream is unavailable.");
  }
}

module.exports = {
  ASK_SEOUL_SKILL_BUNDLE_ID,
  ASK_SEOUL_WEATHER_RISK_PRODUCT_ID,
  isExpectedAskSeoulWeatherRiskSuccess,
  normalizeAskSeoulWeatherRiskQuery,
  proxyAskSeoulWeatherRiskRequest
};
