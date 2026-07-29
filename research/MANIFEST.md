# Research manifest

The only tracked file in `research/`. Everything else here is gitignored.

## What this directory is

The **ungoverned** landing zone for exploration: `geoai-skills` output,
downloaded open benchmarks, scratch rasters, one-off comparisons.

A result in here is a **hypothesis**. It has no checksum, no `ModelRun`, no
registry entry, and no `official_warning=false` marker, so it cannot back a
published claim. Discarding a research result is the normal outcome and is a
success, not a failure — a negative result recorded here is far cheaper than a
wrong claim published.

## The rule

> **Skills explore. `realpipeline` claims.**

| | `research/` | `evidence/` |
| --- | --- | --- |
| Produced by | any tool, any environment | `realpipeline` under the frozen runtime |
| Provenance | none | `ModelRun v2` + `ModelEvaluation v2` + checksum |
| Spatial holdout | not required | required (`blocks.py`) |
| Receipt | none | signed, via `trusted_zonal_adapter` |
| Read by `services/api` | **never** (asserted in CI) | yes |
| Read by `apps/web` | **never** (asserted in CI) | yes |
| Git | ignored | tracked |

Promotion is a **re-run**, never a file copy. Copying an artifact from here into
`evidence/` is the single failure mode this directory exists to prevent, and
`services/api/tests/test_research_boundary.py` fails the build if the API can
resolve a `research/` path.

## Layout

```
research/
├── MANIFEST.md          this file — tracked
├── skills/              geoai-skills output — ignored
├── benchmarks/          downloaded open datasets — ignored
└── .geoai-skills/       skill session state — ignored
```

## Environment

Most exploration needs the GeoAI stack, which is **not installed by default**:

```
uv sync --project services/geoai-runner --extra geoai
```

Component ★ (OmniWaterMask) needs a *separate* environment, because
`omniwatermask` requires `numpy>=2.0,<2.4` and the runner is frozen at
`numpy==2.4.2`:

```
uv venv .venv-research --python 3.12
uv pip install --python .venv-research -r services/geoai-runner/requirements-research.txt
```

Output from that environment carries no frozen-environment receipt and is
research tier by construction.

## Log

Add one block per experiment. Record the negative results too — they are the
ones that stop the same dead end being explored twice.

```markdown
## YYYY-MM-DD · Component X · one-line question
Skill/cmd:  /geoai-skills:... or the script invoked
Environment: runner geoai extra | .venv-research | none
Output:      research/skills/...           (untracked)
Question:    what this was meant to settle
Result:      what actually happened, including numbers
Decision:    promote | discard | rerun — and why
```

---

## 2026-07-29 · Setup · sandbox created

Environment: none
Output:      —
Question:    Where should ungoverned exploratory output live so it cannot be
             mistaken for evidence?
Result:      `research/` created, gitignored except this manifest. Boundary
             asserted by `services/api/tests/test_research_boundary.py` and
             `tests/test_research_boundary_web.py`, which fail if the API or
             the web app can read from here.
Decision:    Adopted. See audit §8A.5 and ADR-I.

---

## 2026-07-29 · Setup · GeoAI toolchain installed and verified (D-33)

Skill/cmd:   `/geoai-skills:install-geoai --check --extras`
Environment: `services/geoai-runner/.venv-geoai` (new; `.venv` left light)
Output:      —
Question:    Can any GeoAI component actually run in this checkout?

Result:      Yes, for the first time. Previously `import geoai` failed in all
             three environments (audit §8A.3).

```
geoai 0.41.1 · numpy 2.4.2 · geopandas 1.1.4 · rasterio 1.4.4
rioxarray 0.22.0 · shapely 2.1.2 · leafmap 0.63.0 · pandas 3.0.3
torch 2.13.0+cpu · torchvision 0.28.0+cpu · transformers 5.14.0
timm 1.0.28 · segmentation_models_pytorch 0.5.0
CUDA: not available (CPU only)
```

