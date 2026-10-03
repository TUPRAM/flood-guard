/**
 * Venue-fallback video of the Mae Sai replay (roadmap P4-1), recorded with the page's own video export.
 *
 * The script serves the static build in `out/` on 127.0.0.1 with the production headers of `vercel.json` (so the
 * export runs under the production Content-Security-Policy), opens the case replay headlessly in English, chooses the
 * 16:9 video shape and presses "Record video". Every request to another host is blocked, so nothing is fetched from
 * the network: the export draws the dated satellite images and the model from the build's own files.
 *
 * The built-in export plays the replay at 2 s per day (about 24 s). A venue fallback for a 60-90 s spoken beat needs a
 * slower pace, so by default the page clock (`performance.now` and the animation-frame timestamps) runs at one third
 * of real speed while the export records: the frames are the export's own, at 6 s per day, about 73 s in all. Pass
 * `--slow 1` for the export's own pace.
 *
 * Usage (from apps/web, after a competition build):
 *   node scripts/record-replay-demo-video.mjs --out <file.mp4|file.webm> [--frames <dir>] [--slow 3] [--query "<replay link query>"]
 *
 * The extension of --out is replaced by the one the browser recorded (MP4 where supported, else WebM). A browser
 * records MP4 as fragments whose header gives a wrong duration (players then show a few seconds and cannot seek), so
 * an MP4 is rewritten as a progressive MP4 with full sample tables (`progressive-mp4.mjs`): the same frames, copied
 * byte for byte, not re-encoded. With --frames, a few frames are decoded back from the saved file and written there as
 * PNG files for a visual check. The script prints a JSON summary: the saved path, its size, SHA-256, the duration the
 * file declares and the browser.
 */
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { launchFloodGuardBrowser } from "./browser-launch.mjs";
import { readCaseReplay } from "./case-replay-inventory.mjs";
import { progressiveMp4 } from "./progressive-mp4.mjs";

const app = fileURLToPath(new URL("../", import.meta.url));
const out = resolve(app, "out");
const args = parseArgs(process.argv.slice(2));
if (!args.out) throw new Error("Usage: node scripts/record-replay-demo-video.mjs --out <file> [--frames <dir>] [--slow 3] [--query <link query>]");
const slow = Number(args.slow ?? 3);
if (!Number.isFinite(slow) || slow < 1 || slow > 6) throw new Error("--slow must be a number from 1 to 6.");
/** The page's own English link to the replay with its default view: water depth, no season envelope. */
const query = args.query ?? "t=0&img=auto&wm=depth&wo=85&rm=state&lang=en&layers=trsc&set=reported&k=8&pop=flooded";
/** Seconds into the saved video at which frames are checked (title card, onset, peak, 15 Sep, end card at the default pace). */
const FRAME_SECONDS = [1.5, 14.5, 24, 42.5, 72];

const config = JSON.parse(readFileSync(resolve(app, "../../vercel.json"), "utf8"));
const headers = Object.fromEntries(config.headers.find((entry) => entry.source === "/(.*)").headers.map(({ key, value }) => [key, value]));
const mime = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".webmanifest": "application/manifest+json",
  ".txt": "text/plain", ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".woff2": "font/woff2", ".ico": "image/x-icon",
  ".bin": "application/octet-stream", ".geojson": "application/geo+json", ".csv": "text/csv; charset=utf-8", ".mp4": "video/mp4", ".webm": "video/webm",
};
/** The saved video, served back at this path for the frame check. */
const VIDEO_ROUTE = "/__replay-demo-video__";
let savedVideo = null;

const server = createServer((request, response) => {
  for (const [name, value] of Object.entries(headers)) response.setHeader(name, value);
  response.setHeader("Cache-Control", "no-store");
  try {
    const pathname = decodeURIComponent(new URL(request.url ?? "/", "http://127.0.0.1").pathname);
    let file = pathname === VIDEO_ROUTE && savedVideo ? savedVideo : resolve(out, `.${pathname}`);
    if (file !== savedVideo && file !== out && !file.startsWith(`${out}${sep}`)) return response.writeHead(403).end();
    if (statSync(file).isDirectory()) file = resolve(file, "index.html");
    const body = readFileSync(file);
    response.setHeader("Content-Type", mime[extname(file)] ?? "application/octet-stream");
    response.setHeader("Accept-Ranges", "bytes");
    // Byte ranges, so the browser can seek in the saved video during the frame check.
    const range = /^bytes=(\d*)-(\d*)$/.exec(request.headers.range ?? "");
    if (range && (range[1] || range[2])) {
      const start = range[1] ? Number(range[1]) : Math.max(0, body.length - Number(range[2]));
      const end = range[1] && range[2] ? Math.min(Number(range[2]), body.length - 1) : body.length - 1;
      if (start > end || start >= body.length) return response.writeHead(416, { "Content-Range": `bytes */${body.length}` }).end();
      response.setHeader("Content-Range", `bytes ${start}-${end}/${body.length}`);
      return response.writeHead(206).end(request.method === "HEAD" ? undefined : body.subarray(start, end + 1));
    }
    return response.writeHead(200).end(request.method === "HEAD" ? undefined : body);
  } catch {
    return response.writeHead(404).end("Not found");
  }
});
await new Promise((resolveListen, rejectListen) => {
  server.once("error", rejectListen);
  server.listen(0, "127.0.0.1", resolveListen);
});
const baseUrl = `http://127.0.0.1:${server.address().port}`;
const replay = readCaseReplay(out);
const browser = await launchFloodGuardBrowser();

