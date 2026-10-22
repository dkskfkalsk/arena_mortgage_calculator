"use strict";

const childProcess = require("node:child_process");
const { version: packageVersion } = require("../package.json");

const PACKAGE_NAME = "@nomadamas/k-skill";
const SKILLS_SOURCE = "NomaDamas/k-skill";
const UPDATE_INVOCATION = "npx -y @nomadamas/k-skill@0 update";

function defaultSpawn(command, args, options) {
  return childProcess.spawnSync(command, args, {
    encoding: "utf8",
    ...options,
  });
}

function isGlobalInstall(argv1 = process.argv[1]) {
  const normalized = String(argv1 || "").replaceAll("\\", "/");
  if (!normalized) return false;
  if (normalized.includes("/_npx/") || normalized.includes("/.npm/_npx/")) return false;
  return /\/node_modules\/@nomadamas\/k-skill\//.test(normalized);
}

function parseVersion(raw) {
  const match = String(raw ?? "").trim().match(/(\d+)\.(\d+)\.(\d+)/);
  if (!match) return null;
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
    raw: `${match[1]}.${match[2]}.${match[3]}`,
  };
}

function compareVersions(left, right) {
  if (left.major !== right.major) return left.major - right.major;
  if (left.minor !== right.minor) return left.minor - right.minor;
  return left.patch - right.patch;
}

function parseMaxVersion(raw) {
  const text = String(raw ?? "");
  const pattern = /(\d+)\.(\d+)\.(\d+)/g;
  let best = null;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    const candidate = {
      major: Number(match[1]),
      minor: Number(match[2]),
      patch: Number(match[3]),
      raw: `${match[1]}.${match[2]}.${match[3]}`,
    };
    if (!best || compareVersions(candidate, best) > 0) best = candidate;
  }
  return best;
}

function spawnOutput(result) {
  return `${result?.stdout || ""}\n${result?.stderr || ""}`;
}

function isMissingAgentFailure(result) {
  const text = spawnOutput(result);
  return /no (coding )?agents?( detected| found)?/i.test(text) || /none detected/i.test(text);
}

function lookupLatest(spawn) {
  const result = spawn("npm", ["view", `${PACKAGE_NAME}@0`, "version"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.error || (result.status ?? 1) !== 0) {
    const error = new Error((result.stderr || result.error?.message || "npm view failed").trim());
    error.code = "EREGISTRY";
    throw error;
  }
  const parsed = parseMaxVersion(result.stdout);
  if (!parsed) {
    const error = new Error(`could not parse registry version from ${JSON.stringify(result.stdout)}`);
    error.code = "EREGISTRY";
    throw error;
  }
  return parsed;
}

function refreshSkills(spawn) {
  const result = spawn("npx", ["--yes", "skills", "add", SKILLS_SOURCE, "--all", "-g"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.error) {
    return { status: "failed", detail: result.error.message };
  }
  if ((result.status ?? 1) === 0) {
    return { status: "refreshed" };
  }
  if (isMissingAgentFailure(result)) {
    return { status: "skipped", detail: spawnOutput(result).trim() };
  }
  return { status: "failed", detail: spawnOutput(result).trim() };
}

function runUpdate(options = {}) {
  const spawn = options.spawn || defaultSpawn;
  const current = parseVersion(options.currentVersion || packageVersion);
  const argv1 = options.argv1 || process.argv[1];
  const checkOnly = Boolean(options.checkOnly);

  if (!current) {
    return {
      ok: false,
      cli: { status: "error", current: options.currentVersion || packageVersion, latest: null },
      skills: { status: "skipped" },
    };
  }

  let latest;
  try {
    latest = lookupLatest(spawn);
  } catch (error) {
    return {
      ok: false,
      cli: { status: "error", current: current.raw, latest: null, detail: error.message },
      skills: { status: "skipped" },
    };
  }

  const cmp = compareVersions(current, latest);
  if (checkOnly) {
    return {
      ok: true,
      cli: {
        status: cmp < 0 ? "outdated" : "already-latest",
        current: current.raw,
        latest: latest.raw,
      },
      skills: { status: "check" },
    };
  }

  let cliStatus = "already-latest";
  if (cmp < 0 && isGlobalInstall(argv1)) {
    const install = spawn("npm", ["install", "-g", `${PACKAGE_NAME}@0`], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    if (install.error || (install.status ?? 1) !== 0) {
      return {
        ok: false,
        cli: {
          status: "error",
          current: current.raw,
          latest: latest.raw,
          detail: spawnOutput(install).trim() || install.error?.message,
        },
        skills: { status: "skipped" },
      };
    }
    cliStatus = "updated";
  } else if (cmp < 0) {
    cliStatus = "stale";
  }

  const skills = refreshSkills(spawn);
  return {
    ok: skills.status !== "failed",
    cli: { status: cliStatus, current: current.raw, latest: latest.raw },
    skills,
  };
}

function formatUpdate(result) {
  const current = result.cli.current || "unknown";
  const latest = result.cli.latest || "unknown";
  const lines = [];

  switch (result.cli.status) {
    case "error":
      lines.push(`cli: error (${current} → ${latest})${result.cli.detail ? ` ${result.cli.detail}` : ""}`);
      break;
    case "stale":
      lines.push(`cli: stale (${current} < ${latest}); re-run ${UPDATE_INVOCATION}`);
      break;
    case "outdated":
      lines.push(`cli: outdated (${current} < ${latest})`);
      break;
    case "updated":
      lines.push(`cli: updated (${current} → ${latest})`);
      break;
    default:
      lines.push(`cli: already-latest (${current})`);
      break;
  }

  lines.push(`skills: ${result.skills.status}`);
  if (result.skills.detail) lines.push(result.skills.detail);
  return `${lines.join("\n")}\n`;
}

module.exports = {
  PACKAGE_NAME,
  SKILLS_SOURCE,
  UPDATE_INVOCATION,
  formatUpdate,
  isGlobalInstall,
  runUpdate,
};
