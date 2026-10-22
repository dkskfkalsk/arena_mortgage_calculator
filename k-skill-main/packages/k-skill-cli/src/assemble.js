"use strict";

const fs = require("node:fs");
const path = require("node:path");

const packageRoot = path.join(__dirname, "..");
const templatesDir = path.join(packageRoot, "templates");
const skillsDir = path.join(packageRoot, "skills");
const CLI_INVOCATION = "npx -y @nomadamas/k-skill@0";

const KNOWN_PROFILES = [
  "core",
  "proxy",
  "browser",
  "vault",
  "action:booking",
  "action:commerce",
  "action:submission",
  "action:account",
  "action:recruiting",
  "legal",
  "lookup",
  "local",
  "operations",
];

function profileTemplatePath(profile) {
  return path.join(templatesDir, `${profile.replace(":", "-")}.md`);
}

function listSkills() {
  if (!fs.existsSync(skillsDir)) return [];
  return fs
    .readdirSync(skillsDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => fs.existsSync(path.join(skillsDir, name, "skill.json")))
    .sort();
}

function loadSkill(skillName) {
  const dir = path.join(skillsDir, skillName);
  const manifestPath = path.join(dir, "skill.json");

  if (!fs.existsSync(manifestPath)) {
    const known = listSkills();
    const error = new Error(
      `unknown skill "${skillName}". Known skills: ${known.join(", ") || "(none bundled)"}`,
    );
    error.code = "EUNKNOWNSKILL";
    throw error;
  }

  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));

  for (const profile of manifest.profiles ?? []) {
    if (!KNOWN_PROFILES.includes(profile)) {
      throw new Error(`skill "${skillName}" declares unknown profile "${profile}"`);
    }
  }

  return {
    dir,
    manifest,
    instruction: fs.readFileSync(path.join(dir, "instruction.md"), "utf8"),
  };
}

function assetRelativePaths(skillName) {
  const { dir } = loadSkill(skillName);
  return bundledFiles(skillName).map((filePath) => path.relative(dir, filePath).split(path.sep).join("/"));
}

function resolveBundledAsset(skillName, relativePath, allowedRoots = ["scripts", "references", "tests"]) {
  const { dir } = loadSkill(skillName);
  const normalized = path.posix.normalize(String(relativePath).replaceAll("\\", "/"));
  const root = normalized.split("/")[0];

  if (
    normalized === "." ||
    normalized.startsWith("../") ||
    path.posix.isAbsolute(normalized) ||
    !allowedRoots.includes(root)
  ) {
    const error = new Error(
      `asset path "${relativePath}" must stay inside ${allowedRoots.join(", ")} for skill "${skillName}"`,
    );
    error.code = "EASSETPATH";
    throw error;
  }

  const candidate = path.resolve(dir, ...normalized.split("/"));
  if (!fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) {
    const error = new Error(`asset "${normalized}" is not bundled for skill "${skillName}"`);
    error.code = "EASSETNOTFOUND";
    throw error;
  }

  const realDir = fs.realpathSync(dir);
  const realCandidate = fs.realpathSync(candidate);
  if (!realCandidate.startsWith(`${realDir}${path.sep}`)) {
    const error = new Error(`asset "${normalized}" escapes skill "${skillName}"`);
    error.code = "EASSETPATH";
    throw error;
  }

  return realCandidate;
}

