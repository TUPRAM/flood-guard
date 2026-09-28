# Studio study library

Studio separates measured research, model applications, planning qualification and historical experiments. The website displays saved evidence. It does not train models, acquire imagery, or promote research outputs into decisions.

## Pages and ownership

| Route | Evidence owner | Scope |
| --- | --- | --- |
| `/studio/` | Study catalogue | Choose a study; no global model leaderboard or borrowed planning status |
| `/studio/planning-evidence/` | Existing Mae Sai evidence context | Qualification, restricted model registry, governance and authorization |
| `/studio/archive/mae-sai-geoai/` | Historical `2026-07-30-r1` report | Original optical/teacher experiments and earlier research; distillation fidelity is not water accuracy |
| `/studio/studies/c2s-ms-20260915/` | C2S-MS `r1` | Original-chip public benchmark overview |
| `…/data/` | Same C2S revision | All event assignments, observation dates, source licences and geographic context |
| `…/models/` | Selected frozen model/input version | Fitting, features, calibration, abstention and recorded TreeSHAP |
| `…/results/` | Original C2S chips | Raw/calibrated, pooled/per-event, full-valid/selective scores with support |
| `…/rtc/` | Separate matched RTC record | 46 chips, two events, fixed-ramp comparison and transfer limitations |
| `…/explorer/` | C2S human labels and frozen predictions | All 111 test chips; six trained model/input combinations |
| `…/files/` | Source receipts and public projections | Downloadable JSON evidence, attribution, checksums and reproduction limits |
| `…/mae-sai/` | Separate Mae Sai inference record | Six model/input versions, four layers, pre/post radar, checkpoint lineage; no local accuracy metrics |
| `/studio/cases/mae-sai-2024/` | Mae Sai 2024 timeline manifest (`TIMELINE_MANIFEST_URL`) | Hour-by-hour replay of a low-confidence terrain-model reconstruction with dated Sentinel imagery; modelled, not observed |

Each C2S section has its own static route. Query parameters record model/input, calibration state, event/chip, map layer and overlay selections. Invalid selections or revisions display an unavailable state. Ordinary browser Back and refresh preserve the selection.

## Frozen public projection

`apps/web/public/studies/c2s-ms-20260915/r1/manifest.json` binds the summary and all report/index assets by exact byte length and SHA-256. Its reviewed digest is pinned in `apps/web/src/lib/study-report-release.ts`; the browser does not trust a digest downloaded alongside an unchecked manifest. JSON loads validate study/revision, schemas, safety flags, partition roles, metric support and inference restrictions. Missing, altered, wrongly scoped or redirected evidence fails closed.

The records are independent of `useFloodGuardData` and the existing Mae Sai model registry. No C2S metric is inserted into a blocked Thai evaluation. Separate original-chip, RTC and Mae Sai records retain checkpoint lineage. Source hashes and public-projection hashes are separate because downloads are reserialized and private experiment-root paths are made relative.

The source experiment checkout was `codex/public-flood-models` at `36e2536d9dee68c7747e1755e508893858fd9a69`. Reproduction requires that experiment's archived reports and acquired work data, including its frozen checkpoints. Those large local inputs are not supplied by this frontend branch, and there is no published checkpoint download. The website documents this limit and links public dataset acquisition sources.

### Visual evidence

- All 111 test chips: 65 Australian, 18 Nigerian and 28 Pakistani chips.
- Six combinations: RF, XGBoost and U-Net, each with SAR-only and context inputs.
- 633 combinations with valid inputs; 33 explicitly unavailable combinations from 11 context-empty chips.
- 2,147 small PNG previews, including 26 Mae Sai previews. Full rasters and weights remain outside Git.
- Each available case has radar/reference, calibrated probability, binary prediction and error views. Preview dimensions are at most 256 pixels; benchmark counts use the original full-resolution valid pixels.
- Export verification replayed all 633 available cases from frozen checkpoints. Every TP/FP/FN/TN count matched the archived report exactly. This checks correspondence with the saved C2S evaluation; it does not establish Mae Sai accuracy.
- Mae Sai probability and entropy remain inspectable in abstained areas. The optional tint and separate abstention map disclose the screening result; neither creates a new accepted prediction or reference label.

The visual index itself is checksummed through the manifest. PNGs carry embedded provenance and individual digests in that index. `export_study_visuals.py` verifies all source/checkpoint receipts and the full-resolution confusion counts before publishing a completed index.

`.gitattributes` preserves `/studies/` files byte-for-byte, including the original newline style of independently exported indexes. The integrity check also compares working files with their Git blobs, so a locally passing manifest cannot become invalid after a clean checkout.

