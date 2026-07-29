"""Cross-cutting baseline — OmniWaterMask (sensor-agnostic pre-trained water).

Anchor: *Introduction to GeoAI* (Wu, 2026), Ch. 9 §9.6.4 and Ch. 19. A
zero-training reference model (``geoai.segment_water`` wrapping OmniWaterMask:
deep learning + NDWI + OSM) used to sanity-check the trained U-Net (Component B)
so we are not marking our own homework. Optical-only; it cannot replace the SAR
detector during a cloud-covered active storm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from geoai_runner.realpipeline.raster_io import read_geotiff


class OmniWaterMaskUnavailableError(RuntimeError):
    """Raised when OmniWaterMask is not installed in the active environment."""


@dataclass
class BaselineResult:
    water_mask: np.ndarray
    metrics: dict
    artifacts: dict[str, Path] = field(default_factory=dict)


def _require_omniwatermask() -> None:
    """Fail with an actionable message instead of an opaque ImportError.

    ``omniwatermask`` requires ``numpy>=2.0,<2.4`` and cannot coexist with this
    runner's frozen ``numpy==2.4.2`` boundary, so it is deliberately absent from
    every extra (D-39). Without this guard the failure surfaces from deep inside
    ``geoai.segment_water`` as a bare ImportError with no indication that a
    separate environment is required.
    """

    try:
        import omniwatermask  # noqa: F401
    except ImportError as exc:
        raise OmniWaterMaskUnavailableError(
            "Component * (OmniWaterMask) needs a separate research-tier "
            "environment: omniwatermask requires numpy>=2.0,<2.4 and this "
            "runner is frozen at numpy==2.4.2.\n"
            "  uv venv .venv-research --python 3.12\n"
            "  uv pip install --python .venv-research "
            "-r services/geoai-runner/requirements-research.txt\n"
            "Output from that environment is RESEARCH TIER: it carries no "
            "frozen-environment receipt, so write it to research/ and record "
            "it in research/MANIFEST.md. See ADR-I."
        ) from exc


def run_omniwatermask_baseline(
    s2_path: str | Path,
    output_dir: str | Path,
    *,
    band_order: list[int] | None = None,
    reference_mask_path: str | Path | None = None,
    max_size: int = 512,
) -> BaselineResult:
    """Run OmniWaterMask on a real Sentinel-2 stack (zero training).

    ``band_order`` maps the 6-band S2 stack (1=B2,2=B3,3=B4,4=B8,5=B11,6=B12) to
    the model's expected R,G,B,NIR order -> [3, 2, 1, 4]. The input is downsampled
    to ``max_size`` first: OmniWaterMask allocates a large tensor and a full-size
    tile OOMs on a laptop (~5 GB at 1024px).
    """

    _require_omniwatermask()

    import geoai

    from geoai_runner.realpipeline.raster_io import write_geotiff

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_path = Path(s2_path)
    stack, transform, crs = read_geotiff(s2_path)
    if max(stack.shape[1], stack.shape[2]) > max_size:
        from affine import Affine

        small = _downsample(stack, max_size)
        scale = stack.shape[1] / small.shape[1]
        transform = transform * Affine.scale(scale, scale)
        run_path = output_dir / "s2_baseline_input.tif"
        write_geotiff(run_path, small, transform, crs)

    out_path = output_dir / "water_mask_baseline.tif"
    geoai.segment_water(
        str(run_path),
        band_order=band_order or [3, 2, 1, 4],
        output_raster=str(out_path),
    )
    mask, _, _ = read_geotiff(out_path)
    mask = (mask[0] > 0).astype("uint8")

    metrics: dict = {
        "data_mode": "real_licensed_inputs",
        "water_fraction": round(float(mask.mean()), 4),
        "method": "OmniWaterMask (geoai.segment_water, pre-trained, zero training)",
        "assumptions": (
            "Zero-training optical baseline for the trained U-Net (Component B). "
            "Optical-only; not usable under cloud during an active storm. "
            "Agreement (IoU) with the U-Net's MNDWI labels is a sanity check, not "
            "an accuracy claim."
        ),
    }
    if reference_mask_path is not None:
        ref, _, _ = read_geotiff(reference_mask_path)
        r = ref[0]
        if r.shape != mask.shape:  # align full-res labels to the downsampled mask
            r = _downsample(r[None], max(mask.shape))[0]
        r = r.astype(bool)
        m = mask.astype(bool)
        inter = int((m & r).sum())
        union = int((m | r).sum())
        metrics["iou_vs_unet_labels"] = round(inter / union, 4) if union else 0.0

    return BaselineResult(
        water_mask=mask, metrics=metrics, artifacts={"baseline": out_path}
    )


def _downsample(stack: np.ndarray, max_size: int) -> np.ndarray:
    """Nearest-neighbour downsample a (bands, H, W) array so max(H,W)==max_size."""

    _, h, w = stack.shape
    ys = np.linspace(0, h - 1, min(h, max_size)).astype(int)
    xs = np.linspace(0, w - 1, min(w, max_size)).astype(int)
    return stack[:, ys][:, :, xs]
