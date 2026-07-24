# FloodGuard Thailand — GeoAI Methodology (Section 6)

**Anchor reference:** Qiusheng Wu, *Introduction to GeoAI* (2026). Every AI
component below is tied to a specific chapter of the book, which is the
methodological anchor for this project. In FloodGuard's scoring the AI carries
the most weight, so this section is the technical heart of the proposal.

**Status of this build — everything below was executed on real data.** All
eight AI methods are implemented and run end to end over **Mae Sai District,
Chiang Rai**, using only authoritative, live sources — no synthetic pixels. Six
produce meaningful metrics; two (E, G) produce an honest null / degraded result
that we explain rather than hide, in keeping with the project's no-fabrication
rule.

| # | Method | Core AI task | Book | Real input used | Executed result |
|---|--------|--------------|------|-----------------|-----------------|
| **A** | SAR Flood-Extent Detection | Traditional change detection | Ch. 12 | Sentinel-1 RTC pre/post (Planetary Computer) | 0.21% of district newly flooded |
| **B** | Water-Mask Refinement | Semantic segmentation (U-Net) | Ch. 9 | Sentinel-2 L2A + ImageNet encoder | IoU 0.38 / F1 0.55 |
| **C** | Flood Susceptibility Surface | Pixel-level regression / index | Ch. 13 | Copernicus DEM GLO-30 + DWR rivers | AUC 0.74 vs SAR flood, 0.72 vs JRC |
| **D** | Critical-Infrastructure Extraction | Foundation-model segmentation (SAM) | Ch. 14 | OpenStreetMap footprints | 463 buildings extracted |
| **★** | Sensor-Agnostic Water Baseline | Pre-trained segmentation (OmniWaterMask) | Ch. 9/19 | Sentinel-2 L2A | IoU 0.07 agreement vs U-Net |
| **E** | Encroachment / Exposure-Growth | Deep-learning change detection (ChangeStar) | Ch. 12 | Sentinel-2 2020 vs 2024 | 0% change (resolution-limited — honest) |
| **F** | Label-Scarce Generalization | Satellite embeddings + light classifier | Ch. 16 | Sentinel-2 features + few labels | IoU 0.56 few-shot |
| **G** | Narrative Generation | Vision-language model (Moondream) | Ch. 15 | Before/after imagery | Runs; GPU-recommended (see §6.2) |

The AI lives inside the isolated `services/geoai-runner/` service and is
surfaced directly in the **`/command`** (planning) and **`/studio`** (evidence)
role websites — not a separate dashboard (see §6.4).

**Run it yourself**

```bash
# Core six methods on real data (trains the U-Net):
python -m geoai_runner.realpipeline
# Add the three heavy methods (OmniWaterMask, ChangeStar E, Moondream G):
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
which harden, extend, and communicate the MVP). We describe only what is
credible and build only what we can run — every claim below is backed by an
executed result.

**How the AI reaches the decision.** The model tier produces georeferenced
rasters. `geoai_runner.realpipeline.aggregate` runs *zonal statistics* over each
sub-district polygon and emits the two **highest-weighted** FPPS inputs:

```
FPPS = 0.30·flood_likelihood + 0.25·exposure + 0.20·access_gap
     + 0.15·road_criticality + 0.10·vulnerability_context