try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, acceptDownloads: true, serviceWorkers: "block" });
  // Nothing leaves this machine: the basemap tiles (not drawn by the export) and any other host are refused.
  await context.route("**/*", (route) => (new URL(route.request().url()).origin === baseUrl ? route.continue() : route.abort("blockedbyclient")));
  // A switchable page clock: performance.now and the animation-frame timestamps run at `scale` of real speed.
  await context.addInitScript(() => {
    const realNow = performance.now.bind(performance);
    const realFrame = window.requestAnimationFrame.bind(window);
    let scale = 1;
    let anchorReal = 0;
    let anchorVirtual = 0;
    const virtual = (real) => anchorVirtual + (real - anchorReal) * scale;
    performance.now = () => virtual(realNow());
    window.requestAnimationFrame = (callback) => realFrame((timestamp) => callback(virtual(timestamp)));
    Object.defineProperty(window, "__floodguardClockScale", {
      value: (next) => {
        const real = realNow();
        anchorVirtual = virtual(real);
        anchorReal = real;
        scale = next;
      },
    });
  });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto(`${baseUrl}${replay.route}?${query}`, { waitUntil: "load" });
  await page.getByTestId("replay-readout").waitFor({ state: "visible" });
  const record = page.getByRole("button", { name: /^Record video/ });
  await record.waitFor({ state: "visible", timeout: 60_000 });
  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll("button")].find((item) => /^Record video/.test(item.textContent ?? ""));
    return Boolean(button && !button.disabled) && !/Preparing the water model/.test(document.body.innerText);
  }, undefined, { timeout: 60_000 });
  await page.locator('input[name="mae-sai-video-format"][value="landscape"]').check();
  await page.evaluate((scale) => window.__floodguardClockScale(scale), 1 / slow);
  const started = Date.now();
  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 300_000 }),
    record.click(),
  ]);
  const recordedSeconds = (Date.now() - started) / 1000;
  await page.evaluate(() => window.__floodguardClockScale(1));
  const suggested = download.suggestedFilename();
  const target = resolve(args.out).replace(/\.(mp4|webm)$/i, "") + extname(suggested);
  mkdirSync(dirname(target), { recursive: true });
  const recorded = await download.path();
  const status = await page.locator("[role='status']").filter({ hasText: "Video saved" }).first().innerText();
  if (pageErrors.length > 0) throw new Error(`The replay page reported errors while recording: ${pageErrors.join(" | ")}`);
  let container = "WebM as recorded by MediaRecorder (no duration in its header)";
  if (extname(suggested) === ".mp4") {
    const rewritten = progressiveMp4(readFileSync(recorded));
    writeFileSync(target, rewritten.bytes);
    container = `progressive MP4 rewritten from the recorder's fragmented MP4 (${rewritten.samples} frames copied unchanged, ${rewritten.syncSamples} key frames)`;
  } else await download.saveAs(target);
  savedVideo = target;

  const bytes = readFileSync(target);
  const summary = {
    file: target,
    bytes: bytes.byteLength,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    suggested_name: suggested,
    container,
    page_status: status.trim(),
    pace: slow === 1 ? "the export's own pace (2 s per replay day)" : `page clock at 1/${slow} of real speed (${2 * slow} s per replay day)`,
    wall_clock_seconds: Math.round(recordedSeconds * 10) / 10,
    browser: `${browser.browserType().name()} ${browser.version()}`,
    query,
  };

  // Decode the saved file in the browser and read its duration and a few frames back out of it.
  const check = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await check.goto(`${baseUrl}/404.html`, { waitUntil: "load" });
  const frames = await check.evaluate(async ({ route, seconds }) => {
    const video = document.createElement("video");
    video.muted = true;
    video.preload = "auto";
    video.src = route;
    document.body.append(video);
    await new Promise((done, fail) => {
      video.onloadedmetadata = done;
      video.onerror = () => fail(new Error("the saved video could not be decoded"));
    });
    if (!Number.isFinite(video.duration)) {
      // A recording without a duration in its header: seek far past the end once so the browser finds it.
      video.currentTime = 1e9;
      await new Promise((done) => { video.ondurationchange = () => Number.isFinite(video.duration) && done(); });
    }
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    const shots = [];
    for (const at of seconds.filter((value) => value < video.duration)) {
      video.currentTime = at;
      await new Promise((done) => { video.onseeked = done; });
      context.drawImage(video, 0, 0);
      shots.push({ at, png: canvas.toDataURL("image/png") });
    }
    return { duration: video.duration, width: video.videoWidth, height: video.videoHeight, shots };
  }, { route: VIDEO_ROUTE, seconds: FRAME_SECONDS.map((at) => (at * slow) / 3) });
  summary.duration_seconds = Math.round(frames.duration * 10) / 10;
  summary.width = frames.width;
  summary.height = frames.height;
  if (frames.width * 9 !== frames.height * 16) throw new Error(`The saved video is not 16:9: ${frames.width} x ${frames.height}`);
  if (args.frames) {
    mkdirSync(args.frames, { recursive: true });
    summary.frames = frames.shots.map((shot) => {
      const file = resolve(args.frames, `frame-${String(shot.at).replace(".", "_")}s.png`);
      writeFileSync(file, Buffer.from(shot.png.split(",")[1], "base64"));
      return file;
    });
  }
  console.log(JSON.stringify(summary, null, 2));
  await context.close();
} finally {
  await browser.close();
  server.close();
}

function parseArgs(list) {
  const parsed = {};
  for (let index = 0; index < list.length; index += 2) {
    const key = list[index];
    if (!key?.startsWith("--") || list[index + 1] === undefined) throw new Error(`Unexpected argument: ${key}`);
    parsed[key.slice(2)] = list[index + 1];
  }
  return parsed;
}
