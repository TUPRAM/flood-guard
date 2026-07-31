# Run plan — first governed GeoAI re-run

**Planned:** 2026-07-30 · **Branch:** `system-fix` · **Status:** EXECUTED — see §12
**Baseline for comparison:** `docs/baseline/2026-07-30-run1/` (see §12.1 for why the
older committed artifacts could not serve)

---

## 1. What this run is for

Three things landed in code but are not in any published artifact: the D-02
report-only receipt lane, Component D's swap to Overture, and the tier markers
in the web payload. `outputs/geoai/*` and `apps/web/public/geoai/mae-sai-real.json`
still describe the pre-change pipeline. **This run makes the published evidence
match the code**, and it is the first run that produces a signed receipt.

It is also the first opportunity to fix Component B's training label, which
T2.4 showed is the most consequential defect currently in the pipeline.

**What this run is NOT for.** It does not produce an in-area accuracy claim, it
does not clear anything for the decision layer (`can_feed_decision_layer` stays
`false` by construction), and it does not make Component B trustworthy. It
produces *traceable candidate evidence* whose weaknesses are measured instead
of assumed.

---

## 2. Definition of a good result

The single sentence version:

> **A good run is one where every published number either reproduces its
> baseline within tolerance, or moves for a reason recorded before the run
> started.**

An unexplained move is a failure even if the new number looks better. That is
the whole point of having a baseline.

| # | Criterion | Pass condition |
|---|---|---|
| G1 | Receipt exists and verifies | `outputs/geoai/candidate_zonal_receipt.json` present, `verify_candidate_zonal_receipt` returns `True`, `can_feed_decision_layer` is `false` |
| G2 | FPPS unchanged | Every tambon's `fpps_0_100` within **±0.01** of baseline, all 8 `action_class` identical |
| G3 | Unchanged components reproduce | Component A flood fraction within ±20% rel.; Component C AUC within ±0.03 |
| G4 | Component B label defensible | New label documented, with its own agreement figures against JRC recorded *before* B is trained |
| G5 | Component B not leaking | `train`, `val`, `test` role IoUs within **0.15** of each other |
| G6 | Component D honest | `building_count` 10^4–10^5, `building_source: "overture"`, `exposed_count > 0`, **and** the completeness flag does not silently upgrade (see §7.3) |
| G7 | Tier visible | Web payload carries `evidence_tier`, `can_feed_decision_layer`, `aggregation_status` |
| G8 | Suites green | root, runner, api, `ruff`, `pnpm verify:frontend` all pass after regeneration |
| G9 | Every delta explained | Each changed published number has an entry in the run log with a cause |

**G2 deserves emphasis.** FPPS should *not* move. Verified while writing this
plan: `compute_exposure` derives `exposure_0_100` from WorldPop population
density, and building counts were deliberately removed from the score — the
`aggregate` docstring records that OSM "captures ~2% of reality with a 25x
spread… they no longer enter the score." So the Overture swap changes a
*diagnostic*, not the decision layer. **If FPPS moves, something is wrong that
this plan did not anticipate — stop and investigate.**

---

## 3. The blocker: Component B's label must change first

T2.4 established that `water_label = (mndwi > 0.0)` over-detects water ~10x.
Before designing around it I swept alternatives against JRC Global Surface
Water (occurrence > 50 %, **0.373 %** of the scene) on the cached 2024-02-18
dry-season, cloud-free stack:

| Candidate label | Water fraction | IoU | Precision | Recall |
|---|---|---|---|---|
| **MNDWI > 0 (current)** | **3.240 %** | 0.055 | 0.058 | 0.502 |
| MNDWI > 0.05 | 1.993 % | 0.076 | 0.084 | 0.451 |
| MNDWI > 0.10 (best MNDWI) | 1.042 % | 0.079 | 0.100 | 0.279 |
| MNDWI > 0.15 | 0.408 % | 0.049 | 0.089 | 0.097 |
| **NDWI > 0** | 0.872 % | **0.154** | 0.190 | 0.446 |
| MNDWI > Otsu (−0.213) | 23.303 % | 0.012 | 0.012 | 0.737 |
| **OmniWaterMask** | **0.330 %** | — | — | — |

