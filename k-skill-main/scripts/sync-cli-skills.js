#!/usr/bin/env node
// Mirrors every CLI-managed skill source and bundled asset into
// packages/k-skill-cli/skills. --check verifies exact path, content, and mode
// equality so missing and stale/unexpected package files all fail CI.
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const repoRoot = path.join(__dirname, "..");
const targetRoot = path.join(repoRoot, "packages", "k-skill-cli", "skills");

function cliManagedSkills() {
  return fs
    .readdirSync(repoRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => fs.existsSync(path.join(repoRoot, name, "skill.json")))
    .sort();
}

function walkFiles(root) {
  if (!fs.existsSync(root)) return [];
  const files = [];
  const stack = [root];

  while (stack.length) {
    const current = stack.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (entry.name === "__pycache__" || entry.name.startsWith(".") || entry.name.endsWith(".pyc")) {
        continue;
      }
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) stack.push(full);
      else files.push(full);
    }
  }

  return files.sort();
}

function collectSources(skillName) {
  const skillDir = path.join(repoRoot, skillName);
  const manifest = JSON.parse(fs.readFileSync(path.join(skillDir, "skill.json"), "utf8"));
  const pairs = [
    [path.join(skillDir, "skill.json"), "skill.json"],
    [path.join(skillDir, "instruction.md"), "instruction.md"],
  ];

  for (const sub of ["scripts", "references"]) {
    for (const full of walkFiles(path.join(skillDir, sub))) {
      pairs.push([full, path.relative(skillDir, full)]);
    }
  }

  for (const item of manifest.bundle ?? []) {
    pairs.push([path.join(repoRoot, item.from), item.to]);
  }

  return pairs;
}

function expectedFiles(skills) {
  const expected = new Map();

  for (const skillName of skills) {
    for (const [source, relTarget] of collectSources(skillName)) {
      const targetRelative = path.join(skillName, relTarget);
      const previous = expected.get(targetRelative);
      if (previous && fs.realpathSync(previous) !== fs.realpathSync(source)) {
        throw new Error(`duplicate bundled target with different sources: ${targetRelative}`);
      }
      expected.set(targetRelative, source);
    }
  }

  return expected;
}

function checkBundle(expected) {
  const actual = new Set(
    walkFiles(targetRoot).map((filePath) => path.relative(targetRoot, filePath)),
  );
  let stale = 0;

  for (const [targetRelative, source] of expected) {
    const target = path.join(targetRoot, targetRelative);
    actual.delete(targetRelative);

    if (!fs.existsSync(target)) {
      console.error(`missing: packages/k-skill-cli/skills/${targetRelative}`);
      stale += 1;
      continue;
    }

    if (!fs.readFileSync(source).equals(fs.readFileSync(target))) {
      console.error(`stale: packages/k-skill-cli/skills/${targetRelative}`);
      stale += 1;
    }

    if ((fs.statSync(source).mode & 0o111) !== (fs.statSync(target).mode & 0o111)) {
      console.error(`mode mismatch: packages/k-skill-cli/skills/${targetRelative}`);
      stale += 1;
    }
  }

  for (const targetRelative of [...actual].sort()) {
    console.error(`unexpected: packages/k-skill-cli/skills/${targetRelative}`);
    stale += 1;
  }

  if (stale > 0) {
    console.error(`\n${stale} bundled file issue(s). Run: node scripts/sync-cli-skills.js`);
    process.exit(1);
  }
}

function writeBundle(expected) {
  fs.rmSync(targetRoot, { recursive: true, force: true });

  for (const [targetRelative, source] of expected) {
    const target = path.join(targetRoot, targetRelative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(source, target);
    fs.chmodSync(target, fs.statSync(source).mode);
  }
}

function main() {
  const check = process.argv.includes("--check");
  const skills = cliManagedSkills();
  const expected = expectedFiles(skills);

  if (check) checkBundle(expected);
  else writeBundle(expected);

  const assetCount = [...expected.keys()].filter(
    (filePath) => filePath.includes(`${path.sep}scripts${path.sep}`) ||
      filePath.includes(`${path.sep}references${path.sep}`),
  ).length;

  console.log(
    check
      ? `bundled skill files are exact (${skills.length} skills, ${assetCount} assets)`
      : `synced ${skills.length} skills and ${assetCount} assets into packages/k-skill-cli/skills`,
  );
}

main();
