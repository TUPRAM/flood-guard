# Cinematic journey (`/journey/`)

A scroll-driven 3D story that moves through an illustrative neighbourhood and into the real FloodGuard pages. It is a
separate route: the home page (`/`) is unchanged.

```
Opening → 01 Lalita's family → [real /public/, Home tab] → 02 Rain, and a plan → [real /public/, Prepare tab]
→ 03 The road · Narin → [real /studio/cases/mae-sai-2024/] → 04 The district · Pim → [real /command/?t=36]
```

## The people

The story follows three fictional people, each with a reason to use one real page. No character represents a real
person, and every feature a caption names is one the real page has (the copy says which; `journey-copy.ts`).

| Person | Who | Their question | Their page and what they use there |
|---|---|---|---|
| **Lalita** | Resident; lives with her mother **Mali** (regular clinic appointments, regular medicine) and her daughter **Dao** (8) | Can my family still get where they need to go? | Public app: area overview and historical planning priority with date and confidence; **Prepare** (household needs: a child, an older adult, regular medicine); **Shelter** (a destination she checked with the authorities: the app does not know capacity or whether it is open); **Report** (saved on the device, sent nowhere); **SOS** (official hotlines) |
| **Narin** | Planning officer at the district office | What do we know, and what still needs checking? | Case view: Mae Sai, September 2024, replayed day by day; modelled water, roads, facilities and residents in water at low confidence; walking access to shelters and its equity gap |
| **Pim** | District planning coordinator | What should our team review together first? | Command exercise: each subdistrict's modelled figures hour by hour, practice incidents (EX) assigned to team callsigns, trainee mode. It shows no planning score or class (it says none is issued), so the story claims none |

How a request for help travels is told through real channels only: Lalita's report stays on her phone, and her call to
the official hotline 1784 (simulated, nothing dialled) is what reaches the district office in the story. FloodGuard
routes nothing. The amber arc is labelled as that simulated call. Lalita, Narin, Mali, Dao
and Pim carry name labels while the camera is with them; each caption names whose part of the story it is, and the
first caption of each person shows their role and question.

## How it works