### The finding that closes off threshold tuning

**No MNDWI threshold is salvageable.** Best case is IoU 0.079 at 0.10, where
precision is 0.100 — nine of ten flagged pixels are not JRC permanent water.
And the damning statistic: at the *current* threshold MNDWI flags 8.7x the
reference area **while still missing half of it** (recall 0.502). A mask cannot
be fixed by moving a threshold when it simultaneously over-detects and
under-detects; it is responding to something other than water across much of
the scene. In mountainous Mae Sai the likely culprits are terrain shadow (low
SWIR1 → high MNDWI) on one side and silt-laden river water (high SWIR1 → low
MNDWI) on the other.

I also excluded the benign explanation. If the disagreement were mostly
sub-pixel registration between 30 m JRC and our ~22 m grid on 1–2 px rivers,
IoU would jump with matching tolerance. It barely moves:

| mask | IoU @0px | @1px | @2px | @3px |
|---|---|---|---|---|
| MNDWI > 0 | 0.055 | 0.064 | 0.073 | 0.081 |
| NDWI > 0 | 0.154 | 0.191 | 0.227 | 0.263 |

and 79 % of the JRC reference survives 1 px erosion, so it is not a hairline
artefact. **The disagreement is real.**

### Options, and the recommendation

| Option | Effect | Verdict |
|---|---|---|
| **A. Tune the MNDWI threshold** | Best IoU 0.079, precision 0.10 | **Reject.** Cannot fix a mask that both over- and under-detects |
| **B. Switch to NDWI > 0** | 2.8x better IoU (0.154), one-line change | Weak improvement; still 2.3x JRC extent |
| **C. Use OmniWaterMask as the label** | Matches JRC extent to 12 % (0.330 % vs 0.373 %) | **Recommended** |
| **D. Demote Component B from MVP** | Removes an unfixable claim | Keep on the table — see the honesty note |

**Recommendation: C.** Component ★ already produces the best available optical
water mask in this pipeline, it is pre-trained and zero-training, and Ch. 9.6.4
positions it as exactly this kind of reference. Using it as B's target replaces
a demonstrably wrong label with the best one available.

**The honesty problem with C, stated plainly.** If B is trained on ★'s output,
B is *distilling ★*, not learning water independently. A high IoU then measures
how well B copies ★ — which is a real engineering result (a fast local model
with no HF download) but **not evidence that either model is accurate in Mae
Sai**. It must be published as distillation fidelity, never as accuracy, and
Component B's registry entry and `assumptions` string must say so. If that
framing is unacceptable, option D is more honest than pretending B adds
information.

**This decision is a prerequisite. Do not start the run until it is made.**

---

## 4. Preconditions

Each is independently checkable; do not proceed on a failure.

| # | Precondition | Check |
|---|---|---|
| P1 | Working tree clean, on `system-fix`, CI green | `git status --porcelain` empty; `gh run list --branch system-fix --limit 1` |
| P2 | Baseline frozen | copy `outputs/geoai/{geoai_metrics.json,geoai_subdistrict_priority.csv,extra_methods_metrics.json}` to `docs/baseline/2026-07-30/`, record SHA-256 |
| P3 | GeoAI env healthy, GPU live | `.venv-geoai` → `torch 2.13.0+cu126`, `cuda.is_available() True`, `inspect_environment()` issues a receipt |
| P4 | Signing key set | `FLOODGUARD_ZONAL_SIGNING_KEY_HEX` ≥ 32 bytes hex; run fails closed without it |
| P5 | Network reachable | Planetary Computer STAC, `ngis.go.th` (TLS verified), Overture S3 |
| P6 | Label decision made and written down | §3 recorded in `research/MANIFEST.md` with its agreement figures |
| P7 | Disk | ≥ 20 GB free for `outputs/geoai/work/` rasters |

---

## 5. The run

