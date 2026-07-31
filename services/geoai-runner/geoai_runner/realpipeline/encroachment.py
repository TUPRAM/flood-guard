"""Component E -- Encroachment / exposure-growth detection.

Anchor: *Introduction to GeoAI* (Wu, 2026), Ch. 12 §12.5.2 (deep change
detection) and Ch. 19 (ready-to-use products).

The question and the retained null
----------------------------------
The FloodGuard question is **encroachment**: is new built-up appearing inside
the floodplain between two dates? That is a development-pressure indicator for
land-use policy, and it is a good question.

The first implementation answered it with ChangeStar (Changen2 weights), which
returned exactly **0% change** on 2020-03-10 -> 2024-03-09 Sentinel-2. That null
is not a bug and it is not deleted: ChangeStar is trained on sub-metre aerial
imagery where a building spans hundreds of pixels, and on 10 m Sentinel-2 a
house is one or two pixels. The model and pipeline ran end to end; the imagery
could not carry the signal. :data:`CHANGESTAR_NULL_RESULT` preserves that as a
structured, citable record -- "we ran the state-of-the-art deep change detector
and it failed for a stated resolution reason" is a stronger methodological claim
than silence, and it is the honest reason for the substitution below.

What replaced it
----------------
A multi-temporal built-up *surface fraction* product (GHSL GHS-BUILT-S by
default). Three reasons it fits where ChangeStar did not:

* it is explicitly designed for multi-decade change, so differencing two epochs
  is the intended use rather than an off-label one;
* it is a continuous fraction, not a binary mask, so a partial-pixel change is
  representable instead of being thresholded away at 10 m;
* at 100 m it is honest about what is resolvable from this input, rather than
  implying building-instance precision the imagery cannot support.

Sub-metre THEOS-2 with ChangeStar remains the upgrade path; this is what can be
answered today.

The georeferencing bug this also fixes
--------------------------------------
The previous flow wrote the susceptibility surface on the **full district** grid
and then nearest-neighbour resized it onto ChangeStar's **town-subset** grid.
Those are different geographic extents, so the floodplain mask was silently
stretched across the wrong ground. It never surfaced only because the change
mask was empty, so the intersection was empty either way. :func:`reproject_to_grid`
replaces the resize with a real reprojection and refuses to proceed when the two
extents do not substantially overlap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from geoai_runner.realpipeline.raster_io import read_geotiff, write_geotiff


class EncroachmentError(RuntimeError):
    """Raised when an encroachment input is unavailable or misaligned."""


class GridMismatchError(EncroachmentError):
    """Raised when two rasters do not overlap enough to be intersected."""


# Preserved verbatim from the executed ChangeStar run so the negative result
# stays citable after the engine was swapped out.
CHANGESTAR_NULL_RESULT: dict[str, object] = {
    "method": "ChangeStar (s1_s1c1_vitb, Changen2 pretrained)",
    "book_ref": "Ch. 12, Sec. 12.5.2",
    "t1": "2020-03-10",
    "t2": "2024-03-09",
    "input": "Sentinel-2 L2A RGB, 10 m, Mae Sai town subset",
    "change_fraction": 0.0,
    "outcome": "null_result_resolution_limited",
    "executed": True,
    "runtime_seconds": 76.2,
    "interpretation": (
        "ChangeStar is trained on sub-metre aerial imagery where a building spans "
        "hundreds of pixels. On 10 m Sentinel-2 a building is 1-2 pixels, below the "
        "scale the architecture can resolve, so it detected no built-up change. The "
        "model and pipeline executed end to end; this is a resolution limit of the "
        "input, not a failure of the run. Sub-metre THEOS-2 is the upgrade path."
    ),
    "superseded_by": "ghsl_built_s_multitemporal",
}

# Candidate STAC collection identifiers for multi-temporal built-up surface.
# Tried in order; the resolver reports every identifier it attempted so a
# catalogue change produces an actionable error instead of a silent skip.
GHSL_COLLECTION_CANDIDATES: tuple[str, ...] = (
    "jrc-ghsl-built-s",
    "ghsl-built-s",
    "jrc-ghsl",
)


@dataclass
class EncroachmentResult:
    """Outputs of the built-up change component."""

    change_mask: np.ndarray
    metrics: dict
    artifacts: dict[str, Path] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Grid alignment -- the bug fix
# --------------------------------------------------------------------------- #
def _bounds_from(transform, shape: tuple[int, int]) -> tuple[float, float, float, float]:
    height, width = shape
    left, top = transform * (0, 0)
    right, bottom = transform * (width, height)
    return (min(left, right), min(top, bottom), max(left, right), max(top, bottom))


def _overlap_fraction(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Return the fraction of ``a``'s area covered by its intersection with ``b``."""

    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    return ((ix1 - ix0) * (iy1 - iy0)) / area_a if area_a > 0 else 0.0


