"use strict";

const { findDongcode } = require("./dongcode");

const BASE = "https://api.kbland.kr";
const KBLAND = "https://kbland.kr";
const NEXT_DATA_BASE = "https://kbland.kr/_next/data";
const HEADERS = {
  Accept: "application/json, text/plain, */*",
  "Accept-Language": "ko-KR,ko;q=0.9",
  "Cache-Control": "no-cache",
  Origin: "https://kbland.kr",
  Referer: "https://kbland.kr/",
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
};
const HTML_HEADERS = {
  ...HEADERS,
  Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
  "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
  "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
  "sec-ch-ua-mobile": "?0",
  "sec-ch-ua-platform": '"Windows"',
  "Upgrade-Insecure-Requests": "1",
};

async function fetchJson(url, params = {}) {
  const u = new URL(url);
  Object.entries(params).forEach(([k, v]) => u.searchParams.set(k, String(v)));
  const res = await fetch(u.toString(), { headers: HEADERS });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
  return res.json();
}

async function fetchText(url, headers = HTML_HEADERS) {
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
  return res.text();
}

async function getComplexList(dongcode) {
  const data = await fetchJson(`${BASE}/land-price/price/fastPriceInfo`, {
    법정동코드: dongcode,
    유형: "1",
    거래유형: "0",
  });
  return (data.dataBody && data.dataBody.data) || [];
}

async function getComplexPrice(complexId) {
  const data = await fetchJson(`${BASE}/land-complex/complex/mpriByType`, {
    단지기본일련번호: complexId,
  });
  return (data.dataBody && data.dataBody.data) || [];
}

/** 단지 기본정보 (세대수 등). api.kbland.kr */
async function getComplexInfo(complexId) {
  try {
    const data = await fetchJson(`${BASE}/land-complex/complex/info`, {
      단지기본일련번호: complexId,
    });
    return (data.dataBody && data.dataBody.data) || null;
  } catch (_) {
    return null;
  }
}

function extractComplexName(address) {
  const patterns = [
    /([가-힣]+마을)/,
    /([가-힣]+단지)/,
    /([가-힣]+아파트)/,
    /([가-힣]+(?:힐스|힐스테이트))/,
    /([가-힣]+(?:아이파크|래미안|자이|힐스테이트|푸르지오|센트럴|팰리스|월드|뉴|더|디|엘|리|그린|보람|연화|은하|중흥|한라|포도|무지개|꿈|덕유|설악|복사골|금강|동원|대신|범양|영안|현대|형진|풍남|우방|아이유쉘|유쉘))/,
  ];
  for (const re of patterns) {
    const m = address.match(re);
    if (m) return m[1];
  }
  const lotName = /\d+(?:-\d+)?\s+([가-힣]+?)(?=\s+제\d+동|\s+제\d+층|\s+제\d+호|$)/;
  let m = address.match(lotName);
  if (m) {
    const name = m[1].trim();
    if (name.length >= 2 && !["동", "구", "시", "군", "읍", "면"].includes(name)) return name;
  }
  const lot = /(\d+(?:-\d+)?)\s+([가-힣]+(?:마을|단지|아파트)?)/;
  m = address.match(lot);
  if (m) {
    const name = m[2];
    if (name.length >= 2 && !["동", "구", "시", "군", "읍", "면"].includes(name)) return name;
  }
  return null;
}

function selectComplex(complexes, complexName, address) {
  let lotNumber = null;
  const lm = address.match(/(\d+(?:-\d+)?)/);
  if (lm) lotNumber = lm[1];

  let selected = null;
  let bestScore = 0;
  let bestMatch = null;

  for (const c of complexes) {
    const apiName = (c["단지명"] || c.name || "").trim();
    const apiNameNs = apiName.replace(/\s/g, "");
    const addr = c["주소"] || "";

    if (complexName && (complexName === apiName || (apiNameNs && complexName === apiNameNs))) {
      selected = c;
      break;
    }

    let score = 0;
    const base = (apiName || "").replace(/\s/g, "").replace(/[()]/g, "");
    if (complexName && (apiName.includes(complexName) || (base && base.includes(complexName)))) {
      score = complexName.length / (base.length || 1);
      if ((apiName || "").includes("(")) score = Math.max(score, 0.9);
    } else if (complexName && (complexName.includes(apiName) || (base && complexName.includes(base)))) {
      score = (base.length || apiName.length) / complexName.length;
    }
    if (lotNumber && addr.includes(lotNumber)) score += 0.2;
    if (score > bestScore) {
      bestScore = score;
      bestMatch = c;
    }
  }

  if (selected) return selected;
  if (bestMatch) return bestMatch;
  return complexes[0] || null;
}

