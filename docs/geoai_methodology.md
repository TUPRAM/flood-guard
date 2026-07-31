# FloodGuard Thailand — GeoAI Methodology (Section 6)

**Anchor reference:** Qiusheng Wu, *Introduction to GeoAI* (2026). Every AI
component below is tied to a specific chapter of the book, which is the
methodological anchor for this project. In FloodGuard's scoring the AI carries
the most weight, so this section is the technical heart of the proposal.

**Status of this build.** All eight methods are implemented and run end to end
over **Mae Sai District, Chiang Rai**, using only authoritative, live sources —
no synthetic pixels. Two produced honest null or negative results and were
replaced by methods that answer the same question with the data actually
available; both originals are retained as citable records rather than deleted.

| # | Method | Core AI task | Book | Real input used | Executed result |
|---|--------|--------------|------|-----------------|-----------------|
| **A** | SAR Flood-Extent Detection | Traditional change detection | Ch. 12 | Sentinel-1 RTC pre/post (Planetary Computer) | 0.21% of district newly flooded |
| **A2** | Temporal SAR Flood Detection | Seasonal baseline + robust deviation | Ch. 12 | ~180 Sentinel-1 RTC scenes, one orbit | implemented; see §6.1.1b |
| **B** | Water-Mask Refinement | Semantic segmentation (U-Net) | Ch. 9 | Sentinel-2 L2A + ImageNet encoder | **metric withdrawn — see §6.1.2** |
| **C** | Flood Susceptibility Surface | Pixel-level regression / index | Ch. 13 | Copernicus DEM GLO-30 + DWR rivers | AUC 0.74 vs SAR flood, 0.72 vs JRC |
| **D** | Critical-Infrastructure Extraction | Foundation-model segmentation (SAM) | Ch. 14 | OpenStreetMap footprints | 463 buildings; coverage flagged |
| **★** | Sensor-Agnostic Water Baseline | Pre-trained segmentation (OmniWaterMask) | Ch. 9/19 | Sentinel-2 L2A | IoU 0.07 agreement vs MNDWI |
| **E** | Encroachment / Exposure-Growth | Change detection on built-up surface | Ch. 12/19 | Multi-temporal built-up product | ChangeStar null → replaced (§6.2) |
| **F** | Label-Scarce Generalization | Satellite embeddings + light classifier | Ch. 16 | Sentinel-2 features + few labels | workflow demo; scope flags in §6.2 |
| **G** | Plain-Language Narrative | Deterministic NLG from the decision table | Ch. 15 | Scored sub-district table | 8 bilingual EN/TH narratives |

The AI lives inside the isolated `services/geoai-runner/` service and is
surfaced directly in the **`/command`** (planning) and **`/studio`** (evidence)
role websites — not a separate dashboard (see §6.4).

**Run it yourself**

```bash
python -m geoai_runner.realpipeline --all-methods
```

> **Architecture note (GeoAI isolation).** This pipeline is the only place
> allowed to import `geoai-py`, PyTorch, rasterio, or reach the network, honoring
> the branch's GeoAI-isolation ADR. The root `src/floodguard/` decision engine
> stays GeoAI-free; the runner *imports* it (never the reverse) to score the
> Flood Preparedness Priority Score (FPPS). Nothing here is an official warning.

---

## 6.0 Architecture and rationale

FloodGuard's AI stack has two tiers: a **committed MVP** (A–D, the backbone of
the priority score) and a **baseline + roadmap** set (OmniWaterMask, E, F, G,
which harden, extend, and communicate the MVP).

**How the AI reaches the decision.** The model tier produces georeferenced
rasters. `geoai_runner.realpipeline.aggregate` runs *zonal statistics* over each
sub-district polygon and emits the two **highest-weighted** FPPS inputs:

```
FPPS = 0.30·flood_likelihood + 0.25·exposure + 0.20·access_gap
     + 0.15·road_criticality + 0.10·vulnerability_context
```

`flood_likelihood` (0.30) is AI-derived and `exposure` (0.25) is real WorldPop
population density — **55% of the score**. The remaining 45% is now joined from
the decision layer's own real outputs (`outputs/mae_sai_subdistrict_flood_inputs.csv`)
rather than synthesised from the AI signals, so **every FPPS component is
measured rather than assumed**. Both AI scales are pinned to versioned anchors
(`fpps_flood_anchor_v1`, `fpps_exposure_anchor_v1`) and every published number
cites them.