```powershell
$env:FLOODGUARD_ZONAL_SIGNING_KEY_HEX = (python -c "import secrets;print(secrets.token_hex(32))")
$env:FLOODGUARD_ZONAL_SIGNING_KEY_ID  = "candidate-rerun-2026-07-30"

# Smoke first: 20 epochs, ~2 min on GPU. Catches wiring faults cheaply.
services/geoai-runner/.venv-geoai/Scripts/python.exe `
  -m geoai_runner.realpipeline.run_real --fast

# Then the real pass: 120 epochs.
services/geoai-runner/.venv-geoai/Scripts/python.exe `
  -m geoai_runner.realpipeline.run_real
```

Run `--fast` first and check G1/G2/G6 on its output. A wiring fault — missing
key, Overpass fallback firing, receipt not written — shows up identically at 20
epochs and at 120, and the smoke costs two minutes.

`--all-methods` (adds ★ and Component E) and `--temporal` (Component A2, ~180
scene download) are **out of scope**. Component A2 has never been run; pairing
its first execution with a re-baselining run means two unknowns in one diff.

### Expected duration

| Step | Time | Notes |
|---|---|---|
| 1 DOPA sub-districts | <1 min | NGIS, TLS verified |
| 2 Component A — Sentinel-1 | 3–6 min | windowed COG reads, 2 dates x 2 pol |
| 3 Sentinel-2 composite | 2–5 min | same-date mosaic |
| 4 **Component B — U-Net** | **2–3 min** | 120 epochs on GPU; was 64 min on CPU |
| 5 Component C — DEM/HAND | 3–6 min | Copernicus DEM + DWR + JRC |
| 6 **Component D — Overture** | **2–5 min** | ~118 k footprints, S3 parquet |
| 7 Component F — few-shot | 1–2 min | |
| 8 Bridge + receipt | <1 min | signed receipt written here |
| 9 Metrics, figures, page | 1–2 min | |
| **Total** | **~15–30 min** | GPU is what makes this feasible in one sitting |

---

## 6. Success criteria per component

Baselines are the `debe413` values in `outputs/geoai/geoai_metrics.json`.

### Component A — SAR flood extent · nothing changed, so reproduce

| Metric | Baseline | Pass | Rationale |
|---|---|---|---|
| `flood_fraction` | 0.0021 | 0.0017–0.0025 | Same pinned scene pair (2024-08-22 / 2024-09-15); ±20 % allows COG resampling jitter |
| `pre_datetime` / `post_datetime` | as baseline | **exact** | Different scenes means a different experiment |

A move outside this band means the acquisition changed. Investigate before
reading anything else — every downstream component consumes A.

### Component B — U-Net · the component being changed

| Metric | Baseline | Pass | Rationale |
|---|---|---|---|
| label documented | MNDWI > 0 | new label + its JRC agreement recorded | G4 |
| `train`/`val`/`test` IoU spread | not published | **≤ 0.15** | G5. `train ≈ test` is the leakage check `evaluate_roles` exists for |
| test IoU vs its own label | 0.3816 (vs MNDWI) | **≥ 0.70** if label = ★ | Distilling a consistent teacher should be easy; a low value means a *training* fault |
| predicted water fraction | — | **0.25 %–0.60 %** | Must bracket JRC's 0.373 %. Above 1 % is still over-detecting |
| framing | "weak supervision" | "distillation fidelity, not accuracy" | The honesty condition from §3 |

**Do not compare the new test IoU to 0.3816.** Different reference, different
quantity. Recording both with their references named is the correct output;
reporting an improvement from 0.38 to 0.7+ would be meaningless.

### Component C — susceptibility · nothing changed, so reproduce

| Metric | Baseline | Pass |
|---|---|---|
| `auc` | 0.7441 | 0.71–0.78 |
| `auc_vs_jrc_permanent_water` | 0.72 | 0.69–0.75 |

### Component D — buildings · the other component being changed

| Metric | Baseline | Pass | Rationale |
|---|---|---|---|
| `building_source` | absent | `"overture"` | If `"openstreetmap_overpass"`, the fallback fired — Overture failed, investigate |
| `building_count` | 463 | 10^4–10^5 | ~118 k over bbox, ~55 k in-district measured 2026-07-29 |
| `exposed_count` | **0** | **> 0** | Flood covers 0.21 % of area and buildings cluster near rivers; expect ~10^2–10^3. **Still 0 = the exposure intersection is broken**, which the 463-building version was too sparse to reveal |
| completeness flag | `severely_incomplete` (all 8) | see §7.3 | Must not silently upgrade |

