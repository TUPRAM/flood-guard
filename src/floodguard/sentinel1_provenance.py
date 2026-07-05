"""Metadata-only provenance resolution for selected local Sentinel-1 files."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import re
from typing import Any

import pandas as pd

SENTINEL1_RESOLVED_COLUMNS: tuple[str, ...] = (
    "source_name",
    "file_name",
    "local_path_hint",
    "sha256",
    "sha256_status",
    "raster_width",
    "raster_height",
    "raster_count",
    "raster_dtypes",
    "band_descriptions",
    "crs",
    "bbox_lon_min",
    "bbox_lat_min",
    "bbox_lon_max",
    "bbox_lat_max",
    "mvp_overlap",
    "resolved_product_id",
    "source_package",
    "acquisition_datetime",
    "orbit_direction",
    "relative_orbit",
    "platform",
    "product_type",
    "candidate_role",
    "provenance_status",
    "event_timing_status",
    "timing_confidence",
    "provenance_confidence",
    "tiff_tag_summary",
    "filename_evidence",
    "zip_member_evidence",
    "cdse_match_evidence",
    "provider_note_evidence",
    "reference_mask_status",
    "processing_scope",
    "processing_allowed",
    "still_blocked_reason",
    "assumptions",
)

REQUIRED_SELECTED_COLUMNS: tuple[str, ...] = (
    "source_name",
    "file_name",
    "local_path_hint",
    "sha256",
    "sha256_status",
    "raster_width",
    "raster_height",
    "raster_count",
    "raster_dtypes",
    "band_descriptions",
    "crs",
    "bbox_lon_min",
    "bbox_lat_min",
    "bbox_lon_max",
    "bbox_lat_max",
    "mvp_overlap",
    "source_license_status",
    "reference_mask_status",
)

REQUIRED_ZIP_MEMBER_COLUMNS: tuple[str, ...] = (
    "container_name",
    "member_name",
    "member_kind",
    "library_group",
)

CDSE_COLUMNS: tuple[str, ...] = (
    "acquisition_date",
    "product_name",
    "cdse_product_id",
    "mission_platform_prefix",
    "product_storage_type",
    "candidate_role",
)

READY_CANDIDATE_ROLES: tuple[str, ...] = (
    "pre_event_candidate",
    "post_event_candidate",
)


class Sentinel1ProvenanceError(ValueError):
    """Raised when Sentinel-1 provenance inputs or gates are invalid."""


def resolve_sentinel1_provenance(
    input_dir: str | Path,
    selected_manifest: str | Path | pd.DataFrame,
    zip_members: str | Path | pd.DataFrame | None = None,
    cdse_metadata: str | Path | pd.DataFrame | None = None,
    provider_notes: str | Path | None = None,
) -> pd.DataFrame:
    """Resolve selected Sentinel-1 provenance from metadata only.

    The resolver never reads raster pixels, extracts ZIP members, downloads
    products, or promotes rows into the real SAR baseline. It records whatever
    evidence is available and keeps processing blocked until provenance, timing,
    and reference-mask gates pass.
    """

    root = Path(input_dir)
    if not root.exists():
        raise Sentinel1ProvenanceError(
            f"Sentinel-1 input directory does not exist: {root}"
        )
    selected = _coerce_frame(selected_manifest)
    _require_columns(selected, REQUIRED_SELECTED_COLUMNS, "selected Sentinel-1 manifest")
    members = _optional_frame(zip_members)
    if members is not None:
        _require_columns(members, REQUIRED_ZIP_MEMBER_COLUMNS, "ZIP member catalog")
    cdse = _optional_frame(cdse_metadata)
    if cdse is not None:
        _require_columns(cdse, CDSE_COLUMNS, "CDSE metadata")
    provider_note_evidence = _provider_note_evidence(provider_notes)

    rows: list[dict[str, object]] = []
    for row in selected.to_dict(orient="records"):
        file_name = str(row["file_name"])
        source_path = root / file_name
        if not source_path.exists():
            raise Sentinel1ProvenanceError(
                f"Selected Sentinel-1 source file is missing: {file_name}"
            )
        filename = parse_sentinel1_product_name(file_name)
        tags = inspect_sentinel1_tiff_tags(source_path)
        zip_evidence = summarize_sentinel1_zip_evidence(file_name, members)
        cdse_evidence = match_cdse_metadata(file_name, filename, cdse)
        rows.append(
            _resolved_row(
                row=row,
                filename=filename,
                tiff_tags=tags,
                zip_evidence=zip_evidence,
                cdse_evidence=cdse_evidence,
                provider_note_evidence=provider_note_evidence,
            )
        )
    return pd.DataFrame(rows, columns=SENTINEL1_RESOLVED_COLUMNS)


def write_sentinel1_provenance_outputs(
    input_dir: str | Path,
    selected_manifest_path: str | Path,
    output_path: str | Path,
    zip_members_path: str | Path | None = None,
    cdse_metadata_path: str | Path | None = None,
    provider_notes_path: str | Path | None = None,
    report_path: str | Path | None = None,
) -> tuple[Path, Path | None]:
    """Write the resolved Sentinel-1 provenance manifest and optional report."""

    output = _metadata_csv_path(output_path)
    cdse_input = cdse_metadata_path if _path_exists(cdse_metadata_path) else None
    zip_input = zip_members_path if _path_exists(zip_members_path) else None
    frame = resolve_sentinel1_provenance(
        input_dir=input_dir,
        selected_manifest=selected_manifest_path,
        zip_members=zip_input,
        cdse_metadata=cdse_input,
        provider_notes=provider_notes_path if _path_exists(provider_notes_path) else None,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)

    report_written: Path | None = None
    if report_path is not None:
        report_written = Path(report_path)
        report_written.parent.mkdir(parents=True, exist_ok=True)
        report_written.write_text(
            build_sentinel1_local_provenance_report(frame),
            encoding="utf-8",
        )
    return output, report_written


def parse_sentinel1_product_name(file_name: str) -> dict[str, str]:
    """Parse a Sentinel-1 product name when available.

    The local hackathon tile names are not canonical Sentinel-1 product names.
    Placeholder tile offsets such as `0000000000-0000000000` are treated as
    non-timing evidence, not acquisition timestamps.
    """

    name = Path(file_name).name
    product = re.match(
        r"(?P<platform>S1[ABC])_(?P<mode>[A-Z0-9]+)_(?P<product_type>[A-Z0-9_]+)_"
        r"(?P<start>\d{8}T\d{6})_(?P<stop>\d{8}T\d{6})_"
        r"(?P<orbit>\d{6})_(?P<take>[0-9A-F]+)_(?P<unique>[0-9A-F]+)"
        r"(?P<cog>_COG)?\.SAFE$",
        name,
        flags=re.IGNORECASE,
    )
    if product:
        groups = product.groupdict()
        return {
            "parse_status": "canonical_sentinel1_product_name",
            "platform": groups["platform"].upper(),
            "product_type": groups["product_type"].upper(),
            "acquisition_datetime": _format_s1_datetime(groups["start"]),
            "relative_orbit": groups["orbit"],
            "product_storage_type": "COG" if groups.get("cog") else "SAFE",
            "filename_evidence": "canonical Sentinel-1 product name parsed",
        }

    if re.search(r"Sentinel1_Thailand-\d{10}-\d{10}", name, flags=re.IGNORECASE):
        return {
            "parse_status": "local_tile_placeholder_name",
            "platform": "",
            "product_type": "",
            "acquisition_datetime": "",
            "relative_orbit": "",
            "product_storage_type": "",
            "filename_evidence": (
                "local Sentinel1_Thailand tile name uses placeholder numeric "
                "offsets, not acquisition timestamps"
            ),
        }
    return {
        "parse_status": "unrecognized_filename",
        "platform": "",
        "product_type": "",
        "acquisition_datetime": "",
        "relative_orbit": "",
        "product_storage_type": "",
        "filename_evidence": "filename does not contain Sentinel-1 acquisition metadata",
    }


def inspect_sentinel1_tiff_tags(path: str | Path) -> dict[str, str]:
    """Inspect TIFF tags and band metadata without reading pixels."""

    source = Path(path)
    try:
        import rasterio
    except Exception:
        return {
            "tag_status": "reader_unavailable",
            "tiff_tag_summary": "rasterio unavailable; TIFF tag inspection skipped",
            "platform": "",
            "product_type": "",
            "acquisition_datetime": "",
            "orbit_direction": "",
            "relative_orbit": "",
        }

    try:
        with rasterio.open(source) as dataset:
            tags: dict[str, Any] = {}
            tags.update(dataset.tags())
            tags.update({f"band_{index}_description": value or "" for index, value in zip(dataset.indexes, dataset.descriptions)})
            image_structure = dataset.tags(ns="IMAGE_STRUCTURE")
            if image_structure:
                tags.update({f"IMAGE_STRUCTURE:{key}": value for key, value in image_structure.items()})
    except Exception as exc:
        return {
            "tag_status": "unreadable",
            "tiff_tag_summary": f"TIFF tags unreadable: {exc}",
            "platform": "",
            "product_type": "",
            "acquisition_datetime": "",
            "orbit_direction": "",
            "relative_orbit": "",
        }

    parsed = _parse_tag_metadata(tags)
    if tags:
        summary = "; ".join(f"{key}={tags[key]}" for key in sorted(tags) if str(tags[key]) != "")
    else:
        summary = "no TIFF tags beyond raster core metadata"
    parsed["tag_status"] = "read"
    parsed["tiff_tag_summary"] = summary
    return parsed


def summarize_sentinel1_zip_evidence(
    selected_file_name: str,
    zip_members: pd.DataFrame | None,
) -> dict[str, str]:
    """Summarize ZIP member evidence without extracting files."""

    if zip_members is None or zip_members.empty:
        return {
            "source_package": "",
            "zip_member_evidence": "ZIP member catalog not supplied",
            "zip_member_match_status": "not_checked",
        }
    frame = zip_members.copy()
    sentinel = frame[frame["library_group"].astype(str) == "sentinel1_sar"]
    if sentinel.empty:
        return {
            "source_package": "",
            "zip_member_evidence": "no Sentinel-1 ZIP members found",
            "zip_member_match_status": "no_sentinel1_members",
        }
    exact = sentinel[sentinel["member_name"].astype(str).map(Path).map(lambda path: path.name) == selected_file_name]
    if not exact.empty:
        packages = sorted(set(exact["container_name"].astype(str)))
        return {
            "source_package": "|".join(packages),
            "zip_member_evidence": (
                f"selected file appears as exact ZIP member in {len(packages)} package(s)"
            ),
            "zip_member_match_status": "exact_match",
        }

    packages = sorted(set(sentinel["container_name"].astype(str)))
    members = sorted(Path(value).name for value in sentinel["member_name"].astype(str))
    sidecars = [
        name
        for name in members
        if not name.lower().endswith((".tif", ".tiff", ".ovr"))
    ]
    evidence = (
        f"{len(members)} Sentinel-1 ZIP member(s) found in {', '.join(packages)}; "
        "no exact selected-file match; tiled companion names: "
        f"{', '.join(members)}"
    )
    if sidecars:
        evidence += f"; sidecar candidates: {', '.join(sidecars)}"
    else:
        evidence += "; no Sentinel-1 sidecar metadata files found"
    return {
        "source_package": "|".join(packages),
        "zip_member_evidence": evidence,
        "zip_member_match_status": "no_exact_match_tiled_companions_only",
    }


def match_cdse_metadata(
    file_name: str,
    filename_metadata: dict[str, str],
    cdse_metadata: pd.DataFrame | None,
) -> dict[str, str]:
    """Match local evidence against optional no-download CDSE metadata snapshots."""

    if cdse_metadata is None or cdse_metadata.empty:
        return {
            "resolved_product_id": "",
            "acquisition_datetime": "",
            "platform": "",
            "product_type": "",
            "candidate_role_from_cdse": "",
            "cdse_match_evidence": "no CDSE metadata snapshot supplied",
            "provenance_status": "unresolved",
        }

    frame = cdse_metadata.copy()
    target_name = file_name.lower()
    matches = frame[frame["product_name"].astype(str).str.lower() == target_name]
    parsed_time = filename_metadata.get("acquisition_datetime", "")
    if matches.empty and parsed_time:
        matches = frame[
            frame["acquisition_date"].astype(str).str.startswith(parsed_time[:19])
        ]
    if matches.empty:
        return {
            "resolved_product_id": "",
            "acquisition_datetime": "",
            "platform": "",
            "product_type": "",
            "candidate_role_from_cdse": "",
            "cdse_match_evidence": (
                "CDSE metadata supplied, but no product matched local filename "
                "or parsed acquisition time"
            ),
            "provenance_status": "unresolved",
        }

    match = matches.iloc[0]
    product_name = str(match["product_name"])
    product = parse_sentinel1_product_name(product_name)
    return {
        "resolved_product_id": str(match["cdse_product_id"]),
        "acquisition_datetime": str(match["acquisition_date"]),
        "platform": str(match["mission_platform_prefix"]) or product["platform"],
        "product_type": product["product_type"],
        "candidate_role_from_cdse": _normalize_cdse_role(str(match["candidate_role"])),
        "cdse_match_evidence": f"matched CDSE product metadata row: {product_name}",
        "provenance_status": "confirmed",
    }


def validate_sentinel1_provenance_ready_for_baseline(
    resolved_manifest: pd.DataFrame,
) -> pd.DataFrame:
    """Return ready Sentinel-1 rows only when provenance gates pass."""

    _require_columns(
        resolved_manifest,
        SENTINEL1_RESOLVED_COLUMNS,
        "Sentinel-1 resolved provenance manifest",
    )
    frame = resolved_manifest.copy()
    blockers: list[str] = []
    for role in READY_CANDIDATE_ROLES:
        matches = frame[frame["candidate_role"].astype(str) == role]
        if matches.empty:
            blockers.append(f"missing {role}")
            continue
        ready = matches[matches["processing_allowed"].map(_truthy)]
        if ready.empty:
            row = matches.iloc[0]
            blockers.append(f"{role}: {row['still_blocked_reason']}")
    if blockers:
        raise Sentinel1ProvenanceError(
            "Sentinel-1 provenance is not ready for the real SAR baseline: "
            + "; ".join(blockers)
        )
    return frame[
        frame["candidate_role"].isin(READY_CANDIDATE_ROLES)
        & frame["processing_allowed"].map(_truthy)
    ].reset_index(drop=True)


def build_sentinel1_local_provenance_report(resolved_manifest: pd.DataFrame) -> str:
    """Build a compact Markdown report for local Sentinel-1 provenance."""

    _require_columns(
        resolved_manifest,
        SENTINEL1_RESOLVED_COLUMNS,
        "Sentinel-1 resolved provenance manifest",
    )
    lines = [
        "# Sentinel-1 Local Provenance",
        "",
        "Status: timing unresolved; processing remains blocked.",
        "",
        "This note records metadata-only evidence for the local hackathon-provided "
        "Sentinel-1 file. It does not process pixels, download imagery, or "
        "authorize the real SAR baseline.",
        "",
        "## Selected File Evidence",
        "",
        "| File | Candidate role | Timing status | Provenance status | Processing allowed | Blocker |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in resolved_manifest.to_dict(orient="records"):
        lines.append(
            "| {file_name} | {candidate_role} | {event_timing_status} | "
            "{provenance_status} | {processing_allowed} | {still_blocked_reason} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## What Was Checked",
            "",
            "- TIFF tags were inspected without reading raster pixels.",
            "- Local Drive ZIP member names were inspected without extraction.",
            "- Optional CDSE metadata snapshots were checked when present.",
            "- Provider/hackathon notes were treated as usage notes, not acquisition timing.",
            "",
            "## Findings",
            "",
        ]
    )
    for row in resolved_manifest.to_dict(orient="records"):
        lines.extend(
            [
                f"### {row['file_name']}",
                "",
                f"- Filename evidence: {row['filename_evidence']}",
                f"- TIFF tag evidence: {row['tiff_tag_summary']}",
                f"- ZIP evidence: {row['zip_member_evidence']}",
                f"- CDSE evidence: {row['cdse_match_evidence']}",
                f"- Provider/hackathon note: {row['provider_note_evidence']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Decision",
            "",
            "The standalone local Sentinel-1 TIFF is useful as a checksum-backed "
            "SAR context candidate, but it cannot be called pre-event, post-event, "
            "or event-window yet. The acquisition date is not recoverable from the "
            "current filename, TIFF tags, ZIP member names, or committed metadata "
            "snapshots.",
            "",
            "It must not be used as the real Mae Sai flood baseline until provenance, "
            "event timing, and reference-mask status are resolved.",
            "",
            "## Next Step",
            "",
            "Proceed to Task 43 - DEM Readiness Lane while Sentinel-1 provenance "
            "remains blocked, or acquire a provider note/source package manifest "
            "that maps the local TIFF to a real Sentinel-1 acquisition.",
            "",
        ]
    )
    return "\n".join(lines)


def _resolved_row(
    *,
    row: dict[str, object],
    filename: dict[str, str],
    tiff_tags: dict[str, str],
    zip_evidence: dict[str, str],
    cdse_evidence: dict[str, str],
    provider_note_evidence: str,
) -> dict[str, object]:
    acquisition_datetime = (
        cdse_evidence.get("acquisition_datetime")
        or filename.get("acquisition_datetime")
        or tiff_tags.get("acquisition_datetime")
        or ""
    )
    provenance_status = _provenance_status(filename, tiff_tags, cdse_evidence)
    event_timing_status = "confirmed" if acquisition_datetime else "timing_unresolved"
    candidate_role = _candidate_role(
        acquisition_datetime=acquisition_datetime,
        mvp_overlap=str(row["mvp_overlap"]),
        cdse_role=cdse_evidence.get("candidate_role_from_cdse", ""),
    )
    reference_mask_status = str(row.get("reference_mask_status", "unresolved"))
    resolved_product_id = (
        cdse_evidence.get("resolved_product_id")
        or _product_id_from_filename(filename)
        or "unresolved"
    )
    platform = (
        cdse_evidence.get("platform")
        or filename.get("platform")
        or tiff_tags.get("platform")
        or "unresolved"
    )
    product_type = (
        cdse_evidence.get("product_type")
        or filename.get("product_type")
        or tiff_tags.get("product_type")
        or "unresolved"
    )
    relative_orbit = (
        filename.get("relative_orbit") or tiff_tags.get("relative_orbit") or "unresolved"
    )
    orbit_direction = tiff_tags.get("orbit_direction") or "unresolved"
    processing_allowed = _processing_allowed(
        row=row,
        provenance_status=provenance_status,
        event_timing_status=event_timing_status,
        reference_mask_status=reference_mask_status,
        candidate_role=candidate_role,
        resolved_product_id=resolved_product_id,
    )
    still_blocked_reason = _still_blocked_reason(
        row=row,
        provenance_status=provenance_status,
        event_timing_status=event_timing_status,
        reference_mask_status=reference_mask_status,
        candidate_role=candidate_role,
        resolved_product_id=resolved_product_id,
        processing_allowed=processing_allowed,
    )
    return {
        "source_name": row["source_name"],
        "file_name": row["file_name"],
        "local_path_hint": row["local_path_hint"],
        "sha256": row["sha256"],
        "sha256_status": row["sha256_status"],
        "raster_width": row["raster_width"],
        "raster_height": row["raster_height"],
        "raster_count": row["raster_count"],
        "raster_dtypes": row["raster_dtypes"],
        "band_descriptions": row["band_descriptions"],
        "crs": row["crs"],
        "bbox_lon_min": row["bbox_lon_min"],
        "bbox_lat_min": row["bbox_lat_min"],
        "bbox_lon_max": row["bbox_lon_max"],
        "bbox_lat_max": row["bbox_lat_max"],
        "mvp_overlap": row["mvp_overlap"],
        "resolved_product_id": resolved_product_id,
        "source_package": zip_evidence.get("source_package") or "unresolved",
        "acquisition_datetime": acquisition_datetime or "unresolved",
        "orbit_direction": orbit_direction,
        "relative_orbit": relative_orbit,
        "platform": platform,
        "product_type": product_type,
        "candidate_role": candidate_role,
        "provenance_status": provenance_status,
        "event_timing_status": event_timing_status,
        "timing_confidence": "high" if event_timing_status == "confirmed" else "low",
        "provenance_confidence": "high" if provenance_status == "confirmed" else "low",
        "tiff_tag_summary": tiff_tags["tiff_tag_summary"],
        "filename_evidence": filename["filename_evidence"],
        "zip_member_evidence": zip_evidence["zip_member_evidence"],
        "cdse_match_evidence": cdse_evidence["cdse_match_evidence"],
        "provider_note_evidence": provider_note_evidence,
        "reference_mask_status": reference_mask_status,
        "processing_scope": "sentinel1_provenance_resolution_only",
        "processing_allowed": processing_allowed,
        "still_blocked_reason": still_blocked_reason,
        "assumptions": (
            "Metadata-only provenance resolver; source TIFF and ZIP packages remain "
            "outside Git; not a real flood baseline or official warning product."
        ),
    }


def _candidate_role(
    *,
    acquisition_datetime: str,
    mvp_overlap: str,
    cdse_role: str,
) -> str:
    if cdse_role in {"pre_event_candidate", "post_event_candidate"}:
        return cdse_role
    if "mae_sai_2024_point" not in mvp_overlap:
        return "context_only"
    if not acquisition_datetime:
        return "unresolved"
    if acquisition_datetime < "2024-09-10":
        return "pre_event_candidate"
    return "post_event_candidate"


def _normalize_cdse_role(candidate_role: str) -> str:
    role = candidate_role.lower()
    if "pre-event" in role:
        return "pre_event_candidate"
    if "post-event" in role:
        return "post_event_candidate"
    if "event-window" in role:
        return "context_only"
    return "unresolved"


def _provenance_status(
    filename: dict[str, str],
    tiff_tags: dict[str, str],
    cdse_evidence: dict[str, str],
) -> str:
    if cdse_evidence.get("provenance_status") == "confirmed":
        return "confirmed"
    if filename.get("parse_status") == "canonical_sentinel1_product_name":
        return "filename_confirmed"
    if any(
        tiff_tags.get(key)
        for key in ("platform", "product_type", "relative_orbit", "acquisition_datetime")
    ):
        return "tag_metadata_partial"
    return "unresolved_placeholder_filename"


def _processing_allowed(
    *,
    row: dict[str, object],
    provenance_status: str,
    event_timing_status: str,
    reference_mask_status: str,
    candidate_role: str,
    resolved_product_id: str,
) -> bool:
    return all(
        [
            str(row["sha256_status"]) == "recorded",
            str(row["source_license_status"]) in {
                "confirmed",
                "user_reported_hackathon_free_use",
            },
            provenance_status == "confirmed",
            event_timing_status == "confirmed",
            reference_mask_status == "confirmed",
            candidate_role in READY_CANDIDATE_ROLES,
            resolved_product_id not in {"", "unresolved", "not_selected", "unknown"},
        ]
    )


def _still_blocked_reason(
    *,
    row: dict[str, object],
    provenance_status: str,
    event_timing_status: str,
    reference_mask_status: str,
    candidate_role: str,
    resolved_product_id: str,
    processing_allowed: bool,
) -> str:
    if processing_allowed:
        return ""
    reasons: list[str] = []
    if str(row["sha256_status"]) != "recorded":
        reasons.append("sha256 checksum not recorded")
    if provenance_status != "confirmed":
        reasons.append("Sentinel-1 product provenance unresolved")
    if event_timing_status != "confirmed":
        reasons.append("acquisition timing unresolved")
    if candidate_role not in READY_CANDIDATE_ROLES:
        reasons.append("candidate role is not pre/post baseline ready")
    if resolved_product_id in {"", "unresolved", "not_selected", "unknown"}:
        reasons.append("resolved product id unavailable")
    if reference_mask_status != "confirmed":
        reasons.append("reference mask not confirmed")
    return "; ".join(reasons)


def _parse_tag_metadata(tags: dict[str, Any]) -> dict[str, str]:
    text = " ".join(str(value) for value in tags.values())
    product = parse_sentinel1_product_name(text)
    acquisition = _find_first_datetime(text)
    return {
        "platform": product["platform"],
        "product_type": product["product_type"],
        "acquisition_datetime": product["acquisition_datetime"] or acquisition,
        "orbit_direction": _find_tag_value(tags, ("ORBIT_DIRECTION", "orbit_direction")),
        "relative_orbit": _find_tag_value(
            tags,
            ("RELATIVE_ORBIT", "relative_orbit", "relativeOrbitNumber"),
        ),
    }


def _find_tag_value(tags: dict[str, Any], candidates: tuple[str, ...]) -> str:
    lowered = {str(key).lower(): str(value) for key, value in tags.items()}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return ""


def _find_first_datetime(text: str) -> str:
    match = re.search(r"(\d{8}T\d{6})", text)
    if not match:
        return ""
    return _format_s1_datetime(match.group(1))


def _format_s1_datetime(value: str) -> str:
    return (
        f"{value[0:4]}-{value[4:6]}-{value[6:8]}T"
        f"{value[9:11]}:{value[11:13]}:{value[13:15]}Z"
    )


def _product_id_from_filename(filename: dict[str, str]) -> str:
    if filename.get("parse_status") == "canonical_sentinel1_product_name":
        return "filename_product_name"
    return ""


def _provider_note_evidence(provider_notes: str | Path | None) -> str:
    if provider_notes is None:
        return "no provider or hackathon note supplied"
    path = Path(provider_notes)
    if not path.exists():
        return "provider note path not found"
    text = path.read_text(encoding="utf-8", errors="replace")
    if "hackathon-provided data can be used freely" in text:
        return (
            "hackathon usage note found: project owner reported free use; "
            "no acquisition date or Sentinel-1 product id found"
        )
    return "provider note reviewed; no acquisition date or Sentinel-1 product id found"


def _optional_frame(source: str | Path | pd.DataFrame | None) -> pd.DataFrame | None:
    if source is None:
        return None
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    path = Path(source)
    if not path.exists():
        return None
    return pd.read_csv(path, dtype=str).fillna("")


def _coerce_frame(source: str | Path | pd.DataFrame) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    return pd.read_csv(source, dtype=str).fillna("")


def _require_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    label: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise Sentinel1ProvenanceError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )


def _metadata_csv_path(output_path: str | Path) -> Path:
    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise Sentinel1ProvenanceError(
            "Sentinel-1 provenance output must be a CSV metadata file."
        )
    return target


def _path_exists(path: str | Path | None) -> bool:
    return path is not None and Path(path).exists()


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}
