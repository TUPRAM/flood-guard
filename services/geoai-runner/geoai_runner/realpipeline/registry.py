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
            "refinement layer. In the real run, labels are derived from the MNDWI "
            "water index (weak supervision from a physical index, not hand "
            "annotation), so metrics are measured against that index."
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
            "The real run uses OpenStreetMap footprints, whose completeness varies "
            "by area. Exposure is counted against the observed SAR flood extent, so "
            "a post-peak acquisition (as on 2024-09-15) can report zero exposed "
            "structures even where buildings sit in the floodplain -- read it with "
            "the susceptibility surface. SAM 3 on THEOS-2 is the resolution upgrade."
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
        ai_task="Deep-learning change detection (ChangeStar)",
        book_ref="Ch. 12, Sec. 12.5.2",
        tier="Roadmap",
        status="runnable",
        architecture="ChangeStar (Changen2 weights) building-change siamese network",
        inputs="Pre/post high-resolution optical pairs (THEOS-2)",
        output_artifact="encroachment_change.gpkg",
        feeds_into="Development-pressure indicator for policy narrative",
        criteria=("Communication", "GeoAI Approach"),
        plain_language=(
            "Detects new buildings appearing inside the floodplain between two dates "
            "-- a development-pressure signal for land-use policy."
        ),
        limitations=(
            "ChangeStar detects building change, not floodwater; scope is strictly "
            "encroachment. Gated on availability of suitable optical pairs."
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
            "Published benchmark (Kaushik et al., 2026, IEEE JSTARS) shows foundation "
            "models trail on SAR vs optical; positioned as a complement to Component "
            "B, validated on optical first. Real embeddings need download; offline "
            "demo fits the classifier on locally-computed feature vectors."
        ),
    ),
    GeoAIComponent(
        key="narrative",
        letter="G",
        name="Narrative Generation (Vision-Language Model)",
        ai_task="Image captioning / VQA (Moondream)",
        book_ref="Ch. 15, Sec. 15.7-15.8",
        tier="Roadmap",
        status="runnable",
        architecture="Compact VLM prompted on before/after image pairs",
        inputs="Before/after flood image pairs",
        output_artifact="Auto-drafted plain-language captions (team-reviewed)",
        feeds_into="Dashboard story tile (Communication criterion)",
        criteria=("Communication",),
        plain_language=(
            "Drafts a plain-language caption for each before/after pair to help "
            "explain the map to non-technical decision-makers."
        ),
        limitations=(
            "Assistive drafting only, always human-reviewed; needs model weights "
            "downloaded. Optional, lowest priority."
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