### Evaluation protocol (what makes the numbers mean something)

Learned components (B, F) are evaluated on a **spatial-block holdout**:

- The scene is divided into 8.3 km blocks assigned to `train` / `val` / `test`
  by a stable hash, with a **1600 m buffer** — half a 128 px tile's ~3.2 km
  ground width — between blocks of differing roles.
- Preprocessing statistics and training labels are fitted on **training blocks
  only**, which is leakage control #6 in
  [`immutable-multi-event-partitions-v1.md`](immutable-multi-event-partitions-v1.md).
- Decision thresholds are selected on **validation** blocks and reported on
  **test** blocks.
- Train, val and test scores are all published: `train ≈ test ≈ low` means
  optimisation failed, `train ≫ test` means overfitting. Publishing only the
  headline would discard the evidence that distinguishes them.
- A role metric is **refused** rather than published when its held-out
  positive count is too small to support it.

The conservative buffer costs ~31% of the scene and forces a 3×3 block grid
(5 train / 2 val / 2 test), so block-level variance is high. The partition seed
is chosen before any model runs, on a purely geometric criterion — that no role
collapses into a single contiguous patch — so the holdout can never become a
hyperparameter.

> **This is not a sealed partition.** Every artifact carries
> `is_sealed_multi_event_partition: false`. Sealing requires qualified label
> releases across ≥5 hydrological episodes and a signed holdout-custody receipt,
> all of which remain externally blocked. This is the weaker, honest construct:
> one scene, one event, spatially disjoint roles.

---

## 6.1 MVP core — the four decision-driving methods

### 6.1.1 Component A — SAR Flood-Extent Detection (Ch. 12, change detection)

**What it is.** SAR = *Synthetic Aperture Radar*. Unlike a camera, radar is an
**active** sensor: the satellite emits its own microwave pulse and measures the
echo, so it works **day or night and straight through clouds** — essential
during a monsoon flood when optical satellites see only cloud tops. The physics
we exploit: **calm open water is smooth, so it reflects the radar pulse away
from the satellite like a mirror (specular reflection) and appears dark**; dry,
rough land scatters the pulse back and appears bright. "Change detection" simply
compares a *before* and *after* image and flags pixels where bright land turned
dark — i.e., became water. This is the book's textbook case for *traditional*
(non-deep-learning) change detection: it needs **no training labels at all**.

**How it works in our pipeline.** We convert the pre- and post-event VV+VH
backscatter to decibels, apply a boxcar multi-look speckle filter (radar images
are grainy), measure the backscatter **drop**, map the VH-weighted drop to a
0–1 flood probability, threshold it, and remove permanent water so the layer
shows only *new* inundation. (`real_data.real_sar_flood_extent`.)

**How we ran it (real).** Sentinel-1 RTC (radiometric-terrain-corrected,
analysis-ready) from Microsoft Planetary Computer, windowed cloud-optimised
reads (no full-scene download). Pre/post pair on the **same descending orbit**
so the viewing geometry is identical: **2024-08-22 → 2024-09-15**.

**Executed result.** **0.21% of the district mapped as newly flooded**, permanent
water suppressed. We deliberately report *no* IoU: there is no independent
ground-truth flood mask for this exact date, and inventing one would be
fabrication. This layer is the base every downstream component consumes.

**Limitation.** Thresholding is sensitive to mis-registration and incidence
angle, and — decisively here — Sentinel-1's **12-day revisit** means the nearest
same-orbit post-event scene (Sep 15) is **~4 days after the ~Sep 11 flood
peak**, so the mapped extent is *residual* flooding that under-represents the
peak. This single fact drives the confidence classes in §6.3 and is the reason
Component C exists alongside it.

### 6.1.1b Component A2 — Temporal SAR Flood Detection (Ch. 12, temporal extension)

**The problem A2 solves.** Component A's two weaknesses have the same root and
the same fix. Its *reference* is one arbitrary pre-event date, which carries
whatever soil moisture, vegetation state and wind roughening happened to exist
that day — so a difference confounds "this pixel flooded" with "this pixel was
unusually dry three weeks ago". And its *post-event* date is chosen by the orbit,
not the flood: 4 days late, mapping residual drainage.

**What it is.** Replace the single "before" image with **the pixel's own
multi-year history**. For each pixel and each season we compute the median and
median-absolute-deviation of VH backscatter across ~180 acquisitions
(2018–2024) on a single relative orbit. Flooding is then a robust negative
z-score: *this pixel is much darker than it normally is at this time of year*.