### Geographic context

The event map uses the recorded bounding-box centres and Natural Earth 1:110m country outlines. The outlines are [public domain](https://www.naturalearthdata.com/about/terms-of-use/). They are display context, not model features or labels. Country labels inferred by point-in-polygon lookup are marked accordingly; a centre does not describe every chip or establish an event boundary. Source URL, downloaded bytes, SHA-256, verification time and transformation assumptions are saved in `geography.json`.

### Case replay: links, exports and offline copy

The replay's data revision is chosen only by `TIMELINE_MANIFEST_URL` in `apps/web/src/lib/flood-timeline.ts`; the page, the offline inventory (`apps/web/scripts/case-replay-inventory.mjs`), the integrity check and the tests derive every asset from that manifest.

- The page serves revision `r2`. Its HAND raster is RGB: R is the effective HAND code and G the per-cell depth factor k × 255, so depth is k × (stage − HAND) while wetness depends on the code alone. Roads and facilities carry the same k: a road is impassable when the rounded k × (stage − h) reaches 0.3 m and wet when that rounded depth is above 0, the same rule as `floodguard.flood_timeline.road_state`; a Python-generated fixture (`apps/web/scripts/road-state-parity-fixture.py`) checks every hour of the replay grid. The stage is the assumed Sai main-stem stage at the Mae Sai bridges; tributary cells rise k × stage. The stage curve interpolates over every anchor, including 10 Sep 18:15 (0.12 m, GISTDA-anchored; GISTDA gives no time zone, so ICT is assumed — as UTC the knot would be 11 Sep 01:15 ICT) and 11 Sep 02:00 (2.5 m). Area, road, facility, people-in-water and access figures recomputed in the browser equal the manifest's baked keyframe statistics, and unit tests enforce this.
- Water can show depth at the moment, the first flooded hour, hours under water, people in flood water (wet cells coloured by WorldPop 2020 residents per hectare) or all residents. Arrival and duration are pure functions of the assumed stage curve sampled at the start of each local hour (9 Sep 00:00 to 19 Sep 23:00); road-cut hours use the same grid and the same 0.3 m threshold as the road state. WorldPop is modelled residential population, not the 2024 population or border-market visitors.
- Evacuation access is a T1 scenario, not observed outcomes. It covers residents at road nodes who can walk to an open, dry shelter within 2 km on roads that are still passable. The shelter set is either the sites reported in use in September 2024 or the first k sites of the ranked plan (k = 1 … N, default the knee). The node file (`access-nodes.bin`, little-endian columns per the manifest layout) is reduced once per set to cumulative histograms by cut level, so each hour costs O(1). The Evacuation Equity Gap uses the rules of `floodguard.equity`. "Vulnerable" there is the terrain/remoteness proxy, not demographic vulnerability. The "people cut off" layer draws the nodes that have lost access as population-weighted blobs on a canvas overlay.
- Shelters: reported 2024 sites are stars with sourced popups and a model check at the modelled peak, and unlocated sites are listed without a pin. The Mae Sai District Office (R05) is drawn as a relief and command site (diamond), not a shelter, and Wat Mueang Daeng (R04) is labelled a shelter only from 21 Sep, following the research notes (`REPORTED_SITE_ROLES`, tied to the manifest wording by a unit test). Plan candidates appear as numbered top-k badges, eligible rings and grey ineligible markers with reasons; candidates off the DEM tile (east of 100°E) or off the grid are drawn as not modelled instead of showing the build's placeholder high-ground or flood results. A collapsible "Other shelter candidates" card lists every ring and dot with its reasons and a "Show on map" button, so none is pointer-only. Popups give the capacity estimate with its Sphere basis and the load for the chosen k. The coverage curve shows the ranking as a range, and the uncoverable residents are called out as the shelter gap.
- The address bar records `t` (hour index), `img`, `wm`, `wo`, `rm`, `cmp`, `lang`, `layers` (letters `t r f s c i x`), `set` (`reported` or `plan`) and `k`; invalid values fall back to the defaults.
- PNG and video exports render offscreen at the full study extent. They carry the model disclaimer, local time, figures (including modelled residents in flood water) with their scope (the modelled part of Mae Sai district, not the whole pictured frame) and source attribution. Cancelling while the video is still being prepared stops it from starting; a recording started in a hidden tab begins paused. Video is offered only where the browser can record a canvas.
- Offline: the route is part of the competition core cache. Its data (about 5.6 MB, including the residents raster and the access node file) is an opt-in bucket, not part of the blocking installation. After the replay renders online, it asks the service worker to keep the manifest's files, and each is stored only when its SHA-256 matches the build. The street basemap is online-only, and the page says so when it is unavailable.
- Confidence and timestamps: the access, plan and reported-shelter cards state the water reconstruction's confidence class, the OpenStreetMap extract date and the WorldPop estimate, and the reported list's status (public reporting, not an official register) with its source-date range. External figures are split into the calibration anchor (GISTDA, which set the onset knot) and independent checks; UNOSAT 3991's cumulative 13–19 Sep extent is compared with the model's largest extent in that window (2.65 m on 13 Sep 00:00 ICT), with the earlier modelled peak shown for reference only. Cards carry planning themes ("Protect Lives Now", "Keep Routes Open"), not FPPS action classes. One card, "Which subdistrict to act on first", computes a scenario FPPS per subdistrict at the current moment and for the chosen shelter set (`apps/web/src/lib/replay-fpps.ts`): flood likelihood from the flooded share of modelled area, exposure from residents in water (share and headcount), access gap from the share of people whose homes are wet who cannot walk to a dry shelter of the set, road criticality from class-weighted impassable road length, and vulnerability from the terrain/remoteness proxy, each on fixed anchors (`replay_fpps_anchor_v1`). It scores them with the locked weights and A–E rules (`apps/web/src/lib/fpps.ts`, checked against `floodguard.scoring` via `tests/fixtures/fpps_parity_cases.json`), so with the replay's low confidence every class is E and the score-implied class is shown separately. The ranking stays in the replay; it does not change the Planning areas.
- Known limits of the frozen r2 build, disclosed on the page rather than fixed in the data: the precomputed `reported_2024` access set still counts R04 and R05 as open shelters for the whole replay; `access` and `shelters` carry no confidence or timestamp fields of their own (the page derives them as above); and road pieces and access edges take the depth factor k of their lowest-HAND sample, so closures can come later than the "any 10 m sample" rule. A later builder revision should fix these at the source.

### Historical archive

The archive uses `studies/mae-sai-geoai/2026-07-30-r1/`. It preserves the original report, hashed preview filenames, baseline metrics/notes and MNDWI module diagnosis. The archive wrapper explains the old optical U-Net's teacher-agreement score. The original observation timestamp remains separate from the baseline run date. Current planning outputs and their existing research disclosure are preserved.

## Reproduction and maintenance

From the repository root, with the original experiment data available:

```powershell
# Explicit inputs: an experiment checkout and a separate staging checkout.
python services/geoai-runner/scripts/export_study_visuals.py --source-root <experiment-checkout> --output-root <staging-checkout> --device cuda

# Optional explicit network acquisition for cartographic display only.
# Use the committed r1 summary as the event inventory; output must be new.
python services/geoai-runner/scripts/acquire_study_geography.py --summary apps/web/public/studies/c2s-ms-20260915/r1/summary.json --output <staging-checkout>/apps/web/public/studies/c2s-ms-20260915/r1/geography.json

# Assemble report projections after the visual index and geography exist.
python services/geoai-runner/scripts/export_studio_study.py --experiment-root <experiment-checkout> --output <staging-checkout>/apps/web/public/studies/c2s-ms-20260915/r1

# Validate/reproduce the committed historical projection from its original sources.
node apps/web/scripts/archive-historical-study.mjs
```

The report and historical exporters reject conflicting bytes in an existing revision. Acquisition refuses to overwrite an existing projection. A newly acquired cartographic file has a new verification timestamp; to reproduce the exact r1 bytes, reuse its committed `geography.json`. Future scientific runs require a new study/revision and reviewed manifest pin. Do not update September 15 metrics in place or use the already observed final test for tuning.

### Verification commands

```powershell
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test:contracts
pnpm test:web
pnpm --filter @floodguard/web exec node scripts/verify-study-assets.mjs
pnpm --filter @floodguard/web verify:profiles
pnpm test:offline
pnpm --filter @floodguard/web test:csp
pnpm test:studies
python -m pytest services/geoai-runner/tests -q
python -m ruff check services/geoai-runner/scripts services/geoai-runner/tests/test_export_studio_study.py services/geoai-runner/tests/test_export_study_visuals.py services/geoai-runner/tests/test_study_geography.py
```

Browser tests serve the static export, exercise filters, refresh/Back, missing evidence, unavailable context chips, mobile layouts and all Mae Sai model/layer combinations. Public-profile verification checks that the entire `/studies/` asset directory is absent. Competition's core offline download keeps the planning report available but does not require the large research preview collection.

Deployment review uses a branch Preview. A Ready build is separate from browser verification and from production publication. This change does not alter the promotion gate, authorize a model, or claim real-time warning capability.
