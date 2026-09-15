/** Local review of the existing static export with the repository's production security headers. */
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const app = fileURLToPath(new URL("../", import.meta.url));
const root = resolve(app, "out");
const port = Number(process.argv[2] ?? 3100);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error("Expected a port from 1 to 65535.");
await stat(resolve(root, "index.html"));
const config = JSON.parse(await readFile(resolve(app, "../../vercel.json"), "utf8"));
const headers = Object.fromEntries(config.headers.find((entry) => entry.source === "/(.*)").headers.map(({ key, value }) => [key, value]));
const mime = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".webmanifest": "application/manifest+json", ".txt": "text/plain", ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".woff2": "font/woff2", ".ico": "image/x-icon" };

createServer(async (request, response) => {
  for (const [name, value] of Object.entries(headers)) response.setHeader(name, value);
  response.setHeader("Cache-Control", "no-cache");
  if (!["GET", "HEAD"].includes(request.method)) return response.writeHead(405).end();
  try {
    const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
    let file = resolve(root, `.${pathname}`);
    if (file !== root && !file.startsWith(`${root}${sep}`)) return response.writeHead(403).end();
    if ((await stat(file)).isDirectory()) file = resolve(file, "index.html");
    const body = await readFile(file);
    response.setHeader("Content-Type", mime[extname(file)] ?? "application/octet-stream");
    response.writeHead(200).end(request.method === "HEAD" ? undefined : body);
  } catch {
    response.writeHead(404).end("Not found");
  }
}).listen(port, "127.0.0.1", () => console.log(`FloodGuard static preview: http://127.0.0.1:${port}/ (production CSP; local only)`));