### Component F, ★, decision layer

| Item | Pass |
|---|---|
| Component F | `iou` 0.50–0.62; the tautology caveat must survive |
| ★ (only with `--all-methods`) | `iou_vs_unet_labels` field renamed or its label named explicitly |
| **FPPS** | **±0.01 on every tambon; all 8 action classes identical** (G2) |
| Receipt | verifies; `area_count == 8`; `can_feed_decision_layer false` |

---

## 7. Predicted changes to published figures

Written before the run so they cannot be rationalised after it.

### 7.1 Will change, expected

| Field | From | To | Cause |
|---|---|---|---|
| `infrastructure.building_count` | 463 | ~10^5 | Overture |
| `infrastructure.exposed_count` | 0 | >0 | denser footprints intersect the flood mask |
| `infrastructure.building_source` | absent | `overture` | new provenance field |
| `water_unet.*` | vs MNDWI | vs new label | §3 decision |
| payload tier fields | absent | present | D-02 |
| `candidate_zonal_receipt.json` | absent | present | D-02 |

### 7.2 Must not change

`fpps_0_100`, `action_class`, `top_reason`, `confidence_class`, Component A
datetimes, Component C AUCs.

### 7.3 The trap: the completeness flag will silently upgrade

Measured while writing this plan:

```
district population (WorldPop)        81,798
implied buildings @ 4 people/bldg     20,450
OSM found                                397  -> ratio 0.019  severely_incomplete
Overture in-district                  54,978  -> ratio 2.69    usable
```

`osm_completeness` flags `severely_incomplete` when `ratio < 0.25` and `usable`
otherwise. **It has no upper bound.** Overture's 2.69 is 2.7x the
population-implied expectation and would be stamped `usable` — a *stronger*
claim than before, produced by swapping a data source, with nothing validated.

Overture includes ML-derived footprints, sheds and outbuildings, so 2.69 may be
over-counting rather than good coverage. **Required before this run publishes:**
add an upper bound (e.g. `ratio > 2.0` → `over_counted_review_needed`) or rename
the flag to reflect that it measures agreement-with-expectation in both
directions. Shipping `usable` on an unvalidated 2.69 is the kind of quiet
upgrade a reviewer should catch, and it would be ours to answer for.

---

## 8. Stop criteria

| Signal | Meaning | Action |
|---|---|---|
| FPPS moves at all | Building counts are feeding the score contrary to §2 | **Stop.** Do not publish. Trace the coupling |
| `building_source == "openstreetmap_overpass"` | Overture failed, fallback fired | Stop; a run mixing sources is not the run this plan describes |
| Component A fraction outside ±20 % | Acquisition changed | Stop; re-pin the scene pair |
| B's `train` IoU ≫ `test` IoU (>0.15) | Leakage returned | Stop; do not publish a B metric |
| `exposed_count` still 0 with 10^5 buildings | Exposure intersection is broken | Stop; that is a real bug the sparse layer was hiding |
| Receipt missing or fails verification | D-02 lane not actually engaged | Stop; the run has no provenance |
| Any suite red after regeneration | Regression | Stop; fix before publishing |

---

## 9. What gets promoted, and what does not

**Promoted to `outputs/geoai/` + `apps/web/public/geoai/`** — only if every G
criterion passes: metrics, priority CSV, receipt, previews, narratives, page.

**Stays in `research/`**: the label comparison sweeps in this plan, the OWM
diagnosis, any threshold experiments, the Overture GeoJSON.

**Not produced by this run**: in-area accuracy claims; anything with
`can_feed_decision_layer=true`; Component A2 or E; benchmark calibration (T2.3,
separate).

---

