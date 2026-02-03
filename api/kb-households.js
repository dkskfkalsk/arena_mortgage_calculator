/**
 * Vercel Serverless (Node.js) — kbland.kr/c/{id} Puppeteer 스크래핑
 * GET /api/kb-households?complex_id=15385 → { households, buildings, error }
 * Python 웹훅에서 세대수·동수 조회 시 호출 (Vercel 환경).
 * 로컬 테스트: vercel dev 또는 배포 후 curl. Windows에서는 Linux Chromium 미지원.
 */

const puppeteer = require("puppeteer-core");
const chromium = require("@sparticuz/chromium");

const BASE = "https://kbland.kr/c";
const MAX_H = 100000;
const MAX_B = 10000;

function parseNumber(s) {
  if (!s || typeof s !== "string") return null;
  const n = parseInt(s.replace(/[,，\s]/g, ""), 10);
  return isNaN(n) ? null : n;
}

function parseHouseholdsBuildings(text) {
  let households = null;
  let buildings = null;
  // "783세대(임대165)" 형식 우선 → 기본정보 총 세대수(임대 포함)
  const totalWithRental = text.match(/(\d{1,5})\s*세대\s*\(\s*임대\s*\d+/);
  if (totalWithRental) {
    const v = parseNumber(totalWithRental[1]);
    if (v != null && v >= 1 && v <= MAX_H) households = v;
  }
  const patterns = [
    /([\d,，\s]+)\s*세대/,
    /(\d{1,3}(?:[,，\s]\d{3})*)\s*세대/,
    /세대\s*[수:：]*\s*([\d,，]+)/,
    /총\s*([\d,，]+)\s*세대/,
    /아파트\s*([\d,，]+)\s*세대/,
  ];
  if (households == null) {
    for (const re of patterns) {
      const m = text.match(re);
      if (m) {
        const v = parseNumber(m[1]);
        if (v != null && v >= 1 && v <= MAX_H) {
          households = v;
          break;
        }
      }
    }
  }
  const bm = text.match(/(\d+)\s*개동/);
  if (bm) {
    const v = parseInt(bm[1], 10);
    if (!isNaN(v) && v >= 1 && v <= MAX_B) buildings = v;
  }
  return { households, buildings };
}

function parseApprovalDate(text) {
  let approval_date = null;
  let years_since_completion = null;
  // 사용승인일 2015.05.21(12년차) 또는 사용승인일 2015.05.21
  const m = text.match(/사용\s*승인\s*일\s*(\d{4}\.\d{2}\.\d{2})\s*(?:\(\s*(\d+)\s*년\s*차\s*\))?/);
  if (m) {
    approval_date = m[1];
    if (m[2]) {
      const y = parseInt(m[2], 10);
      if (!isNaN(y) && y >= 0 && y <= 100) years_since_completion = y;
    }
  }
  return { approval_date, years_since_completion };
}

async function scrape(complexId) {
  const url = `${BASE}/${complexId}`;
  let browser;
  try {
    if (process.env.AWS_LAMBDA_FUNCTION_VERSION || process.env.VERCEL) {
      chromium.setGraphicsMode = false;
    }
    const executablePath = await chromium.executablePath();
    const args = chromium.args || [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-gpu",
      "--disable-dev-shm-usage",
    ];
    browser = await puppeteer.launch({
      args,
      executablePath,
      headless: "shell",
      ignoreHTTPSErrors: true,
      defaultViewport: { width: 1920, height: 1080 },
    });
    const page = await browser.newPage();
    await page.setUserAgent(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    );
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 15000 });
    await new Promise((r) => setTimeout(r, 5000));
    const bodyText = await page.evaluate(() => (document.body && document.body.innerText) || "");
    await page.close();
    await browser.close();
    browser = null;
    const { households, buildings } = parseHouseholdsBuildings(bodyText);
    const { approval_date, years_since_completion } = parseApprovalDate(bodyText);
    return { households, buildings, approval_date, years_since_completion };
  } catch (e) {
    if (browser) {
      try {
        await browser.close();
      } catch (_) {}
    }
    throw e;
  }
}

module.exports = async function handler(req, res) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  let cid = (req.query && req.query.complex_id) || (req.body && req.body.complex_id);
  if (!cid && req.url && req.url.includes("?")) {
    try {
      const q = req.url.slice(req.url.indexOf("?") + 1);
      cid = new URLSearchParams(q).get("complex_id");
    } catch (_) {}
  }
  if (!cid || String(cid).trim() === "") {
    res.status(400).end(
      JSON.stringify({ households: null, buildings: null, approval_date: null, years_since_completion: null, error: "complex_id required" })
    );
    return;
  }
  try {
    const out = await scrape(String(cid).trim());
    res.status(200).end(JSON.stringify({ ...out, error: null }));
  } catch (e) {
    res.status(500).end(
      JSON.stringify({
        households: null,
        buildings: null,
        approval_date: null,
        years_since_completion: null,
        error: (e && (e.message || String(e))) || "scrape failed",
      })
    );
  }
};
