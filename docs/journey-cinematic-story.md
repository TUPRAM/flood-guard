# Cinematic journey (`/journey/`)

A scroll-driven 3D story that moves through an illustrative neighbourhood and into the real FloodGuard pages. It is a
separate route: the home page (`/`) is unchanged.

```
Opening → 01 Everyday connections → [real /public/] → 02 Conditions change → [real /public/, SOS stop]
→ 03 Connections affected → [real /studio/cases/mae-sai-2024/] → 04 Coordinated response → [real /command/?t=36]
```

## How it works

| Part | File | Notes |
|---|---|---|
| Story timeline (segments, stops, chapters, beats) | `apps/web/src/lib/journey/timeline.ts` | Pure, unit-tested. Scrolling cannot pass a stop; explicit buttons continue. |
| Screen projection | `apps/web/src/lib/journey/screen-projection.ts` | CSS `matrix3d` homography that maps a real page onto a projected 3D screen. |
| Illustrative terrain | `apps/web/src/lib/journey/terrain.ts` | Tested rule: home and clinic stay dry in every water state; one road stretch floods only in the "affected" state. The road sits on a graded bench (equal to the natural ground on the centre line, so flooding is unchanged). |
| Art direction, textures, geometry helpers | `apps/web/src/components/journey/stage/materials.ts` | Controlled palette from the brand (cream, muted green, teal, dark neutral); small procedural textures (plaster, roof tiles, standing seam, asphalt, concrete, timber, ripples, contact shadows). |
| Architecture | `apps/web/src/components/journey/stage/architecture.ts` | Houses with real roof solids (thickness, overhang, fascia, soffit), framed windows with sills and hoods, doors with steps and canopies, porches, garden walls, tanks, AC units; a clinic with a raised floor, portico, ramp and sign. Merged per material. |
| Vegetation | `apps/web/src/components/journey/stage/vegetation.ts` | Rain trees, fruit trees, tall trees, coconut palms, shrubs: clumped noise-displaced canopies with baked occlusion; instanced per 48 m tile (so culling works); kept clear of the camera's actual path. |
| Landscape, water, roads, phone, sky | `apps/web/src/components/journey/stage/world.ts` | Painted ground (paddy fields and bunds, yards, driveways, banks) with close-range detail and wetness; depth-aware water (`terrain-glsl.ts` mirrors the height function); kerbs, footpaths, markings, concrete sois, poles and wires; the route band; a modelled phone; clouds. |
| Operations room | `apps/web/src/components/journey/stage/operations.ts` | A furnished planning office (timber floor, task chair, desk, monitor, keyboard, lamp, shelving, whiteboard, clock), merged per material. |
| People | `apps/web/src/components/journey/stage/characters.ts` | The resident and the responder are rigged models (`public/journey/characters/*.glb`, built from the delivered characters by `scripts/build-journey-characters.mjs`). Each carries its bind pose and one held pose (`PhoneHold`, `Typing`); the stage blends per bone from a relaxed pose (her right arm mirrored from her relaxed left, still gripping the phone) to the phone pose, and adds breathing, small head movements and typing fingers. The real public app is projected onto a plane fitted to the screen of the phone she holds. |
| Fallback people | `apps/web/src/components/journey/stage/figure.ts` | Procedural sculpted figures, shown only until the models load (the story waits up to 9 s) or if they fail to load. |
| Camera, lighting and scene state | `apps/web/src/components/journey/stage/journey-stage.ts` | Per-segment keyframes; push-ins end exactly where the screen fills the viewport. Neutral tone mapping, outdoor sky environment light, a sun whose shadow frustum follows the shot. |
| UI, input, docking, history | `apps/web/src/components/journey/journey-experience.tsx` | Wheel/touch/keys scrub; stops dock the real page; `?scene=` links and Back/Forward. |
| Copy (EN/TH) | `apps/web/src/components/journey/journey-copy.ts` | Thai strings need native review. |

**Real pages, not mockups.** Each real route runs in its own same-origin `<iframe>` (so its routing, URL parameters
and state stay its own). While the camera moves, the iframe is transformed onto the 3D phone, monitor or planning
table; when the camera aligns, the transform becomes identity, the page fills the viewport and receives input.

## The transitions

1. **Opening → resident:** camera descends from the establishing shot to a person by their home; they raise the phone
   (IK arm) and the real public app wakes on its screen.
2. **Phone → public app:** camera orbits behind the shoulder and pushes along the screen normal; the page fills the
   height, then (desktop) widens to the full viewport.
3. **SOS → operations room:** story-mode "Simulate SOS" (nothing is sent). Water crosses the road, the connection turns
   amber/dashed, a signal arcs to an operations building and the camera flies in through its window.
