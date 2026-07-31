/**
 * Serve the static export with the production security headers from
 * vercel.json and assert the app still works under them (D-22).
 *
 * A Content-Security-Policy that breaks the app is worse than no CSP: it ships
 * a blank page to people during a flood. This is not theoretical here --
 * `script-src 'self'` looks like the obviously correct value and silently
 * breaks everything, because the Next.js static export inlines 43 hydration
 * scripts (`self.__next_f.push(...)`) and a static export cannot use nonces.
 *
 * The check loads every exported route under the real headers and fails on any
 * CSP violation, console error, or failed request.
 *
 * Usage:  node apps/web/scripts/csp-smoke.mjs
 */

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const OUT_DIR = resolve(HERE, "..", "out");
const VERCEL_JSON = resolve(HERE, "..", "..", "..", "vercel.json");

const ROUTES = ["/", "/public/", "/command/", "/studio/"];

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
};

function globalHeaders() {
  const config = JSON.parse(readFileSync(VERCEL_JSON, "utf8"));
  const entry = (config.headers ?? []).find((h) => h.source === "/(.*)");
  if (!entry) throw new Error("vercel.json has no global /(.*) header block");
  return Object.fromEntries(entry.headers.map((h) => [h.key, h.value]));
}

async function main() {
  if (!existsSync(OUT_DIR)) {
    throw new Error(`Static export missing at ${OUT_DIR}. Run 'pnpm build:web' first.`);
  }
  const headers = globalHeaders();
  for (const required of [
    "Content-Security-Policy",
    "Strict-Transport-Security",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
  ]) {
    if (!headers[required]) throw new Error(`vercel.json is missing ${required}`);
  }

  const server = createServer(async (req, res) => {
    let path = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
    if (path.endsWith("/")) path += "index.html";
    let file = join(OUT_DIR, path);
    if (!existsSync(file) && existsSync(`${file}.html`)) file = `${file}.html`;
    for (const [key, value] of Object.entries(headers)) res.setHeader(key, value);
    if (!existsSync(file)) {
      res.writeHead(404).end("not found");
      return;
    }
    res.setHeader("Content-Type", MIME[extname(file)] ?? "application/octet-stream");
    res.writeHead(200).end(await readFile(file));
  });

  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const base = `http://127.0.0.1:${server.address().port}`;

  const browser = await launchFloodGuardBrowser();
  const failures = [];
  try {
    for (const route of ROUTES) {
      const context = await browser.newContext();
      const page = await context.newPage();
      const problems = [];
      page.on("console", (message) => {
        const text = message.text();
        // Tile requests to external hosts fail in a sandbox with no network;
        // that is an environment artifact, not a CSP violation.
        const offline =
          text.includes("tile.openstreetmap.org") ||
          text.includes("arcgisonline.com") ||
          text.includes("opentopomap.org");
        if (message.type() === "error" && !offline) problems.push(`console: ${text}`);
        if (/Content Security Policy|Refused to/i.test(text)) problems.push(`CSP: ${text}`);
      });
      page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));

      await page.goto(`${base}${route}`, { waitUntil: "networkidle" });
      // Hydration is the thing 'unsafe-inline' protects; if it were blocked the
      // React root would stay empty.
      const rendered = await page.evaluate(
        () => (document.body.innerText ?? "").trim().length,
      );
      if (rendered < 50) problems.push(`route rendered only ${rendered} chars of text`);

      if (problems.length) failures.push(`${route}\n    ${problems.join("\n    ")}`);
      else console.log(`  ok  ${route} (${rendered} chars rendered)`);
      await context.close();
    }
  } finally {
    await browser.close();
    server.close();
  }

  if (failures.length) {
    throw new Error(`CSP smoke failed:\n  ${failures.join("\n  ")}`);
  }
  console.log("csp smoke: all routes render under production security headers");
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