def reproject_to_grid(
    source_path: str | Path,
    destination_transform,
    destination_shape: tuple[int, int],
    destination_crs: str,
    *,
    resampling: str = "bilinear",
    min_overlap: float = 0.5,
) -> np.ndarray:
    """Reproject a raster onto an explicit destination grid, refusing to stretch.

    The previous implementation index-resampled one grid onto another without
    checking that they described the same ground. That silently produces a
    plausible-looking array over the wrong location -- the worst kind of
    geospatial bug, because nothing downstream can detect it.

    Raises:
        GridMismatchError: when less than ``min_overlap`` of the destination
            extent is covered by the source.
    """

    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject, transform_bounds

    source_path = Path(source_path)
    destination_bounds = _bounds_from(destination_transform, destination_shape)
    with rasterio.open(source_path) as src:
        source_bounds = src.bounds
        if str(src.crs) != str(destination_crs):
            source_bounds = transform_bounds(src.crs, destination_crs, *src.bounds)
        covered = _overlap_fraction(destination_bounds, tuple(source_bounds))
        if covered < min_overlap:
            raise GridMismatchError(
                f"{source_path.name} covers only {covered:.1%} of the destination "
                f"extent (minimum {min_overlap:.0%}). Source bounds "
                f"{tuple(round(v, 5) for v in source_bounds)} vs destination "
                f"{tuple(round(v, 5) for v in destination_bounds)}. "
                "Reproject or re-window the source rather than resampling across "
                "mismatched extents."
            )
        destination = np.zeros(destination_shape, dtype="float32")
        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=destination_transform,
            dst_crs=destination_crs,
            resampling=getattr(Resampling, resampling),
        )
    return destination


# --------------------------------------------------------------------------- #
# Built-up surface fetch
# --------------------------------------------------------------------------- #
def resolve_builtup_collection(
    candidates: tuple[str, ...] = GHSL_COLLECTION_CANDIDATES,
) -> str:
    """Return the first candidate collection present in the STAC catalogue.

    The identifier is resolved at run time rather than hard-coded because a
    wrong constant would make this component silently unavailable. The error
    names every identifier tried so the fix is obvious.
    """

    from geoai_runner.realpipeline import real_data as rd

    catalogue = rd._pc_client()
    available: list[str] = []
    for candidate in candidates:
        try:
            catalogue.get_collection(candidate)
            return candidate
        except Exception:  # pragma: no cover - network dependent
            available.append(candidate)
    raise EncroachmentError(
        "no multi-temporal built-up collection found. Tried: "
        + ", ".join(available)
        + ". List available collections with "
        "`pystac_client.Client.open(PC_STAC).get_collections()` and pass the "
        "correct id via collection_id."
    )


def fetch_builtup_surface(
    bbox: tuple[float, float, float, float],
    year: int,
    out_path: str | Path,
    *,
    out_shape: tuple[int, int] = (512, 512),
    collection_id: str | None = None,
) -> dict[str, object]:
    """Fetch a built-up surface-fraction epoch and write it as a GeoTIFF."""

    from affine import Affine

    from geoai_runner.realpipeline import real_data as rd

    collection_id = collection_id or resolve_builtup_collection()
    catalogue = rd._pc_client()
    items = list(
        catalogue.search(
            collections=[collection_id],
            bbox=list(bbox),
            datetime=f"{year}-01-01/{year}-12-31",
        ).items()
    )
    if not items:
        raise EncroachmentError(
            f"no {collection_id} item for {year} over {bbox}. GHSL epochs are "
            "5-yearly; pick an epoch year the product actually publishes."
        )
    asset_key = next(
        (k for k in ("built_surface", "data", "built-s") if k in items[0].assets),
        next(iter(items[0].assets)),
    )
    layers = [rd._read_asset(item, asset_key, bbox, out_shape) for item in items]
    surface = np.nanmax(np.stack(layers), axis=0)

    left, bottom, right, top = bbox
    transform = Affine.translation(left, top) * Affine.scale(
        (right - left) / out_shape[1], (bottom - top) / out_shape[0]
    )
    write_geotiff(out_path, surface.astype("float32"), transform, "EPSG:4326")
    return {
        "path": Path(out_path),
        "year": year,
        "collection_id": collection_id,
        "asset_key": asset_key,
        "item_ids": [item.id for item in items],
        "transform": transform,
    }