## 10. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Overture S3 fetch fails mid-run | Medium | High | `--fast` smoke first; cache to `work/buildings.json`; fallback is *stop*, not silent OSM |
| Sentinel-2 picks a different scene | Medium | High | Date range is fixed (`2024-01-15/2024-03-15`) but "least cloudy" could shift; assert `datetime` matches baseline (2024-02-18) or record the change |
| Overpass still down | High | None | Expected; Overture is primary now |
| 6.4 GB VRAM insufficient | Low | Medium | Measured 0.85 GB peak for B |
| Receipt key lost after run | Medium | Medium | Receipts verify only against the key that signed them — record the key id, store the key outside the repo |
| ★ needs `.venv-research` | Certain | Low | Only with `--all-methods`; out of scope here |
| Run partially completes | Medium | Medium | `outputs/geoai/` would be half-updated; `git checkout -- outputs/geoai` to restore |

---

## 11. Post-run verification

```powershell
# 1. Receipt verifies
python -c "import json;from floodguard.candidate_zonal_receipt import verify_candidate_zonal_receipt as v; import os; r=json.load(open('outputs/geoai/candidate_zonal_receipt.json')); print('verifies:', v(r, signing_key=bytes.fromhex(os.environ['FLOODGUARD_ZONAL_SIGNING_KEY_HEX'])), '| can_feed:', r['can_feed_decision_layer'])"

# 2. FPPS unchanged vs frozen baseline (G2)
python -c "import pandas as pd; a=pd.read_csv('docs/baseline/2026-07-30/geoai_subdistrict_priority.csv').set_index('subdistrict_id'); b=pd.read_csv('outputs/geoai/geoai_subdistrict_priority.csv').set_index('subdistrict_id'); d=(a['fpps_0_100']-b['fpps_0_100']).abs(); print('max |dFPPS| =', d.max()); print('action classes identical:', (a['action_class']==b['action_class']).all())"

# 3. Suites
services/geoai-runner/.venv/Scripts/python.exe -m pytest services/geoai-runner/tests -m "not geoai_smoke" -q
services/geoai-runner/.venv/Scripts/python.exe -m ruff check services/geoai-runner/geoai_runner services/geoai-runner/tests
.venv/Scripts/python.exe -m pytest tests/ -q
pnpm verify:frontend
```

Then write the run up in `research/MANIFEST.md` — **including any G criterion
that failed**. A run recorded as "mostly fine" is worth less than one recorded
with its two known problems named.

---

## 12. Outcome — executed 2026-07-30

The run completed all nine steps. **G1, G3, G4, G6, G7 passed.** Two criteria
were mis-specified by this plan and one is genuinely unmet; all three are
recorded below rather than adjusted away.

### 12.1 G2 was mis-specified — the old baseline was never one run

The first check failed with `max|dFPPS| = 3.39` and differing action classes.
That looked like the stop criterion firing. It was not a regression. Everything
the plan assumed would be constant *was* constant:

| Checked | Result |
| --- | --- |
| Sentinel-1 pair, repeated fetches | **byte-identical** (all four bands) |
| Copernicus DEM, three fetches | **byte-identical**, same two tiles |
| `real_sar_flood_extent` call and `drop_threshold_db` | unchanged at `b07bebd`, `095c39e`, `debe413`, HEAD |
| Aggregation threshold `sar_prob >= 0.5` | unchanged across all commits |
| Sub-district geometry | identical, 2,131 vertices both |
| River features | 1,925 both |

The cause was the reference. `git log` per artifact:

```
geoai_metrics.json              b07bebd  2026-07-23
extra_methods_metrics.json      095c39e  2026-07-24
geoai_subdistrict_priority.csv  debe413  2026-07-28
subdistricts.geojson            b07bebd  2026-07-23
geoai_component_summary.csv     b07bebd  2026-07-23
```

**The published evidence was assembled from at least three separate executions
across three commits.** No single run of any version of this pipeline would
produce that set together — which is why `dem_range_m` and `ai_flood_share`
differed while the code and inputs were provably identical.

This is a more serious finding than the regression it was mistaken for: the
project's published GeoAI evidence was not internally consistent, and nothing
detected it. The audit recorded that those figures were "not currently
reproducible"; they were also not *coherent*.

**Resolution.** The baseline is now `docs/baseline/2026-07-30-run1/` — one
execution, one receipt, one commit. `test_decision_layer_invariance.py` enforces
G2 against it from now on. G2 is not weakened; it is finally checkable.

