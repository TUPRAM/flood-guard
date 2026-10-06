# Desktop V4: A Dry Home, An Affected Connection

The original Mae Sai-inspired world is retained, but the visual explanation uses
one deliberately bounded synthetic graph. Neither geometry nor flooding is
surveyed, observed, hydraulically simulated, or a representation of current
conditions. No external aerial, texture, model, or artwork is loaded.

## One Controlled Scenario

`src/lib/landing/illustrative-scenario.ts` is the shared source for road-node
coordinates, link identities, the authored water footprint, projected annotation
anchors, and the computed finding. `SYN-HOME-A` and `SYN-FACILITY-A` remain outside
the footprint. Only an explicit assumption removes `SYN-LINK-CROSSING`.

The undirected graph has a baseline path. Removing the crossing makes the
destination unavailable within this graph. The algorithm does not infer a
closure from a water intersection. It does not estimate travel time, population,
facility capacity, or a priority score. Surrounding geographic streets are not a
complete modeled transport network; alternative connections remain unverified.

The same graph coordinates build physical connector streets and their analytical
route. Solid blue denotes the illustrated baseline. Amber dashes denote the
assumed removed link. A separate amber ring at the dry home associates the
finding with the origin, not with direct flood exposure. Meanings must also be
stated in HTML; color alone is not the explanation.

## Frame Contract

`createDroneScene()` synchronously returns one master with local DataTextures.
`applyDroneFrame(rig, camera, aspect, {flight, flood, network, result, pointer})`
directly samples every state. `network` and `result` are optional, defaulting to
zero. No timer, autoplay, random per-frame state, operational data write, or
geometry replacement is involved. The camera remains fixed after `flight = 1`.

`getDroneTelemetry()` exposes normalized `annotations.home`,
`annotations.facility`, and `annotations.affectedLink`, as well as camera and
legacy landmark signatures, channel values, and computed reachability. Runtime
HTML labels should use these projected anchors and supply accessible equivalents.

The caller owns scroll timing, pointer damping, visibility suspension, first-frame
readiness, and failure fallback. Scene and posters use ACES tone mapping at 1.02
exposure and a fixed 34-degree perspective FOV. The bounded close framing leaves
the left reading column clear; narrow desktop aspect ratios adjust camera
distance without changing the dry/flood registration.

## Reproduction

From the repository root:

```powershell
pnpm --filter @floodguard/web exec node scripts/render-drone-assets.mjs --preview
pnpm --filter @floodguard/web exec node scripts/render-drone-assets.mjs
pnpm --filter @floodguard/web exec vitest run src/lib/landing/illustrative-scenario.test.ts src/components/landing/scene/drone-scene.test.ts
```

Preview writes only `apps/web/test-results/drone-v4-art-preview`.
Publication writes five 1600x900 stills to `apps/web/public/landing/desktop-v4`:
`far`, `connected`, `flood`, `access`, and `finding`. `scene-manifest.json` records
editable source hashes, asset hashes, camera signatures, projected anchors,
scenario data, computed finding, and actual capture rendering counts. Legacy V2
and V3 public assets are not overwritten by this generator.

These browser-rendered stills and tests establish technical consistency, not
geographic accuracy, operational readiness, or user comprehension. The finding
does not promise an available scenario editor in the historical Planning demo.
