"""Single source of truth for the FloodGuard GeoAI component catalogue.

Both the proposal document and the dashboard's AI page are generated from this
registry, so the story stays consistent everywhere. Each entry maps a FloodGuard
AI component to its anchor chapter in *Introduction to GeoAI* (Wu, 2026), its
core AI task, its tier (committed MVP vs gated roadmap), the run status in this
build, the artifacts it emits, and the judging criteria it targets.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GeoAIComponent:
    key: str
    letter: str
    name: str
    ai_task: str
    book_ref: str
    tier: str  # "MVP" | "Roadmap" | "Baseline"
    status: str  # "runnable" | "runnable-fallback" | "documented"
    architecture: str
    inputs: str
    output_artifact: str
    feeds_into: str
    criteria: tuple[str, ...]
    plain_language: str = ""
    limitations: str = ""
    metrics: dict = field(default_factory=dict)


COMPONENTS: tuple[GeoAIComponent, ...] = (
    GeoAIComponent(
        key="sar_flood",
        letter="A",
        name="SAR Flood-Extent Detection",
        ai_task="Traditional change detection (image differencing on SAR backscatter)",
        book_ref="Ch. 12, Sec. 12.3-12.4",
        tier="MVP",
        status="runnable",
        architecture="Pre/post Sentinel-1 VV+VH dB-drop -> logistic probability -> threshold",
        inputs="Sentinel-1 GRD pre/post pair (VV+VH), permanent-water/HAND mask",
        output_artifact="flood_extent_binary.tif + flood_extent.geojson",
        feeds_into="Priority score (flood likelihood), road-disruption overlay",
        criteria=("Problem Clarity", "GeoAI Approach"),
        plain_language=(
            "Radar sees through monsoon cloud. Open water reflects radar away from "
            "the satellite, so flooded ground suddenly looks dark. We compare a "
            "before image to an after image and flag the pixels that darkened."
        ),
        limitations=(
            "Thresholding is sensitive to mis-registration, incidence angle, and "
            "urban double-bounce; a HAND / permanent-water mask suppresses false "
            "positives (book Sec. 12.3.2)."
        ),
    ),
    GeoAIComponent(
        key="temporal_sar",
        letter="A2",
        name="Temporal SAR Flood Detection",
        ai_task="Per-pixel seasonal baseline + robust deviation (unsupervised)",
        book_ref="Ch. 12, Sec. 12.3-12.4 (temporal extension)",
        tier="Roadmap",
        status="runnable",
        architecture=(
            "Per-pixel, per-season median and MAD over a multi-year single-orbit "
            "Sentinel-1 stack; flood = robust negative z-score; probability from a "
            "two-component Gaussian mixture on the z histogram (reference-free) or "
            "a calibrated logistic"
        ),
        inputs="~180 Sentinel-1 RTC acquisitions on one relative orbit (2018-2024)",
        output_artifact=(
            "temporal_flood_probability.tif + inundation_history.csv + "
            "inundation_frequency.csv"
        ),
        feeds_into=(
            "Supersedes Component A's single pre/post pair once validated; supplies "
            "multi-year inundation frequency as a real validation target for Component C"
        ),
        criteria=("GeoAI Approach", "Geo Intelligence Quality"),
        plain_language=(
            "Instead of comparing one before-image to one after-image, compare each "
            "pixel to what it normally looks like at this time of year across seven "
            "years. Water shows up as an unusual darkening against the pixel's own "
            "history, and the same machinery answers how often each tambon floods."
        ),
        limitations=(
            "Requires a single relative orbit: mixing orbits mixes incidence angles "
            "and makes the baseline bimodal. Needs ~8 observations per season bin, so "
            "monthly binning falls back to wet/dry on short archives. Agricultural "
            "drainage and harvest also darken a pixel; seasonal binning reduces but "
            "does not eliminate that false positive. Under-sampled pixels return NaN "
            "rather than 'dry'. Probability is currently uncalibrated: no licensed "
            "reference exists for the Sept-2024 event, so calibration is reported as "
            "blocked rather than fitted against an inadequate proxy."
        ),
    ),
    GeoAIComponent(
        key="water_unet",
        letter="B",
        name="Water-Mask Refinement",
        ai_task="Semantic segmentation (U-Net, ResNet encoder)",
        book_ref="Ch. 9, Sec. 9.6.1-9.6.3",
        tier="MVP",
        status="runnable",
        architecture="U-Net + ResNet encoder, class-weighted cross-entropy, 2 classes",
        inputs="Sentinel-2 L2A 6-band composite (B2/B3/B4/B8/B11/B12)",
        output_artifact="water_mask_refined.tif + water_mask_probability.tif + water_bodies.geojson",
        feeds_into="Confidence classes; cleaned water boundaries",
        criteria=("GeoAI Approach",),
        plain_language=(
            "A neural network learns the spectral fingerprint of water and cleans up "
            "the noisy radar mask, giving smooth water-body outlines with a "
            "per-pixel confidence score."
        ),
        limitations=(
            "Optical only, so cloud-limited during active storms -- the monsoon "
            "scenes over Mae Sai are heavily clouded, which is precisely why SAR "
            "is the primary all-weather detector and this is a clear-sky "
            "refinement layer. Labels are derived from the MNDWI water index "
            "(weak supervision from a physical index, not hand annotation), so "
            "metrics measure agreement with that index rather than gold-standard "
            "accuracy. Metrics are reported per partition role on spatially "
            "disjoint blocks with a 1600 m buffer; the headline is the held-out "
            "test role. The conservative buffer costs ~31% of the scene and "
            "forces a 3x3 block grid, so block-level variance is high. This is a "
            "runner-local split, NOT a sealed multi-event partition."
        ),
    ),
    GeoAIComponent(
        key="susceptibility",
        letter="C",
        name="Flood Susceptibility Surface",
        ai_task="Pixel-level regression / physical index",
        book_ref="Ch. 13 (full chapter)",
        tier="MVP",
        status="runnable",
        architecture="Weighted logistic HAND/slope/distance/TWI index; optional U-Net pixel regressor",
        inputs="HAND, slope, distance-to-river, TWI (from DEM + hydrology)",
        output_artifact="flood_susceptibility.tif",
        feeds_into="Priority score (new city-agnostic likelihood layer)",
        criteria=("Feasibility", "GeoAI Approach"),
        plain_language=(
            "Even where no flood has been mapped, terrain tells you where water will "
            "go: low ground near rivers floods first. This produces a 0-100 "
            "susceptibility surface for any subdistrict, including ones never "
            "analyst-mapped."
        ),
        limitations=(
            "Susceptibility is relative propensity, not flood depth in metres; the "
            "learned regressor targets JRC Global Surface Water Recurrence (no manual "
            "labels), a multi-decade presence signal, not a depth product."
        ),
    ),
    GeoAIComponent(
        key="infrastructure",
        letter="D",
        name="Critical-Infrastructure Extraction",
        ai_task="Foundation-model / instance segmentation (SAM 3)",
        book_ref="Ch. 14, Sec. 14.7",
        tier="MVP",
        status="runnable-fallback",
        architecture="Real OSM footprints (current) | SAM 3 box-prompt zero-shot on THEOS-2 (upgrade) | impervious-threshold vectoriser (offline fallback)",
        inputs="OpenStreetMap building footprints; high-resolution optical (THEOS-2) + OSM POI boxes for the SAM upgrade",
        output_artifact="critical_infrastructure_footprints.geojson",
        feeds_into="Exposed-facility layer, shelter capacity vs demand",
        criteria=("Feasibility", "Communication"),
        plain_language=(
            "To know who is cut off, we need building outlines, not dots. A "
            "foundation model turns a hospital or school prompt into a precise "
            "footprint; each footprint is then flagged if it sits inside the flood."
        ),
        limitations=(
            "OpenStreetMap coverage in Mae Sai is 0.9-5.1% of the population-implied "
            "building expectation and exactly zero in two tambons, so building counts "
            "are a diagnostic with an explicit completeness flag and no longer enter "
            "the exposure score -- exposure is WorldPop 2020 population density "
            "instead. Exposure-to-flood is counted against the observed SAR extent, so "
            "a post-peak acquisition (as on 2024-09-15) can report zero exposed "
            "structures even where buildings sit in the floodplain; read it with the "
            "susceptibility surface. SAM 3 on THEOS-2 is the resolution upgrade."
        ),
    ),
    GeoAIComponent(
        key="omniwatermask",
        letter="*",
        name="Sensor-Agnostic Water Baseline (OmniWaterMask)",
        ai_task="Pre-trained segmentation (inference only)",
        book_ref="Ch. 9, Sec. 9.6.4; Ch. 19",
        tier="Baseline",
        status="runnable",
        architecture="geoai.segment_water() wrapping OmniWaterMask (DL + NDWI + OSM)",
        inputs="Sentinel-2 / NAIP / Landsat (optical)",
        output_artifact="water_mask_baseline.tif (online)",
        feeds_into="Sanity-check baseline for Component B",
        criteria=("GeoAI Approach",),
        plain_language=(
            "A zero-training reference model to check our trained U-Net against, so "
            "we are not marking our own homework."
        ),
        limitations=(
            "Optical-only and needs pretrained weights downloaded; cannot substitute "
            "for SAR during a cloud-covered active storm. Documented, not run offline."
        ),
    ),
    GeoAIComponent(
        key="encroachment",
        letter="E",
        name="Encroachment / Exposure-Growth Detection",
        ai_task="Change detection on a multi-temporal built-up surface product",
        book_ref="Ch. 12, Sec. 12.5.2; Ch. 19",
        tier="Roadmap",
        status="runnable",
        architecture=(
            "Built-up surface-fraction differencing (GHSL GHS-BUILT-S class product) "
            "intersected with the susceptibility surface. Replaces ChangeStar "
            "(Changen2 weights), which executed but returned a resolution-limited "
            "0% null on 10 m Sentinel-2; that result is retained as "
            "encroachment.CHANGESTAR_NULL_RESULT."
        ),
        inputs="Two epochs of a multi-temporal built-up surface product (~100 m)",
        output_artifact="builtup_growth.tif + encroachment_floodplain_growth.tif",
        feeds_into="Development-pressure indicator for policy narrative",
        criteria=("Communication", "GeoAI Approach"),
        plain_language=(
            "Measures where built-up surface grew between two dates and how much of "
            "that growth landed inside the floodplain -- a development-pressure "
            "signal for land-use policy."
        ),
        limitations=(
            "This detects built-up change, not floodwater; scope is strictly "
            "encroachment. At ~100 m it measures neighbourhood-scale growth, not "
            "individual buildings. ChangeStar on sub-metre THEOS-2 remains the "
            "instance-level upgrade path; on 10 m Sentinel-2 it is below the scale "
            "the architecture can resolve."
        ),
    ),
    GeoAIComponent(
        key="embeddings",
        letter="F",
        name="Label-Scarce Generalization (Satellite Embeddings)",
        ai_task="Foundation-model embeddings + lightweight classifier",
        book_ref="Ch. 16 (full chapter)",
        tier="Roadmap",
        status="runnable-fallback",
        architecture="Precomputed embeddings (Clay/AlphaEarth/TESSERA) + kNN/RF/logreg",
        inputs="Precomputed embeddings per location + a handful of labels",
        output_artifact="flood_classifier_embeddings.parquet",
        feeds_into="Rapid re-training as new labels arrive",
        criteria=("Feasibility",),
        plain_language=(
            "Instead of retraining a big network per city, we reuse a foundation "
            "model's compact 'fingerprint' per location and fit a tiny classifier on "
            "only a few labels."
        ),
        limitations=(
            "Two limits, both machine-readable in the metrics. (1) The local feature "
            "vector contains green and SWIR1, the same bands the MNDWI target is "
            "derived from, so the classifier re-derives an index it was handed rather "
            "than generalising (`feature_contains_target_inputs=True`). (2) These are "
            "not foundation-model embeddings; real Clay/AlphaEarth/TESSERA vectors "
            "require download (`is_foundation_model_embedding=False`). Labels are now "
            "drawn only from training blocks and the headline is the held-out test "
            "role, but the Ch. 16 claim needs real embeddings evaluated on a "
            "different district (`is_cross_district_transfer=False`). Published "
            "benchmark (Kaushik et al., 2026, IEEE JSTARS) shows foundation models "
            "trail on SAR vs optical."
        ),
    ),
    GeoAIComponent(
        key="narrative",
        letter="G",
        name="Plain-Language Narrative Generation",
        ai_task="Deterministic natural-language generation from the decision table",
        book_ref="Ch. 15, Sec. 15.7-15.8",
        tier="Roadmap",
        status="runnable",
        architecture=(
            "Versioned template generator (narrative_bands_v1) over the scored "
            "sub-district table, bilingual EN/TH. Replaces Moondream "
            "(vikhyatk/moondream2), which executed but returned zero usable "
            "captions; that result is retained as "
            "narrative.MOONDREAM_EVALUATION_RECORD."
        ),
        inputs="Scored sub-district decision table (flood, exposure, FPPS, action class)",
        output_artifact="narratives.json (EN/TH per sub-district)",
        feeds_into="Role-surface story tiles and action briefs (Communication criterion)",
        criteria=("Communication",),
        plain_language=(
            "Writes a plain-language paragraph per sub-district in Thai and English, "
            "assembled from the decision numbers so every clause traces to a field."
        ),
        limitations=(
            "Not a generative model: it cannot describe anything outside the "
            "decision table, which is the point -- every number traces to a field "
            "and every qualitative phrase is licensed by a versioned band table, so "
            "the text cannot fabricate. The uncertainty clause is mandatory and "
            "cannot be suppressed. A vision-language model was evaluated first and "
            "rejected: it returned no usable caption, degrades on false-colour SAR "
            "and analytical figures, and its output is not auditable."
        ),
    ),
)


def component_by_key(key: str) -> GeoAIComponent:
    for c in COMPONENTS:
        if c.key == key:
            return c
    raise KeyError(key)


def mvp_components() -> tuple[GeoAIComponent, ...]:
    return tuple(c for c in COMPONENTS if c.tier == "MVP")