4. **Monitor → case view:** over-the-shoulder push into the responder's monitor (landscape aspect = viewport aspect, so
   the hand-off is seamless on desktop).
5. **Case view → landscape:** reverse pull out of the monitor, out of the window, up to an aerial view of the network.
6. **Landscape → command exercise:** top-down dive through the skylight onto the planning table, which becomes the
   real command page.

## Safety and honesty

- The neighbourhood, water states and SOS are illustrative. A permanent tag says so; captions say the case view is a
  separate, historical Mae Sai 2024 case.
- The story never triggers the real SOS (`tel:`/`sms:` links). At the SOS stop a warning says the app's SOS tab places
  real calls; the story uses its own simulated control.
- No report, case change or dispatch is created by any transition.

## Deployment notes

- **Headers:** `vercel.json` now allows same-origin framing only (`X-Frame-Options: SAMEORIGIN`,
  `frame-ancestors 'self'`). Other origins still cannot frame FloodGuard.
- **Profiles:** `/journey/` is a staff/competition route; the public-production build removes it with `/command/` and
  `/studio/` (`scripts/build-profile.mjs`, plus prune/artifact checks).
- **Offline:** online-only. Its chunks carry the `data-floodguard-journey` marker and are excluded from the blocking
  offline install (`scripts/write-offline-assets.mjs`).
- **Dependencies:** none added (`three` was already a dependency). The character build script uses meshoptimizer and sharp,
  which are already in the workspace (through `@types/three` and `next`).
- **Assets:** `public/journey/characters/` (about 5.5 MB) loads only on `/journey/`; it is not in the offline install and
  the public-production build removes it with the route.

## Accessibility and fallbacks

Reduced motion (system setting or the toggle) replaces camera flights with cross-fades between story beats. Every
control is a real button or link with visible focus; the skip dialog traps focus and closes with Escape. Without WebGL
the page shows the story as text with links to every real page.

## Testing

- `pnpm --filter @floodguard/web test` (journey: `src/lib/journey/journey.test.ts`)
- `node scripts/csp-smoke.mjs` loads `/journey/` and `/journey/?scene=case` under production headers.

## Visual quality and performance

- **Lighting:** neutral tone mapping (keeps the brand hues), an image-based outdoor sky (warm ground bounce, sun disc)
  instead of a studio environment, a soft hemisphere fill and a warm sun. The sun's shadow map follows the shot: tight
  and per-frame for close shots (crisp contact shadows), wide and only re-rendered when it moves a step for aerial shots.
- **Grounding without post-processing:** draped contact shadows under buildings, trees and the resident, occlusion
  baked into canopies and interior walls. Screen-space AO (GTAO) was tried and removed: on integrated graphics it cost
  several times the whole frame for a subtle difference.
- **Budget:** buildings and the operations room are merged per material; trees are instanced per tile and the distant
  forest uses lighter canopies; the water mesh only covers ground that can flood; interior lights switch on only near the
  operations room (both lighting states are compiled at load); the resolution adapts (pixel ratio steps between 1.0
  and the device ratio, capped at 1.75) to hold the frame rate. Phones and small windows use the low-quality path.
- **Measured (Intel Iris Xe, 1440 × 900, production build):** the WebGL frame costs about 2–9 ms per shot at a pixel
  ratio of 1. Whole-page frame rates on that laptop vary between 20 and 60 fps, and the original scene measured the same
  in the same shots: the remaining cost is the live pages in the iframes (they keep running while hidden), not the 3D.

## Known limitations

- The people come from single-image generated models (Meshy, per `deliver/README.md`), simplified for the web
  (about 300k → 40k triangles, 8K → 2K textures; the phone hand keeps its full detail). Confirm the generator plan's
  licence covers publishing them. The poses are held poses, so the raise of the phone is a blend between two poses,
  not motion capture. During the two push-ins the resident's head is folded away (the camera ends where her eyes are)
  and the responder is hidden once the camera passes him.
- The delivered source files (`deliver/`, about 200 MB with the .blend files) are not needed at run time; rebuild the web
  versions with `node scripts/build-journey-characters.mjs` after changing them.
- Assets that would add the most after that: a phone model with a real camera bump and edge chamfers, residential and
  clinic building kits in one style, and a few photo-scanned tree species. Check licences before use.
- Hidden iframes keep running their pages; unmounting far-away pages would raise frame rates on low-end laptops.
- The landscape is illustrative geometry, not Mae Sai terrain.
- The phone hand-off on desktop ends with the public app widening from a phone column to full width (it reflows).
- On portrait phones the monitor and table hand-offs use a short fade, because a landscape screen cannot fill a
  portrait viewport without reflowing.
