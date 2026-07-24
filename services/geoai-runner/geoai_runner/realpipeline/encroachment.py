"""Component E — Encroachment / exposure-growth detection (ChangeStar).

Anchor: *Introduction to GeoAI* (Wu, 2026), Ch. 12 §12.5.2. ChangeStar jointly
performs change detection and building segmentation, outputting a change mask
plus built-up masks at each time step, using Changen2 pretrained weights that
generalise to new regions without fine-tuning.

FloodGuard's defensible use (not flood-water detection): run ChangeStar on two
real Sentinel-2 dates over Mae Sai to detect NEW built-up appearing between the
dates, then intersect that change with the floodplain (susceptibility surface)
to produce a "development-pressure inside the floodplain" indicator for the
policy narrative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from geoai_runner.realpipeline import real_data as rd
from geoai_runner.realpipeline.raster_io import read_geotiff, write_geotiff


@dataclass
class EncroachmentResult:
    change_mask: np.ndarray
    metrics: dict
    artifacts: dict[str, Path] = field(default_factory=dict)


def fetch_rgb_uint8(
    date_range: str, bbox, out_path: str | Path, out_shape: tuple[int, int] = (512, 512),
    max_cloud: float = 8.0,
) -> dict:
    """Fetch a real Sentinel-2 scene and write an RGB uint8 GeoTIFF for ChangeStar."""

    s2 = rd.fetch_sentinel2_composite(
        bbox=bbox, datetime_range=date_range, max_cloud=max_cloud, out_shape=out_shape
    )
    rgb = np.clip(s2["stack"][[2, 1, 0]] * 3.5, 0, 1)  # red, green, blue, brightened
    rgb8 = (rgb * 255).astype("uint8")
    from affine import Affine

    left, bottom, right, top = bbox
    transform = Affine.translation(left, top) * Affine.scale(
        (right - left) / out_shape[1], (bottom - top) / out_shape[0]
    )
    write_geotiff(out_path, rgb8, transform, "EPSG:4326", dtype="uint8")
    return {"path": Path(out_path), "datetime": s2["datetime"], "cloud": s2["cloud_cover"],
            "transform": transform}


def detect_encroachment(
    t1_path: str | Path, t2_path: str | Path, output_dir: str | Path,
    *,
    model_name: str = "s1_s1c1_vitb",
    floodplain_path: str | Path | None = None,
    floodplain_threshold: float = 50.0,
) -> EncroachmentResult:
    """Run ChangeStar between two dates; flag change inside the floodplain."""

    from geoai.change_detection import changestar_detect

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    change_path = output_dir / "encroachment_change.tif"
    result = changestar_detect(
        str(t1_path), str(t2_path), model_name=model_name,
        output_change=str(change_path),
        output_t1_semantic=str(output_dir / "encroachment_t1_builtup.tif"),
        output_t2_semantic=str(output_dir / "encroachment_t2_builtup.tif"),
        output_vector=str(output_dir / "encroachment_change.geojson"),
    )
    change, transform, crs = read_geotiff(change_path)
    change = (change[0] > 0).astype("uint8")

    floodplain_change = None
    metrics: dict = {
        "data_mode": "real_licensed_inputs",
        "change_fraction": round(float(change.mean()), 4),
        "model": f"ChangeStar ({model_name}, Changen2 pretrained)",
        "assumptions": (
            "ChangeStar detects BUILT-UP change between two real Sentinel-2 dates, "
            "not floodwater. 'Encroachment' = new built-up intersecting the flood "
            "susceptibility surface. Development-pressure indicator only; "
            "non-operational, not an official warning."
        ),
    }
    if floodplain_path is not None:
        fp, _, _ = read_geotiff(floodplain_path)
        fp = fp[0]
        if fp.shape != change.shape:  # align by simple resample-nearest
            fp = _resize_nn(fp, change.shape)
        floodplain = fp >= floodplain_threshold
        floodplain_change = (change.astype(bool) & floodplain).astype("uint8")
        metrics["floodplain_encroachment_fraction"] = round(float(floodplain_change.mean()), 5)
        metrics["floodplain_encroachment_share_of_change"] = (
            round(float(floodplain_change.sum() / max(1, change.sum())), 3)
        )

    artifacts = {"change": change_path,
                 "change_vector": output_dir / "encroachment_change.geojson"}
    return EncroachmentResult(
        change_mask=change if floodplain_change is None else floodplain_change,
        metrics=metrics, artifacts=artifacts,
    )


def _resize_nn(arr: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    ys = (np.linspace(0, arr.shape[0] - 1, shape[0])).astype(int)
    xs = (np.linspace(0, arr.shape[1] - 1, shape[1])).astype(int)
    return arr[np.ix_(ys, xs)]
