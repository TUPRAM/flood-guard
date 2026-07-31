"""Generate deterministic, authority-pending SAR review-display candidates.

This module creates continuous pre-minus-event VV/VH dB change rasters and a
fixed-stretch RGB composite from already governed, common-grid Sentinel-1
rasters. Display parameters are supplied before any statistics are computed;
reported statistics never influence the outputs. The products are review
evidence candidates only and remain ineligible for decisions, FPPS, warnings,
or model training.
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
    EventRegistryError,
    format_utc_datetime,
    parse_utc_datetime,
)
from floodguard.label_factory.processing_alignment import (
    ProcessingAlignmentError,
    ReceiptInput as ProcessingReceiptInput,
    validate_processing_alignment_receipt,
)
from floodguard.label_factory.review_derivatives import (
    REVIEW_DERIVATIVE_BUILD_SPEC_SCHEMA,
)
from floodguard.label_factory.rights_clearance import (
    RightsClearanceError,
    validate_rights_clearance_package,
)


REVIEW_DERIVATIVE_GENERATION_SCHEMA = (
    "floodguard.review_derivative_candidate_generation.v1"
)
REVIEW_DERIVATIVE_GENERATOR_ID = "floodguard_review_derivative_generator_v1"
REVIEW_DERIVATIVE_GENERATOR_VERSION = "1.0.0"
AUTHORITY_APPROVAL_STATUS = "authority_approval_pending"
CHANGE_NODATA = -9999.0
COLOR_MAP_ID = "floodguard_blue_neutral_red_v1"
COLOR_HEX = ("#2166AC", "#F7F7F7", "#B2182B")

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")


class ReviewDerivativeGenerationError(ValueError):
    """Raised when a candidate display cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class ReviewDerivativeCandidatePaths:
    """Write-once output paths from one candidate generation."""

    vv_change: Path
    vh_change: Path
    fixed_stretch_change_composite: Path
    build_spec: Path
    generation_manifest: Path

    def as_dict(self) -> dict[str, Path]:
        return {
            "vv_change": self.vv_change,
            "vh_change": self.vh_change,
            "fixed_stretch_change_composite": self.fixed_stretch_change_composite,
            "build_spec": self.build_spec,
            "generation_manifest": self.generation_manifest,
        }


