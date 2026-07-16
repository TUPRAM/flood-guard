"""Auditable physical-band encoding shared by training and inference."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import rasterio
from numpy.typing import NDArray

from .contract import PreprocessingContract
from .validate import RasterGrid, read_grid


class PreprocessingError(ValueError):
    """Raised for a band-order, domain, or transform-contract violation."""


@dataclass(frozen=True, slots=True)
class BandTransform:
    name: str
    physical_min: float
    physical_max: float
    units: str
    description: str

    def validate(self) -> None:
        if (
            not self.name.strip()
            or not self.units.strip()
            or self.physical_min >= self.physical_max
        ):
            raise PreprocessingError(f"Invalid transform for {self.name!r}.")


@dataclass(frozen=True, slots=True)
class EncodingReceipt:
    """Byte and grid evidence for one encoded feature stack."""

    feature_sha256: str
    sidecar_sha256: str
    grid: RasterGrid


DEFAULT_TRANSFORMS: tuple[BandTransform, ...] = (
    BandTransform("pre_vv_db", -30.0, 0.0, "dB", "Pre-event Sentinel-1 VV backscatter"),
    BandTransform("post_vv_db", -30.0, 0.0, "dB", "Post-event Sentinel-1 VV backscatter"),
    BandTransform("pre_vh_db", -35.0, -5.0, "dB", "Pre-event Sentinel-1 VH backscatter"),
    BandTransform("post_vh_db", -35.0, -5.0, "dB", "Post-event Sentinel-1 VH backscatter"),
    BandTransform("vv_change_db", -15.0, 15.0, "dB", "Pre-event minus post-event VV"),
    BandTransform("vh_change_db", -15.0, 15.0, "dB", "Pre-event minus post-event VH"),
    BandTransform("slope_degrees", 0.0, 60.0, "degrees", "Terrain slope clipped at 60 degrees"),
    BandTransform("permanent_water_flag", 0.0, 1.0, "binary", "Permanent-water context flag"),
)


def encode_physical_stack(
    stack: NDArray[np.floating],
    transforms: Iterable[BandTransform] = DEFAULT_TRANSFORMS,
) -> NDArray[np.uint8]:
    """Clip each physical band and linearly encode it to uint8 [0,255]."""

    specs = tuple(transforms)
    if stack.ndim != 3 or stack.shape[0] != len(specs) or not 6 <= len(specs) <= 8:
        raise PreprocessingError("Stack must be (6-8 bands, height, width) in declared order.")
    if not np.isfinite(stack).all():
        raise PreprocessingError(
            "Physical stack contains non-finite values; nodata must be masked first."
        )
    encoded = np.empty(stack.shape, dtype=np.uint8)
    for index, spec in enumerate(specs):
        spec.validate()
        clipped = np.clip(stack[index], spec.physical_min, spec.physical_max)
        scaled = (clipped - spec.physical_min) / (spec.physical_max - spec.physical_min)
        encoded[index] = np.rint(scaled * 255.0).astype(np.uint8)
    return encoded


def geoai_uint8_preprocess(tile: NDArray[np.generic]) -> NDArray[np.float32]:
    """Explicit inference transform matching stock GeoTIFF training's `/255`.

    GeoAI 0.41.1 reads raster windows and casts them to float32 before invoking
    ``preprocess_fn``. The function therefore accepts uint8 or an exact
    float32 representation of uint8 values, but rejects fractional/raw physical
    values, negative SAR dB, NaN, and values outside ``[0, 255]``.
    """

    values = np.asarray(tile)
    if values.ndim != 3 or not 6 <= values.shape[0] <= 8:
        raise PreprocessingError("Inference tile must retain the declared 6-8 channels.")
    if not np.issubdtype(values.dtype, np.number) or not np.isfinite(values).all():
        raise PreprocessingError("Inference tile must contain finite encoded values.")
    if values.min() < 0 or values.max() > 255:
        raise PreprocessingError("Inference requires a pre-encoded uint8 [0,255] GeoTIFF.")
    if values.dtype != np.uint8 and not np.equal(values, np.rint(values)).all():
        raise PreprocessingError("Float inference tiles must be exact uint8 values.")
    return values.astype(np.float32) / np.float32(255.0)


def sidecar_payload(transforms: Iterable[BandTransform] = DEFAULT_TRANSFORMS) -> dict[str, object]:
    specs = tuple(transforms)
    for spec in specs:
        spec.validate()
    return {
        "schema_version": "1.0",
        "method": "clip_linear_uint8_v1",
        "encoded_dtype": "uint8",
        "encoded_range": [0, 255],
        "training_loader_contract": "geoai stock GeoTIFF loader divides values by 255",
        "inference_preprocess": "validate uint8 then divide by 255",
        "channels": [asdict(spec) for spec in specs],
    }


def write_sidecar(path: Path, transforms: Iterable[BandTransform] = DEFAULT_TRANSFORMS) -> str:
    """Write canonical JSON and return the byte-level SHA-256 receipt."""

    payload = (
        json.dumps(
            sidecar_payload(transforms),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8", newline="\n")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_transform_sidecar(
    path: Path,
    contract: PreprocessingContract,
) -> str:
    """Re-hash and parse the exact per-band transform receipt before consumption."""

    contract.validate()
    try:
        encoded = path.read_bytes()
    except OSError as exc:
        raise PreprocessingError(f"Could not read preprocessing sidecar: {exc}") from exc
    receipt = hashlib.sha256(encoded).hexdigest()
    if receipt != contract.sidecar_sha256:
        raise PreprocessingError("Preprocessing sidecar checksum does not match the run contract.")
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreprocessingError(f"Preprocessing sidecar is not valid UTF-8 JSON: {exc}") from exc
    transforms = tuple(
        BandTransform(
            name=item.name,
            physical_min=item.physical_min,
            physical_max=item.physical_max,
            units=item.units,
            description=item.description,
        )
        for item in contract.transforms
    )
    if payload != sidecar_payload(transforms):
        raise PreprocessingError(
            "Preprocessing sidecar statistics do not match the typed run contract."
        )
    return receipt


def encode_feature_geotiff(
    physical_path: Path,
    encoded_path: Path,
    sidecar_path: Path,
    transforms: Iterable[BandTransform] = DEFAULT_TRANSFORMS,
) -> EncodingReceipt:
    """Encode an aligned physical-value GeoTIFF into the frozen uint8 contract."""

    resolved_paths = {
        physical_path.resolve(),
        encoded_path.resolve(),
        sidecar_path.resolve(),
    }
    if len(resolved_paths) != 3:
        raise PreprocessingError("Physical input, encoded output, and sidecar must be distinct.")
    specs = tuple(transforms)
    with rasterio.open(physical_path) as source:
        if source.crs is None:
            raise PreprocessingError("Physical feature stack requires an explicit CRS.")
        if source.count != len(specs) or not 6 <= source.count <= 8:
            raise PreprocessingError("Physical feature stack must contain 6-8 declared bands.")
        expected_names = tuple(spec.name for spec in specs)
        if tuple(source.descriptions) != expected_names:
            raise PreprocessingError(
                "Physical feature band descriptions must exactly match the frozen channel order."
            )
        physical = source.read(masked=True)
        if np.ma.getmaskarray(physical).any():
            raise PreprocessingError(
                "Physical stack contains nodata; establish a fully valid common footprint first."
            )
        values = np.asarray(physical.data)
        profile = source.profile.copy()

    encoded = encode_physical_stack(values, specs)
    profile.update(dtype="uint8", count=len(specs), nodata=None, compress="lzw")
    encoded_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(encoded_path, "w", **profile) as target:
        target.write(encoded)
        for index, spec in enumerate(specs, start=1):
            target.set_band_description(index, spec.name)

    sidecar_sha256 = write_sidecar(sidecar_path, specs)
    return EncodingReceipt(
        feature_sha256=_sha256(encoded_path),
        sidecar_sha256=sidecar_sha256,
        grid=read_grid(encoded_path),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
