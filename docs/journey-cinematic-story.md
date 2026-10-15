# Cinematic journey (`/journey/`)

A scroll-driven 3D story on the real map of Mae Sai town, with the water of FloodGuard's published replay (r5, a model
reconstruction of September 2024 with low confidence), that moves into the real FloodGuard pages. The people are
fictional. It is a separate route: the home page (`/`) is unchanged. Branch `journey-v2`; the data contract, the facts
the story rests on and the decisions are in [journey-v2-real-map.md](journey-v2-real-map.md).

```
Opening → 01 Lalita's family (9 Sep 12:00) → [real /public/, Home, "Normal day"]
→ 02 Rain, and a plan (10 Sep 14:00–16:00) → [real /public/, Prepare, "Shallow water on roads"]
→ 03 The night (10 Sep 16:00 → 11 Sep 01:00)
→ 04 Cut off · Narin (12 Sep 12:00) → [real /studio/cases/mae-sai-2024/?t=84]
→ 05 The district · Pim → [real /command/?t=84]
→ 06 Water going down (14 Sep 12:00)
```

## The people and the place

| Person | Who | Their question | Their page |
|---|---|---|---|
| **Lalita** | Resident at the Public app's example home in Mae Sai town (a model point, not an address); lives with her mother **Mali** (regular medicine) and her daughter **Dao** (8) | Can my family still get where they need to go? | Public app, opened on the practice scenario of the story's hour: Home, Prepare, Report |
| **Narin** | Planning officer at the Mae Sai District Office | What do we know, and what still needs checking? | Case view, opened at hour 84 (12 Sep 12:00) |
| **Pim** | District planning coordinator | What should our team review together first? | Command exercise, opened at hour 84 |

- **Lalita's home** stands on the outline nearest the Public app's dry example home (cell code 76: dry at every hour),
  facing the street the walk starts from (road 112): a two-storey house kit set back behind a small yard and garden
  wall (with a spirit house and potted plants), and a one-storey back wing on the rest of the outline. The plot is
  laid out by `home-plot.ts` so that the roof, the wall and the wing clear every other outline; the real building
  reaches the street, so the yard and the house's looks are illustrative. Her neighbours 110 m away are the app's
  flooded example home (0.75 m of modelled water at the peak).
- **The walk** is the family's usual way to the nearest reported shelter in use in September 2024 by the replay's own
  walking network: the Mae Sai Subdistrict Municipality Office shelter, about 1.6 km south. Its first low edge, from
  75 m to 112 m along the walk south of the home, closes at a stage of 2.05 m: open at midnight on 11 September, cut
  by about 1:00, as the app's own states say ("Walk to a shelter nearly cut" at hour 48, "Cut off, home dry" at
  hour 84).
- **The District Office** (the reported 2024 incident command centre): an illustrative operations room stands at its
  real place, in place of the real building (whose outline is larger); inside and out, the room is illustrative.
- **Wat Mueang Daeng** is not a shelter in the story: the record says it was itself flooded and evacuated around 11–12
  September 2024 and used as a shelter from 21 September; the model shows its cell dry. Narin's caption uses it as an
  example of what still needs checking.

## How it works