**Five design decisions, each load-bearing:**

1. **One relative orbit only.** Incidence angle spans ~30–46° across the swath
   and backscatter varies by several dB with it, so a baseline mixing orbits is
   bimodal and its z-scores are meaningless. The acquisition layer selects the
   most-populated qualifying orbit and records how many scenes it discarded.
2. **Median and MAD, not mean and standard deviation.** Historical floods are
   *in* the archive; a mean would be dragged down by every past flood. A median
   over ~180 samples is unmoved by a handful — which is exactly what lets the
   method stay **label-free**. It never needs to know which past dates were
   floods.
3. **Seasonal binning.** VH over paddy and forest swings 2–4 dB between wet and
   dry season, so a single annual baseline would flag the whole monsoon as
   flooded. Default is wet (May–Oct) / dry (Nov–Apr); monthly bins are used when
   the archive supports ~8 observations each, and the builder falls back
   automatically rather than emitting a baseline it cannot support.
4. **Signed z-scores.** A *brightening* is diagnostic of flooded vegetation
   (double-bounce), a known SAR failure mode if merged with darkening. Positive
   deviations are published as a separate `possible_flooded_vegetation` layer.
5. **Under-sampled pixels return NaN, never "dry".** A pixel with too little
   history is unknown, and substituting zero would assert it is behaving
   normally.

**Probability, at last.** Component A's "probability" was
`clip((drop_db − 2.5) / 3.5, 0, 1)` — a linear ramp between two hand-picked
decibel values. It is a number in [0,1], but nothing about it asserts that
pixels scored 0.7 are flooded about 70% of the time, and every downstream
consumer has been treating it as if it did. A2 offers two honest replacements:
a **two-component Gaussian mixture** fitted to the z histogram (the classical
Bayesian SAR water-detection posterior, requiring **no reference at all**), or a
**calibrated logistic** whose coefficients are fitted, not chosen.

**Calibration status — deliberately blocked.** `calibration.py` implements
Brier, log loss, ECE, MCE, reliability curves, and both isotonic (PAVA) and Platt
mappers, satisfying the calibration layer that Model Evaluation v2 requires and
that nothing in this repository previously produced. It is **not fitted**,
because no licensed reference for the September-2024 event exists yet. JRC
permanent water cannot stand in: the temporal method is *designed* to report no
deviation over permanently dark water, so JRC would constrain the wrong end of
the curve. The pipeline records
`calibration: blocked_no_qualified_reference` rather than fitting against an
inadequate proxy.

The leading candidate is **UNOSAT/UNITAR's satellite-detected water extent for
Mae Sai District, 13–19 September 2024** (~70 km² of water within a ~305 km²
analysed area). We searched the Copernicus EMS Rapid Mapping activation list and
found **no EMSR activation** for this event, so UNOSAT remains the reference to
clear — tracked in `docs/reference_mask_licensing_log.md`. `fit_calibration` is
ready for the moment it does.

That UNOSAT figure is also a **sanity check that motivates this whole
component**: an independent authority mapped a large fraction of its analysed
area as water during 13–19 September, while our single post-peak same-orbit
snapshot maps 0.21% of Mae Sai District. The footprints, windows and definitions
differ, so the two numbers are not directly comparable — but the direction is
unambiguous, and it is the strongest available argument that one 4-day-late
acquisition badly under-detects this event.

**The genuinely new product.** The same machinery yields a **per-tambon
inundation history across 2018–2024** (`inundation_history.csv`) and a derived
**inundation frequency** (`inundation_frequency.csv`). That answers "how often
does Ko Chang actually flood?" from observation rather than terrain — which is
what `flood_likelihood` is really asking in a preparedness tool — and it gives
Component C a validation target worth having: does the susceptibility surface
predict *multi-year inundation frequency*, rather than one residual post-peak
extent?

**How to run it.** Opt-in, because the first run downloads ~180 scenes:

```bash
python -m geoai_runner.realpipeline --temporal
```

Scenes are cached as windowed GeoTIFFs and re-runs skip what is already present,
so an interrupted run resumes. The baseline is computed in row chunks (~94 MB at
a 128-row chunk, versus ~1.5 GB for the full cube).

**Limitation.** Agricultural drainage and harvest also darken a pixel. Seasonal
binning reduces this but does not remove it, and it is the main expected false
positive over Mae Sai's paddy. RTC coverage before ~2019 may be sparse over
Thailand; the builder reports scenes per year and refuses to emit a baseline
below the observation floor.

