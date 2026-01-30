"use strict";

const { getKbPriceFromRegistry } = require("./kb-api");

async function main() {
  const address = process.argv[2];
  const area = process.argv[3];
  if (!address || !area) {
    process.stderr.write("Usage: node index.js <address> <area>\n");
    process.exit(1);
  }

  try {
    const result = await getKbPriceFromRegistry(address, area);
    if (!result) {
      process.stdout.write(JSON.stringify({ ok: false, error: "KB 시세 조회 실패" }) + "\n");
      process.exit(1);
    }
    process.stdout.write(JSON.stringify({ ok: true, ...result }) + "\n");
  } catch (e) {
    process.stderr.write(String(e) + "\n");
    process.stdout.write(JSON.stringify({ ok: false, error: String(e.message || e) }) + "\n");
    process.exit(1);
  }
}

main();
