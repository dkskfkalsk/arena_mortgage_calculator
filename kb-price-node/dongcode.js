"use strict";

const fs = require("fs");
const path = require("path");

const REGION_MAP = {
  서울: "서울특별시",
  부산: "부산광역시",
  대구: "대구광역시",
  인천: "인천광역시",
  광주: "광주광역시",
  대전: "대전광역시",
  울산: "울산광역시",
  세종: "세종특별자치시",
  경기: "경기도",
  강원: "강원도",
  충북: "충청북도",
  충남: "충청남도",
  전북: "전라북도",
  전남: "전라남도",
  경북: "경상북도",
  경남: "경상남도",
  제주: "제주특별자치도",
};

let dongcodeData = null;

function loadDongcode() {
  if (dongcodeData) return dongcodeData;
  const p = path.join(__dirname, "..", "KB_api", "전국_dongcode_data.json");
  const raw = fs.readFileSync(p, "utf8");
  const data = JSON.parse(raw);
  dongcodeData = data.regions || {};
  return dongcodeData;
}

function parseAddress(address) {
  const result = {};
  if (!address || typeof address !== "string") return result;
  let s = address.replace(/\s+/g, " ").trim();
  s = s.replace(/\s+제\d+동/g, "").replace(/\s+제\d+호/g, "").replace(/\s+제\d+층/g, "").replace(/\s+제\d+번지/g, "");

  const regionPatterns = [
    /(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|경기도|강원도|충청북도|충청남도|전라북도|전라남도|경상북도|경상남도|제주특별자치도)/,
    /(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)/,
  ];
  for (const re of regionPatterns) {
    const m = s.match(re);
    if (m) {
      result.region = REGION_MAP[m[1]] || m[1];
      break;
    }
  }

  const districtPatterns = [
    /(?:시|도)\s+([가-힣]+시)\s+[가-힣]+구/,
    /(?:시|도)\s+([가-힣]+시|[가-힣]+군)/,
  ];
  for (const re of districtPatterns) {
    const m = s.match(re);
    if (m) {
      result.district = m[1];
      break;
    }
  }

  const dongPatterns = [
    /(?:시|도)\s+[가-힣]+(?:시|구|군)\s+([가-힣]+(?:구|군|시)\s+[가-힣]+(?:동|읍|면))/,
    /(?:구|군|시)\s+([가-힣]+(?:구|군|시)?\s*[가-힣]+(?:동|읍|면))/,
    /(?:구|군|시)\s+([가-힣]+(?:동|읍|면))/,
    /(?:구|군|시)\s+제?(\d+동)/,
  ];
  for (const re of dongPatterns) {
    const m = s.match(re);
    if (m) {
      let d = m[1].replace(/^제/, "").trim();
      result.dong = d;
      break;
    }
  }

  if (result.dong) {
    const i = s.indexOf(result.dong) + result.dong.length;
    result.detail = s.slice(i).trim();
  }
  return result;
}

function findDongcode(address) {
  const data = loadDongcode();
  const parsed = parseAddress(address);
  let region = parsed.region;
  let district = parsed.district;
  let dong = parsed.dong;
  if (!region || !district || !dong) return null;

  let regionData = data[region] || null;
  if (!regionData) {
    for (const k of Object.keys(data)) {
      if (k.includes(region) || region.includes(k)) {
        regionData = data[k];
        region = k;
        break;
      }
    }
  }
  if (!regionData || !regionData.districts) return null;

  let districtData = regionData.districts[district] || null;
  if (!districtData) {
    for (const k of Object.keys(regionData.districts)) {
      if (k.includes(district) || district.includes(k)) {
        districtData = regionData.districts[k];
        district = k;
        break;
      }
    }
  }
  if (!districtData || !districtData.dongs) return null;

  let dongData = districtData.dongs[dong] || null;
  if (!dongData) {
    for (const k of Object.keys(districtData.dongs)) {
      if (dong === k || k.includes(dong) || (k.includes(" ") && k.split(" ").pop() === dong)) {
        dongData = districtData.dongs[k];
        dong = k;
        break;
      }
    }
  }
  if (dongData && typeof dongData.code === "string") return dongData.code;

  for (const [k, v] of Object.entries(districtData.dongs)) {
    if (v && typeof v.code === "string") return v.code;
  }
  return null;
}

module.exports = { loadDongcode, parseAddress, findDongcode };