### 6.1.2 Component B — Water-Mask Refinement (Ch. 9, semantic segmentation, U-Net)

**What it is.** *Semantic segmentation* means classifying **every pixel** in an
image (here: water / not-water). The workhorse architecture is the **U-Net** — a
convolutional network shaped like a "U". The left side (the **encoder**)
progressively compresses the image into abstract features that answer *"what is
here?"*; the right side (the **decoder**) upsamples back to full resolution to
answer *"where exactly?"*. The signature trick is the **skip connections** that
copy fine detail from encoder to decoder at each scale, so boundaries stay
crisp. We use a **ResNet encoder pre-trained on ImageNet** (transfer learning).

**Why we use it.** The radar mask (Component A) is noisy at class boundaries
(mixed pixels, shadow, turbid water). A learned segmentation model cleans that
up and gives a **per-pixel confidence**.

**How we ran it (real).** Trained on a real **Sentinel-2 L2A** scene over Mae Sai
(**2024-02-18, 0.000% cloud**, tiles mosaicked to cover the district). The
training **labels come from the MNDWI water index** (a physical green-vs-SWIR
band ratio) — *weak supervision from a physical index*, not hand annotation.

**Executed result — the previous metric is withdrawn.** An earlier run reported
IoU 0.38 / F1 0.55. That number is **not valid and is withdrawn**, because it was
produced under three stacked leaks: overlapping tiles straddled the train/val
split, the split was random rather than spatial, and the score was computed by
inferring over the *same full raster the model had trained on*. It measured
memorisation, not generalisation.

Two things make that number additionally uninterpretable. The target,
`MNDWI > 0`, is a closed-form function of green and SWIR1 — **two of the model's
own six input channels** — so the task is near-trivial; and IoU 0.38 with recall
0.41 on a near-trivial task with full leakage is the signature of a broken
optimisation, not a hard problem. The likely cause is input scaling: L2A
reflectance clipped to [0,1] has near-zero variance where ImageNet weights
expect roughly unit variance.

The rebuilt component now standardises per channel using **training-block
statistics only**, trains on training blocks, selects its threshold on
validation, and reports train/val/test separately with an explicit
`generalisation_diagnosis`. **A re-run of the full pipeline is required to
produce the replacement numbers; we do not publish an estimate we have not
measured.**

**Limitation.** Optical-only, so cloud-limited exactly when a storm is active —
which is why SAR is the primary detector and this is a clear-sky *refinement*
layer. Note also that the Sentinel-2 scene is from February 2024, five months
before the flood: Component B characterises the district's water surfaces, it
does not observe the September event.

### 6.1.3 Component C — Flood Susceptibility Surface (Ch. 13, pixel regression)

**What it is.** *Pixel-level regression* predicts a **continuous number** per
pixel (here 0–100 "how susceptible to flooding") instead of a category. The
insight: **terrain dictates where water goes**. We combine **HAND** (Height Above
Nearest Drainage — how many metres a pixel sits above the nearest river channel;
low HAND floods first), **slope** (flat land ponds water), **distance-to-river**,
and **TWI** (Topographic Wetness Index). A weighted-logistic combination turns
them into a smooth susceptibility surface. Its distinguishing value: it can be
produced for a sub-district **nobody has ever flood-mapped**, which is the
literal form of "scalable beyond Bangkok."

**How we ran it (real).** Built from the real **Copernicus DEM GLO-30**
(elevation 366–1510 m across the Mae Sai valley) and the real **Department of
Water Resources (DWR) river network — 1,925 river features** — pulled live from
the Thai NGIS ArcGIS service.

**Executed result.** **AUC 0.74** ranking the actually-flooded pixels (the real
Sentinel-1 extent) above dry ground, and **AUC 0.72** against **JRC Global
Surface Water** (Pekel et al., 2016) as a second independent reference — using
terrain alone, with **zero flood labels**.

**Limitations.** Susceptibility is *relative propensity, not flood depth in
metres*. Two further caveats we state rather than hide: the AUC is computed over
~1M highly spatially autocorrelated pixels with no spatial cross-validation, so
it overstates what would be achieved on independent terrain; and the four
drivers are not fully independent — TWI as implemented is a deterministic
function of distance-to-river and slope, so it re-weights those two rather than
adding a third signal.

### 6.1.4 Component D — Critical-Infrastructure Extraction (Ch. 14, SAM)