### 12.2 G5 is genuinely unmet — correctness and evaluability conflict

`DEFAULT_MIN_POSITIVE = 2_000`. Measured positive counts per partition role:

| label | scene % | train | val | test | all roles scoreable |
| --- | --- | --- | --- | --- | --- |
| MNDWI > 0 (the wrong one) | 3.240 % | 6,842 | 4,210 | 9,363 | **yes** |
| NDWI > 0 | 0.872 % | 1,754 | 826 | 2,833 | no |
| **OmniWaterMask (best agreement)** | 0.325 % | **352** | **200** | 2,068 | no |

Role pixel counts are train 436,786 / val 121,115 / test 135,025.

**Only the demonstrably wrong label is dense enough to permit a leakage check —
and it is dense precisely because it over-detects by 8.7x.** So there is a
direct conflict between label correctness and metric evaluability at this scene
size and partition.

The label was not swapped back to manufacture a passing check. G5 is recorded
as **unmet**, and the artifact self-documents why: each blocked role carries
`blocked_reason: insufficient_positive_support` with `n_reference_positive` and
`min_positive_required`.

### 12.3 Component B does not learn from the correct label

Training longer made it worse, which settles the question:

| epochs | test IoU | precision | recall |
| --- | --- | --- | --- |
| 20 (`--fast`) | 0.2448 | 0.279 | 0.666 |
| **120 (default)** | **0.0023** | 0.0667 | **0.0024** |

With 352 positive pixels against 436,786, longer training drove the model to the
majority class. The 20-epoch figure is not better — it is under-fit. **Neither
number is a measurement**, in opposite directions.

`DEGENERATE_RECALL_FLOOR = 0.05` now flags this: a metric with recall below the
floor, or with no predicted positives at all, carries `degenerate: True` and a
reason. The numbers stay visible for diagnosis and cannot be read as accuracy.
Five tests pin the behaviour, including that merely *poor* precision is not
flagged — only collapse is.

### 12.4 What this means for Component B

Three options, in preference order. **This is a product decision, not a
technical one, and it is deliberately left open:**

1. **Fix evaluability, keep the correct label.** Stratify the block partition on
   JRC permanent water — an *independent* reference, not the training target — so
   each role receives comparable water. Defensible because it does not select
   blocks using the label. Moderate work in `blocks.py`, real risk to the
   holdout guarantees, needs its own verification.
2. **Enlarge the scene.** Positives scale with pixel count. At 4096x4096 the OWM
   label would clear the guard on all roles (~5,600 train / ~3,200 val), at 16x
   the compute and memory.
3. **Demote Component B from the MVP tier.** The evidence now supports this more
   strongly than when the run plan was written: the component cannot produce a
   defensible metric against a correct label with the current partition, and its
   only evaluable configuration is one that trains on a target known to be wrong.

Until one is chosen, Component B publishes a flagged degenerate metric with the
distillation caveat. That is honest, and it is not a result.

### 12.5 Criteria summary

| Criterion | Outcome |
| --- | --- |
| G1 receipt verifies, report-only | **PASS** |
| G2 FPPS invariance | **mis-specified** — baseline was incoherent; re-based, now enforced |
| G3 A / C reproduce | **PASS** — A flood fraction 0.0021 identical, C AUC within 0.0013 |
| G4 label documented | **PASS** — method, fraction, JRC ratio, sha256 all published |
| G5 leakage check | **UNMET** — train/val below the positive floor; reason published |
| G5b Component B test IoU | **FAIL, and recorded as the finding** — 0.0023, flagged `degenerate`. Not a build failure; see §12.3 |
| G5c predicted water fraction | **UNMET** — this plan asked for a field the pipeline does not publish. The `degenerate` flag detects the same failure mode, so this is filed as a follow-up rather than blocking the run |
| G6 Component D | **PASS** — overture, 118,050 footprints, 232 exposed, flag `over_expectation_review_needed` |
| G7 tier markers | **PASS** |
| G8 suites green | **PASS** |
| G9 every delta explained | **PASS** — §12.1–12.3 |
