import { existsSync, mkdirSync, readdirSync, renameSync, rmdirSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const requested = process.argv[2]?.trim().toLowerCase();
const profile = requested === "public" || requested === "public-production"
  ? "public-production"
  : requested === "competition"
    ? "competition"
    : null;

if (!profile) throw new Error("Usage: node scripts/build-profile.mjs competition|public-production");

const candidates = [
  resolve(process.cwd(), "node_modules", "next", "dist", "bin", "next"),
  resolve(process.cwd(), "..", "..", "node_modules", "next", "dist", "bin", "next"),
];
const nextCli = candidates.find(existsSync);
if (!nextCli) throw new Error("Next.js executable was not found in the workspace.");

const env = {
  ...process.env,
  FLOODGUARD_APP_PROFILE: profile,
  NEXT_PUBLIC_FLOODGUARD_APP_PROFILE: profile,
};

// Profile builds have different route graphs. Reusing generated route types or
// output from another profile can make a public build reference hidden staff
// routes (or leak stale staff artifacts into `out`).
rmSync(resolve(process.cwd(), ".next"), { recursive: true, force: true });

const hiddenStaffRoutes = profile === "public-production" ? hideStaffRoutes() : [];
let build;
try {
  build = spawnSync(process.execPath, [nextCli, "build"], { cwd: process.cwd(), env, stdio: "inherit" });
} finally {
  restoreStaffRoutes(hiddenStaffRoutes);
}
if (build?.error) throw build.error;
if (build?.status !== 0) process.exit(build?.status ?? 1);

const finalize = spawnSync(process.execPath, [resolve(process.cwd(), "scripts", "write-offline-assets.mjs")], {
  cwd: process.cwd(),
  env,
  stdio: "inherit",
});
if (finalize.error) throw finalize.error;
if (finalize.status !== 0) process.exit(finalize.status ?? 1);

const verify = spawnSync(process.execPath, [resolve(process.cwd(), "scripts", "profile-artifact-smoke.mjs"), profile], {
  cwd: process.cwd(),
  env,
  stdio: "inherit",
});
if (verify.error) throw verify.error;
if (verify.status !== 0) process.exit(verify.status ?? 1);

function hideStaffRoutes() {
  const appDirectory = resolve(process.cwd(), "src", "app");
  const backupDirectory = resolve(process.cwd(), ".profile-route-backup");
  const routeNames = ["command", "studio"];

  if (existsSync(backupDirectory)) {
    recoverInterruptedRouteMove(appDirectory, backupDirectory, routeNames);
  }
  mkdirSync(backupDirectory);

  const moved = [];
  try {
    for (const routeName of routeNames) {
      const source = resolve(appDirectory, routeName);
      const backup = resolve(backupDirectory, routeName);
      if (!existsSync(source)) throw new Error(`Required staff route is missing: ${source}`);
      renameSync(source, backup);
      moved.push({ source, backup });
    }
    return moved;
  } catch (error) {
    restoreStaffRoutes(moved);
    throw error;
  }
}

function restoreStaffRoutes(moved) {
  if (moved.length === 0) return;
  const backupDirectory = resolve(process.cwd(), ".profile-route-backup");
  for (const { source, backup } of [...moved].reverse()) {
    if (!existsSync(backup)) continue;
    if (existsSync(source)) throw new Error(`Cannot restore staff route because the destination exists: ${source}`);
    renameSync(backup, source);
  }
  if (existsSync(backupDirectory)) {
    const unexpected = readdirSync(backupDirectory);
    if (unexpected.length > 0) throw new Error(`Unexpected files remain in route backup: ${unexpected.join(", ")}`);
    rmdirSync(backupDirectory);
  }
}

function recoverInterruptedRouteMove(appDirectory, backupDirectory, routeNames) {
  const unexpected = readdirSync(backupDirectory).filter((name) => !routeNames.includes(name));
  if (unexpected.length > 0) {
    throw new Error(`Refusing to use route backup with unexpected contents: ${unexpected.join(", ")}`);
  }
  for (const routeName of routeNames) {
    const source = resolve(appDirectory, routeName);
    const backup = resolve(backupDirectory, routeName);
    if (existsSync(source) && existsSync(backup)) {
      throw new Error(`Both live and backup staff routes exist for ${routeName}; resolve this manually.`);
    }
    if (!existsSync(source) && existsSync(backup)) renameSync(backup, source);
  }
  const remaining = readdirSync(backupDirectory);
  if (remaining.length > 0) throw new Error(`Unable to recover route backup: ${remaining.join(", ")}`);
  rmdirSync(backupDirectory);
}