# --------------------------------------------------------------------------- #
# Change detection
# --------------------------------------------------------------------------- #
def builtup_change(
    t1_path: str | Path,
    t2_path: str | Path,
    output_dir: str | Path,
    *,
    susceptibility_path: str | Path | None = None,
    susceptibility_threshold: float = 50.0,
    change_threshold: float = 0.05,
    t1_year: int | None = None,
    t2_year: int | None = None,
) -> EncroachmentResult:
    """Difference two built-up epochs and intersect the growth with the floodplain.

    ``change_threshold`` is expressed in built-up *surface fraction*: a cell must
    gain at least this much built surface to count as growth, which filters the
    product's own epoch-to-epoch noise without discarding partial-pixel change
    the way a binary mask would.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    t1, transform, crs = read_geotiff(t1_path)
    t2, t2_transform, _ = read_geotiff(t2_path)
    t1, t2 = t1[0].astype("float32"), t2[0].astype("float32")
    if t1.shape != t2.shape:
        raise GridMismatchError(f"built-up epochs have different shapes: {t1.shape} vs {t2.shape}.")
    # Normalise percent-scaled products to a 0-1 fraction.
    scale = 100.0 if max(float(np.nanmax(t1)), float(np.nanmax(t2))) > 1.5 else 1.0
    t1, t2 = t1 / scale, t2 / scale

    delta = np.clip(t2 - t1, -1.0, 1.0)
    growth = (delta >= change_threshold).astype("uint8")

    metrics: dict = {
        "data_mode": "real_licensed_inputs",
        "method": "Built-up surface-fraction differencing (GHSL-class product)",
        "t1_year": t1_year,
        "t2_year": t2_year,
        "change_threshold_fraction": change_threshold,
        "growth_cell_fraction": round(float(growth.mean()), 5),
        "mean_builtup_t1": round(float(np.nanmean(t1)), 5),
        "mean_builtup_t2": round(float(np.nanmean(t2)), 5),
        "mean_builtup_delta": round(float(np.nanmean(delta)), 5),
        "superseded_method": CHANGESTAR_NULL_RESULT,
        "assumptions": (
            "Built-up surface fraction differenced between two epochs; this is "
            "development pressure, not floodwater. Resolution is ~100 m, so this "
            "measures neighbourhood-scale growth rather than individual buildings. "
            "Non-operational; not an official warning."
        ),
    }

    change_for_result = growth
    if susceptibility_path is not None:
        # Real reprojection with an overlap guard -- see reproject_to_grid.
        susceptibility = reproject_to_grid(
            susceptibility_path, transform, t1.shape, crs, resampling="bilinear"
        )
        floodplain = susceptibility >= susceptibility_threshold
        in_floodplain = (growth.astype(bool) & floodplain).astype("uint8")
        growth_cells = int(growth.sum())
        metrics["floodplain_cell_fraction"] = round(float(floodplain.mean()), 5)
        metrics["floodplain_growth_cell_fraction"] = round(float(in_floodplain.mean()), 6)
        metrics["floodplain_share_of_growth"] = (
            round(float(in_floodplain.sum() / growth_cells), 4) if growth_cells else None
        )
        # Mean built-up gain inside vs outside the floodplain is the headline
        # policy number: growth concentrating in the flood zone is the finding.
        metrics["mean_delta_in_floodplain"] = (
            round(float(np.nanmean(delta[floodplain])), 5) if floodplain.any() else None
        )
        metrics["mean_delta_outside_floodplain"] = (
            round(float(np.nanmean(delta[~floodplain])), 5) if (~floodplain).any() else None
        )
        change_for_result = in_floodplain
        write_geotiff(
            output_dir / "encroachment_floodplain_growth.tif",
            in_floodplain,
            transform,
            crs,
            dtype="uint8",
        )

    artifacts = {
        "growth": write_geotiff(
            output_dir / "builtup_growth.tif", growth, transform, crs, dtype="uint8"
        ),
        "delta": write_geotiff(
            output_dir / "builtup_delta.tif", delta.astype("float32"), transform, crs
        ),
    }
    if susceptibility_path is not None:
        artifacts["floodplain_growth"] = output_dir / "encroachment_floodplain_growth.tif"
    return EncroachmentResult(change_mask=change_for_result, metrics=metrics, artifacts=artifacts)


def detect_builtup_change(
    bbox: tuple[float, float, float, float],
    t1_year: int,
    t2_year: int,
    output_dir: str | Path,
    *,
    susceptibility_path: str | Path | None = None,
    susceptibility_threshold: float = 50.0,
    out_shape: tuple[int, int] = (512, 512),
    collection_id: str | None = None,
) -> EncroachmentResult:
    """Fetch two built-up epochs over ``bbox`` and report floodplain encroachment."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    first = fetch_builtup_surface(
        bbox,
        t1_year,
        output_dir / f"builtup_{t1_year}.tif",
        out_shape=out_shape,
        collection_id=collection_id,
    )
    second = fetch_builtup_surface(
        bbox,
        t2_year,
        output_dir / f"builtup_{t2_year}.tif",
        out_shape=out_shape,
        collection_id=first["collection_id"],
    )
    result = builtup_change(
        first["path"],
        second["path"],
        output_dir,
        susceptibility_path=susceptibility_path,
        susceptibility_threshold=susceptibility_threshold,
        t1_year=t1_year,
        t2_year=t2_year,
    )
    result.metrics["collection_id"] = first["collection_id"]
    result.metrics["t1_item_ids"] = first["item_ids"]
    result.metrics["t2_item_ids"] = second["item_ids"]
    return result
