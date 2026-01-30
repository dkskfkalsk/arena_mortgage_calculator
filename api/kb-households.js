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
  const patterns = [
    /([\d,，\s]+)\s*세대/,
    /(\d{1,3}(?:[,，\s]\d{3})*)\s*세대/,
    /세대\s*[수:：]*\s*([\d,，]+)/,
  ];
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
  const bm = text.match(/(\d+)\s*개동/);
  if (bm) {
    const v = parseInt(bm[1], 10);
    if (!isNaN(v) && v >= 1 && v <= MAX_B) buildings = v;
  }
  return { households, buildings };
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
    await page.goto(url, { waitUntil: "networkidle0", timeout: 20000 });
    await new Promise((r) => setTimeout(r, 3000));
    const bodyText = await page.evaluate(() => (document.body && document.body.innerText) || "");
    await page.close();
    await browser.close();
    browser = null;
    return parseHouseholdsBuildings(bodyText);
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
    res.status(400).end(JSON.stringify({ households: null, buildings: null, error: "complex_id required" }));
    return;
  }
  try {
    const { households, buildings } = await scrape(String(cid).trim());
    res.status(200).end(JSON.stringify({ households, buildings, error: null }));
  } catch (e) {
    res.status(500).end(
      JSON.stringify({
        households: null,
        buildings: null,
        error: (e && (e.message || String(e))) || "scrape failed",
      })
    );
  }
};
