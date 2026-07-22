import { cpSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, sep } from "node:path";
import { spawnSync } from "node:child_process";

const appRoot = process.cwd();
const profileBuild = resolve(appRoot, "scripts", "build-profile.mjs");
const publicBrowser = resolve(appRoot, "scripts", "browser-public-profile-smoke.mjs");
const transitionBrowser = resolve(appRoot, "scripts", "browser-profile-transition-smoke.mjs");
const temporaryRoot = mkdtempSync(resolve(tmpdir(), "floodguard-public-profile-"));
const publicSnapshot = resolve(temporaryRoot, "out");

try {
  run(profileBuild, ["public-production"]);
  run(publicBrowser);
  cpSync(resolve(appRoot, "out"), publicSnapshot, { recursive: true });
  run(profileBuild, ["competition"]);
  run(transitionBrowser, [], {
    FLOODGUARD_COMPETITION_PROFILE_OUT: resolve(appRoot, "out"),
    FLOODGUARD_PUBLIC_PROFILE_OUT: publicSnapshot,
  });
  console.log("deployment profile verification: public and competition builds plus same-origin cache downgrade passed");
} finally {
  const resolvedTemporaryRoot = resolve(temporaryRoot);
  const resolvedSystemTemp = resolve(tmpdir());
  if (!resolvedTemporaryRoot.startsWith(`${resolvedSystemTemp}${sep}`)) {
    throw new Error(`Refusing to remove temporary profile output outside ${resolvedSystemTemp}`);
  }
  rmSync(resolvedTemporaryRoot, { recursive: true, force: true });
}

function run(script, args = [], extraEnv = {}) {
  const result = spawnSync(process.execPath, [script, ...args], {
    cwd: appRoot,
    env: { ...process.env, ...extraEnv },
    stdio: "inherit",
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const name = script.split(/[\\/]/u).at(-1) ?? script;
    throw new Error(`${name} exited with status ${result.status ?? 1}`);
  }
}