**What it is.** **SAM = Segment Anything Model** (Meta AI) — a *foundation model*
for segmentation. Ordinary segmentation models are trained for one class; SAM is
**promptable and zero-shot**: you give it a box, point, or text prompt and it
returns a precise mask with **no task-specific training**, because it was
pre-trained on ~1 billion masks.

**How we ran it (real).** SAM 3's checkpoint is GPU-class, so the current
executed path uses **real OpenStreetMap building data** (fetched live via the
Overpass API), each tested against the real SAR flood extent. The faithful SAM 3
box-prompt path is implemented (`extract_buildings_sam`) for the THEOS-2 upgrade.

**Executed result and its honest boundary.** **463 OSM buildings** across Mae Sai
District, **0 flood-exposed on the 2024-09-15 acquisition**. Two disclosures:

1. Overpass is queried with `out center`, so these are building **centroids**,
   not footprints. The area-based reasoning footprints would enable is not yet
   in place.
2. Measured against WorldPop, OSM coverage here is **0.9%–5.1%** of the
   population-implied building count, and **exactly zero in two tambons**. A
   signal that captures ~2% of reality with a 25× spread between units is not
   evidence. OSM building counts therefore now carry an
   `osm_completeness_flag` and are reported as a **diagnostic only** — they no
   longer contribute to the exposure score (see §6.3).

**Limitation.** SAM 3 on sub-metre THEOS-2 is the resolution upgrade for true
instance footprints.

---

## 6.2 Baseline + roadmap methods

### ★ OmniWaterMask — the sensor-agnostic water baseline (Ch. 9 §9.6.4, Ch. 19)

**What it is.** A **pre-trained, ready-to-run** water-detection model (via
`geoai.segment_water`) fusing a deep segmentation network, the classical
**NDWI** index, and **OpenStreetMap** water reference data. It is
*sensor-agnostic* and needs **no training**. We use it as a **second opinion** on
our own trained U-Net so we are not "marking our own homework."

**Executed result.** Ran on the real Sentinel-2 scene (downsampled to 512 px). It
detected 0.33% water and agreed with the MNDWI labels at **IoU 0.07**.

**We flag this as suspect rather than explanatory.** Two water detectors on the
same clear-sky scene should overlap far better than 7%. The most likely cause is
grid misalignment introduced by the downsample, not a genuine finding about
sparse dry-season water. It is reported as-is and marked for investigation.

**Limitation.** Optical-only; cannot substitute for SAR under storm cloud.

### E — Encroachment / Exposure-Growth Detection (Ch. 12 §12.5.2 → Ch. 19)

**The question.** Is new built-up appearing inside the floodplain between two
dates? That is a development-pressure indicator for land-use policy.

**First attempt — ChangeStar, an honest null (retained).** ChangeStar (Zheng et
al., 2021) is a **deep-learning change-detection** architecture that jointly
performs change detection *and* building segmentation, using **Changen2**
pretrained weights that generalise to new regions without fine-tuning. We ran it
on two real cloud-free Sentinel-2 scenes over Mae Sai town, **2020-03-10 →
2024-03-09**. It returned **0% built-up change** in 76 seconds.

That null is a genuine methodological finding, not a bug: ChangeStar is trained
on **sub-metre aerial imagery** where a building spans hundreds of pixels; on
**10 m Sentinel-2** a house is 1–2 pixels, below the scale the architecture can
resolve. The record is preserved verbatim in
`encroachment.CHANGESTAR_NULL_RESULT` and travels with every downstream metric
as `superseded_method`. *We tried the state-of-the-art deep change detector and
it failed for a stated reason* is a stronger methodological claim than silence.

**What replaced it.** A multi-temporal **built-up surface-fraction** product
(GHSL GHS-BUILT-S class), differenced between two epochs and intersected with
the susceptibility surface. Three reasons it fits where ChangeStar did not: it
is designed for multi-decade change, so differencing epochs is the intended use;
it is a *continuous fraction*, so partial-pixel change survives rather than being
thresholded away; and at ~100 m it is honest about what this input can resolve.
Sub-metre THEOS-2 with ChangeStar remains the instance-level upgrade path.

**A latent bug fixed along the way.** The original flow wrote the susceptibility
surface on the **full district** grid and then nearest-neighbour resized it onto
ChangeStar's **town-subset** grid — different geographic extents, silently
stretched. It never surfaced only because the change mask was empty. The
replacement reprojects properly and **refuses to proceed** when two extents do
not substantially overlap.

