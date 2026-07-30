"""Component B's training label, selectable and provenance-bound.

Why this module exists
----------------------
Component B trained on ``(MNDWI > 0)``, and that label is measurably wrong.
Swept against JRC Global Surface Water (occurrence > 50 %, 0.373 % of the
2024-02-18 dry-season scene):

    label                fraction    IoU    precision  recall
    MNDWI > 0  (was)      3.240 %   0.055     0.058     0.502
    MNDWI > 0.05          1.993 %   0.076     0.084     0.451
    MNDWI > 0.10 (best)   1.042 %   0.079     0.100     0.279
    NDWI  > 0             0.872 %   0.154     0.190     0.446
    OmniWaterMask         0.330 %      —         —         —

At the shipped threshold MNDWI flags **8.7x the reference area while missing
half of it**. A mask that over- and under-detects simultaneously is not a
threshold problem, so tuning is not a fix -- the best MNDWI threshold still has
precision 0.100. Sub-pixel registration was excluded as the benign explanation:
IoU only reaches 0.081 at 3 px tolerance and 79 % of the reference survives 1 px
erosion.

The three usable options are exposed here rather than hard-coded, because the
choice carries a claim and the claim must travel with the artifact.

The distillation caveat
-----------------------
``external`` normally means an OmniWaterMask raster. OWM matches the JRC extent
to within 12 %, which makes it the best available optical label -- but a U-Net
trained on it is **distilling OWM**, not learning water independently. The
resulting IoU measures copy fidelity, not accuracy, and
:func:`label_assumptions` says so in the published metrics. Anything stronger
would be a false claim.

OWM cannot be computed inside the runner: ``omniwatermask`` requires
``numpy>=2.0,<2.4`` and the runner is frozen at ``numpy==2.4.2``. So an external
label is produced in the research environment and passed in as a raster, with
its SHA-256 and grid recorded so the binding is checkable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

__all__ = [
    "LABEL_METHODS",
    "WaterLabelError",
    "build_water_label",
    "label_assumptions",
]

LABEL_METHODS = ("mndwi", "ndwi", "external")

#: Retained as the historical default so a run without ``--water-label`` still
#: reproduces the published baseline exactly. It is not recommended.
DEFAULT_METHOD = "mndwi"

MNDWI_DEFAULT_THRESHOLD = 0.0
NDWI_DEFAULT_THRESHOLD = 0.0


class WaterLabelError(RuntimeError):
    """Raised when a requested label cannot be built or bound to its grid."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_water_label(
    stack: np.ndarray,
    *,
    method: str = DEFAULT_METHOD,
    threshold: float | None = None,
    external_raster: str | Path | None = None,
) -> tuple[np.ndarray, dict[str, object]]:
    """Return ``(label, provenance)`` for a 6-band Sentinel-2 reflectance stack.

    Band order is the pipeline's own: 1=B2 2=B3 3=B4 4=B8 5=B11 6=B12, so
    green is index 1, NIR index 3, SWIR1 index 4.
    """

    if method not in LABEL_METHODS:
        raise WaterLabelError(f"unknown water-label method {method!r}; expected {LABEL_METHODS}")
    if stack.ndim != 3 or stack.shape[0] < 5:
        raise WaterLabelError(
            f"expected a 6-band stack shaped (bands, H, W); got {stack.shape}"
        )

    green, nir, swir1 = stack[1], stack[3], stack[4]

    if method == "mndwi":
        cut = MNDWI_DEFAULT_THRESHOLD if threshold is None else float(threshold)
        index = (green - swir1) / (green + swir1 + 1e-6)
        label = (index > cut).astype("uint8")
        provenance: dict[str, object] = {
            "label_method": "mndwi",
            "label_threshold": cut,
            "label_expression": "(B3 - B11) / (B3 + B11) > threshold",
            "label_is_distillation": False,
        }
    elif method == "ndwi":
        cut = NDWI_DEFAULT_THRESHOLD if threshold is None else float(threshold)
        index = (green - nir) / (green + nir + 1e-6)
        label = (index > cut).astype("uint8")
        provenance = {
            "label_method": "ndwi",
            "label_threshold": cut,
            "label_expression": "(B3 - B8) / (B3 + B8) > threshold",
            "label_is_distillation": False,
        }
    else:  # external
        if external_raster is None:
            raise WaterLabelError(
                "method='external' requires --water-label-raster. Generate one "
                "with research/skills/build_owm_label.py in .venv-research; "
                "OmniWaterMask cannot run inside the frozen runner (it needs "
                "numpy<2.4)."
            )
        path = Path(external_raster)
        if not path.is_file():
            raise WaterLabelError(f"external water label not found: {path}")

        from geoai_runner.realpipeline.raster_io import read_geotiff

        array = read_geotiff(path)[0]
        mask = array[0] if array.ndim == 3 else array
        expected = stack.shape[1:]
        if mask.shape != expected:
            raise WaterLabelError(
                f"external label grid {mask.shape} does not match the Sentinel-2 "
                f"stack {expected}. A label from a different grid would train "
                f"Component B against misaligned pixels. Regenerate it for this run."
            )
        label = (mask > 0).astype("uint8")
        provenance = {
            "label_method": "external",
            "label_source_path": path.name,
            "label_source_sha256": _sha256(path),
            "label_is_distillation": True,
        }

    provenance["label_water_fraction"] = round(float(label.mean()), 5)
    return label, provenance


def label_assumptions(provenance: dict[str, object]) -> str:
    """The published caveat for a label. Must travel with every B metric."""

    method = provenance.get("label_method")
    fraction = provenance.get("label_water_fraction")

    if method == "external":
        return (
            "Component B was trained against an EXTERNAL water mask "
            f"({provenance.get('label_source_path')}, sha256 "
            f"{str(provenance.get('label_source_sha256'))[:12]}...), normally "
            "OmniWaterMask. Any IoU or F1 reported here is DISTILLATION "
            "FIDELITY -- how closely the U-Net reproduces that teacher -- and is "
            "NOT an accuracy claim about water in Mae Sai. The teacher itself is "
            "unvalidated in-area; it agrees with JRC permanent-water extent to "
            "within 12% on a dry-season scene, which is an extent check, not a "
            "per-pixel accuracy result. The label was produced in the research "
            "environment and carries no frozen-environment receipt."
        )
    if method == "ndwi":
        return (
            f"Component B was trained on NDWI > {provenance.get('label_threshold')} "
            f"weak labels covering {fraction} of the scene. Measured against JRC "
            "permanent water, NDWI > 0 reaches IoU 0.154 with precision 0.190 -- "
            "roughly 2.8x better than the MNDWI label it replaces, but still "
            "about 2.3x the reference extent. Weak supervision from a spectral "
            "index, not hand annotation; not an accuracy claim."
        )
    return (
        f"Component B was trained on MNDWI > {provenance.get('label_threshold')} "
        f"weak labels covering {fraction} of the scene. THIS LABEL IS KNOWN TO BE "
        "POOR: measured against JRC permanent water it flags ~8.7x the reference "
        "area while recovering only ~50% of it (IoU 0.055, precision 0.058). No "
        "threshold fixes it -- the best case is IoU 0.079 at 0.10. Any metric "
        "below is agreement with a demonstrably wrong target and must not be read "
        "as accuracy. Retained only to reproduce the historical baseline."
    )
