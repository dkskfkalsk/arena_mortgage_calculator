#!/usr/bin/env node
// Rewrites relative bundled script/reference usage in source instruction.md
// files to the stable @nomadamas/k-skill exec/read interface.
// --check fails when any source still needs migration.
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const { rewriteAssetCommandReferences } = require("../packages/k-skill-cli/src/assemble");

const repoRoot = path.join(__dirname, "..");

function main() {
  const check = process.argv.includes("--check");
  const skills = fs
    .readdirSync(repoRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => fs.existsSync(path.join(repoRoot, name, "instruction.md")))
    .sort();
  const stale = [];

  for (const skillName of skills) {
    const documents = [
      path.join(repoRoot, skillName, "instruction.md"),
      path.join(repoRoot, "docs", "features", `${skillName}.md`),
      path.join(repoRoot, "docs", "install.md"),
    ].filter((filePath) => fs.existsSync(filePath));

    for (const documentPath of documents) {
      const source = fs.readFileSync(documentPath, "utf8");
      const migrated = rewriteAssetCommandReferences(source, skillName);
      if (source === migrated) continue;

      stale.push(path.relative(repoRoot, documentPath));
      if (!check) fs.writeFileSync(documentPath, migrated);
    }
  }

  if (check && stale.length) {
    console.error(
      `${stale.length} document(s) use relative bundled assets: ${stale.join(", ")}`,
    );
    console.error("Run: node scripts/migrate-cli-asset-instructions.js");
    process.exit(1);
  }

  console.log(
    check
      ? `instruction and feature-doc asset commands are normalized (${skills.length} skills checked)`
      : `migrated ${stale.length} instruction/feature document(s) to CLI asset commands`,
  );
}

main();