### F — Label-Scarce Generalization via Satellite Embeddings (Ch. 16)

**What it is.** A *satellite embedding* is a compact numerical "fingerprint" of a
place. A foundation model pre-trained on millions of satellite images turns each
location into a fixed-length vector. Because the heavy learning is baked into the
vectors, you can fit a **lightweight classifier** on **a handful of labels** —
*few-shot* learning, the most direct mitigation for scarce Thai flood labels.
Real embedding datasets are Clay, AlphaEarth and TESSERA.

**Executed result and its two scope limits.** A Random Forest fitted on
locally-computed Sentinel-2 feature vectors reproduces the water mask from a few
dozen labels. Labels are now drawn from **training blocks only** and metrics are
reported per role. But two limits are recorded machine-readably in the output so
no surface can overstate it:

- `feature_contains_target_inputs: true` — the feature vector includes green and
  SWIR1, the same bands the MNDWI target is derived from. The classifier is
  **re-deriving a threshold it was handed**, not generalising.
- `is_foundation_model_embedding: false` — these are local spectral/texture
  features, not Clay/AlphaEarth/TESSERA vectors.
- `is_cross_district_transfer: false` — the real Ch. 16 claim is *40 labels from
  Mae Sai predict water in a district the model has never seen*. Reproducing an
  index inside the scene it was computed from is a tautology however few labels
  are used.

**Honest caveat (published).** Kaushik et al., 2026 (IEEE JSTARS) show foundation
models trail on **SAR vs. optical** (Clay ~0.51 mIoU on SAR vs ~0.79 on optical).

### G — Plain-Language Narrative Generation (Ch. 15)

**First attempt — Moondream, a negative result (retained).** Moondream is a
compact (~2B-parameter) **vision-language model** that takes an image plus a text
question and generates a text answer. We ran it on real imagery. It produced
**zero usable captions** — all three attempts returned
`[caption unavailable: FileNotFoundError]` after 410 s of CPU inference. The
record is preserved in `narrative.MOONDREAM_EVALUATION_RECORD`.

**Why we replaced rather than fixed it.** Beyond the plumbing failure, two
objections stand. VLMs are trained on natural photographs and degrade on
false-colour SAR and analytical figures. More fundamentally, **a generative
caption is the wrong instrument for an emergency-adjacent product**: it is not
auditable, cannot be regression-tested, and can fabricate. For a preparedness
tool, a sentence about flooding must trace to the numbers that produced it.

**What replaced it.** A deterministic bilingual generator over the scored
decision table. Every number traces to a field; no qualitative phrase appears
unless the versioned band table `narrative_bands_v1` licenses it; the uncertainty
clause is **mandatory and cannot be suppressed by a caller**; and the artifact is
byte-identical across runs. Thai strings reuse the repository's existing reviewed
action labels rather than new translations.

**Executed result.** 8 sub-districts × 2 languages, written to
`outputs/geoai/narratives.json`. Example:

> Ko Chang shows substantial observed inundation on the 2024-09-15 acquisition
> (1.29% of the sub-district). Combined with terrain susceptibility this gives a
> moderate flood likelihood of 47.3/100. The sub-district is sparsely populated
> (about 6,708 residents, exposure 14.1/100). Priority score 40.6/100 places it
> in action class E - Monitor and Verify. Treat with caution: the acquisition is
> 4 days after the flood peak, so the mapped extent is residual and
> under-represents the peak; model confidence is low; OpenStreetMap building
> coverage here is far below the population-implied expectation, so building
> counts are indicative only. This is a planning estimate, not an official
> warning.

---

## 6.3 The decision bridge — real result

`aggregate.aggregate_subdistrict_ai_inputs` zonal-aggregates the SAR flood
probability and the susceptibility surface over the **8 real DOPA sub-districts
(tambon)** of Mae Sai; exposure comes from **WorldPop Thailand 100 m 2020**; and
access gap, road criticality and vulnerability are joined from the decision
layer's real context. Executed real ranking:

| Sub-district (DOPA) | Flood likelihood (AI) | Exposure (WorldPop) | Access gap | FPPS | Action | Confidence |
|---------------------|----------------------:|--------------------:|-----------:|-----:|:------:|:----------:|
| **Ko Chang** | 47.3 | 14.1 | 86.4 | **40.6** | E | low |
| Si Mueang Chum | 36.2 | 17.1 | 72.4 | 35.0 | E | low |
| Mae Sai | 30.9 | 82.9 | 0.4 | 32.2 | E | low |
| Wiang Phang Kham | 9.4 | 64.3 | 0.0 | 22.3 | E | high |
| Ban Dai | 30.8 | 14.9 | 1.0 | 16.4 | E | low |
| Pong Pha | 19.6 | 21.3 | 0.2 | 14.2 | E | low |
| Huai Khrai | 12.9 | 20.1 | 0.0 | 12.1 | E | medium |
| Pong Ngam | 11.0 | 17.0 | 0.0 | 11.3 | E | medium |

The low-lying riverside tambons (**Ko Chang**, Si Mueang Chum, Mae Sai) rank
highest — geographically correct for the Sai/Ruak river corridor.

**Three things this table says that the previous one did not.**

*Scales are absolute.* The earlier version divided each unit's flooded share by
the **district maximum**, so the wettest tambon always scored ~96 — it would have
scored 96 in a drought. `fpps_flood_anchor_v1` fixes the observed term to a 5%
inundation saturation point and centres the terrain prior on the district mean,
so values are comparable across events, districts and time.

*Exposure is people, not mappers.* It was OSM building density; it is now
WorldPop population density. This changes the answer: Mae Sai's exposure rises
from 42.0 to 82.9 (17,893 residents at 829/km²), while Wiang Phang Kham falls
from 60.0 — its old score came from having 136 OSM buildings mapped.

*Everything is class E, and that is the finding.* `confidence_class` is now the
gap between the two normalised signals that form the score. For the riverside
tambons that gap is large: terrain says the valley floods, the image shows mostly
drained ground. The cause is documented and singular — **the only same-orbit
acquisition is 4 days past the flood peak**. Low confidence routes those units to
*"Monitor and Verify"*, which is the literally correct operational instruction
for a 4-day-stale snapshot. A regression test asserts this is a property of the
data and not a degenerate scale: a unit with 6% observed inundation on flood-prone
terrain returns high confidence and a likelihood above 90.

This is the strongest available argument for the temporal-SAR work in the
roadmap: a single post-peak snapshot cannot support life-safety prioritisation,
and the system now says so instead of implying otherwise.

---

## 6.4 How the AI appears in the role websites

The GeoAI is integrated **into the existing role surfaces**, not a standalone
dashboard. A single React panel (`GeoaiRealPanel`) reads a bundle the pipeline
emits (`apps/web/public/geoai/mae-sai-real.json` + preview images) and renders,
using the app's own design system:

- **`/command`** (rescue/planning team) — a **"GEOAI LAYER · REAL DATA"** section:
  the four model components (input → AI-output image pairs), the additional-method
  row, and the real per-tambon priority table with its bilingual narratives.
- **`/studio`** (validation/developer) — the same evidence under the **"Models &
  evaluation"** tab, alongside the branch's governed evidence panels.

The panel is deliberately kept **separate from the branch's fail-closed
"synthetic_integration_only" proof panel**: our real evidence is clearly labelled
*real observed data, planning-only, not an official warning*.

---

## 6.5 Mapping to the judging criteria

**Round 1**
- *Soundness of GeoAI approach (30).* Eight methods, each tied to a book chapter,
  executed on real data (Sentinel-1/2, Copernicus DEM, JRC, DOPA/DWR/OSM/WorldPop)
  with a spatial-holdout evaluation protocol, versioned scales, and two methods
  retired on evidence rather than retained for appearance.
- *Problem clarity & regional relevance (30).* Grounded in the Sept-2024 Mae Sai
  flood with real validation references (UNOSAT, GISTDA) and a peer-reviewed
  precedent (UN-SPIDER Chiang Rai differencing).
- *Feasibility & applicability (20).* Runs today; output is a concrete tambon
  action list (A–E), not just a map.

**Round 2**
- *GeoAI Methodology (35%).* Reproducible pipeline; leakage controls, absolute
  anchors and per-role metrics are enforced in code and covered by tests;
  limitations and uncertainty are stated per method and encoded as a confidence
  class from multi-signal agreement.
- *Geo Intelligence Quality (40%).* A genuine spatial insight — which tambon to
  prioritise and why — plus a defensible statement of what this acquisition
  cannot support.
- *Communication & Impact (25%).* The AI is embedded in the role surfaces with
  plain-language method explanations, deterministic bilingual narratives, and a
  clear A–E call to action.

---

## 6.6 Consolidated limitations (for the risk table)