function findMatchingPrice(prices, area) {
  const tol = 0.01;
  let best = null;
  let minDiff = Infinity;

  for (const p of prices) {
    const parse = (v) => {
      if (v == null) return null;
      const n = parseFloat(String(v).replace(/,/g, "").replace(/만원/g, "").trim());
      return isNaN(n) ? null : n;
    };
    const ded = parse(p["전용면적"]);
    const sup = parse(p["공급면적"] || p["면적"]);
    const val = ded ?? sup;
    if (val == null) continue;
    const diff = Math.abs(val - area);
    if (diff <= tol && diff < minDiff) {
      minDiff = diff;
      best = p;
    }
  }
  return best;
}

function parsePrice(v) {
  if (v == null) return null;
  const s = String(v).replace(/,/g, "").replace(/만원/g, "").trim();
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

const HOUSEHOLD_KEYS = ["세대수", "households", "totHshldCnt", "hshldCnt", "총세대수", "totalHouseholdCnt"];
const MAX_HOUSEHOLDS = 100000;

function findNumInObj(obj, keys, maxVal = MAX_HOUSEHOLDS, seen = new Set()) {
  if (obj == null || seen.has(obj)) return null;
  try {
    seen.add(obj);
  } catch (_) {
    return null;
  }
  if (typeof obj === "object" && obj !== null) {
    for (const [k, v] of Object.entries(obj)) {
      if (keys.includes(k) && v != null) {
        const n = typeof v === "number" ? v : parseInt(String(v).replace(/,/g, ""), 10);
        if (!isNaN(n) && n >= 1 && n <= maxVal) return n;
      }
      const r = findNumInObj(v, keys, maxVal, seen);
      if (r != null) return r;
    }
  }
  if (Array.isArray(obj)) {
    for (const item of obj) {
      const r = findNumInObj(item, keys, maxVal, seen);
      if (r != null) return r;
    }
  }
  return null;
}

function getBuildIdFromHtml(html) {
  const m =
    html.match(/<script[^>]*id=["']__NEXT_DATA__["'][^>]*>([^<]+)<\/script>/) ||
    html.match(/<script[^>]*type=["']application\/json["'][^>]*id=["']__NEXT_DATA__["'][^>]*>([^<]+)<\/script>/);
  if (!m) return null;
  try {
    const data = JSON.parse(m[1]);
    const bid = data && data.buildId;
    return typeof bid === "string" && bid.length > 0 ? bid : null;
  } catch (_) {
    return null;
  }
}

function parseHouseholdsFromText(text) {
  const m = text.match(/([\d,，\s]+)\s*세대/) || text.match(/세대\s*[수:：]*\s*([\d,，]+)/);
  if (!m) return null;
  const s = String(m[1]).replace(/,/g, "").replace(/，/g, "").replace(/\s/g, "").trim();
  const n = parseInt(s, 10);
  return !isNaN(n) && n >= 1 && n <= MAX_HOUSEHOLDS ? n : null;
}

/**
 * kbland.kr/c/{complexId} 또는 API에서 정확한 세대수 추출.
 * 1) land-complex/complex/info API 2) _next/data JSON 3) HTML __NEXT_DATA__/regex
 * @param {string} complexId
 * @returns {Promise<number|null>}
 */
async function fetchHouseholdsFromKbland(complexId) {
  if (!complexId || String(complexId).trim() === "") return null;
  const cid = String(complexId).trim();

  const info = await getComplexInfo(cid);
  if (info) {
    for (const key of HOUSEHOLD_KEYS) {
      const v = info[key];
      if (v != null && String(v).trim() !== "") {
        const n = parseInt(String(v).replace(/,/g, ""), 10);
        if (!isNaN(n) && n >= 1 && n <= MAX_HOUSEHOLDS) return n;
      }
    }
  }

  let buildId = null;
  let html = null;
  for (const url of [`${KBLAND}/`, `${KBLAND}/c/${cid}`]) {
    try {
      html = await fetchText(url);
      buildId = getBuildIdFromHtml(html);
      if (buildId) break;
    } catch (_) {}
  }

  if (buildId) {
    try {
      const url = `${NEXT_DATA_BASE}/${buildId}/c/${cid}.json`;
      const data = await fetch(url, { headers: { ...HEADERS, Accept: "application/json" } }).then((r) =>
        r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))
      );
      const h = findNumInObj(data, HOUSEHOLD_KEYS);
      if (h != null) return h;
    } catch (_) {}
  }

  if (html) {
    const nextMatch =
      html.match(/<script[^>]*id=["']__NEXT_DATA__["'][^>]*>([^<]+)<\/script>/) ||
      html.match(/<script[^>]*type=["']application\/json["'][^>]*id=["']__NEXT_DATA__["'][^>]*>([^<]+)<\/script>/);
    if (nextMatch) {
      try {
        const data = JSON.parse(nextMatch[1]);
        const h = findNumInObj(data, HOUSEHOLD_KEYS);
        if (h != null) return h;
      } catch (_) {}
    }
    const fromText = parseHouseholdsFromText(html);
    if (fromText != null) return fromText;
  }

  return null;
}

/**
 * @param {string} address
 * @param {number} area
 * @param {string|null} [complexName]
 * @returns {Promise<object|null>}
 */
async function getKbPrice(address, area, complexName = null) {
  const dongcode = findDongcode(address);
  if (!dongcode) return null;

  const complexes = await getComplexList(dongcode);
  if (!complexes.length) return null;

  const name = complexName ?? extractComplexName(address);
  const selected = selectComplex(complexes, name, address);
  if (!selected) return null;

  const complexId = selected["단지기본일련번호"] != null ? String(selected["단지기본일련번호"]) : null;
  let prices = selected["매매"] || selected["매매가"] || [];
  if (!prices.length && complexId) {
    prices = await getComplexPrice(complexId);
  }
  if (!prices.length) return null;

  const matched = findMatchingPrice(prices, area);
  if (!matched) return null;

  const pv = matched["일반평균"] || matched["매매일반거래가"] || matched["매매가"] || matched["매매평균가"];
  const pm = matched["하위평균"] || matched["매매하한가"];
  const priceNum = parsePrice(pv);
  if (priceNum == null) return null;

  const priceMinNum = parsePrice(pm);
  const areaVal = parseFloat(
    matched["전용면적"] || matched["공급면적"] || matched["면적"] || area
  );
  const pyeong = (areaVal / 3.3058).toFixed(1);

  let households = null;
  for (const key of ["세대수", "총세대수", "총호수", "호수"]) {
    const v = selected[key];
    if (v != null && String(v).trim() !== "") {
      const n = parseInt(String(v).replace(/,/g, ""), 10);
      if (!isNaN(n) && n >= 1 && n <= MAX_HOUSEHOLDS) {
        households = n;
        break;
      }
    }
  }
  if (households == null && complexId) {
    const h = await fetchHouseholdsFromKbland(complexId);
    if (h != null) households = h;
  }

  return {
    kb_price: priceNum,
    kb_price_min: priceMinNum ?? null,
    kb_price_raw: `${Math.round(priceNum).toLocaleString()}만원`,
    kb_price_min_raw: priceMinNum != null ? `${Math.round(priceMinNum).toLocaleString()}만원` : null,
    households,
    complex_name: selected["단지명"] || selected.name || "알 수 없음",
    complex_id: complexId,
    dongcode,
    area: areaVal,
    pyeong,
    type: matched["주택형타입내용"] || matched["타입"] || "",
  };
}

/**
 * @param {string} address
 * @param {string} area
 * @returns {Promise<object|null>}
 */
async function getKbPriceFromRegistry(address, area) {
  const am = String(area).match(/([\d.]+)/);
  if (!am) return null;
  const areaNum = parseFloat(am[1]);
  if (isNaN(areaNum) || areaNum <= 0) return null;

  const complexName = extractComplexName(address);
  return getKbPrice(address, areaNum, complexName);
}

module.exports = {
  getKbPrice,
  getKbPriceFromRegistry,
  getComplexList,
  getComplexPrice,
  extractComplexName,
  findDongcode,
  fetchHouseholdsFromKbland,
};