| Part | File | Notes |
|---|---|---|
| Story timeline, replay time, phone state | `apps/web/src/lib/journey/timeline.ts` | Pure, unit-tested. Segments, stops and chapters; replay hour per position (`replayHourAt`), skips in time behind a page or a dip to dark (`veilAt`); the Public app's page and practice scenario per position (`phoneAt`). |
| The town bake | `scripts/build_journey_town.py` → `apps/web/public/journey/town/` | Building outlines, OSM roads and land cover, DEM relief, the r5 cells of the area, places, the walk, beats. Deterministic, `--verify`, receipt `docs/journey_town_input_receipt.json`; tests `tests/test_journey_town.py`. |
| Decoding and the flood field | `apps/web/src/lib/journey/town-data.ts` | Pure, unit-tested on the committed bake. Ground of a floodable cell = k_s × h, water surface = k_s × stage; wet exactly where stage > h (the model's rule). Pads (round or rectangular) hold the story's dry places at their cell's height. |
| Lalita's plot | `apps/web/src/lib/journey/home-plot.ts` | Pure, unit-tested: faces the street nearest the home place, sets the house back behind a yard, sizes it so its roof, garden wall and back wing touch no other outline, and keeps the house on cells dry at the peak. Roads, poles and cables are not drawn on the plot. |
| The town | `apps/web/src/components/journey/stage/town.ts` | Ground (fine grid near the story, coarser beyond, DEM hills), water mesh where the replay can wet the ground and on the river, extruded outlines with pitched or flat roofs, awnings and rooftop tanks, roads, poles, cables and lamps, the walk band. Merged per material and per 300 m tile. |
| Shading | `apps/web/src/components/journey/stage/town-materials.ts`, `facade-atlas.ts` | One flood field for every surface: water depth and colour, wet bands and mud tide lines on walls and ground once the water goes down, lit windows at night (dark where a ground floor is under water). A painted atlas of Thai facade bays (no words on signs). |
| People | `characters.ts`, `figure.ts` | Unchanged from cinematic-journey-v2: rigged Lalita and Narin; stand-in Mali, Dao and Pim. The family stands side by side at the gate, facing the street; the front shot looks at them from the street with the house behind. |
| Camera paths | `apps/web/src/lib/journey/camera-path.ts` | Unit-tested. Position on a centripetal Catmull-Rom spline; orientation interpolated as heading, tilt and roll (a move between opposite headings turns round the horizon, never through straight down); each move eases in and out once (sine) and is paced by how fast the picture changes (travel relative to height, plus rotation), so a dive slows near the street and turns get their time. A key can widen the lens (`zoom`) where the street is too narrow to back off. |
| Camera, light, weather | `journey-stage.ts` | Shots anchored to real places (the gate, the walk's low point, the deepest lane near the home, the river, the office window); tall screens get their own framings of the family. Light follows the replay hour (day, dusk, night), with the sky blended over a moment after the Public app's page (Monday noon to Tuesday afternoon); the sun is fixed in the east-south-east, so Lalita's house front is lit; weather is illustrative, rain from 10 September easing after the peak. |
| Shell | `journey-experience.tsx` | Loads the bake before the stage; sets the phone's page and practice scenario through the frame's address (while the phone shows, or at a rest before it shows again); loads the Public app at the title and each next page after the previous one has docked; keeps loaded pages painted at near-zero opacity (inert) so they are first drawn at rest; the compact chapter bar under the caption (previous, the chapter's name, which opens the list of chapters, next; the owner's request of 15 October 2026); the dips to dark; fades for the title and captions; the Credits panel (Escape closes it). |
| Copy (EN/TH) | `journey-copy.ts` | Linted by the shared wording lint in both languages. Thai is written by the assistant and has not had a native review. |

**Real pages, not mockups.** Each real route runs in its own same-origin `<iframe>`. The Public app reads `?practice=`
once and drops it from its address (Back and Forward then cannot bring a stale scenario back); the story sets it again
whenever its hour changes.

## Safety and honesty

- The notice (fictional people on the real map of Mae Sai; water from the FloodGuard replay (r5), a model
  reconstruction of September 2024, low confidence; not a forecast, not real-time) and a one-line data credit are on the
  title screen; the full credits and "heights and looks of buildings, and Lalita's house and yard, are illustrative"
  are in the Credits panel of the top bar. The scene itself carries no corner text (the owner's request of 15 October
  2026). The replay clock over the scene was removed at the owner's request (15 October 2026, later the same day):
  the captions name the replay date and hour where a beat depends on it, and the real pages show their own replay
  stamp. Credits: Google Open
  Buildings v3 (CC BY 4.0), Microsoft footprints (ODbL), © OpenStreetMap contributors, Copernicus DEM © DLR, Airbus DS.
- Every time and depth a caption names is the replay's, at that beat's replay hour. Weather is illustrative.
- The title is the owner's text (15 October 2026): "See the flood. / Understand what it changes." with "FloodGuard
  connects flood evidence with communities, roads, and essential services to support informed local planning." (Thai
  written by the assistant, not native-reviewed). The Meet Lalita overview carries no place labels (the owner's
  request, same day): the caption names the home, the shelter and the walk, and the teal line draws the walk.
- The story never triggers the real SOS and never says FloodGuard sends a request for help: the call to 1784 is
  simulated and goes through the hotline. No report, case change or dispatch is created by any transition.
- Real reported places are named with their record (reported in use, reported command centre, reported flooded); no
  real business is named; the home is a model point, not an address. The tone stays respectful of a real event.

## Deployment notes

- **Headers:** same-origin framing only (`X-Frame-Options: SAMEORIGIN`, `frame-ancestors 'self'`).
- **Profiles:** staff/competition route; the public-production build removes it, `public/journey/**` included.
- **Offline:** online-only; its chunks carry the `data-floodguard-journey` marker.
- **Assets:** the bake (`public/journey/town/`, about 1.4 MB, the JSON compressed in transit) and the characters
  (about 5.5 MB) load only on `/journey/`.
- **Rights:** the simplified outlines are published as a derivative database under ODbL 1.0 with the credit (note of
  14 October 2026 in `docs/proposal_execution/SOURCES_AND_RIGHTS.md`; an engineering note, not a legal clearance).

## Testing

- `pnpm --filter @floodguard/web test`: `src/lib/journey/journey.test.ts` (timeline, replay hours, phone state, screen
  projection, two-bone reach), `src/lib/journey/town-data.test.ts` (the bake: home dry at every story hour, the
  neighbour's 0.75 m, the walk open at hour 48 and cut by 49, the replay's stages), `journey-copy.test.ts` (wording
  lint in both languages, people introduced before their part, the call simulated), `characters.test.ts`.
- `pytest tests/test_journey_town.py` (the bake against the committed replay files, without external data).
- `node scripts/csp-smoke.mjs` loads `/journey/` and `/journey/?scene=case` under production headers.

## Known limitations

- The water is the replay's: HAND from a 30 m surface model, so buildings bias it upward in town and street-level depths
  are approximate; the drawn shore is smoothed between the replay's 15 m cells.
- The replay's drainage lines run about 100 to 150 m south of the mapped Sai River through town (r5's 30 m surface
  model): the water rises from the model's lines, while the river at a dry hour is drawn from OpenStreetMap.
- Ground that never floods is ramped from the floodable ground over about 60 m (the two come from different bases);
  its shape near that edge is drawn, not measured.
- Building outlines come from images of earlier years and overlap where the source does; heights, roofs, facades and
  trees are illustrative.
- North of the Sai River (Tachileik) the outline file has no buildings; OSM land use is sparse, so the hills read as
  open ground with sparse trees.
- The walk is the replay's network: straight node-to-node edges may run beside the drawn road centreline.
- The scene's walk is cut from a stage of 2.05 m; the app's resident point (its 10 m grid) from 2.15 m. No beat falls
  between the two.
- Mali, Dao and Pim are procedural stand-ins until rigged models of them are made.
- Hidden iframes keep running their pages; unmounting far-away pages would raise frame rates on low-end laptops.
- Docking a real page, and leaving the Prepare page into the night, can still drop a few frames (the page's own
  layout and re-render); camera moves through the town run at full rate on the test machine (headless Chrome,
  Direct3D 11), helped by a WebGL flush after each frame and a draw of every segment behind the loading screen.
- Lalita's house is set back behind a yard; the real building on that outline reaches the street.
