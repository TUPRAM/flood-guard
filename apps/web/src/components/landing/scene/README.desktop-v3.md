# Desktop V3 Continuous World

`drone-scene.ts` is an independent original Three.js art source. V2 source and
mobile assets remain separate and unchanged. No photograph or alternate model
crossfades into this scene: the detailed neighborhood is embedded in the larger
town from the first frame, and remains the same geometry throughout the flight.

## Authorship and Scope

The low-rise town, mountain-edge terrain, river, fields, architecture, foliage,
street details and material textures are authored here. Three small DataTextures
provide deterministic terrain grain, roof corrugation and distant facades. There
are no external textures, NYC models, projected aerial imagery, private records,
remote tile dependencies or asynchronous image loads.

The scene is a stylized Mae Sai-inspired architectural illustration. It is not
documentary imagery, a geographic survey, photogrammetry, a terrain elevation
product or a hydraulic simulation. The location, river alignment, building use,
water height and flood extent are illustrative. No real-world distance is
assigned to the coordinate units. A visible water state is not a warning,
confirmed road closure, measured flood depth or current-condition claim.

The city has 1,419 primary context buildings with attached wings and 42 detailed
neighborhood structures. Attached wings are parts of buildings, not additional
separately counted addresses. The selected neighborhood uses the same lighting,
ground plane and material family as its surroundings; there is no floating base.
Four persistent scene anchors are Neighborhood_A, Junction_A, Service_A and
Field_A. Their projected positions are available for registration checks, not
geographic validation.

## Runtime Contract

`createDroneScene()` synchronously returns the scene rig. `applyDroneFrame`
accepts a PerspectiveCamera, viewport aspect and `{ flight, flood, pointer? }`.
Flight and flood are clamped to [0,1]; pointer coordinates are clamped to [-1,1].
The caller owns scroll timing, pointer damping, demand invalidation, readiness,
visibility suspension and fallback decisions. The art source uses no timers,
accumulated transforms, autoplay actions or operational data writes.

The fixed field of view is 34 degrees. The far pose is [65,110,115], targeting
[0,0,-20]; the close pose is [12,17,20], targeting [0,0.2,0]. A deterministic
smooth path and small altitude arc join them. Narrow desktop viewports increase
camera distance rather than changing FOV. At close range, a 15% horizontal view
offset reserves a reading area. A neutral-pointer dry/flood pair has identical
camera matrices. Flooding changes only the water surface, leaving geometry and
landmarks unchanged and the service apron above the illustrative water plane.

Render with ACESFilmicToneMapping and exposure 1.02. The world has its own
hemisphere, ambient and directional lights. The shadow map is 2048 square, with
deterministic far/close coverage. Distant foliage uses simplified instanced
canopies; neighborhood foliage retains smoother geometry. Every generated
geometry, material, texture and shadow-map resource is disposed by the rig.

## Reproduce and Verify

From `apps/web`, run:

```powershell
node scripts/render-drone-assets.mjs
```

This uses existing Three.js, Playwright, Vite/esbuild and Next/Sharp dependencies.
A temporary browser renders the actual master, then closes. Four 1600x900 WebPs
are generated in `public/landing/desktop-v3`: far, approach, dry and flood. The
manifest records source hashes, seed, camera contract, output hashes, renderer
counts and landmark projections. No GLB export is claimed; the TypeScript master
and procedural texture source are the editable handoff.

`--preview` writes only to `test-results/drone-art-preview`, never to public
assets or the authoritative manifest. Final stills are same-master readiness
posters, not a second photographic interpretation.

`drone-scene.test.ts` checks building bounds, projected dry/flood registration,
exact unchanged geometry bytes, reverse seeking, pointer reset, finite geometry,
original texture types, invalid-input handling and ground coverage beyond the
desktop frame. Browser tests separately verify actual canvas pixels, transitions,
idle rendering, fallback behavior, layout and the preserved V2 mobile experience.
Render budgets and tests are technical evidence, not owner art acceptance or
field-device, production, geographic, scientific or agency acceptance.