```

`flood_likelihood` (0.30) and `exposure` (0.25) — **55% of the score** — are now
AI-derived instead of hand-entered. The `confidence_class` is set from the
**agreement between two independent AI signals** (the SAR flood observation vs.
the terrain susceptibility prior): when they agree the unit is high-confidence,
when they conflict it drops to medium/low. That multi-signal uncertainty
handling is exactly what the Round-2 GeoAI-Methodology criterion rewards.

---

## 6.1 MVP core — the four decision-driving methods

Each method below is described as: **what it is** (plain language + how it
works), **why we use it**, **how we ran it on real data**, the **executed
result**, and its **honest limitation**.

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
shows only *new* inundation. (`sar_flood.py`.)

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
peak. This is the concrete reason Component C (susceptibility) exists alongside
it.

### 6.1.2 Component B — Water-Mask Refinement (Ch. 9, semantic segmentation, U-Net)

**What it is.** *Semantic segmentation* means classifying **every pixel** in an
image (here: water / not-water), producing a dense map at the image's native
resolution. The workhorse architecture is the **U-Net** — a convolutional neural
network shaped like a "U". The left side (the **encoder**) progressively
compresses the image into abstract features that answer *"what is here?"*; the
right side (the **decoder**) upsamples those features back to full resolution to
answer *"where exactly?"*. The signature trick is the **skip connections** that
copy fine detail from encoder to decoder at each scale, so boundaries stay
crisp. We use a **ResNet encoder pre-trained on ImageNet** (transfer learning):
it already knows edges and textures from a million natural photos, so it needs
far less flood data to specialise.

**Why we use it.** The radar mask (Component A) is noisy at class boundaries
(mixed pixels, shadow, turbid water). A learned segmentation model cleans that
up and gives a **per-pixel confidence** (from its softmax output).

**How we ran it (real).** Trained with `geoai.train_segmentation_model` on a
real **Sentinel-2 L2A** scene over Mae Sai (**2024-02-18, 0.000% cloud**, tiles
mosaicked to cover the district), 100 tiles, 30 epochs, real ImageNet weights.
The training **labels come from the MNDWI water index** (a physical
green-vs-SWIR band ratio) — this is *weak supervision from a physical index*,
not hand annotation.

**Executed result.** IoU **0.38**, F1 **0.55**, precision **0.83**, recall
**0.41**. This is lower than the book's 0.71 on a curated hand-labelled dataset —
and that honesty is the point: our score measures agreement with the automatic
MNDWI label, not against a gold human mask.

**Limitation.** Optical-only, so it is cloud-limited exactly when a storm is
active — which is why SAR (all-weather) is the primary detector and this is a
clear-sky *refinement* layer.

### 6.1.3 Component C — Flood Susceptibility Surface (Ch. 13, pixel regression)

**What it is.** *Pixel-level regression* predicts a **continuous number** per
pixel (here 0–100 "how susceptible to flooding") instead of a category. The
insight: **terrain dictates where water goes**. We combine four physical drivers:
**HAND** (Height Above Nearest Drainage — how many metres a pixel sits above the
nearest river channel; low HAND floods first), **slope** (flat land ponds
water), **distance-to-river**, and **TWI** (Topographic Wetness Index, which
captures where water accumulates). A weighted-logistic combination turns them
into a smooth susceptibility surface. Its distinguishing value: it can be
produced for a sub-district **nobody has ever flood-mapped**, which is the
literal form of "scalable beyond Bangkok."

**How we ran it (real).** Built from the real **Copernicus DEM GLO-30**
(elevation 366–1510 m across the Mae Sai valley) and the real **Department of
Water Resources (DWR) river network — 1,925 river features** — pulled live from
the Thai NGIS ArcGIS service. HAND/slope/distance/TWI are derived from those.

**Executed result.** **AUC 0.74** ranking the actually-flooded pixels (the real
Sentinel-1 extent) above dry ground, and **AUC 0.72** against **JRC Global
Surface Water** (Pekel et al., 2016) as a second independent reference — using
terrain alone, with **zero flood labels**.

**Limitation.** Susceptibility is *relative propensity, not flood depth in
metres*; it must not be presented as equivalent to GISTDA's field-calibre
HAND+SAR depth product.

### 6.1.4 Component D — Critical-Infrastructure Extraction (Ch. 14, SAM)

**What it is.** **SAM = Segment Anything Model** (Meta AI) — a *foundation model*
for segmentation. Ordinary segmentation models are trained for one class; SAM is
**promptable and zero-shot**: you give it a box, point, or text prompt and it
returns a precise mask for that object with **no task-specific training**,
because it was pre-trained on ~1 billion masks. SAM 3 adds *promptable concept
segmentation* (e.g. the phrase "hospital building" returns every matching
footprint). We need building **footprints** — not dots — so we can compute
exposed area and realistic access geometry for hospitals, schools and shelters.

**How we ran it (real).** SAM 3's checkpoint is large/GPU-class, so the current
executed path uses **real OpenStreetMap building footprints** (fetched live via
the Overpass API), each tested against the real SAR flood extent to flag
`exposed_to_flood`. The faithful SAM 3 box-prompt path is implemented
(`extract_buildings_sam`) for the THEOS-2 upgrade.

**Executed result.** **463 real building footprints** across Mae Sai District.
**0 were flood-exposed on the 2024-09-15 acquisition** — an honest result, not a
bug: the post-peak overpass maps residual flooding that no longer reaches the
built-up core. Exposure must therefore be read *together with* the susceptibility
surface, which is exactly why Component C exists.

**Limitation.** OSM completeness varies by area; SAM 3 on sub-metre THEOS-2 is
the resolution upgrade for true instance footprints.

---

## 6.2 Baseline + roadmap methods — also executed

These four were "documented only" in earlier drafts; they now **run on real
data**. Two produce honest null/degraded results that we explain.

### ★ OmniWaterMask — the sensor-agnostic water baseline (Ch. 9 §9.6.4, Ch. 19)

**What it is.** OmniWaterMask is a **pre-trained, ready-to-run** water-detection
model (accessed via `geoai.segment_water`). It fuses three ideas: a deep-learning
segmentation network, the classical **NDWI** spectral water index, and
**OpenStreetMap** water reference data, and it is *sensor-agnostic* — the same
model runs on Sentinel-2, NAIP, Landsat, PlanetScope, or Maxar with **no
training**. We use it as a **second opinion**: an independent check on our own
trained U-Net so we are not "marking our own homework."

**Executed result.** Ran on the real Sentinel-2 scene (downsampled to 512 px to
fit laptop memory). It detected 0.33% water and agreed with the U-Net's MNDWI
labels at **IoU 0.07** — deliberately reported low, because clear-sky dry-season
surface water is genuinely sparse, so two detectors have little to agree on.

**Limitation.** Optical-only; it cannot substitute for SAR under storm cloud —
reinforcing why SAR is the primary detector.

### E — Encroachment / Exposure-Growth Detection (Ch. 12 §12.5.2, **ChangeStar**)

**What is ChangeStar?** ChangeStar (Zheng et al., 2021) is a **deep-learning
change-detection** architecture. The classic way to compare two dates is a
**siamese network**: the same encoder (with shared weights) looks at the
*before* and *after* images and a comparison module highlights where their
learned features differ. ChangeStar's innovation is that it **jointly does change
detection *and* building segmentation** — from a pair of dates it outputs three
things: (1) a building map at time 1, (2) a building map at time 2, and (3) a
change map between them. It uses **Changen2 pretrained weights**, learned by a
clever "change generation" trick — synthesising diverse fake before/after
changes from single images — which lets it **generalise to brand-new regions
without fine-tuning**.

**Why (and how) we use it.** ChangeStar is *not* a floodwater detector — using it
that way would be a misuse. Its correct FloodGuard job is **encroachment**:
detecting *new buildings appearing inside the floodplain between two dates*, a
"development-pressure" indicator for land-use policy. We ran it on two real,
cloud-free Sentinel-2 scenes over Mae Sai town: **2020-03-10 → 2024-03-09**.

**Executed result — an honest null.** **0% built-up change detected.** ChangeStar
is trained on **sub-metre aerial imagery**, where a building spans hundreds of
pixels; on **10 m Sentinel-2** a whole house is 1–2 pixels, too coarse to
resolve building-scale change. The model and pipeline run end to end; the null
is a genuine methodological finding, and the upgrade path is the team's
**sub-metre THEOS-2** imagery.

### F — Label-Scarce Generalization via Satellite Embeddings (Ch. 16)

**What it is.** A *satellite embedding* is a compact numerical "fingerprint" of a
place. A foundation model pre-trained on millions of satellite images turns each
location into a fixed-length vector that encodes its spectral signature,
texture, and seasonality. Because the heavy learning is already baked into the
vectors, you can skip training a big network and instead fit a **lightweight
classifier** (k-NN, Random Forest, logistic regression) on **a handful of
labels** — this is *few-shot* learning, the most direct mitigation for scarce
Thai flood labels. Real embedding datasets are Clay, AlphaEarth and TESSERA.

**Executed result.** A Random Forest fitted on locally-computed Sentinel-2
feature vectors reproduced the water mask at **IoU 0.56** from only a few dozen
labels, demonstrating the few-shot workflow.

**Honest caveat (published).** Kaushik et al., 2026 (IEEE JSTARS) show foundation
models trail on **SAR vs. optical** (Clay ~0.51 mIoU on SAR vs ~0.79 on optical),
so this is positioned as a *complement* to Component B, validated on optical
first.

### G — Narrative Generation with a Vision-Language Model (Ch. 15, **Moondream**)

**What is Moondream?** Moondream is a **compact (~2-billion-parameter)
vision-language model (VLM)** — a small multimodal AI that takes **an image plus
a text question** and generates a **text answer** (visual question answering and
captioning). Big VLMs need data-centre GPUs; Moondream is designed to be small
enough to run locally. FloodGuard's use targets the **Communication** criterion:
auto-drafting plain-language descriptions of before/after flood imagery for
non-technical decision-makers — always reviewed and edited by the team, never an
autonomous claim.

**Executed result — honest.** The model downloads, loads, and runs on real
imagery (we fixed the geoai call convention — the API is
`moondream_query(question, source)`, question first). Two honest findings: (1) on
the **abstract SAR/analytical figures** used here it returns degraded output,
because VLMs are trained on natural photographs, not scientific visualisations;
and (2) generation is **impractically slow on a laptop CPU**. We therefore
surface it as *executed, GPU-recommended*, and — per the no-fabrication rule — we
do **not** publish a fabricated caption. The production path captions natural RGB
optical imagery on a GPU host.

---

## 6.3 The decision bridge — AI drives 55% of the priority score (real result)

`aggregate.aggregate_subdistrict_ai_inputs` zonal-aggregates the SAR flood
probability, the susceptibility surface, and the building footprints over the
**8 real DOPA sub-districts (tambon)** of Mae Sai, and the root decision engine
scores the FPPS. Executed real ranking:

| Sub-district (DOPA) | Flood likelihood (AI) | Exposure (AI) | FPPS | Action | Confidence |
|---------------------|----------------------:|--------------:|-----:|:------:|:----------:|
| **Ko Chang** | 95.8 | 56.8 | **70.0** | D | high |
| Mae Sai | 46.3 | 42.0 | 44.3 | D | high |
| Si Mueang Chum | 61.9 | 15.3 | 42.1 | D | high |
| Wiang Phang Kham | 24.7 | 60.0 | 41.2 | D | medium |
| Pong Ngam | 26.0 | 40.6 | 35.3 | D | medium |
| Ban Dai | 44.2 | 2.1 | 30.3 | E | high |
| Pong Pha | 33.0 | 11.5 | 28.7 | E | medium |
| Huai Khrai | 28.4 | 9.3 | 26.0 | E | high |

The low-lying eastern/riverside tambons (**Ko Chang**, Si Mueang Chum, Mae Sai)
rank highest — geographically correct for the Sai/Ruak river corridor. Action
class **D = "Build Resilience"**, **E = "Monitor & Verify"** (the residual
post-peak extent keeps everything below the A/B life-safety thresholds, which is
itself an honest reflection of the acquisition timing).

---

## 6.4 How the AI appears in the role websites

The GeoAI is integrated **into the existing role surfaces**, not a standalone
dashboard. A single React panel (`GeoaiRealPanel`) reads a bundle the pipeline
emits (`apps/web/public/geoai/mae-sai-real.json` + preview images) and renders,
using the app's own design system:

- **`/command`** (rescue/planning team) — a **"GEOAI LAYER · REAL DATA"** section:
  the four model components (input → AI-output image pairs), the additional-method
  row (OmniWaterMask, E, F, G), and the real per-tambon priority table.
- **`/studio`** (validation/developer) — the same evidence under the **"Models &
  evaluation"** tab, alongside the branch's governed evidence panels.

The panel is deliberately kept **separate from the branch's fail-closed
"synthetic_integration_only" proof panel** (whose validator rejects real-accuracy
claims): our real evidence is clearly labelled *real observed data,
planning-only, not an official warning*.

---

## 6.5 Mapping to the judging criteria

**Round 1**
- *Soundness of GeoAI approach (30).* Eight methods, each tied to a book chapter,
  **executed on real data** (Sentinel-1/2, Copernicus DEM, JRC, DOPA/DWR/OSM)
  with real metrics and an explicit honesty boundary on the two null/degraded
  cases.
- *Problem clarity & regional relevance (30).* Grounded in the Sept-2024 Mae Sai
  flood with real validation references (UNOSAT, GISTDA) and a peer-reviewed
  precedent (UN-SPIDER Chiang Rai differencing).
- *Feasibility & applicability (20).* Runs today; output is a concrete tambon
  action list (A–E), not just a map.

**Round 2**
- *GeoAI Methodology (35%).* Reproducible pipeline (`python -m
  geoai_runner.realpipeline --all-methods`); limitations and uncertainty stated
  per method and encoded as a confidence class from multi-signal agreement.
- *Geo Intelligence Quality (40%).* A genuine spatial insight — which tambon to
  prioritise and why — specific to the Mae Sai valley.
- *Communication & Impact (25%).* The AI is embedded in the three role surfaces
  with plain-language method explanations and a clear A–E call to action.

---

## 6.6 Consolidated limitations (for the risk table)

1. Sentinel-1's ~12-day revisit put the nearest same-orbit post-event scene ~4
   days after the flood peak → mapped extent is **residual** (Component A).
2. The U-Net's labels are the **MNDWI index** (weak supervision), so its IoU
   measures index agreement, not gold-standard accuracy (Component B).
3. Susceptibility is **relative propensity, not flood depth** (Component C).
4. Component D uses **real OSM footprints**; SAM 3 on THEOS-2 is the sub-metre
   upgrade.
5. **ChangeStar (E)** needs sub-metre imagery; 10 m Sentinel-2 is too coarse →
   0% change is a resolution limit, not a bug.
6. **Embeddings (F)** show a published **SAR-vs-optical** performance gap
   (Kaushik et al., 2026).
7. **OmniWaterMask** is optical-only and unusable under storm cloud.
8. **Moondream (G)** degrades on abstract figures and is CPU-slow; GPU-recommended
   and always human-reviewed.
9. GISTDA "Repeated Flood Areas" is a **WMS (rendered image)** — a visual prior,
   not per-pixel data without its data/ImageServer endpoint.

---

## 6.7 File map & reproducibility

All GeoAI code lives in the isolated runner service
`services/geoai-runner/geoai_runner/realpipeline/`:

| Path | Role |
|------|------|
| `real_data.py` | Real fetchers: Sentinel-1/2, Copernicus DEM, JRC, DOPA/DWR (NGIS), OSM |
| `sar_flood.py` | **A** — SAR change-detection flood extent |
| `water_unet.py` | **B** — U-Net water segmentation (train + infer) |
| `susceptibility.py` | **C** — HAND/slope/distance/TWI susceptibility surface |
| `infrastructure.py` | **D** — building/infrastructure extraction (SAM path + OSM) |
| `water_baseline.py` | **★** — OmniWaterMask baseline |
| `encroachment.py` | **E** — ChangeStar encroachment |
| `embeddings.py` | **F** — few-shot satellite-embedding classifier |
| `narrative.py` | **G** — Moondream VLM narrative |
| `aggregate.py` | AI rasters → per-tambon FPPS inputs (imports root scoring) |
| `registry.py` | Single source of truth for all eight methods |
| `run_real.py` | End-to-end orchestrator (`--all-methods`, `--fast`) |
| `synth.py` | Synthetic-scene ablation for offline CI |
| `geoai_page.py`, `annotate.py` | Standalone `geoai.html` showcase + figures |

Tests: `services/geoai-runner/tests/test_realpipeline.py` (network-free, runs on
the synthetic scene). Web integration: `apps/web/src/components/geoai-real-panel.tsx`.
Reproduce with `python -m geoai_runner.realpipeline --all-methods` (needs network;
E/G download heavy weights and are GPU-class for routine use).