function readBundledAsset(skillName, relativePath) {
  return fs.readFileSync(resolveBundledAsset(skillName, relativePath, ["references", "scripts"]), "utf8");
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function scriptPathPattern(skillName, relativePath) {
  const rel = escapeRegex(relativePath);
  const skill = escapeRegex(skillName);
  return `(?:"?\\$SKILL_DIR/|\\./${skill}/|${skill}/|\\./)?${rel}"?`;
}

function rewriteAssetCommandReferences(raw, skillName) {
  let output = raw;
  const assets = assetRelativePaths(skillName);
  const scripts = assets.filter((relativePath) => relativePath.startsWith("scripts/"));
  const references = assets.filter((relativePath) => relativePath.startsWith("references/"));

  for (const relativePath of scripts.sort((a, b) => b.length - a.length)) {
    const assetPattern = scriptPathPattern(skillName, relativePath);
    const execCommand = `${CLI_INVOCATION} exec ${skillName} ${relativePath} --`;

    output = output.replace(
      new RegExp(`(?:python3?|node|bash|uv\\s+run)\\s+${assetPattern}`, "g"),
      execCommand,
    );
    output = output.replace(
      new RegExp(`(^|[|;&]\\s*)${assetPattern}(?=\\s|$)`, "gm"),
      `$1${execCommand}`,
    );
  }

  for (const relativePath of assets.filter((item) => /\.(?:md|txt|pin)$/i.test(item))) {
    const assetPattern = scriptPathPattern(skillName, relativePath);
    const readCommand = `${CLI_INVOCATION} read ${skillName} ${relativePath}`;

    output = output.replace(new RegExp(`cat\\s+${assetPattern}`, "g"), readCommand);
  }

  for (const relativePath of references.sort((a, b) => b.length - a.length)) {
    const escaped = escapeRegex(relativePath);
    const readCommand = `${CLI_INVOCATION} read ${skillName} ${relativePath}`;

    output = output.replace(
      new RegExp(`\\[([^\\]]+)\\]\\((?:\\./)?${escaped}\\)`, "g"),
      (_match, label) =>
        label.includes(relativePath) ? `\`${readCommand}\`` : `${label} (\`${readCommand}\`)`,
    );
    output = output.replace(
      new RegExp(`\`(?:\\./)?${escaped}\``, "g"),
      `\`${readCommand}\``,
    );
  }

  return output;
}

// Source instructions are migrated to the CLI surface, and assembly repeats
// the normalization defensively so a newly added relative command cannot leak
// into a released instruction before CI catches it.
function rewriteBundledAssetInstructions(raw, skillName) {
  const assets = assetRelativePaths(skillName);
  const scripts = assets.filter((relativePath) => relativePath.startsWith("scripts/"));
  const references = assets.filter((relativePath) => relativePath.startsWith("references/"));
  let output = rewriteAssetCommandReferences(raw, skillName);

  if (scripts.length || references.length) {
    const accessRules = [
      "## Bundled asset access",
      "",
      `- Execute bundled helpers only through \`${CLI_INVOCATION} exec ${skillName} scripts/<file> -- <args>\`; do not assume a repository-relative or installed-skill-relative path.`,
      `- Resolve an asset path with \`${CLI_INVOCATION} path ${skillName} <relative-path>\` only when another tool explicitly requires a filesystem path.`,
    ];
    if (references.length) {
      accessRules.push(
        `- Read bundled references through \`${CLI_INVOCATION} read ${skillName} references/<file>\`.`,
      );
    }
    output = `${accessRules.join("\n")}\n\n${output}`;
  }

  return output;
}

// Template files interleave `<!-- mode:always -->`, `<!-- mode:dolshoi -->`,
// and `<!-- mode:generic -->` markers. Only the sections matching the detected
// mode (plus always-sections) are emitted.
function renderTemplate(raw, mode) {
  const lines = raw.replace(/\r\n?/g, "\n").split("\n");
  const output = [];
  let current = "always";

  for (const line of lines) {
    const marker = line.match(/^<!-- mode:(always|dolshoi|generic) -->$/);
    if (marker) {
      current = marker[1];
      continue;
    }
    if (current === "always" || current === mode) output.push(line);
  }

  return output.join("\n").trim();
}

function assemble(skillName, runtime) {
  const { manifest, instruction } = loadSkill(skillName);
  const profiles = ["core", ...(manifest.profiles ?? []).filter((p) => p !== "core")];

  const blocks = profiles
    .map((profile) => {
      const templatePath = profileTemplatePath(profile);
      const rendered = renderTemplate(fs.readFileSync(templatePath, "utf8"), runtime.mode);
      return rendered;
    })
    .filter(Boolean);

  const header = [
    `# ${manifest.name} — assembled instructions`,
    "",
    `Runtime mode: ${runtime.mode}${runtime.cloakBrowser ? " (CloakBrowser available)" : ""}`,
    "",
    "## Runtime rules",
    "",
    blocks.join("\n"),
  ].join("\n");

  // instruction.md may also use mode markers for mode-specific sections.
  const renderedInstruction = renderTemplate(instruction, runtime.mode);
  return `${header}\n\n${rewriteBundledAssetInstructions(renderedInstruction, skillName)}\n`;
}

function bundledFiles(skillName) {
  const { dir } = loadSkill(skillName);
  const results = [];

  for (const sub of ["scripts", "references", "tests"]) {
    const subDir = path.join(dir, sub);
    if (!fs.existsSync(subDir)) continue;
    const stack = [subDir];
    while (stack.length) {
      const currentDir = stack.pop();
      for (const entry of fs.readdirSync(currentDir, { withFileTypes: true })) {
        if (entry.name === "__pycache__" || entry.name.startsWith(".") || entry.name.endsWith(".pyc")) continue;
        const full = path.join(currentDir, entry.name);
        if (entry.isDirectory()) stack.push(full);
        else results.push(full);
      }
    }
  }

  return results.sort();
}

module.exports = {
  CLI_INVOCATION,
  KNOWN_PROFILES,
  assemble,
  assetRelativePaths,
  bundledFiles,
  listSkills,
  loadSkill,
  readBundledAsset,
  renderTemplate,
  resolveBundledAsset,
  rewriteAssetCommandReferences,
  rewriteBundledAssetInstructions,
};
