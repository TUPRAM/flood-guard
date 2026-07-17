# FloodGuard offline judging instructions

## What the bundle proves

The offline bundle demonstrates the role-specific interface and typed fixture
decision flow. It is labeled `Fixture demo` and `Non-operational`; it does not
prove live data, current emergency conditions, real flood accuracy, or official
warning capability.

## Build the static bundle

From the repository root on a prepared development machine:

```powershell
pnpm install --frozen-lockfile
pnpm verify:frontend
pnpm --filter @floodguard/web build
```

Package the generated static export using the repository release script once
that script is present. Do not hand-edit the built bundle. Include this file,
the pinned Git commit, and SHA-256 checksums in the ZIP.

## Launch on Windows / เปิดใช้งานบน Windows

Open PowerShell in the extracted bundle and run a local static server. One
portable option is:

```powershell
python -m http.server 4173
```

Then open:

```text
http://127.0.0.1:4173/public/
```

หากมี Python ให้เปิด PowerShell ในโฟลเดอร์ที่แตกไฟล์ รันคำสั่งด้านบน และเปิด
ที่อยู่ `/public/` ในเบราว์เซอร์

If Python is not available, use any reviewed local static-file server that
preserves directory index files. Opening generated HTML directly with
`file://` is not the supported judging path because browser service-worker and
route behavior varies.

## Required routes

- `http://127.0.0.1:4173/public/`
- `http://127.0.0.1:4173/command/`
- `http://127.0.0.1:4173/studio/`

The root route redirects or links to `/public/`.

## Offline acceptance check

1. Disconnect the network or block all browser network access except
   `127.0.0.1`.
2. Do not start FastAPI.
3. Start the local static server.
4. Visit all three routes and refresh each route directly.
5. Confirm every local JS, CSS, icon, map and evidence asset returns 200.
6. Confirm the public and command screens show source time, confidence,
   `Fixture demo` and `Non-operational`.
7. Confirm no screen says live, real-time, official warning, safe route or live
   evacuation.
8. Confirm Studio labels the GeoAI artifact as a synthetic integration proof
   and shows `can_feed_decision_layer=false`.
9. Exercise Thai/English switching and keyboard navigation.
10. Inspect browser developer tools and confirm no external request is made.

The automated repository check is:

```powershell
pnpm --filter @floodguard/web test:offline
```

The final ZIP is acceptable only after the automated check and a clean manual
run both pass.

## Cached API behavior

When an API URL was configured in a separate development run, a validated API
snapshot may be cached. If the API later becomes unavailable, that snapshot
must be labeled stale/offline. A fresh extracted judging ZIP with no valid
cache uses the committed fixture bundle instead. Cached candidate data must not
be relabeled as official input.

## Legacy fallback

`outputs/dashboard.html` remains the reproducible legacy static dashboard.
Serve the `outputs` directory if the Next.js bundle is unavailable:

```powershell
uv run python -m http.server 8000 -d outputs
```

Then open `http://127.0.0.1:8000/dashboard.html`. Optional online map tiles are
context only; the embedded decision vectors and text equivalent remain local.

## Troubleshooting / การแก้ปัญหา

- Blank route after direct refresh: verify the server serves directory
  `index.html` files and the static export contains the route directory.
- Missing map: confirm the committed GeoJSON and local Leaflet assets exist;
  do not enable an external tile service as a silent fix.
- Old snapshot appears: clear site data and reload the fresh bundle.
- Thai characters are unreadable: confirm UTF-8 files and local/system Thai
  font fallback; do not replace Thai text with images.
- Evidence unavailable: confirm `proposal-evidence.json` was copied into the
  public bundle by the release build and its artifact hashes still match.