Three findings worth carrying forward:

1. **`geoai_runner.environment.inspect_environment()` issued a receipt.** The
   project's own frozen-environment gate passes: Python 3.12.13, geoai-py
   0.41.1, declared commit matched. That gate had never been exercised here.
2. **CPU-only torch despite an RTX 3060 (6 GB) being present.** PyPI's Windows
   wheels ship without CUDA. Resolved the same day — see the CUDA entry below.
3. **All 30 `geoai` APIs the skills call exist** on 0.41.1 — the skill contract
   holds against this pinned version.

             Isolation verified intact after install: the dependency-light
             `.venv` and the root `.venv` still cannot import `geoai` or
             `torch`, so CI job `geoai-normal` is unaffected.

Decision:    Adopted. `.venv-geoai` is the research-tier environment.
             Nothing produced here is evidence until re-run under the governed
             runner.

---

## 2026-07-29 · Component D · Overpass is down, and Overture corroborates the completeness flag

Skill/cmd:   `/geoai-skills:inspect-geo outputs/geoai/subdistricts.geojson`
             `/geoai-skills:overture-data building --bbox 99.83,20.33,99.97,20.49`
Environment: `.venv-geoai`
Output:      `research/skills/overture_buildings_mae_sai.geojson` (untracked)
Question:    Does an independent building source agree with Component D's 463
             OSM footprints, and is the coverage caveat quantified correctly?

### Finding 1 — Component D cannot fetch data at all right now

`fetch_osm_buildings` fails on **both** mirrors:

| Mirror | Result |
| --- | --- |
| `overpass-api.de` | `CERTIFICATE_VERIFY_FAILED — certificate has expired` |
| `overpass.kumi.systems` | certificate valid (to 2026-08-31), but `RemoteDisconnected` on the query |

Not caused by the D-01 TLS change: `fetch_osm_buildings` calls `urlopen` with
no context and always did (unchanged at `debe413`, line 539). The expired
certificate was confirmed by an independent socket probe.

The docstring promises a cached fallback "so a transient outage does not
silently drop Component D" — but the cache lives in `outputs/geoai/work/`,
which is gitignored (`.gitignore:67`). **On a fresh clone there is no cache, so
Component D has no working path today.**

### Finding 2 — the project's own completeness flag is accurate

This is a correction to how the audit framed it. FloodGuard already measured
this and already publishes it:

```
subdistrict        osm_building_count  completeness_ratio  flag
Wiang Phang Kham                  136              0.0279  severely_incomplete
Pong Ngam                          92              0.0508  severely_incomplete
Mae Sai                            86              0.0192  severely_incomplete
Ko Chang                           38              0.0227  severely_incomplete
Pong Pha                           26              0.0112  severely_incomplete
Huai Khrai                         19              0.0085  severely_incomplete
Si Mueang Chum / Ban Dai            0              0.0000  severely_incomplete
                            TOTAL 397
```

Overture, same bbox, spatially joined to the same 8 tambons: **54,978
buildings**. So 397 / 54,978 ≈ **0.7 %** — the same order of magnitude as the
0.85–5.1 % the pipeline computes for itself. The `severely_incomplete` flag was
not hedging; it was correct, and an independent source now corroborates it.

### Finding 3 — Component D contributes no signal

`ai_exposed_building_count` is **0 for every one of the 8 tambons**, and
`metrics.infrastructure.exposed_count = 0`. A layer that is ~99 % incomplete
*and* contributes zero exposed structures is not adding information to the
decision layer. That is an argument for replacing its source or dropping it
from the MVP tier, not for another caveat.

Result:      Overture returns 138x more buildings than OSM/Overpass over the
             same area, works today, and is already installed via `geoai-py`.
Decision:    **Do not promote.** Swapping Component D's source would change a
             published figure, and per ADR-I that requires a governed re-run
             with an evaluation behind it, not a file copy. Recorded as the
             evidence for a follow-up decision on Component D's source.