| Part | File | Notes |
|---|---|---|
| Story timeline (segments, stops, chapters, beats) | `apps/web/src/lib/journey/timeline.ts` | Pure, unit-tested. Scrolling cannot pass a stop; explicit buttons continue. |
| Screen projection | `apps/web/src/lib/journey/screen-projection.ts` | CSS `matrix3d` homography that maps a real page onto a projected 3D screen. |
| Two-bone reach | `apps/web/src/lib/journey/reach.ts` | Pure, unit-tested: where an elbow or knee goes so a wrist or ankle arrives at a target (bends toward a pole; a target out of reach is approached). The stage turns the people's arm and leg bones to match. |
| Illustrative terrain | `apps/web/src/lib/journey/terrain.ts` | Tested rule: home and clinic stay dry in every water state; one road stretch floods only in the "affected" state. The road sits on a graded bench (equal to the natural ground on the centre line, so flooding is unchanged). |
| Art direction, textures, geometry helpers | `apps/web/src/components/journey/stage/materials.ts` | Controlled palette from the brand (cream, muted green, teal, dark neutral); small procedural textures (plaster, roof tiles, standing seam, asphalt, concrete, timber, ripples, contact shadows). |
| Architecture | `apps/web/src/components/journey/stage/architecture.ts` | Houses with real roof solids (thickness, overhang, fascia, soffit), framed windows with sills and hoods, doors with steps and canopies, porches, garden walls, tanks, AC units; a clinic with a raised floor, portico, ramp and sign. Merged per material. |
| Vegetation | `apps/web/src/components/journey/stage/vegetation.ts` | Rain trees, fruit trees, tall trees, coconut palms, shrubs: clumped noise-displaced canopies with baked occlusion; instanced per 48 m tile (so culling works); kept clear of the camera's actual path. |
| Landscape, water, roads, phone, sky | `apps/web/src/components/journey/stage/world.ts` | Painted ground (paddy fields and bunds, yards, driveways, banks) with close-range detail and wetness; depth-aware water (`terrain-glsl.ts` mirrors the height function); kerbs, footpaths, markings, concrete sois, poles and wires; the route band; a modelled phone; clouds. |
| Operations room | `apps/web/src/components/journey/stage/operations.ts` | A furnished planning office (timber floor, task chair, desk, monitor, keyboard, lamp, shelving, whiteboard, clock), merged per material. The chair is drawn up to the desk and the keyboard faces it; the room reports where the cushion and the keyboard's home row are, and the responder is seated from those. |
| People | `apps/web/src/components/journey/stage/characters.ts` | All five people are rigged models (`public/journey/characters/*.glb`, built from the delivered characters by `scripts/build-journey-characters.mjs`). Each carries its bind pose and one held pose (`PhoneHold`, `Typing`), made without the scene, so the stage fits them to it. **Responder:** hips on the chair's cushion, feet flat on the floor, each fingertip lowered onto the keyboard's home row (the knuckle bends until the skin meets the keys); his wrists are held there every frame, so breathing does not lift his hands, and typing is a small lift and tap of each finger. **Resident:** the phone stays exactly where the delivered pose reads it, but her hand is rebuilt around it (`PHONE_GRIP`: fingers hooked on the far edge from behind, thumb beside the near edge), because the real page is drawn over the whole screen and would cut through a finger in front of it; her arm is then brought to that hand. The story blends per bone from a relaxed pose (her right arm mirrored from her relaxed left, still holding the phone) to the reading pose, and adds breathing and small head movements. The real public app is projected onto a plane fitted to the screen of the phone she holds. **Mali, Dao and Pim** (Meshy auto-rig, generated 15 Oct 2026 to match Lalita's look; heights 1.52, 1.28 and 1.58 m) carry no held pose: the build renames their spine and neck bones to the names above and drops Meshy's sample clips, and the stage poses them from their bind (A) pose in world space. Mali and Dao stand at the gate with their arms hanging (Mali a little stooped, Dao's head turned up toward Lalita); Pim leans over the planning table with each palm flat on its rim (the hand is lowered until its skin meets the rim's top), refitted whenever the table follows the page's aspect. |
| Fallback people | `apps/web/src/components/journey/stage/figure.ts` | Procedural sculpted figures for all five until their models load (the story waits up to 9 s for Lalita and Narin) or if a model fails to load: Mali and Dao (scaled to a child, larger head) beside Lalita at her gate and Pim leaning on the planning table with her hands on its edge (two-bone IK). |
| Camera, lighting and scene state | `apps/web/src/components/journey/stage/journey-stage.ts` | Per-segment keyframes; push-ins end exactly where the screen fills the viewport. Neutral tone mapping, outdoor sky environment light, a sun whose shadow frustum follows the shot. |
| UI, input, docking, history | `apps/web/src/components/journey/journey-experience.tsx` | The story waits on every caption: → (or Page Down / Space / a clicker) glides to the next caption or real page; scrolling also stops on each caption and needs a fresh gesture to move on. One bottom bar (chapters, ←, ↗, →) stays over the real pages too, which open at full height. ← on the opening goes to the end. `?scene=` links and Back/Forward. |
| Copy (EN/TH) | `apps/web/src/components/journey/journey-copy.ts` | The people, captions, labels and real-page notes. `journey-copy.test.ts` runs every string through the shared wording lint (both languages) and checks that each person is introduced before their captions and page. Thai strings need native review. |

**Real pages, not mockups.** Each real route runs in its own same-origin `<iframe>` (so its routing, URL parameters
and state stay its own). While the camera moves, the iframe is transformed onto the 3D phone, monitor or planning
table; when the camera aligns, the transform becomes identity, the page fills the viewport and receives input.

## The transitions

1. **Opening → resident:** camera descends from the establishing shot to a person by their home; they raise the phone
   (IK arm) and the real public app wakes on its screen.
2. **Phone → public app:** camera orbits behind the shoulder and pushes along the screen normal; the page fills the
   height, then (desktop) widens to the full viewport.
3. **The family → the plan:** the camera holds on Lalita, Mali and Dao at the gate while they talk it through, then
   goes round her shoulder onto the phone, which the story has switched to the app's Prepare tab.
4. **The road → the office:** water crosses the road and the connection turns amber/dashed; Lalita's simulated call to
   the hotline arcs to the district office and the camera flies in through its window to Narin.
5. **Monitor → case view:** over-the-shoulder push into the responder's monitor (landscape aspect = viewport aspect, so
   the hand-off is seamless on desktop).
