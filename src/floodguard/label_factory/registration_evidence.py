"""Build transparent residual-registration and processing evidence for SAR.

The four inputs are already calibrated, terrain-corrected dB rasters.  This
module does not alter them or infer flood.  It verifies their common grid,
measures residual pre/event displacement with deterministic tiled gradient
phase correlation, and emits the exact v1 CSV consumed by
``build_processing_alignment_receipt``.

The registration statistic is a diagnostic envelope, not geodetic truth:
the norm of the median measured shift plus the 90th percentile radial
dispersion of accepted window estimates.  Flood-related scene change can
reduce or bias correlation, so inadequate texture, support, quality, or
cross-polarization agreement blocks evidence generation.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping

import numpy as np
import pandas as pd

from floodguard.label_factory.event_registry import (
    MAX_GEOREGISTRATION_ERROR_PIXELS,
    parse_utc_datetime,
)
from floodguard.label_factory.processing_alignment import PROCESSING_EVIDENCE_COLUMNS


REGISTRATION_EVIDENCE_SCHEMA = "floodguard.sar_registration_evidence.v1"
COVERAGE_EVIDENCE_SCHEMA = "floodguard.raster_coverage_evidence.v1"
VALID_DATA_EVIDENCE_SCHEMA = "floodguard.raster_valid_data_evidence.v1"
BUILD_MANIFEST_SCHEMA = "floodguard.processing_evidence_build.v1"
PROCESSING_EVIDENCE_FILENAME = "processing_evidence.csv"
REGISTRATION_EVIDENCE_FILENAME = "residual_registration.json"
BUILD_MANIFEST_FILENAME = "processing_evidence_build.json"
GRID_CONTRACT_TAG = "grid_contract_sha256"

RASTER_ROLES: tuple[str, ...] = (
    "pre_vv",
    "pre_vh",
    "event_vv",
    "event_vh",
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")


class RegistrationEvidenceError(ValueError):
    """Raised when residual-registration evidence cannot be built safely."""


@dataclass(frozen=True, slots=True)
class RegistrationParameters:
    """Fixed quality controls for tiled phase-correlation diagnostics."""

    window_size_pixels: int = 256
    minimum_valid_fraction: float = 0.80
    maximum_search_shift_pixels: int = 3
    minimum_peak_to_sidelobe_ratio: float = 6.0
    minimum_windows_per_polarization: int = 3
    maximum_polarization_disagreement_pixels: float = 0.35

    def __post_init__(self) -> None:
        if self.window_size_pixels < 32:
            raise RegistrationEvidenceError(
                "window_size_pixels must be at least 32 pixels."
            )
        if not 0 < self.minimum_valid_fraction <= 1:
            raise RegistrationEvidenceError(
                "minimum_valid_fraction must be in (0, 1]."
            )
        if not 1 <= self.maximum_search_shift_pixels < self.window_size_pixels // 4:
            raise RegistrationEvidenceError(
                "maximum_search_shift_pixels must be positive and smaller than "
                "one quarter of the window size."
            )
        if self.minimum_peak_to_sidelobe_ratio <= 0:
            raise RegistrationEvidenceError(
                "minimum_peak_to_sidelobe_ratio must be positive."
            )
        if self.minimum_windows_per_polarization < 1:
            raise RegistrationEvidenceError(
                "minimum_windows_per_polarization must be positive."
            )
        if self.maximum_polarization_disagreement_pixels < 0:
            raise RegistrationEvidenceError(
                "maximum_polarization_disagreement_pixels must be non-negative."
            )


@dataclass(frozen=True, slots=True)
class ProcessingEvidencePaths:
    """Artifacts published by one immutable evidence build."""

    processing_evidence_csv: Path
    registration_evidence: Path
    build_manifest: Path


@dataclass(frozen=True, slots=True)
class _RasterSignature:
    crs_wkt: str
    crs_text: str
    affine: tuple[float, float, float, float, float, float]
    width: int
    height: int
    dtype: str
    nodata: float
    grid_contract_sha256: str

    @property
    def pixel_size_x(self) -> float:
        return self.affine[0]

    @property
    def pixel_size_y(self) -> float:
        return -self.affine[4]

    @property
    def cell_count(self) -> int:
        return self.width * self.height

    def as_json(self) -> dict[str, object]:
        return {
            "crs": self.crs_text,
            "crs_wkt": self.crs_wkt,
            "affine": list(self.affine),
            "width_pixels": self.width,
            "height_pixels": self.height,
            "pixel_size_x_m": self.pixel_size_x,
            "pixel_size_y_m": self.pixel_size_y,
            "dtype": self.dtype,
            "nodata": self.nodata,
            "grid_contract_sha256": self.grid_contract_sha256,
        }


def build_and_write_processing_evidence(
    *,
    pre_vv_path: str | Path,
    pre_vh_path: str | Path,
    event_vv_path: str | Path,
    event_vh_path: str | Path,
    asset_ids: Mapping[str, str],
    output_directory: str | Path,
    source_timestamp_utc: datetime | str,
    processing_software: str,
    processing_software_version: str,
    rtc_terrain_correction_method: str,
    pre_layover_shadow_mask_path: str | Path | None = None,
    event_layover_shadow_mask_path: str | Path | None = None,
    resampling_method: str = (
        "bilinear reprojection of linear Gamma0 followed by dB conversion"
    ),
    parameters: RegistrationParameters | None = None,
) -> ProcessingEvidencePaths:
    """Measure registration and atomically write receipt-compatible evidence.

    ``asset_ids`` must map each of ``pre_vv``, ``pre_vh``, ``event_vv``, and
    ``event_vh`` to a distinct source-registry asset id.  The timestamp is
    caller-supplied so repeated builds over identical evidence are byte
    deterministic.
    """

    paths = _coerce_raster_paths(
        pre_vv=pre_vv_path,
        pre_vh=pre_vh_path,
        event_vv=event_vv_path,
        event_vh=event_vh_path,
    )
    ids = _coerce_asset_ids(asset_ids)
    masks = _coerce_mask_paths(
        pre=pre_layover_shadow_mask_path,
        event=event_layover_shadow_mask_path,
    )
    timestamp = _canonical_utc_timestamp(source_timestamp_utc)
    software = _meaningful_text(processing_software, "processing_software")
    version = _meaningful_text(
        processing_software_version, "processing_software_version"
    )
    rtc_method = _meaningful_text(
        rtc_terrain_correction_method, "rtc_terrain_correction_method"
    )
    resampling = _meaningful_text(resampling_method, "resampling_method")
    controls = parameters or RegistrationParameters()
    output = Path(output_directory)
    if output.exists():
        raise RegistrationEvidenceError(
            f"Output directory already exists and is immutable: {output}"
        )

    rasterio = _load_rasterio()
    source_hashes = {role: _file_sha256(path) for role, path in paths.items()}
    mask_hashes = {role: _file_sha256(path) for role, path in masks.items()}
    with ExitStack() as stack:
        datasets = {
            role: stack.enter_context(rasterio.open(path))
            for role, path in paths.items()
        }
        mask_datasets = {
            role: stack.enter_context(rasterio.open(path))
            for role, path in masks.items()
        }
        signature = _validate_common_raster_grid(datasets)
        _validate_masks(mask_datasets, signature)
        arrays, valid = _read_rasters(datasets, mask_datasets)
        registration = _registration_diagnostic(
            arrays,
            valid,
            paths=paths,
            source_hashes=source_hashes,
            masks=masks,
            mask_hashes=mask_hashes,
            signature=signature,
            timestamp=timestamp,
            parameters=controls,
        )
        valid_summaries = {
            role: _valid_data_summary(
                role,
                valid[role],
                raster_path=paths[role],
                raster_sha256=source_hashes[role],
                mask_path=masks.get(_acquisition(role)),
                mask_sha256=mask_hashes.get(_acquisition(role)),
                signature=signature,
                timestamp=timestamp,
            )
            for role in RASTER_ROLES
        }
        coverage_summaries = {
            role: _coverage_summary(
                role,
                raster_path=paths[role],
                raster_sha256=source_hashes[role],
                signature=signature,
                timestamp=timestamp,
            )
            for role in RASTER_ROLES
        }

    # Guard against source mutation between measurement and publication.
    if {role: _file_sha256(path) for role, path in paths.items()} != source_hashes:
        raise RegistrationEvidenceError(
            "A SAR raster changed while registration evidence was being built."
        )
    if {role: _file_sha256(path) for role, path in masks.items()} != mask_hashes:
        raise RegistrationEvidenceError(
            "A layover/shadow mask changed while evidence was being built."
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=str(output.parent))
    )
    try:
        registration_path = temporary / REGISTRATION_EVIDENCE_FILENAME
        _write_json(registration_path, registration)
        registration_sha256 = _file_sha256(registration_path)

        coverage_paths: dict[str, Path] = {}
        valid_paths: dict[str, Path] = {}
        for role in RASTER_ROLES:
            coverage_path = temporary / f"{role}_coverage.json"
            valid_path = temporary / f"{role}_valid_data.json"
            _write_json(coverage_path, coverage_summaries[role])
            _write_json(valid_path, valid_summaries[role])
            coverage_paths[role] = coverage_path
            valid_paths[role] = valid_path

        final_paths = {
            role: {
                "coverage": output / coverage_paths[role].name,
                "valid": output / valid_paths[role].name,
            }
            for role in RASTER_ROLES
        }
        evidence = _processing_evidence_frame(
            paths=paths,
            source_hashes=source_hashes,
            asset_ids=ids,
            signature=signature,
            valid_summaries=valid_summaries,
            coverage_paths=coverage_paths,
            valid_paths=valid_paths,
            final_paths=final_paths,
            registration_path=output / registration_path.name,
            registration_sha256=registration_sha256,
            registration=registration,
            timestamp=timestamp,
            processing_software=software,
            processing_software_version=version,
            rtc_method=rtc_method,
            resampling_method=resampling,
        )
        evidence_path = temporary / PROCESSING_EVIDENCE_FILENAME
        evidence.to_csv(
            evidence_path,
            index=False,
            lineterminator="\n",
            float_format="%.12g",
        )
        build_manifest = _self_hashed(
            {
                "artifact_schema": BUILD_MANIFEST_SCHEMA,
                "source_timestamp": timestamp,
                "sources": {
                    role: {
                        "file_name": paths[role].name,
                        "sha256": source_hashes[role],
                        "asset_id": ids[role],
                    }
                    for role in RASTER_ROLES
                },
                "masks": {
                    role: {
                        "file_name": masks[role].name,
                        "sha256": mask_hashes[role],
                        "supported_value": 0,
                    }
                    for role in sorted(masks)
                },
                "outputs": {
                    "processing_evidence_csv": {
                        "file_name": evidence_path.name,
                        "sha256": _file_sha256(evidence_path),
                        "row_count": len(evidence),
                    },
                    "registration_evidence": {
                        "file_name": registration_path.name,
                        "sha256": registration_sha256,
                    },
                    "coverage_evidence": {
                        role: {
                            "file_name": coverage_paths[role].name,
                            "sha256": _file_sha256(coverage_paths[role]),
                        }
                        for role in RASTER_ROLES
                    },
                    "valid_data_evidence": {
                        role: {
                            "file_name": valid_paths[role].name,
                            "sha256": _file_sha256(valid_paths[role]),
                        }
                        for role in RASTER_ROLES
                    },
                },
                "registration_gate_passed": registration[
                    "registration_gate_passed"
                ],
                "safety": _safety_contract(),
                "assumptions": (
                    "Evidence describes byte-bound processing support and a "
                    "scene-correlation diagnostic only. It is not flood truth, "
                    "independent geodetic validation, a warning, or FPPS input."
                ),
            }
        )
        manifest_path = temporary / BUILD_MANIFEST_FILENAME
        _write_json(manifest_path, build_manifest)

        if output.exists():
            raise RegistrationEvidenceError(
                f"Output directory appeared during publication: {output}"
            )
        temporary.rename(output)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    return ProcessingEvidencePaths(
        processing_evidence_csv=output / PROCESSING_EVIDENCE_FILENAME,
        registration_evidence=output / REGISTRATION_EVIDENCE_FILENAME,
        build_manifest=output / BUILD_MANIFEST_FILENAME,
    )


def _registration_diagnostic(
    arrays: Mapping[str, np.ndarray],
    valid: Mapping[str, np.ndarray],
    *,
    paths: Mapping[str, Path],
    source_hashes: Mapping[str, str],
    masks: Mapping[str, Path],
    mask_hashes: Mapping[str, str],
    signature: _RasterSignature,
    timestamp: str,
    parameters: RegistrationParameters,
) -> dict[str, object]:
    if parameters.window_size_pixels > min(signature.height, signature.width):
        raise RegistrationEvidenceError(
            "window_size_pixels exceeds the source raster dimensions."
        )
    windows = _window_origins(
        signature.height, signature.width, parameters.window_size_pixels
    )
    measurements: list[dict[str, object]] = []
    accepted_by_pol: dict[str, list[dict[str, object]]] = {"VV": [], "VH": []}
    for polarization, pre_role, event_role in (
        ("VV", "pre_vv", "event_vv"),
        ("VH", "pre_vh", "event_vh"),
    ):
        common_valid = valid[pre_role] & valid[event_role]
        for row_off, col_off in windows:
            size = parameters.window_size_pixels
            selector = np.s_[row_off : row_off + size, col_off : col_off + size]
            support = common_valid[selector]
            valid_fraction = float(support.mean())
            record: dict[str, object] = {
                "polarization": polarization,
                "row_offset": row_off,
                "column_offset": col_off,
                "window_size_pixels": size,
                "valid_fraction": _round(valid_fraction),
            }
            if valid_fraction < parameters.minimum_valid_fraction:
                record.update(
                    {
                        "accepted": False,
                        "rejection_reason": "insufficient_common_valid_support",
                    }
                )
                measurements.append(record)
                continue
            try:
                estimate = _phase_correlation_shift(
                    arrays[pre_role][selector],
                    arrays[event_role][selector],
                    support,
                    maximum_shift=parameters.maximum_search_shift_pixels,
                )
            except RegistrationEvidenceError as exc:
                record.update(
                    {"accepted": False, "rejection_reason": str(exc)}
                )
                measurements.append(record)
                continue
            record.update(estimate)
            if float(estimate["peak_to_sidelobe_ratio"]) < (
                parameters.minimum_peak_to_sidelobe_ratio
            ):
                record.update(
                    {"accepted": False, "rejection_reason": "low_peak_quality"}
                )
            elif bool(estimate["peak_on_search_boundary"]):
                record.update(
                    {
                        "accepted": False,
                        "rejection_reason": "peak_on_search_boundary",
                    }
                )
            else:
                record.update({"accepted": True, "rejection_reason": ""})
                accepted_by_pol[polarization].append(record)
            measurements.append(record)

    for polarization, accepted in accepted_by_pol.items():
        if len(accepted) < parameters.minimum_windows_per_polarization:
            raise RegistrationEvidenceError(
                f"Registration has only {len(accepted)} accepted {polarization} "
                "windows; the minimum is "
                f"{parameters.minimum_windows_per_polarization}."
            )

    medians: dict[str, tuple[float, float]] = {}
    all_vectors: list[tuple[float, float]] = []
    for polarization, accepted in accepted_by_pol.items():
        vectors = np.asarray(
            [
                (float(row["row_shift_pixels"]), float(row["column_shift_pixels"]))
                for row in accepted
            ],
            dtype=float,
        )
        median = tuple(float(value) for value in np.median(vectors, axis=0))
        medians[polarization] = (median[0], median[1])
        all_vectors.extend((float(row), float(column)) for row, column in vectors)
    polarization_disagreement = math.dist(medians["VV"], medians["VH"])
    if polarization_disagreement > parameters.maximum_polarization_disagreement_pixels:
        raise RegistrationEvidenceError(
            "VV/VH residual-shift medians disagree by "
            f"{polarization_disagreement:.6g} pixels, exceeding "
            f"{parameters.maximum_polarization_disagreement_pixels:.6g}."
        )

    vectors = np.asarray(all_vectors, dtype=float)
    combined = np.median(vectors, axis=0)
    radial_dispersion = np.linalg.norm(vectors - combined, axis=1)
    p90_dispersion = float(np.percentile(radial_dispersion, 90))
    median_magnitude = float(np.linalg.norm(combined))
    diagnostic_envelope = median_magnitude + p90_dispersion
    minimum_psr = min(
        float(record["peak_to_sidelobe_ratio"])
        for accepted in accepted_by_pol.values()
        for record in accepted
    )
    method = (
        "deterministic tiled dual-polarization gradient phase correlation; "
        "error=norm(combined median shift)+p90 radial dispersion"
    )
    payload = {
        "artifact_schema": REGISTRATION_EVIDENCE_SCHEMA,
        "source_timestamp": timestamp,
        "method": method,
        "shift_semantics": (
            "row/column shift to apply to the event image to align it to the "
            "pre-event image; positive row is downward and positive column is right"
        ),
        "parameters": {
            "window_size_pixels": parameters.window_size_pixels,
            "minimum_valid_fraction": parameters.minimum_valid_fraction,
            "maximum_search_shift_pixels": parameters.maximum_search_shift_pixels,
            "minimum_peak_to_sidelobe_ratio": (
                parameters.minimum_peak_to_sidelobe_ratio
            ),
            "minimum_windows_per_polarization": (
                parameters.minimum_windows_per_polarization
            ),
            "maximum_polarization_disagreement_pixels": (
                parameters.maximum_polarization_disagreement_pixels
            ),
            "receipt_maximum_registration_error_pixels": (
                MAX_GEOREGISTRATION_ERROR_PIXELS
            ),
        },
        "grid": signature.as_json(),
        "sources": {
            role: {"file_name": paths[role].name, "sha256": source_hashes[role]}
            for role in RASTER_ROLES
        },
        "layover_shadow_masks": {
            role: {
                "file_name": masks[role].name,
                "sha256": mask_hashes[role],
                "supported_value": 0,
            }
            for role in sorted(masks)
        },
        "window_measurements": measurements,
        "accepted_window_count": sum(len(rows) for rows in accepted_by_pol.values()),
        "accepted_window_count_by_polarization": {
            polarization: len(rows)
            for polarization, rows in accepted_by_pol.items()
        },
        "polarization_median_shifts_pixels": {
            polarization: {
                "row": _round(values[0]),
                "column": _round(values[1]),
            }
            for polarization, values in medians.items()
        },
        "combined_median_shift_pixels": {
            "row": _round(float(combined[0])),
            "column": _round(float(combined[1])),
            "magnitude": _round(median_magnitude),
        },
        "p90_radial_dispersion_pixels": _round(p90_dispersion),
        "polarization_median_disagreement_pixels": _round(
            polarization_disagreement
        ),
        "minimum_accepted_peak_to_sidelobe_ratio": _round(minimum_psr),
        "registration_error_pixels": _round(diagnostic_envelope),
        "registration_gate_passed": (
            diagnostic_envelope <= MAX_GEOREGISTRATION_ERROR_PIXELS
        ),
        "safety": _safety_contract(),
        "limitations": (
            "Scene correlation is not independent control-point or geodetic "
            "validation. Flooding, speckle, land-cover change, and residual "
            "terrain effects can bias or weaken the diagnostic. No pixel is "
            "classified as flood or dry by this procedure."
        ),
    }
    return _self_hashed(payload)


def _phase_correlation_shift(
    reference: np.ndarray,
    moving: np.ndarray,
    valid: np.ndarray,
    *,
    maximum_shift: int,
) -> dict[str, object]:
    support = _erode_one_pixel(np.asarray(valid, dtype=bool))
    if int(support.sum()) < 64:
        raise RegistrationEvidenceError("insufficient_eroded_support")
    reference_z = _robust_standardize(reference, support)
    moving_z = _robust_standardize(moving, support)
    ref_y, ref_x = np.gradient(reference_z)
    mov_y, mov_x = np.gradient(moving_z)
    window = np.outer(np.hanning(reference.shape[0]), np.hanning(reference.shape[1]))
    weighted_support = support.astype(float) * window
    ref_y *= weighted_support
    ref_x *= weighted_support
    mov_y *= weighted_support
    mov_x *= weighted_support
    gradient_energy = float(
        np.sqrt(np.mean((ref_y[support] ** 2 + ref_x[support] ** 2)))
        * np.sqrt(np.mean((mov_y[support] ** 2 + mov_x[support] ** 2)))
    )
    if not math.isfinite(gradient_energy) or gradient_energy <= 1e-8:
        raise RegistrationEvidenceError("insufficient_texture")

    cross = (
        np.fft.fft2(ref_y) * np.conj(np.fft.fft2(mov_y))
        + np.fft.fft2(ref_x) * np.conj(np.fft.fft2(mov_x))
    )
    magnitude = np.abs(cross)
    usable = magnitude > np.finfo(float).eps
    if int(usable.sum()) < 16:
        raise RegistrationEvidenceError("insufficient_frequency_support")
    cross_power = np.zeros_like(cross)
    cross_power[usable] = cross[usable] / magnitude[usable]
    correlation = np.abs(np.fft.ifft2(cross_power))

    candidates = list(range(0, maximum_shift + 1)) + list(
        range(reference.shape[0] - maximum_shift, reference.shape[0])
    )
    candidate_columns = list(range(0, maximum_shift + 1)) + list(
        range(reference.shape[1] - maximum_shift, reference.shape[1])
    )
    best = max(
        ((row, column) for row in candidates for column in candidate_columns),
        key=lambda index: (correlation[index], -index[0], -index[1]),
    )
    row_index, column_index = best
    row_integer = _signed_fft_index(row_index, reference.shape[0])
    column_integer = _signed_fft_index(column_index, reference.shape[1])
    row_delta = _parabolic_offset(
        correlation[(row_index - 1) % reference.shape[0], column_index],
        correlation[row_index, column_index],
        correlation[(row_index + 1) % reference.shape[0], column_index],
    )
    column_delta = _parabolic_offset(
        correlation[row_index, (column_index - 1) % reference.shape[1]],
        correlation[row_index, column_index],
        correlation[row_index, (column_index + 1) % reference.shape[1]],
    )
    row_shift = float(row_integer + row_delta)
    column_shift = float(column_integer + column_delta)

    sidelobes = correlation.copy()
    for row_delta_index in range(-2, 3):
        for column_delta_index in range(-2, 3):
            sidelobes[
                (row_index + row_delta_index) % reference.shape[0],
                (column_index + column_delta_index) % reference.shape[1],
            ] = np.nan
    background = sidelobes[np.isfinite(sidelobes)]
    background_std = float(np.std(background))
    if background_std <= np.finfo(float).eps:
        psr = float("inf")
    else:
        psr = (float(correlation[best]) - float(np.mean(background))) / background_std
    if not math.isfinite(psr):
        # Exact equality can create a mathematically infinite PSR; use a large,
        # stable finite value so strict JSON never emits Infinity.
        psr = 1_000_000.0
    return {
        "row_shift_pixels": _round(row_shift),
        "column_shift_pixels": _round(column_shift),
        "shift_magnitude_pixels": _round(math.hypot(row_shift, column_shift)),
        "peak_to_sidelobe_ratio": _round(psr),
        "peak_on_search_boundary": (
            abs(row_integer) == maximum_shift
            or abs(column_integer) == maximum_shift
        ),
        "gradient_energy": _round(gradient_energy),
    }


def _processing_evidence_frame(
    *,
    paths: Mapping[str, Path],
    source_hashes: Mapping[str, str],
    asset_ids: Mapping[str, str],
    signature: _RasterSignature,
    valid_summaries: Mapping[str, Mapping[str, object]],
    coverage_paths: Mapping[str, Path],
    valid_paths: Mapping[str, Path],
    final_paths: Mapping[str, Mapping[str, Path]],
    registration_path: Path,
    registration_sha256: str,
    registration: Mapping[str, object],
    timestamp: str,
    processing_software: str,
    processing_software_version: str,
    rtc_method: str,
    resampling_method: str,
) -> pd.DataFrame:
    error = float(registration["registration_error_pixels"])
    confidence = "medium" if error <= MAX_GEOREGISTRATION_ERROR_PIXELS else "low"
    method = str(registration["method"])
    rows: list[dict[str, object]] = []
    for role in RASTER_ROLES:
        mask_note = (
            "; corresponding acquisition layover/shadow mask value 0 required"
            if registration["layover_shadow_masks"]
            else "; no separate layover/shadow masks supplied"
        )
        rows.append(
            {
                "asset_id": asset_ids[role],
                "processed_artifact_id": f"RTC-{asset_ids[role]}",
                "processed_file_path": str(paths[role]),
                "processed_file_sha256": source_hashes[role],
                "processing_software": processing_software,
                "processing_software_version": processing_software_version,
                "rtc_terrain_correction_method": rtc_method,
                "output_crs": signature.crs_text,
                "affine_a": signature.affine[0],
                "affine_b": signature.affine[1],
                "affine_c": signature.affine[2],
                "affine_d": signature.affine[3],
                "affine_e": signature.affine[4],
                "affine_f": signature.affine[5],
                "width_pixels": signature.width,
                "height_pixels": signature.height,
                "pixel_size_x_m": signature.pixel_size_x,
                "pixel_size_y_m": signature.pixel_size_y,
                "nodata_convention": (
                    f"explicit GeoTIFF nodata={signature.nodata}; nonfinite excluded"
                    + mask_note
                ),
                "resampling_method": resampling_method,
                "coverage_fraction": 1.0,
                "valid_data_fraction": valid_summaries[role]["valid_data_fraction"],
                "coverage_evidence_path": str(final_paths[role]["coverage"]),
                "coverage_evidence_sha256": _file_sha256(coverage_paths[role]),
                "valid_data_evidence_path": str(final_paths[role]["valid"]),
                "valid_data_evidence_sha256": _file_sha256(valid_paths[role]),
                "registration_method": method,
                "registration_error_pixels": error,
                "registration_evidence_path": str(registration_path),
                "registration_evidence_sha256": registration_sha256,
                "grid_contract_sha256": signature.grid_contract_sha256,
                "source_timestamp": timestamp,
                "confidence_class": confidence,
                "assumptions": (
                    "Residual registration is a scene-correlation diagnostic, not "
                    "independent control-point truth. Unsupported cells are not dry "
                    "labels. Report/query-model evidence only."
                ),
                **_safety_contract(),
            }
        )
    return pd.DataFrame(rows, columns=PROCESSING_EVIDENCE_COLUMNS).sort_values(
        "asset_id", kind="stable"
    ).reset_index(drop=True)


def _coverage_summary(
    role: str,
    *,
    raster_path: Path,
    raster_sha256: str,
    signature: _RasterSignature,
    timestamp: str,
) -> dict[str, object]:
    return _self_hashed(
        {
            "artifact_schema": COVERAGE_EVIDENCE_SCHEMA,
            "source_timestamp": timestamp,
            "raster_role": role,
            "source": {"file_name": raster_path.name, "sha256": raster_sha256},
            "grid": signature.as_json(),
            "coverage_definition": (
                "The raster affine and dimensions cover every cell of the declared "
                "common grid. Pixel support is reported separately as valid data."
            ),
            "coverage_fraction": 1.0,
            "covered_cell_count": signature.cell_count,
            "grid_cell_count": signature.cell_count,
            "safety": _safety_contract(),
        }
    )


def _valid_data_summary(
    role: str,
    valid: np.ndarray,
    *,
    raster_path: Path,
    raster_sha256: str,
    mask_path: Path | None,
    mask_sha256: str | None,
    signature: _RasterSignature,
    timestamp: str,
) -> dict[str, object]:
    valid_count = int(valid.sum())
    payload: dict[str, object] = {
        "artifact_schema": VALID_DATA_EVIDENCE_SCHEMA,
        "source_timestamp": timestamp,
        "raster_role": role,
        "source": {"file_name": raster_path.name, "sha256": raster_sha256},
        "validity_definition": (
            "Raster cell is unmasked by GeoTIFF nodata, finite, and, when a "
            "layover/shadow mask is supplied, has mask value 0."
        ),
        "valid_cell_count": valid_count,
        "invalid_cell_count": signature.cell_count - valid_count,
        "cell_count": signature.cell_count,
        "valid_data_fraction": _round(valid_count / signature.cell_count),
        "layover_shadow_mask": None,
        "safety": _safety_contract(),
    }
    if mask_path is not None:
        payload["layover_shadow_mask"] = {
            "file_name": mask_path.name,
            "sha256": mask_sha256,
            "supported_value": 0,
        }
    return _self_hashed(payload)


def _validate_common_raster_grid(datasets: Mapping[str, Any]) -> _RasterSignature:
    signatures: dict[str, _RasterSignature] = {}
    for role in RASTER_ROLES:
        dataset = datasets[role]
        if dataset.count != 1:
            raise RegistrationEvidenceError(f"{role} must be single-band.")
        if dataset.crs is None or not dataset.crs.is_projected:
            raise RegistrationEvidenceError(f"{role} must have a projected CRS.")
        transform = dataset.transform
        if not (
            transform.a > 0
            and transform.e < 0
            and transform.b == 0
            and transform.d == 0
        ):
            raise RegistrationEvidenceError(
                f"{role} must use a north-up, unrotated affine."
            )
        if dataset.nodata is None or not math.isfinite(float(dataset.nodata)):
            raise RegistrationEvidenceError(
                f"{role} must declare a finite explicit nodata value."
            )
        grid_hash = _casefold_tag(dataset.tags(), GRID_CONTRACT_TAG)
        if grid_hash is None or _SHA256_PATTERN.fullmatch(grid_hash) is None:
            raise RegistrationEvidenceError(
                f"{role} must have a lowercase complete {GRID_CONTRACT_TAG} tag."
            )
        signatures[role] = _RasterSignature(
            crs_wkt=dataset.crs.to_wkt(),
            crs_text=dataset.crs.to_string(),
            affine=tuple(float(value) for value in transform[:6]),
            width=int(dataset.width),
            height=int(dataset.height),
            dtype=str(dataset.dtypes[0]),
            nodata=float(dataset.nodata),
            grid_contract_sha256=grid_hash,
        )
    reference = signatures[RASTER_ROLES[0]]
    for role in RASTER_ROLES[1:]:
        if signatures[role] != reference:
            raise RegistrationEvidenceError(
                f"{role} does not exactly match {RASTER_ROLES[0]} for CRS, "
                "affine, dimensions, dtype, nodata, and grid identity."
            )
    return reference


def _validate_masks(
    masks: Mapping[str, Any], signature: _RasterSignature
) -> None:
    for role, dataset in masks.items():
        if dataset.count != 1:
            raise RegistrationEvidenceError(f"{role} mask must be single-band.")
        if dataset.crs is None:
            raise RegistrationEvidenceError(f"{role} mask has no CRS.")
        grid_hash = _casefold_tag(dataset.tags(), GRID_CONTRACT_TAG)
        observed = (
            dataset.crs.to_wkt(),
            tuple(float(value) for value in dataset.transform[:6]),
            int(dataset.width),
            int(dataset.height),
            grid_hash,
        )
        expected = (
            signature.crs_wkt,
            signature.affine,
            signature.width,
            signature.height,
            signature.grid_contract_sha256,
        )
        if observed != expected:
            raise RegistrationEvidenceError(
                f"{role} layover/shadow mask does not match the SAR common grid."
            )


def _read_rasters(
    datasets: Mapping[str, Any], mask_datasets: Mapping[str, Any]
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    arrays: dict[str, np.ndarray] = {}
    valid: dict[str, np.ndarray] = {}
    acquisition_support: dict[str, np.ndarray] = {}
    for acquisition, dataset in mask_datasets.items():
        masked = dataset.read(1, masked=True)
        values = np.asarray(masked.data)
        acquisition_support[acquisition] = (
            ~np.ma.getmaskarray(masked) & np.isfinite(values) & (values == 0)
        )
    for role, dataset in datasets.items():
        masked = dataset.read(1, masked=True)
        values = np.asarray(masked.data, dtype=np.float64)
        support = ~np.ma.getmaskarray(masked) & np.isfinite(values)
        if _acquisition(role) in acquisition_support:
            support &= acquisition_support[_acquisition(role)]
        if not bool(support.any()):
            raise RegistrationEvidenceError(f"{role} has no valid data support.")
        arrays[role] = values
        valid[role] = support
    return arrays, valid


def _robust_standardize(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    selected = np.asarray(values, dtype=float)[valid]
    median = float(np.median(selected))
    q25, q75 = (float(value) for value in np.percentile(selected, [25, 75]))
    scale = (q75 - q25) / 1.349
    if not math.isfinite(scale) or scale <= 1e-8:
        scale = float(np.std(selected))
    if not math.isfinite(scale) or scale <= 1e-8:
        raise RegistrationEvidenceError("insufficient_texture")
    prepared = np.zeros(values.shape, dtype=float)
    prepared[valid] = np.clip((values[valid] - median) / scale, -5.0, 5.0)
    return prepared


def _erode_one_pixel(mask: np.ndarray) -> np.ndarray:
    result = mask.copy()
    result[0, :] = False
    result[-1, :] = False
    result[:, 0] = False
    result[:, -1] = False
    interior = mask[1:-1, 1:-1]
    result[1:-1, 1:-1] = (
        interior
        & mask[:-2, 1:-1]
        & mask[2:, 1:-1]
        & mask[1:-1, :-2]
        & mask[1:-1, 2:]
    )
    return result


def _window_origins(height: int, width: int, size: int) -> list[tuple[int, int]]:
    def origins(length: int) -> list[int]:
        values = list(range(0, length - size + 1, size))
        last = length - size
        if last not in values:
            values.append(last)
        return sorted(values)

    return [(row, column) for row in origins(height) for column in origins(width)]


def _parabolic_offset(left: float, center: float, right: float) -> float:
    denominator = left - 2.0 * center + right
    if abs(denominator) <= np.finfo(float).eps:
        return 0.0
    offset = 0.5 * (left - right) / denominator
    return float(np.clip(offset, -0.5, 0.5))


def _signed_fft_index(index: int, length: int) -> int:
    return index if index <= length // 2 else index - length


def _coerce_raster_paths(**values: str | Path) -> dict[str, Path]:
    paths = {role: _existing_file(values[role], f"{role} raster") for role in RASTER_ROLES}
    if len({path.resolve() for path in paths.values()}) != len(RASTER_ROLES):
        raise RegistrationEvidenceError("The four SAR rasters must be distinct files.")
    return paths


def _coerce_mask_paths(
    *, pre: str | Path | None, event: str | Path | None
) -> dict[str, Path]:
    if (pre is None) != (event is None):
        raise RegistrationEvidenceError(
            "Pre and event layover/shadow masks must be supplied together or both omitted."
        )
    result: dict[str, Path] = {}
    if pre is not None:
        result["pre"] = _existing_file(pre, "pre layover/shadow mask")
    if event is not None:
        result["event"] = _existing_file(event, "event layover/shadow mask")
    return result


def _coerce_asset_ids(values: Mapping[str, str]) -> dict[str, str]:
    if set(values) != set(RASTER_ROLES):
        raise RegistrationEvidenceError(
            f"asset_ids must map exactly: {', '.join(RASTER_ROLES)}."
        )
    normalized: dict[str, str] = {}
    for role in RASTER_ROLES:
        asset_id = str(values[role]).strip()
        if _ID_PATTERN.fullmatch(asset_id) is None:
            raise RegistrationEvidenceError(f"Invalid asset id for {role}.")
        normalized[role] = asset_id
    if len(set(normalized.values())) != len(RASTER_ROLES):
        raise RegistrationEvidenceError(
            "Each polarization/acquisition raster requires a distinct asset id."
        )
    return normalized


def _existing_file(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise RegistrationEvidenceError(f"{label} does not exist: {path}")
    return path


def _load_rasterio() -> Any:
    try:
        import rasterio
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RegistrationEvidenceError(
            "Registration evidence requires rasterio and NumPy."
        ) from exc
    return rasterio


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RegistrationEvidenceError(f"Could not hash {path}: {exc}") from exc
    return digest.hexdigest()


def _self_hashed(payload: Mapping[str, object]) -> dict[str, object]:
    unsigned = dict(payload)
    unsigned.pop("manifest_sha256", None)
    return {**unsigned, "manifest_sha256": _canonical_json_sha256(unsigned)}


def _canonical_json_sha256(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _canonical_utc_timestamp(value: datetime | str) -> str:
    try:
        parsed = parse_utc_datetime(value, "source_timestamp_utc")
    except Exception as exc:
        raise RegistrationEvidenceError(str(exc)) from exc
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _meaningful_text(value: str, label: str) -> str:
    text = str(value).strip()
    if len(text) < 3 or text.casefold() in {"na", "n/a", "none", "unknown", "tbd"}:
        raise RegistrationEvidenceError(f"{label} requires specific evidence.")
    return text


def _casefold_tag(tags: Mapping[str, str], target: str) -> str | None:
    values = [value for key, value in tags.items() if key.casefold() == target.casefold()]
    if len(values) > 1:
        raise RegistrationEvidenceError(f"Duplicate raster tag {target!r}.")
    return values[0].strip().lower() if values else None


def _acquisition(role: str) -> str:
    return "pre" if role.startswith("pre_") else "event"


def _round(value: float) -> float:
    return round(float(value), 12)


def _safety_contract() -> dict[str, bool]:
    return {
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