---

## 2026-07-29 · Setup · CUDA enabled for the research environment

Skill/cmd:   `uv pip install --index-url .../cu126 --reinstall-package torch ...`
Environment: `.venv-geoai` only
Output:      —
Question:    Is the frozen pin actually a barrier to using the GPU, and is the
             GPU worth using?

### Correction to the audit's framing

Two claims made earlier were wrong, and both were checked rather than repeated:

| Claim | Reality |
| --- | --- |
| "a CUDA wheel invalidates the environment receipt" | `environment.py` checks Python 3.12, the geoai commit, and `geoai-py==0.41.1`. **It never checks torch.** Receipt still issues under cu126. |
| "a CUDA wheel leaves the frozen pin" | `torch==2.13.0` is satisfied by `2.13.0+cu126` under PEP 440 local-version rules. The pin holds. |

So this was an empirical question, not a governance one. The only genuine cost
is divergence from `uv.lock` inside `.venv-geoai` — which is why it goes there
and not into `.venv`.

### Measurement

Component B's real config (unet/resnet18, 6 channels, 128 px tiles, batch 8):

```
CPU        913 ms/step   20 epochs 11 min    120 epochs 64 min
CUDA 12.6   33 ms/step   20 epochs  0.4 min  120 epochs  2.3 min   (28x)
peak VRAM 0.85 GB of 6.4 GB
```

`calibration.py` does **not** train — it computes Brier score, log loss and
reliability curves over probability arrays — so T2.3 needs inference only and
would have been fine on CPU. The GPU is justified by Component B's withdrawn
metric needing a **re-run**: a 64-minute feedback loop is where iteration dies.

### Two practical traps, both hit

1. `uv pip install "torch==2.13.0"` against the CUDA index **does nothing** —
   uv sees `2.13.0+cpu` as already satisfying the specifier.
   `--reinstall-package torch` is required.
2. The first attempt failed after downloading 2.4 GB:
   `UV_HTTP_TIMEOUT` defaults to 30 s. Set it to 1800. uv rolled back cleanly
   and `.venv-geoai` was verified healthy before retrying.

Result:      `torch 2.13.0+cu126`, CUDA 12.6, RTX 3060 Laptop active.
             Environment receipt still issued. Both isolation gates still hold:
             the light `.venv` and root `.venv` cannot import geoai or torch.
Decision:    Adopted for `.venv-geoai` only. Documented in the runner README,
             including the two traps.

---

## 2026-07-29 · Component ★ / B · T2.4 — the IoU 0.07 is not a defect; the reference is wrong

Skill/cmd:   `research/skills/diagnose_owm.py`
Environment: `.venv-research` (numpy 2.3.5 + omniwatermask 0.5.0)
Output:      `research/skills/owm_diagnosis/` (untracked)
Question:    Is Component ★'s IoU of 0.07 a defect, and if so which one?

### Both leading hypotheses were wrong

The audit ranked **wrong `band_order`** first. Dead on reading:
`water_baseline.py` already passes `[3, 2, 1, 4]` and documents the mapping.

Reading the fetch path inverted the second one. `fetch_sentinel2_composite`
already normalises (`np.clip(mosaic / 10000.0, 0, 1)`), so OWM is handed 0-1
reflectance while the book's Ch. 9.6.4 example feeds it raw L2A. Plausible —
and testable by running OWM on both scalings of identical pixels:

```
reflectance 0-1     water fraction 0.00325   IoU 0.0536
scaled 0-10000      water fraction 0.00330   IoU 0.0541
```

They agree to three decimal places. **Scaling is not the cause** — OWM
normalises internally. H1′ rejected.

### What it actually is

The scene is **2024-02-18, cloud cover 0.004 %** — the pipeline deliberately
requests the dry season (`datetime_range="2024-01-15/2024-03-15"`) because
monsoon skies are cloudy. So there is **no flood in this scene**, and true
water extent should sit near permanent water. An independent reference already
in the pipeline settles it:

| Source | Water fraction |
| --- | --- |
| OmniWaterMask (either scaling) | **0.33 %** |
| **JRC Global Surface Water, occurrence > 50 %** | **0.37 %** |
| MNDWI > 0 — *the reference the IoU was measured against* | **3.24 %** |

OmniWaterMask lands within 12 % of JRC. **MNDWI > 0 over-detects water by
roughly 10x** on a cloud-free dry-season scene — consistent with it being a
permissive threshold that also flags wet soil, terrain shadow, and some
vegetation.

**H3 CONFIRMED.** The 0.07 measures disagreement between two different water
definitions, not OmniWaterMask's accuracy. Publishing it as a suspect model
metric is backwards: the model matches the independent reference; the label
does not.

### The consequence that matters more

`water_label = (mndwi > 0.0)` is not only the ★ comparison reference — it is
**Component B's training target and its evaluation target**:

```
run_real.py:201  water_label = (mndwi > 0.0)
run_real.py:210  write_geotiff(work/"water_label.tif", water_label, ...)
run_real.py:222  water_unet.fit_channel_stats(work/"water_label.tif", ..., role="train")
run_real.py:253  water_unet.evaluate_roles(b_prob, water_label, assignment)
```

So Component B learns, and is scored against, a target that over-detects water
by ~10x. Its metric was already withdrawn as leaky (spatial autocorrelation);
this is a **second, independent defect** in the same component, and the leakage
fix would not have touched it.

Result:      Component ★ is behaving correctly. The reference is the problem.
Decision:    **Do not promote.** Two follow-ups recorded, neither taken here
             because both change published figures:
             1. Re-frame ★'s published metric as label disagreement, not
                model accuracy — or drop the IoU and report extent vs JRC.
             2. Review the MNDWI threshold before Component B is re-run. A
                threshold review is a prerequisite for that re-run, not a
                separate nicety.

---

## 2026-07-29 · Component D · source swapped to Overture Maps

Skill/cmd:   `overturemaps.geodataframe("building", bbox=...)` via
             `real_data.fetch_buildings`
Environment: `.venv-geoai`
Output:      code change (tracked); no published artifact regenerated
Question:    Can Component D's building source be replaced with one that works?

Result:      Yes. `fetch_buildings` now tries Overture first and falls back to
             OSM/Overpass, returning `(buildings, source_name)` so the source is
             recorded in the run metrics rather than assumed.

Live over the real study bbox (`99.799, 20.2499, 100.0445, 20.4754`):

```
source: overture
count : 118,072      (vs OSM's 397 across the 8 tambons)
shape : {id, lon, lat, tags} — matches the fetch_osm_buildings contract
```

`overturemaps` is now declared explicitly in the `realpipeline` extra rather
than relied on transitively through `geoai-py`, so acquisition stays
independent of the optional geoai extra — the same rationale recorded on
`_pc_client`.

### What has NOT changed, and why

**The committed artifacts still say 463 buildings and 0 exposed.** Only the
code path changed. `outputs/geoai/*` and `apps/web/public/geoai/mae-sai-real.json`
are regenerated by a full `run_real` pass, which needs the whole component
chain and roughly an hour. Publishing a new building count without re-running
the exposure computation that depends on it would be exactly the file-copy
promotion ADR-I forbids.

So the state is honest but split: the **source is fixed**, the **published
figures are stale**, and the next full run will move `building_count` from 463
to ~10^5 and `exposed_count` off zero. That re-run is the promotion step, and
it needs the D-02 receipt (now in place) plus a look at whether Overture's
weaker per-building attribution changes what `amenity`-based logic can claim.

Decision:    Code swap adopted. Published figures deliberately left stale until
             a governed re-run. Recorded here so the gap is visible rather than
             discovered later.