6. **Case view → Pim → landscape:** back from the monitor to Pim at the planning table, then up through the skylight to
   an aerial view where Lalita's home, the cut crossing and the clinic are labelled.
7. **Landscape → command exercise:** top-down dive through the skylight onto the planning table, which becomes the
   real command page.

## Safety and honesty

- The people, the neighbourhood, the water states and the call are illustrative. A permanent tag says so ("Fictional
  people in an illustrative scenario"); the first public-app stop says the app's data covers Mae Sai while Lalita's
  street is illustrated, and captions say the case view is a separate, historical Mae Sai 2024 case.
- The story never triggers the real SOS (`tel:`/`sms:` links) and never says FloodGuard sends a request for help. While
  the Prepare stop is open, a note warns that the SOS tab's buttons open the phone's call or message app with real
  hotline numbers. Each real page carries a closable note saying whose page it is in the story.
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

Reduced motion (the system setting) replaces camera flights with cross-fades between story beats. Every
control is a real button or link with visible focus; the skip dialog traps focus and closes with Escape. Without WebGL
the page shows the story as text with links to every real page.

## Testing

- `pnpm --filter @floodguard/web test`. Journey: `src/lib/journey/journey.test.ts` (timeline, screen projection, terrain,
  two-bone reach) and `src/components/journey/stage/characters.test.ts`, which reads the two models and checks that the
  resident's hand never comes in front of her phone or into its body (raised or at her side), that the phone stays where
  the delivered pose reads it, and that the responder's fingertips are on the keys (also while breathing and typing, and
  for a keyboard at another height), with his feet on the floor.
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

- Mali, Dao and Pim hold one pose each (standing, or leaning on the table), built in the scene; there is no hand on
  Mali's bag strap yet. Their source models (Meshy, Premium plan, private) are kept outside Git; rebuild with
  `node apps/web/scripts/build-journey-characters.mjs <dir>` where `<dir>` holds `mali/`, `dao/` and `pim/`.

- The people come from single-image generated models (Meshy, per `deliver/README.md`), simplified for the web
  (about 300k → 40k triangles, 8K → 2K textures; the phone hand keeps its full detail). Confirm the generator plan's
  licence covers publishing them. The poses are held poses, so the raise of the phone is a blend between two poses,
  not motion capture, and the typing is a tap of each finger in place, not key by key. The phone grip in
  `characters.ts` is fitted to this hand and this phone: check it again (the test will say) after rebuilding or
  replacing the model. During the push-in to the phone the resident's head is folded away (the camera ends where her
  eyes are); the camera passes the responder's right shoulder on its way to the monitor, and he is hidden only once it
  is ahead of him and he is out of the frame.
- The delivered source files (`deliver/`, about 200 MB with the .blend files) are not needed at run time; rebuild the web
  versions with `node scripts/build-journey-characters.mjs` after changing them.
- Assets that would add the most after that: a phone model with a real camera bump and edge chamfers, residential and
  clinic building kits in one style, and a few photo-scanned tree species. Check licences before use.
- Hidden iframes keep running their pages; unmounting far-away pages would raise frame rates on low-end laptops.
- The landscape is illustrative geometry, not Mae Sai terrain.
- The phone hand-off on desktop ends with the public app widening from a phone column to full width (it reflows).
- On portrait phones the monitor and table hand-offs use a short fade, because a landscape screen cannot fill a
  portrait viewport without reflowing.