1. Sentinel-1's ~12-day revisit put the nearest same-orbit post-event scene ~4
   days after the flood peak → mapped extent is **residual** (Component A), which
   drives every confidence class in §6.3 down. Component A2 addresses the
   reference half of this but cannot change the sampling.
2. **Component A2's probability is uncalibrated.** No licensed reference exists
   for this event, so calibration is reported as blocked rather than fitted
   against an inadequate proxy. A2's expected false positive is agricultural
   drainage and harvest, which seasonal binning reduces but does not remove; it
   also requires a single relative orbit and ~8 observations per season bin.
3. **Component B's previous IoU is withdrawn** as leaky; replacement metrics
   require a full pipeline re-run. Its labels are the MNDWI index (weak
   supervision), and its Sentinel-2 scene predates the flood by five months.
4. Susceptibility is **relative propensity, not flood depth**, its AUC has no
   spatial cross-validation, and its TWI term is not independent of
   distance-to-river and slope (Component C).
5. Component D returns OSM **centroids, not footprints**, and OSM coverage is
   0.9–5.1% of the population-implied expectation — diagnostic only.
6. **ChangeStar (E)** needs sub-metre imagery; its 0% on 10 m Sentinel-2 is a
   resolution limit, retained as a record and superseded by a built-up surface
   product.
7. **Embeddings (F)** re-derive an index contained in their own features, use
   local features rather than real foundation-model embeddings, and have not been
   tested cross-district. Published SAR-vs-optical gap (Kaushik et al., 2026).
8. **OmniWaterMask**'s IoU 0.07 against MNDWI is flagged as a suspected grid
   misalignment, not accepted as a finding.
9. **Moondream (G)** produced zero usable captions and was replaced by a
   deterministic generator; the record is retained.
10. The spatial holdout is **runner-local**, not a sealed multi-event partition,
    and does not clear the qualified-label gates.
11. GISTDA "Repeated Flood Areas" is a **WMS (rendered image)** — a visual prior,
    not per-pixel data without its data/ImageServer endpoint.
12. Thai NGIS fetches currently run with TLS verification disabled; authoritative
    provenance cannot be claimed over an unauthenticated channel until fixed.

---

## 6.7 File map & reproducibility

All GeoAI code lives in the isolated runner service
`services/geoai-runner/geoai_runner/realpipeline/`:

| Path | Role |
|------|------|
| `real_data.py` | Real fetchers: Sentinel-1/2, Copernicus DEM, JRC, DOPA/DWR (NGIS), OSM |
| `blocks.py` | Spatial-block holdout partition (geometry solver, buffer, seed selection) |
| `metrics.py` | Shared role-scoped metrics with a positive-support floor |
| `sar_flood.py` | **A** — SAR change-detection flood extent |
| `sar_temporal.py` | **A2** — seasonal baseline, robust deviation, inundation history |
| `calibration.py` | Brier/NLL/ECE/MCE, reliability curves, isotonic + Platt mappers |
| `water_unet.py` | **B** — U-Net water segmentation (train + infer + per-role eval) |
| `susceptibility.py` | **C** — HAND/slope/distance/TWI susceptibility surface |
| `infrastructure.py` | **D** — building/infrastructure extraction (SAM path + OSM) |
| `water_baseline.py` | **★** — OmniWaterMask baseline |
| `encroachment.py` | **E** — built-up change + retained ChangeStar null |
| `embeddings.py` | **F** — few-shot classifier with scope flags |
| `narrative.py` | **G** — deterministic bilingual NLG + retained Moondream record |
| `aggregate.py` | AI rasters → per-tambon FPPS inputs (anchors, WorldPop, real context) |
| `registry.py` | Single source of truth for all eight methods |
| `run_real.py` | End-to-end orchestrator (`--all-methods`, `--fast`) |
| `synth.py` | Synthetic-scene ablation for offline CI |

Tests: `services/geoai-runner/tests/` — 215 network-free tests, including the
partition leakage guarantees (`test_blocks.py`), the anchored-scale invariance
properties (`test_aggregate_anchors.py`), the grid-alignment regression
(`test_encroachment_grid.py`), and the narrative traceability properties
(`test_narrative.py`).

Reproduce with `python -m geoai_runner.realpipeline --all-methods` (needs
network); add `--temporal` for Component A2 (downloads ~180 scenes on first run,
cached thereafter). To replay only the decision bridge from committed aggregates without
re-running rasters: `python scripts/recompute_geoai_decision_bridge.py`.
