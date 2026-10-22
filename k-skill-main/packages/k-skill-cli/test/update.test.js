const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const childProcess = require("node:child_process");

const {
  PACKAGE_NAME,
  SKILLS_SOURCE,
  formatUpdate,
  isGlobalInstall,
  runUpdate,
} = require("../src/update");

const binPath = path.join(__dirname, "..", "bin", "k-skill.js");
const GLOBAL_BIN = "/usr/local/lib/node_modules/@nomadamas/k-skill/bin/k-skill.js";
const NPX_BIN = "/Users/me/.npm/_npx/1234/node_modules/@nomadamas/k-skill/bin/k-skill.js";
const LOCAL_BIN = path.join(__dirname, "..", "bin", "k-skill.js");

function mockSpawn(handler) {
  const calls = [];
  const spawn = (command, args = [], options = {}) => {
    const call = { command, args, options };
    calls.push(call);
    const result = handler(call);
    return {
      status: 0,
      stdout: "",
      stderr: "",
      ...result,
    };
  };
  spawn.calls = calls;
  return spawn;
}

function npmView(version) {
  return (call) => {
    if (call.command === "npm" && call.args[0] === "view") {
      return { stdout: `${version}\n` };
    }
    if (call.command === "npm" && call.args[0] === "install") {
      return { stdout: "updated\n" };
    }
    if (call.command === "npx") {
      return { stdout: "skills refreshed\n" };
    }
    return { status: 1, stderr: `unexpected spawn ${call.command} ${call.args.join(" ")}` };
  };
}

test("isGlobalInstall distinguishes global, npx, and local checkouts", () => {
  assert.equal(isGlobalInstall(GLOBAL_BIN), true);
  assert.equal(isGlobalInstall(NPX_BIN), false);
  assert.equal(isGlobalInstall(LOCAL_BIN), false);
  assert.equal(isGlobalInstall(""), false);
});

test("runUpdate updates an outdated global CLI then refreshes all-agent skills", () => {
  const spawn = mockSpawn(npmView("0.9.0"));

  const result = runUpdate({
    currentVersion: "0.8.0",
    argv1: GLOBAL_BIN,
    spawn,
  });

  assert.equal(result.ok, true);
  assert.equal(result.cli.status, "updated");
  assert.equal(result.cli.current, "0.8.0");
  assert.equal(result.cli.latest, "0.9.0");
  assert.equal(result.skills.status, "refreshed");

  assert.deepEqual(spawn.calls[0].args, ["view", `${PACKAGE_NAME}@0`, "version"]);
  assert.deepEqual(spawn.calls[1].args, ["install", "-g", `${PACKAGE_NAME}@0`]);
  assert.equal(spawn.calls[2].command, "npx");
  assert.deepEqual(spawn.calls[2].args, ["--yes", "skills", "add", SKILLS_SOURCE, "--all", "-g"]);
});

test("runUpdate picks the newest version from multi-line npm view range output", () => {
  // Real `npm view <pkg>@0 version` prints one line per matching version, ascending:
  //   @nomadamas/k-skill@0.1.0 '0.1.0'
  //   ...
  //   @nomadamas/k-skill@0.9.0 '0.9.0'
  const versions = ["0.1.0", "0.2.0", "0.8.0", "0.9.0"];
  const registryOutput = versions.map((v) => `${PACKAGE_NAME}@${v} '${v}'`).join("\n") + "\n";
  const spawn = mockSpawn((call) => {
    if (call.command === "npm" && call.args[0] === "view") {
      return { stdout: registryOutput };
    }
    if (call.command === "npm" && call.args[0] === "install") {
      return { stdout: "updated\n" };
    }
    if (call.command === "npx") {
      return { stdout: "skills refreshed\n" };
    }
    return { status: 1, stderr: `unexpected spawn ${call.command}` };
  });

  const result = runUpdate({
    currentVersion: "0.8.0",
    argv1: GLOBAL_BIN,
    spawn,
  });

  assert.equal(result.ok, true);
  assert.equal(result.cli.status, "updated");
  assert.equal(result.cli.latest, "0.9.0");
});