def build_and_write_review_derivative_candidates(
    *,
    event_id: str,
    derivative_set_id: str,
    pre_vv_asset_id: str,
    pre_vv_path: str | Path,
    event_vv_asset_id: str,
    event_vv_path: str | Path,
    pre_vh_asset_id: str,
    pre_vh_path: str | Path,
    event_vh_asset_id: str,
    event_vh_path: str | Path,
    processing_alignment_receipt: ProcessingReceiptInput,
    output_directory: str | Path,
    governance_package: str | Path | None = None,
    generated_at_utc: datetime | str | None = None,
    fixed_stretch_min_db: float = -10.0,
    fixed_stretch_max_db: float = 10.0,
    allow_ungoverned_fixture: bool = False,
) -> ReviewDerivativeCandidatePaths:
    """Generate three fixed reviewer displays and their exact build spec.

    Production generation requires the governed event/source registries and
    processing receipt. The fixture escape hatch is test-only and always
    records production-review ineligibility in the generation manifest; the
    later production derivative receipt still requires governance.
    """

    event = _identifier(event_id, "event_id")
    set_id = _identifier(derivative_set_id, "derivative_set_id")
    stretch_min = _finite_number(fixed_stretch_min_db, "fixed_stretch_min_db")
    stretch_max = _finite_number(fixed_stretch_max_db, "fixed_stretch_max_db")
    if stretch_min >= 0 or stretch_max <= 0 or not math.isclose(
        abs(stretch_min), stretch_max, rel_tol=0.0, abs_tol=1e-12
    ):
        raise ReviewDerivativeGenerationError(
            "The candidate stretch must be finite, symmetric around zero, and "
            "span both negative and positive dB change."
        )
    target = Path(output_directory)
    if target.exists():
        raise ReviewDerivativeGenerationError(
            f"Candidate output directory is immutable and already exists: {target}"
        )
    generated_at = _coerce_utc(generated_at_utc)
    processing, governance = _validate_processing_and_governance(
        processing_alignment_receipt,
        governance_package=governance_package,
        allow_ungoverned_fixture=allow_ungoverned_fixture,
    )
    event_assets = {
        str(row["asset_id"]): row
        for row in processing["assets"]
        if str(row["event_id"]) == event
    }
    if not event_assets:
        raise ReviewDerivativeGenerationError(
            f"Processing receipt has no assets for event {event!r}."
        )
    governed_polarizations = _governed_polarizations(governance_package)
    declared_sources = (
        ("pre_event", "VV", pre_vv_asset_id, pre_vv_path),
        ("event_time", "VV", event_vv_asset_id, event_vv_path),
        ("pre_event", "VH", pre_vh_asset_id, pre_vh_path),
        ("event_time", "VH", event_vh_asset_id, event_vh_path),
    )
    source_bindings: dict[tuple[str, str], dict[str, Any]] = {}
    supplied_ids: list[str] = []
    for role, polarization, raw_asset_id, raw_path in declared_sources:
        asset_id = _identifier(raw_asset_id, f"{role}_{polarization}_asset_id")
        supplied_ids.append(asset_id)
        asset = event_assets.get(asset_id)
        if asset is None:
            raise ReviewDerivativeGenerationError(
                f"Source asset {asset_id!r} is absent from the processing receipt."
            )
        if str(asset["event_relative_role"]) != role:
            raise ReviewDerivativeGenerationError(
                f"Source asset {asset_id!r} is not the declared {role} raster."
            )
        if governed_polarizations is not None and governed_polarizations.get(
            asset_id
        ) != (polarization,):
            raise ReviewDerivativeGenerationError(
                f"Source asset {asset_id!r} is not governed as {polarization}."
            )
        path = _existing_file(raw_path, f"{role}_{polarization}_path")
        actual_hash = _file_sha256(path)
        if (
            path.name != str(asset["processed_file_name"])
            or actual_hash != str(asset["processed_file_sha256"])
        ):
            raise ReviewDerivativeGenerationError(
                f"Source {asset_id!r} filename or bytes do not match the "
                "processing receipt."
            )
        source_bindings[(role, polarization)] = {
            "asset": asset,
            "path": path,
            "sha256": actual_hash,
        }
    if set(supplied_ids) != set(event_assets) or len(supplied_ids) != len(
        set(supplied_ids)
    ):
        raise ReviewDerivativeGenerationError(
            "Candidate sources must exactly and uniquely cover the event's four "
            "processed VV/VH assets."
        )

    _preflight_rasters(source_bindings, processing)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target.parent)
    )
    names = {
        "vv_change": "mae_sai_20240903_20240915_vv_change_db.tif",
        "vh_change": "mae_sai_20240903_20240915_vh_change_db.tif",
        "fixed_stretch_change_composite": (
            "mae_sai_20240903_20240915_fixed_change_rgb.tif"
        ),
        "build_spec": "review_derivative_build_spec_v1.json",
        "generation_manifest": "candidate_display_generation_manifest_v1.json",
    }
    try:
        generated = _generate_candidate_rasters(
            temporary=temporary,
            names=names,
            event_id=event,
            derivative_set_id=set_id,
            processing=processing,
            source_bindings=source_bindings,
            stretch_min=stretch_min,
            stretch_max=stretch_max,
        )
        output_hashes = {
            role: _file_sha256(path)
            for role, path in generated["paths"].items()
        }
        output_sizes = {
            role: path.stat().st_size
            for role, path in generated["paths"].items()
        }
        source_inputs = []
        for (role, polarization), binding in sorted(source_bindings.items()):
            asset = binding["asset"]
            description = generated["source_descriptions"][
                (role, polarization)
            ]
            source_inputs.append(
                {
                    "asset_id": asset["asset_id"],
                    "processed_file_path": str(binding["path"].resolve()),
                    "processed_file_sha256": binding["sha256"],
                    "polarizations": [polarization],
                    "band_by_polarization": {
                        polarization: f"band_1:{description}"
                    },
                }
            )
        grid = generated["grid"]
        common_layer = {
            "output_crs": grid["crs"],
            "affine_transform": grid["affine_transform"],
            "width_pixels": grid["width_pixels"],
            "height_pixels": grid["height_pixels"],
            "confidence_class": "low",
            "formal_review_display_only": True,
            "allowed_for_blinded_review": True,
            "query_model_only": True,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }
        pre_vv = source_bindings[("pre_event", "VV")]["asset"]
        event_vv = source_bindings[("event_time", "VV")]["asset"]
        pre_vh = source_bindings[("pre_event", "VH")]["asset"]
        event_vh = source_bindings[("event_time", "VH")]["asset"]
        color_stops = [
            {"value": stretch_min, "hex": COLOR_HEX[0]},
            {"value": 0.0, "hex": COLOR_HEX[1]},
            {"value": stretch_max, "hex": COLOR_HEX[2]},
        ]
        change_display = {
            "renderer": "single_band_fixed_stretch",
            "stretch_min": stretch_min,
            "stretch_max": stretch_max,
            "gamma": 1.0,
            "clamp": True,
            "color_map_id": COLOR_MAP_ID,
            "color_stops": color_stops,
            "resampling": "nearest",
        }
        vv_id = f"{set_id}-VV-CHANGE"
        vh_id = f"{set_id}-VH-CHANGE"
        rgb_id = f"{set_id}-FIXED-RGB"
        vv_final = target / names["vv_change"]
        vh_final = target / names["vh_change"]
        rgb_final = target / names["fixed_stretch_change_composite"]
        layers = [
            {
                "derivative_id": vv_id,
                "layer_role": "vv_change",
                "output_file_path": str(vv_final.resolve()),
                "output_file_sha256": output_hashes["vv_change"],
                "display_name": (
                    "Mae Sai VV change, pre minus event dB, fixed "
                    f"{stretch_min:g}..{stretch_max:+g}"
                ),
                "path_hint": f"review_context/{target.name}/{vv_final.name}",
                "nodata_convention": (
                    "float32 nodata=-9999.0; valid only where governed pre/event "
                    "VV source cells are finite and valid"
                ),
                "output_dtype": "float32",
                "transformation_parameters": {
                    "operation": "pre_minus_event_db",
                    "expression": "pre_db - event_db",
                    "polarization": "VV",
                    "pre_input_asset_id": pre_vv["asset_id"],
                    "event_input_asset_id": event_vv["asset_id"],
                    "pre_band": f"band_1:{generated['source_descriptions'][('pre_event', 'VV')]}",
                    "event_band": f"band_1:{generated['source_descriptions'][('event_time', 'VV')]}",
                    "input_units": "dB",
                    "output_units": "dB_change",
                    "validity_rule": "valid_where_both_inputs_valid",
                },
                "display_parameters": dict(change_display),
                "assumptions": (
                    "Authority-approval-pending fixed display candidate. Positive "
                    "values are backscatter drops, not flood truth."
                ),
                **common_layer,
            },
            {
                "derivative_id": vh_id,
                "layer_role": "vh_change",
                "output_file_path": str(vh_final.resolve()),
                "output_file_sha256": output_hashes["vh_change"],
                "display_name": (
                    "Mae Sai VH change, pre minus event dB, fixed "
                    f"{stretch_min:g}..{stretch_max:+g}"
                ),
                "path_hint": f"review_context/{target.name}/{vh_final.name}",
                "nodata_convention": (
                    "float32 nodata=-9999.0; valid only where governed pre/event "
                    "VH source cells are finite and valid"
                ),
                "output_dtype": "float32",
                "transformation_parameters": {
                    "operation": "pre_minus_event_db",
                    "expression": "pre_db - event_db",
                    "polarization": "VH",
                    "pre_input_asset_id": pre_vh["asset_id"],
                    "event_input_asset_id": event_vh["asset_id"],
                    "pre_band": f"band_1:{generated['source_descriptions'][('pre_event', 'VH')]}",
                    "event_band": f"band_1:{generated['source_descriptions'][('event_time', 'VH')]}",
                    "input_units": "dB",
                    "output_units": "dB_change",
                    "validity_rule": "valid_where_both_inputs_valid",
                },
                "display_parameters": dict(change_display),
                "assumptions": (
                    "Authority-approval-pending fixed display candidate. Positive "
                    "values are backscatter drops, not flood truth."
                ),
                **common_layer,
            },
            {
                "derivative_id": rgb_id,
                "layer_role": "fixed_stretch_change_composite",
                "output_file_path": str(rgb_final.resolve()),
                "output_file_sha256": output_hashes[
                    "fixed_stretch_change_composite"
                ],
                "display_name": "Mae Sai fixed VV/VH change RGB candidate",
                "path_hint": f"review_context/{target.name}/{rgb_final.name}",
                "nodata_convention": (
                    "three uint8 RGB bands with internal per-dataset validity mask; "
                    "valid only where all four governed input cells are valid"
                ),
                "output_dtype": "uint8",
                "transformation_parameters": {
                    "operation": "fixed_stretch_rgb_composite",
                    "input_derivative_ids": [vv_id, vh_id],
                    "red_expression": _channel_expression(
                        "vv_change_db", stretch_min, stretch_max
                    ),
                    "green_expression": _channel_expression(
                        "vh_change_db", stretch_min, stretch_max
                    ),
                    "blue_expression": _channel_expression(
                        "((vv_change_db + vh_change_db) / 2.0)",
                        stretch_min,
                        stretch_max,
                    ),
                    "validity_rule": "valid_where_all_inputs_valid",
                    "channel_min": 0,
                    "channel_max": 255,
                },
                "display_parameters": {
                    "renderer": "rgb_pre_stretched",
                    "red_band": 1,
                    "green_band": 2,
                    "blue_band": 3,
                    "gamma": 1.0,
                    "resampling": "nearest",
                },
                "assumptions": (
                    "Authority-approval-pending fixed RGB candidate: R=VV change, "
                    "G=VH change, B=their mean; no channel is flood truth."
                ),
                **common_layer,
            },
        ]
        build_spec = {
            "artifact_schema": REVIEW_DERIVATIVE_BUILD_SPEC_SCHEMA,
            "derivative_set_id": set_id,
            "event_id": event,
            "generated_at_utc": format_utc_datetime(generated_at),
            "processing_software": REVIEW_DERIVATIVE_GENERATOR_ID,
            "processing_software_version": (
                f"{REVIEW_DERIVATIVE_GENERATOR_VERSION};"
                f"rasterio={generated['rasterio_version']};"
                f"gdal={generated['gdal_version']};numpy={np.__version__}"
            ),
            "source_inputs": source_inputs,
            "layers": layers,
            "assumptions": (
                f"Authority approval pending. Fixed {stretch_min:g}..{stretch_max:+g} dB displays were "
                "declared before reporting statistics. These are reviewer evidence "
                "candidates, not validation truth, decision input, FPPS, or warning."
            ),
            "formal_review_display_only": True,
            "allowed_for_blinded_review": True,
            "query_model_only": True,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }
        build_spec_path = temporary / names["build_spec"]
        build_spec_path.write_text(
            json.dumps(build_spec, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
        manifest_without_hash = {
            "artifact_schema": REVIEW_DERIVATIVE_GENERATION_SCHEMA,
            "generator": REVIEW_DERIVATIVE_GENERATOR_ID,
            "generator_version": REVIEW_DERIVATIVE_GENERATOR_VERSION,
            "generated_at_utc": format_utc_datetime(generated_at),
            "event_id": event,
            "derivative_set_id": set_id,
            "authority_approval_status": AUTHORITY_APPROVAL_STATUS,
            "governance_binding": governance,
            "processing_alignment_receipt_sha256": processing["receipt_sha256"],
            "source_registry_sha256": processing["source_registry_sha256"],
            "grid_contract_sha256": grid["grid_contract_sha256"],
            "fixed_display_parameters": {
                "stretch_min_db": stretch_min,
                "stretch_max_db": stretch_max,
                "gamma": 1.0,
                "color_map_id": COLOR_MAP_ID,
                "color_stops": color_stops,
                "rgb_channels": {
                    "red": "fixed_scaled_vv_change_db",
                    "green": "fixed_scaled_vh_change_db",
                    "blue": "fixed_scaled_mean_vv_vh_change_db",
                },
                "statistics_influence_display": False,
            },
            "source_rasters": [
                {
                    "asset_id": binding["asset"]["asset_id"],
                    "event_relative_role": role,
                    "polarization": polarization,
                    "file_name": binding["path"].name,
                    "sha256": binding["sha256"],
                }
                for (role, polarization), binding in sorted(source_bindings.items())
            ],
            "outputs": [
                {
                    "layer_role": role,
                    "file_name": generated["paths"][role].name,
                    "file_size_bytes": output_sizes[role],
                    "sha256": output_hashes[role],
                }
                for role in sorted(generated["paths"])
            ],
            "reported_statistics": generated["statistics"],
            "build_spec_file_name": names["build_spec"],
            "build_spec_sha256": _file_sha256(build_spec_path),
            "formal_review_display_only": True,
            "query_model_only": True,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
            "assumptions": (
                "Reported statistics are after-the-fact QA only and did not set "
                "the fixed display. Authority scientific approval is still required."
            ),
        }
        generation_manifest = {
            **manifest_without_hash,
            "manifest_sha256": _canonical_json_sha256(manifest_without_hash),
        }
        manifest_path = temporary / names["generation_manifest"]
        manifest_path.write_text(
            json.dumps(
                generation_manifest,
                ensure_ascii=True,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        if target.exists():
            raise ReviewDerivativeGenerationError(
                f"Candidate output directory appeared during generation: {target}"
            )
        temporary.rename(target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return ReviewDerivativeCandidatePaths(
        vv_change=target / names["vv_change"],
        vh_change=target / names["vh_change"],
        fixed_stretch_change_composite=(
            target / names["fixed_stretch_change_composite"]
        ),
        build_spec=target / names["build_spec"],
        generation_manifest=target / names["generation_manifest"],
    )


def validate_review_derivative_candidate_outputs(
    output_directory: str | Path,
) -> dict[str, Any]:
    """Re-hash and structurally validate one generated candidate directory."""

    root = Path(output_directory)
    manifest_path = root / "candidate_display_generation_manifest_v1.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewDerivativeGenerationError(
            f"Could not load candidate generation manifest: {manifest_path}"
        ) from exc
    if not isinstance(manifest, Mapping):
        raise ReviewDerivativeGenerationError(
            "Candidate generation manifest must be a JSON object."
        )
    unsigned = dict(manifest)
    supplied_hash = unsigned.pop("manifest_sha256", None)
    if (
        not isinstance(supplied_hash, str)
        or _SHA256_PATTERN.fullmatch(supplied_hash) is None
        or _canonical_json_sha256(unsigned) != supplied_hash
    ):
        raise ReviewDerivativeGenerationError(
            "Candidate generation manifest self-hash mismatch."
        )
    if (
        manifest.get("artifact_schema") != REVIEW_DERIVATIVE_GENERATION_SCHEMA
        or manifest.get("authority_approval_status") != AUTHORITY_APPROVAL_STATUS
        or manifest.get("formal_review_display_only") is not True
        or manifest.get("query_model_only") is not True
        or manifest.get("eligible_for_decision_layer") is not False
        or manifest.get("eligible_for_fpps") is not False
        or manifest.get("eligible_for_warning") is not False
    ):
        raise ReviewDerivativeGenerationError(
            "Candidate generation manifest has unsafe or unsupported semantics."
        )
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != 3:
        raise ReviewDerivativeGenerationError(
            "Candidate generation manifest must bind exactly three outputs."
        )
    for row in outputs:
        if not isinstance(row, Mapping):
            raise ReviewDerivativeGenerationError("Invalid candidate output row.")
        path = root / str(row.get("file_name", ""))
        if not path.is_file() or path.name != str(row.get("file_name", "")):
            raise ReviewDerivativeGenerationError(
                f"Candidate output is missing or unsafe: {path}"
            )
        if path.stat().st_size != row.get("file_size_bytes") or _file_sha256(
            path
        ) != row.get("sha256"):
            raise ReviewDerivativeGenerationError(
                f"Candidate output checksum/size mismatch: {path.name}"
            )
    build_spec = root / str(manifest.get("build_spec_file_name", ""))
    if (
        not build_spec.is_file()
        or _file_sha256(build_spec) != manifest.get("build_spec_sha256")
    ):
        raise ReviewDerivativeGenerationError(
            "Candidate build spec checksum mismatch."
        )
    try:
        build_spec_payload = json.loads(build_spec.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewDerivativeGenerationError(
            "Candidate build spec is not valid JSON."
        ) from exc
    if (
        not isinstance(build_spec_payload, Mapping)
        or build_spec_payload.get("artifact_schema")
        != REVIEW_DERIVATIVE_BUILD_SPEC_SCHEMA
    ):
        raise ReviewDerivativeGenerationError(
            "Candidate build spec schema is unsupported."
        )
    _inspect_generated_rasters(root, manifest, build_spec_payload)
    return dict(manifest)


def _generate_candidate_rasters(
    *,
    temporary: Path,
    names: Mapping[str, str],
    event_id: str,
    derivative_set_id: str,
    processing: Mapping[str, Any],
    source_bindings: Mapping[tuple[str, str], Mapping[str, Any]],
    stretch_min: float,
    stretch_max: float,
) -> dict[str, Any]:
    rasterio = _load_rasterio()
    paths = {
        role: temporary / names[role]
        for role in (
            "vv_change",
            "vh_change",
            "fixed_stretch_change_composite",
        )
    }
    with ExitStack() as stack:
        datasets = {
            key: stack.enter_context(rasterio.open(binding["path"]))
            for key, binding in source_bindings.items()
        }
        reference = datasets[("pre_event", "VV")]
        source_descriptions = {
            key: dataset.descriptions[0] or f"{key[0]}_{key[1]}_band_1"
            for key, dataset in datasets.items()
        }
        arrays: dict[tuple[str, str], np.ndarray] = {}
        valid: dict[tuple[str, str], np.ndarray] = {}
        for key, dataset in datasets.items():
            masked = dataset.read(1, masked=True)
            values = np.asarray(masked.data, dtype=np.float32)
            arrays[key] = values
            valid[key] = ~np.ma.getmaskarray(masked) & np.isfinite(values)
        vv_valid = valid[("pre_event", "VV")] & valid[("event_time", "VV")]
        vh_valid = valid[("pre_event", "VH")] & valid[("event_time", "VH")]
        all_valid = vv_valid & vh_valid
        if not np.any(all_valid):
            raise ReviewDerivativeGenerationError(
                "No cell has valid support across all four SAR inputs."
            )
        vv_change = (
            arrays[("pre_event", "VV")] - arrays[("event_time", "VV")]
        ).astype(np.float32)
        vh_change = (
            arrays[("pre_event", "VH")] - arrays[("event_time", "VH")]
        ).astype(np.float32)
        vv_output = np.where(vv_valid, vv_change, CHANGE_NODATA).astype(np.float32)
        vh_output = np.where(vh_valid, vh_change, CHANGE_NODATA).astype(np.float32)

        grid_hash = str(processing["assets"][0]["grid_contract_sha256"])
        common_tags = {
            "artifact_schema": "floodguard.review_derivative_candidate_raster.v1",
            "authority_approval_status": AUTHORITY_APPROVAL_STATUS,
            "event_id": event_id,
            "derivative_set_id": derivative_set_id,
            "operation": "pre_db - event_db",
            "grid_contract_sha256": grid_hash,
            "processing_alignment_receipt_sha256": str(processing["receipt_sha256"]),
            "formal_review_display_only": "true",
            "query_model_only": "true",
            "eligible_for_decision_layer": "false",
            "eligible_for_fpps": "false",
            "eligible_for_warning": "false",
            "fixed_stretch_min_db": format(stretch_min, ".17g"),
            "fixed_stretch_max_db": format(stretch_max, ".17g"),
            "fixed_gamma": "1.0",
            "statistics_influence_display": "false",
        }
        base_profile = {
            "driver": "GTiff",
            "width": reference.width,
            "height": reference.height,
            "crs": reference.crs,
            "transform": reference.transform,
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256,
            "compress": "DEFLATE",
            "zlevel": 6,
            "num_threads": 1,
            "BIGTIFF": "IF_SAFER",
        }
        float_profile = {
            **base_profile,
            "count": 1,
            "dtype": "float32",
            "nodata": CHANGE_NODATA,
            "predictor": 3,
        }
        for role, values, polarization in (
            ("vv_change", vv_output, "VV"),
            ("vh_change", vh_output, "VH"),
        ):
            with rasterio.open(paths[role], "w", **float_profile) as dst:
                dst.write(values, 1)
                dst.set_band_description(1, f"{role}_pre_minus_event_db")
                dst.update_tags(
                    **common_tags,
                    layer_role=role,
                    polarization=polarization,
                    display_renderer="single_band_fixed_stretch",
                    display_color_map_id=COLOR_MAP_ID,
                    display_color_stops=(
                        f"{stretch_min:g}:{COLOR_HEX[0]};0:{COLOR_HEX[1]};"
                        f"{stretch_max:g}:{COLOR_HEX[2]}"
                    ),
                )

        red = _fixed_scale(vv_change, stretch_min, stretch_max)
        green = _fixed_scale(vh_change, stretch_min, stretch_max)
        blue = _fixed_scale(
            (vv_change.astype(np.float64) + vh_change.astype(np.float64)) / 2.0,
            stretch_min,
            stretch_max,
        )
        rgb_profile = {
            **base_profile,
            "count": 3,
            "dtype": "uint8",
            "nodata": None,
            "predictor": 2,
            "photometric": "RGB",
            "interleave": "PIXEL",
        }
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
            with rasterio.open(
                paths["fixed_stretch_change_composite"], "w", **rgb_profile
            ) as dst:
                dst.write(red, 1)
                dst.write(green, 2)
                dst.write(blue, 3)
                dst.write_mask(all_valid.astype(np.uint8) * 255)
                dst.set_band_description(1, "fixed_scaled_vv_change_db")
                dst.set_band_description(2, "fixed_scaled_vh_change_db")
                dst.set_band_description(3, "fixed_scaled_mean_vv_vh_change_db")
                dst.update_tags(
                    **common_tags,
                    layer_role="fixed_stretch_change_composite",
                    display_renderer="rgb_pre_stretched",
                    red_expression=_channel_expression(
                        "vv_change_db", stretch_min, stretch_max
                    ),
                    green_expression=_channel_expression(
                        "vh_change_db", stretch_min, stretch_max
                    ),
                    blue_expression=_channel_expression(
                        "((vv_change_db + vh_change_db) / 2.0)",
                        stretch_min,
                        stretch_max,
                    ),
                )

        statistics = {
            "valid_cell_count": int(np.count_nonzero(all_valid)),
            "total_cell_count": int(all_valid.size),
            "all_input_valid_fraction": float(np.mean(all_valid)),
            "vv_valid_fraction": float(np.mean(vv_valid)),
            "vh_valid_fraction": float(np.mean(vh_valid)),
            "vv_below_fixed_min_fraction_of_valid": float(
                np.mean(vv_change[all_valid] < stretch_min)
            ),
            "vv_above_fixed_max_fraction_of_valid": float(
                np.mean(vv_change[all_valid] > stretch_max)
            ),
            "vh_below_fixed_min_fraction_of_valid": float(
                np.mean(vh_change[all_valid] < stretch_min)
            ),
            "vh_above_fixed_max_fraction_of_valid": float(
                np.mean(vh_change[all_valid] > stretch_max)
            ),
            "statistics_influence_display": False,
        }
        return {
            "paths": paths,
            "source_descriptions": source_descriptions,
            "grid": {
                "crs": str(reference.crs),
                "affine_transform": list(reference.transform)[:6],
                "width_pixels": reference.width,
                "height_pixels": reference.height,
                "grid_contract_sha256": grid_hash,
            },
            "statistics": statistics,
            "rasterio_version": rasterio.__version__,
            "gdal_version": rasterio.__gdal_version__,
        }


def _preflight_rasters(
    source_bindings: Mapping[tuple[str, str], Mapping[str, Any]],
    processing: Mapping[str, Any],
) -> None:
    rasterio = _load_rasterio()
    expected_grid_hash = str(processing["assets"][0]["grid_contract_sha256"])
    signatures: set[tuple[Any, ...]] = set()
    with ExitStack() as stack:
        for key, binding in source_bindings.items():
            dataset = stack.enter_context(rasterio.open(binding["path"]))
            asset = binding["asset"]
            if dataset.count != 1 or dataset.dtypes != ("float32",):
                raise ReviewDerivativeGenerationError(
                    f"Source {asset['asset_id']!r} must be one float32 dB band."
                )
            if dataset.nodata != CHANGE_NODATA:
                raise ReviewDerivativeGenerationError(
                    f"Source {asset['asset_id']!r} must declare nodata=-9999.0."
                )
            tags = dataset.tags()
            if (
                tags.get("grid_contract_sha256") != expected_grid_hash
                or tags.get("query_model_only") != "true"
                or tags.get("eligible_for_decision_layer") != "false"
                or tags.get("eligible_for_fpps") != "false"
                or tags.get("eligible_for_warning") != "false"
            ):
                raise ReviewDerivativeGenerationError(
                    f"Source {asset['asset_id']!r} has stale/unsafe raster tags."
                )
            expected_signature = (
                str(asset["output_crs"]),
                tuple(float(value) for value in asset["affine_transform"]),
                int(asset["width_pixels"]),
                int(asset["height_pixels"]),
            )
            actual_signature = (
                str(dataset.crs),
                tuple(list(dataset.transform)[:6]),
                dataset.width,
                dataset.height,
            )
            if actual_signature != expected_signature:
                raise ReviewDerivativeGenerationError(
                    f"Source {asset['asset_id']!r} metadata does not match the "
                    "processing receipt."
                )
            description = dataset.descriptions[0] or ""
            expected_polarization = key[1].lower()
            if expected_polarization not in description.lower():
                raise ReviewDerivativeGenerationError(
                    f"Source {asset['asset_id']!r} band description does not identify "
                    f"{key[1]}."
                )
            signatures.add(actual_signature)
    if len(signatures) != 1:
        raise ReviewDerivativeGenerationError(
            "Candidate source rasters do not share one exact grid."
        )


def _inspect_generated_rasters(
    root: Path,
    manifest: Mapping[str, Any],
    build_spec: Mapping[str, Any],
) -> None:
    rasterio = _load_rasterio()
    rows = {
        str(row["layer_role"]): row for row in manifest["outputs"]
    }
    expected_roles = {
        "vv_change",
        "vh_change",
        "fixed_stretch_change_composite",
    }
    if set(rows) != expected_roles:
        raise ReviewDerivativeGenerationError(
            "Candidate manifest does not identify the exact three layer roles."
        )
    signatures: set[tuple[Any, ...]] = set()
    for role, row in rows.items():
        path = root / str(row["file_name"])
        with rasterio.open(path) as dataset:
            signatures.add(
                (
                    str(dataset.crs),
                    tuple(list(dataset.transform)[:6]),
                    dataset.width,
                    dataset.height,
                )
            )
            tags = dataset.tags()
            if (
                tags.get("authority_approval_status")
                != AUTHORITY_APPROVAL_STATUS
                or tags.get("statistics_influence_display") != "false"
                or tags.get("eligible_for_decision_layer") != "false"
                or tags.get("eligible_for_fpps") != "false"
                or tags.get("eligible_for_warning") != "false"
            ):
                raise ReviewDerivativeGenerationError(
                    f"Generated raster {path.name} has unsafe or stale tags."
                )
            if role in {"vv_change", "vh_change"}:
                if dataset.count != 1 or dataset.dtypes != ("float32",) or dataset.nodata != CHANGE_NODATA:
                    raise ReviewDerivativeGenerationError(
                        f"Generated change raster contract failed: {path.name}"
                    )
            elif dataset.count != 3 or dataset.dtypes != (
                "uint8",
                "uint8",
                "uint8",
            ):
                raise ReviewDerivativeGenerationError(
                    "Generated fixed composite must be three uint8 RGB bands."
                )
    if len(signatures) != 1:
        raise ReviewDerivativeGenerationError(
            "Generated candidate rasters do not share one exact grid."
        )
    _independently_verify_candidate_math(root, rows, manifest, build_spec)


def _independently_verify_candidate_math(
    root: Path,
    output_rows: Mapping[str, Mapping[str, Any]],
    manifest: Mapping[str, Any],
    build_spec: Mapping[str, Any],
) -> None:
    rasterio = _load_rasterio()
    source_inputs = build_spec.get("source_inputs")
    if not isinstance(source_inputs, list) or len(source_inputs) != 4:
        raise ReviewDerivativeGenerationError(
            "Real candidate build spec must bind four single-polarization sources."
        )
    source_paths: dict[tuple[str, str], Path] = {}
    source_roles = {
        str(row["asset_id"]): str(row["event_relative_role"])
        for row in manifest["source_rasters"]
    }
    for row in source_inputs:
        if not isinstance(row, Mapping):
            raise ReviewDerivativeGenerationError("Invalid candidate source input.")
        asset_id = str(row.get("asset_id", ""))
        polarizations = row.get("polarizations")
        bands = row.get("band_by_polarization")
        if (
            asset_id not in source_roles
            or not isinstance(polarizations, list)
            or len(polarizations) != 1
            or not isinstance(bands, Mapping)
        ):
            raise ReviewDerivativeGenerationError(
                "Candidate source input is not one exact governed polarization."
            )
        polarization = str(polarizations[0])
        if set(bands) != {polarization}:
            raise ReviewDerivativeGenerationError(
                "Candidate source band mapping is incomplete."
            )
        path = _existing_file(row.get("processed_file_path", ""), "source path")
        if _file_sha256(path) != row.get("processed_file_sha256"):
            raise ReviewDerivativeGenerationError(
                f"Candidate source changed after generation: {path.name}"
            )
        source_paths[(source_roles[asset_id], polarization)] = path
    expected_keys = {
        (role, polarization)
        for role in ("pre_event", "event_time")
        for polarization in ("VV", "VH")
    }
    if set(source_paths) != expected_keys:
        raise ReviewDerivativeGenerationError(
            "Candidate build spec does not cover pre/event VV and VH exactly."
        )
    fixed = manifest.get("fixed_display_parameters")
    if not isinstance(fixed, Mapping) or fixed.get(
        "statistics_influence_display"
    ) is not False:
        raise ReviewDerivativeGenerationError(
            "Candidate fixed-display declaration is missing or adaptive."
        )
    minimum = _finite_number(fixed.get("stretch_min_db"), "stretch_min_db")
    maximum = _finite_number(fixed.get("stretch_max_db"), "stretch_max_db")
    with ExitStack() as stack:
        sources = {
            key: stack.enter_context(rasterio.open(path))
            for key, path in source_paths.items()
        }
        outputs = {
            role: stack.enter_context(
                rasterio.open(root / str(row["file_name"]))
            )
            for role, row in output_rows.items()
        }
        arrays: dict[tuple[str, str], np.ndarray] = {}
        valid: dict[tuple[str, str], np.ndarray] = {}
        for key, dataset in sources.items():
            masked = dataset.read(1, masked=True)
            arrays[key] = np.asarray(masked.data, dtype=np.float32)
            valid[key] = ~np.ma.getmaskarray(masked) & np.isfinite(arrays[key])
        vv_valid = valid[("pre_event", "VV")] & valid[("event_time", "VV")]
        vh_valid = valid[("pre_event", "VH")] & valid[("event_time", "VH")]
        all_valid = vv_valid & vh_valid
        vv_change = (
            arrays[("pre_event", "VV")] - arrays[("event_time", "VV")]
        ).astype(np.float32)
        vh_change = (
            arrays[("pre_event", "VH")] - arrays[("event_time", "VH")]
        ).astype(np.float32)
        expected_vv = np.where(vv_valid, vv_change, CHANGE_NODATA).astype(
            np.float32
        )
        expected_vh = np.where(vh_valid, vh_change, CHANGE_NODATA).astype(
            np.float32
        )
        actual_vv = outputs["vv_change"].read(1)
        actual_vh = outputs["vh_change"].read(1)
        if not np.array_equal(actual_vv, expected_vv):
            raise ReviewDerivativeGenerationError(
                "VV candidate is not exact pre-minus-event dB."
            )
        if not np.array_equal(actual_vh, expected_vh):
            raise ReviewDerivativeGenerationError(
                "VH candidate is not exact pre-minus-event dB."
            )
        expected_rgb = (
            _fixed_scale(vv_change, minimum, maximum),
            _fixed_scale(vh_change, minimum, maximum),
            _fixed_scale(
                (vv_change.astype(np.float64) + vh_change.astype(np.float64))
                / 2.0,
                minimum,
                maximum,
            ),
        )
        rgb = outputs["fixed_stretch_change_composite"]
        for band_index, expected in enumerate(expected_rgb, start=1):
            if not np.array_equal(rgb.read(band_index), expected):
                raise ReviewDerivativeGenerationError(
                    f"Fixed composite band {band_index} does not match its "
                    "declared numeric expression."
                )
        if not np.array_equal(
            rgb.dataset_mask(), all_valid.astype(np.uint8) * 255
        ):
            raise ReviewDerivativeGenerationError(
                "Fixed composite validity mask does not match all four inputs."
            )


def _validate_processing_and_governance(
    processing_alignment_receipt: ProcessingReceiptInput,
    *,
    governance_package: str | Path | None,
    allow_ungoverned_fixture: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if governance_package is None:
        if not allow_ungoverned_fixture:
            raise ReviewDerivativeGenerationError(
                "A validated governance package is required for real candidate generation."
            )
        from floodguard.label_factory.processing_alignment import (
            load_processing_alignment_receipt,
        )

        try:
            processing = load_processing_alignment_receipt(
                processing_alignment_receipt
            )
        except ProcessingAlignmentError as exc:
            raise ReviewDerivativeGenerationError(str(exc)) from exc
        if any(
            row["source_license_status"] == "approved_with_provider_conditions"
            for row in processing["assets"]
        ):
            raise ReviewDerivativeGenerationError(
                "Conditionally approved sources cannot use the fixture escape hatch."
            )
        return processing, {
            "governance_binding_status": "synthetic_fixture_only",
            "production_review_eligible": False,
        }
    root = Path(governance_package)
    try:
        seal = validate_rights_clearance_package(root)
        processing = validate_processing_alignment_receipt(
            processing_alignment_receipt,
            root / "events.csv",
            root / "source_assets.csv",
            governance_package=root,
        )
    except (RightsClearanceError, ProcessingAlignmentError) as exc:
        raise ReviewDerivativeGenerationError(str(exc)) from exc
    return processing, {
        "governance_binding_status": "validated",
        "production_review_eligible": True,
        "governance_package_id": seal["package_id"],
        "governance_package_manifest_sha256": seal["package_manifest_sha256"],
        "governance_package_seal_sha256": seal["seal_sha256"],
    }


def _governed_polarizations(
    governance_package: str | Path | None,
) -> dict[str, tuple[str, ...]] | None:
    if governance_package is None:
        return None
    path = Path(governance_package) / "source_assets.csv"
    frame = pd.read_csv(path, dtype=str).fillna("")
    result: dict[str, tuple[str, ...]] = {}
    for row in frame.to_dict(orient="records"):
        values = {
            value.upper()
            for value in re.split(r"[,;/\s]+", str(row["polarizations"]).strip())
            if value
        }
        result[str(row["asset_id"])] = tuple(
            polarization for polarization in ("VV", "VH") if polarization in values
        )
    return result


def _fixed_scale(
    values: np.ndarray,
    minimum: float,
    maximum: float,
) -> np.ndarray:
    normalized = np.clip(
        (values.astype(np.float64) - minimum) / (maximum - minimum),
        0.0,
        1.0,
    )
    return np.floor(normalized * 255.0 + 0.5).astype(np.uint8)


def _channel_expression(name: str, minimum: float, maximum: float) -> str:
    span = maximum - minimum
    return (
        f"floor(clip(({name} - ({minimum:.1f})) / {span:.1f}, 0.0, 1.0) "
        "* 255.0 + 0.5)"
    )


def _coerce_utc(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(UTC).replace(microsecond=0)
    try:
        parsed = parse_utc_datetime(value, "generated_at_utc")
    except EventRegistryError as exc:
        raise ReviewDerivativeGenerationError(str(exc)) from exc
    return parsed.replace(microsecond=0)


def _identifier(value: object, field: str) -> str:
    text = str(value)
    if text != text.strip() or _IDENTIFIER_PATTERN.fullmatch(text) is None:
        raise ReviewDerivativeGenerationError(f"{field} has invalid characters.")
    return text


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise ReviewDerivativeGenerationError(f"{field} must be finite.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ReviewDerivativeGenerationError(f"{field} must be finite.") from exc
    if not math.isfinite(number):
        raise ReviewDerivativeGenerationError(f"{field} must be finite.")
    return number


def _existing_file(value: str | Path, field: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise ReviewDerivativeGenerationError(f"{field} does not exist: {path}")
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_rasterio() -> Any:
    try:
        import rasterio
    except ImportError as exc:  # pragma: no cover - dependency gate
        raise ReviewDerivativeGenerationError(
            "Reviewer derivative generation requires rasterio."
        ) from exc
    return rasterio
