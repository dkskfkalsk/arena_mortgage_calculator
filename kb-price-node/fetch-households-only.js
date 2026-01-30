"use strict";

const { fetchHouseholdsFromKbland } = require("./kb-api");

const cid = process.argv[2] || "15385";

async function main() {
  console.log("complex_id:", cid);
  try {
    const h = await fetchHouseholdsFromKbland(cid);
    console.log("households:", h == null ? "null" : h);
    process.exit(h != null ? 0 : 1);
  } catch (e) {
    console.error(e);
    process.exit(1);
  }
}

main();