test("runUpdate keeps already-latest CLI as a no-op and still refreshes skills", () => {
  const spawn = mockSpawn(npmView("0.8.0"));

  const result = runUpdate({
    currentVersion: "0.8.0",
    argv1: GLOBAL_BIN,
    spawn,
  });

  assert.equal(result.ok, true);
  assert.equal(result.cli.status, "already-latest");
  assert.equal(result.skills.status, "refreshed");
  assert.equal(
    spawn.calls.some((call) => call.command === "npm" && call.args[0] === "install"),
    false,
  );
  assert.equal(
    spawn.calls.some((call) => call.command === "npx"),
    true,
  );
});

test("runUpdate does not force a global install for a stale npx cache", () => {
  const spawn = mockSpawn(npmView("0.9.0"));

  const result = runUpdate({
    currentVersion: "0.8.0",
    argv1: NPX_BIN,
    spawn,
  });

  assert.equal(result.ok, true);
  assert.equal(result.cli.status, "stale");
  assert.equal(result.skills.status, "refreshed");
  assert.equal(
    spawn.calls.some((call) => call.command === "npm" && call.args[0] === "install"),
    false,
  );
});

test("runUpdate skips missing coding agents without failing the CLI update", () => {
  const spawn = mockSpawn((call) => {
    if (call.command === "npm" && call.args[0] === "view") {
      return { stdout: "0.8.0\n" };
    }
    if (call.command === "npx") {
      return { status: 1, stderr: "No coding agents detected\n" };
    }
    return { status: 1, stderr: `unexpected spawn ${call.command}` };
  });

  const result = runUpdate({
    currentVersion: "0.8.0",
    argv1: LOCAL_BIN,
    spawn,
  });

  assert.equal(result.ok, true);
  assert.equal(result.cli.status, "already-latest");
  assert.equal(result.skills.status, "skipped");
});

test("runUpdate --check reports outdated CLI without installing or refreshing", () => {
  const spawn = mockSpawn(npmView("1.0.0"));

  const result = runUpdate({
    currentVersion: "0.8.0",
    argv1: GLOBAL_BIN,
    checkOnly: true,
    spawn,
  });

  assert.equal(result.ok, true);
  assert.equal(result.cli.status, "outdated");
  assert.equal(result.skills.status, "check");
  assert.equal(spawn.calls.length, 1);
  assert.deepEqual(spawn.calls[0].args, ["view", `${PACKAGE_NAME}@0`, "version"]);
});

test("runUpdate fails closed when the registry lookup fails", () => {
  const spawn = mockSpawn(() => ({ status: 1, stderr: "network down\n" }));

  const result = runUpdate({
    currentVersion: "0.8.0",
    argv1: GLOBAL_BIN,
    spawn,
  });

  assert.equal(result.ok, false);
  assert.equal(result.cli.status, "error");
  assert.equal(result.skills.status, "skipped");
  assert.equal(
    spawn.calls.some((call) => call.command === "npx"),
    false,
  );
});

test("formatUpdate emits stable cli: and skills: status tokens", () => {
  const text = formatUpdate({
    ok: true,
    cli: { status: "already-latest", current: "0.8.0", latest: "0.8.0" },
    skills: { status: "refreshed" },
  });

  assert.match(text, /^cli: already-latest /m);
  assert.match(text, /^skills: refreshed$/m);
});

test("CLI help lists the update command", () => {
  const result = childProcess.spawnSync("node", [binPath, "--help"], {
    encoding: "utf8",
    env: { ...process.env, DOLSHOI_ACTION_BROKER_URL: "", CLOAKBROWSER_PEEK_TOKEN: "" },
  });

  assert.equal(result.status, 0);
  assert.match(result.stdout, /^ {2}update /m);
  assert.match(result.stdout, /@nomadamas\/k-skill@0 update/);
});
