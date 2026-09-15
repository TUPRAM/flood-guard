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

### Geographic context

The event map uses the recorded bounding-box centres and Natural Earth 1:110m country outlines. The outlines are [public domain](https://www.naturalearthdata.com/about/terms-of-use/). They are display context, not model features or labels. Country labels inferred by point-in-polygon lookup are marked accordingly; a centre does not describe every chip or establish an event boundary. Source URL, downloaded bytes, SHA-256, verification time and transformation assumptions are saved in `geography.json`.

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
pnpm --filter @floodguard/web verify:profiles
pnpm test:offline
pnpm --filter @floodguard/web test:csp
pnpm --filter @floodguard/web exec node scripts/study-browser-smoke.mjs
python -m pytest services/geoai-runner/tests -q
python -m ruff check services/geoai-runner/scripts services/geoai-runner/tests/test_export_studio_study.py services/geoai-runner/tests/test_export_study_visuals.py services/geoai-runner/tests/test_study_geography.py
```

Browser tests serve the static export, exercise filters, refresh/Back, missing evidence, unavailable context chips, mobile layouts and all Mae Sai model/layer combinations. Public-profile verification checks that the entire `/studies/` asset directory is absent. Competition's core offline download keeps the planning report available but does not require the large research preview collection.

Deployment review uses a branch Preview. A Ready build is separate from browser verification and from production publication. This change does not alter the promotion gate, authorize a model, or claim real-time warning capability.
