"""Guarded outside-Git extraction for open Mae Sai context sources."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pandas as pd

from floodguard.open_context_manifest import DEFAULT_EXTERNAL_DATA_ROOT


REQUIRED_SOURCE_GROUPS: tuple[str, ...] = (
    "worldpop_population",
    "hdx_cod_ab",
    "osm_geofabrik",
    "copernicus_dem_glo30",
)

MANIFEST_REQUIRED_COLUMNS: tuple[str, ...] = (
    "source_name",
    "source_group",
    "local_path",
    "sha256",
    "sha256_status",
    "acquisition_status",
    "processing_scope",
    "processing_allowed",
    "license_status",
    "retrieved_at_utc",
)


class OpenContextExtractError(ValueError):
    """Raised when context extraction or file gates fail."""


def validate_open_context_files(
    manifest: pd.DataFrame,
    *,
    external_data_root: str | Path = DEFAULT_EXTERNAL_DATA_ROOT,
    verify_checksums: bool = True,
) -> dict[str, Path]:
    """Validate context-only file gates and resolve source paths."""

    _require_columns(manifest, MANIFEST_REQUIRED_COLUMNS, "open context manifest")
    root = Path(external_data_root)
    paths: dict[str, Path] = {}
    for group in REQUIRED_SOURCE_GROUPS:
        rows = manifest[manifest["source_group"].astype(str) == group]
        if len(rows) != 1:
            raise OpenContextExtractError(
                f"Expected exactly one open-context row for {group}; found {len(rows)}."
            )
        row = rows.iloc[0]
        if not _truthy(row["processing_allowed"]):
            raise OpenContextExtractError(
                f"Open-context processing is blocked for {group}."
            )
        if str(row["sha256_status"]) != "recorded" or not _valid_sha256(
            str(row["sha256"])
        ):
            raise OpenContextExtractError(
                f"Open-context checksum is not recorded for {group}."
            )
        if str(row["acquisition_status"]) != "available_outside_git":
            raise OpenContextExtractError(
                f"Open-context file is not available outside Git for {group}."
            )
        scope = str(row["processing_scope"])
        if "context" not in scope or "not_flood" not in scope:
            raise OpenContextExtractError(
                f"Open-context scope is unsafe for {group}: {scope}"
            )
        path = resolve_external_context_path(str(row["local_path"]), root)
        if not path.exists() or not path.is_file():
            raise OpenContextExtractError(
                f"Open-context source file is missing for {group}: {path.name}"
            )
        if verify_checksums and _sha256_file(path) != str(row["sha256"]).lower():
            raise OpenContextExtractError(
                f"Open-context checksum mismatch for {group}: {path.name}"
            )
        paths[group] = path
    return paths


def resolve_external_context_path(path_hint: str, external_data_root: Path) -> Path:
    """Resolve a redacted context path hint under the external workspace."""

    prefix = "<external_data_workspace>/"
    normalized = str(path_hint).strip()
    if not normalized.startswith(prefix):
        raise OpenContextExtractError(
            "Open-context local_path must use the external workspace placeholder."
        )
    relative = Path(normalized.removeprefix(prefix))
    resolved = (external_data_root / relative).resolve()
    try:
        resolved.relative_to(external_data_root.resolve())
    except ValueError as exc:
        raise OpenContextExtractError(
            "Open-context path escapes the external data workspace."
        ) from exc
    return resolved


def find_qgis_bin(explicit_path: str | Path | None = None) -> Path:
    """Locate a QGIS/GDAL bin directory containing ogr2ogr."""

    candidates: list[Path] = []
    if explicit_path is not None:
        candidates.append(Path(explicit_path))
    env_path = os.environ.get("FLOODGUARD_QGIS_BIN")
    if env_path:
        candidates.append(Path(env_path))
    executable = shutil.which("ogr2ogr") or shutil.which("ogr2ogr.exe")
    if executable:
        candidates.append(Path(executable).parent)
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    candidates.extend(
        sorted(program_files.glob("QGIS*/bin"), reverse=True)
    )
    for candidate in candidates:
        if (candidate / "ogr2ogr.exe").exists() or (candidate / "ogr2ogr").exists():
            return candidate
    raise OpenContextExtractError(
        "QGIS/GDAL ogr2ogr was not found. Set FLOODGUARD_QGIS_BIN or pass --qgis-bin."
    )


def extract_mae_sai_vector_context(
    source_paths: Mapping[str, Path],
    output_dir: str | Path,
    *,
    qgis_bin: str | Path | None = None,
) -> dict[str, Path]:
    """Extract bounded COD-AB and OSM GeoJSON files outside Git."""

    missing = [group for group in ("hdx_cod_ab", "osm_geofabrik") if group not in source_paths]
    if missing:
        raise OpenContextExtractError(
            "Missing vector context source group(s): " + ", ".join(missing)
        )
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    bin_dir = find_qgis_bin(qgis_bin)
    admin_path = target_dir / "mae_sai_adm3.geojson"
    roads_path = target_dir / "mae_sai_osm_roads.geojson"
    points_path = target_dir / "mae_sai_osm_points.geojson"

    hdx_zip = source_paths["hdx_cod_ab"]
    gdb_uri = f"/vsizip/{hdx_zip.as_posix()}/tha_admin_boundaries.gdb"
    _run_ogr2ogr(
        bin_dir,
        [
            "-f",
            "GeoJSON",
            "-t_srs",
            "EPSG:4326",
            "-where",
            "adm2_pcode = 'TH5709'",
            "-lco",
            "RFC7946=YES",
            str(admin_path),
            gdb_uri,
            "tha_admin3",
        ],
    )
    admin = read_geojson(admin_path)
    if len(admin.get("features", [])) != 8:
        raise OpenContextExtractError(
            "COD-AB Mae Sai extraction must contain exactly eight ADM3 features."
        )
    bbox = geojson_bounds(admin.get("features", []))
    bbox_args = [f"{value:.9f}" for value in bbox]
    osm_path = source_paths["osm_geofabrik"]
    _run_ogr2ogr(
        bin_dir,
        [
            "-f",
            "GeoJSON",
            "-spat",
            *bbox_args,
            "-where",
            "highway IS NOT NULL",
            "-lco",
            "RFC7946=YES",
            str(roads_path),
            str(osm_path),
            "lines",
        ],
    )
    _run_ogr2ogr(
        bin_dir,
        [
            "-f",
            "GeoJSON",
            "-spat",
            *bbox_args,
            "-lco",
            "RFC7946=YES",
            str(points_path),
            str(osm_path),
            "points",
        ],
    )
    return {"admin": admin_path, "roads": roads_path, "points": points_path}


def standardize_mae_sai_admin(raw_geojson: Mapping[str, object]) -> dict[str, object]:
    """Map HDX COD-AB fields to the FloodGuard admin export contract."""

    features = raw_geojson.get("features")
    if not isinstance(features, list) or len(features) != 8:
        raise OpenContextExtractError(
            "Mae Sai admin GeoJSON must contain eight COD-AB ADM3 features."
        )
    standardized: list[dict[str, object]] = []
    identifiers: set[str] = set()
    for index, feature in enumerate(features):
        if not isinstance(feature, Mapping):
            raise OpenContextExtractError(f"Admin feature {index} is invalid.")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
            raise OpenContextExtractError(
                f"Admin feature {index} is missing properties or geometry."
            )
        subdistrict_id = str(properties.get("adm3_pcode", "")).strip()
        subdistrict_name = str(properties.get("adm3_name", "")).strip()
        if not subdistrict_id or not subdistrict_name:
            raise OpenContextExtractError(
                f"Admin feature {index} is missing ADM3 identity fields."
            )
        if subdistrict_id in identifiers:
            raise OpenContextExtractError(
                f"Duplicate COD-AB ADM3 id: {subdistrict_id}"
            )
        identifiers.add(subdistrict_id)
        standardized.append(
            {
                "type": "Feature",
                "properties": {
                    "subdistrict_id": subdistrict_id,
                    "subdistrict_name": subdistrict_name,
                    "subdistrict_name_th": str(properties.get("adm3_name1", "")),
                    "district_id": str(properties.get("adm2_pcode", "")),
                    "district_name": str(properties.get("adm2_name", "")),
                    "province_id": str(properties.get("adm1_pcode", "")),
                    "province_name": str(properties.get("adm1_name", "")),
                    "area_sq_km": _optional_float(properties.get("area_sqkm")),
                    "boundary_valid_on": str(properties.get("valid_on", "")),
                    "boundary_version": str(properties.get("version", "")),
                    "source_name": "HDX Thailand COD-AB",
                    "confidence_class": "medium",
                    "assumptions": (
                        "COD-AB ADM3 boundary context, version v01 valid from "
                        "2022-01-22; verify current local administrative changes."
                    ),
                },
                "geometry": dict(geometry),
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "mae_sai_adm3_context",
        "features": standardized,
    }


def read_geojson(path: str | Path) -> dict[str, object]:
    """Read a GeoJSON object from disk."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OpenContextExtractError(f"Cannot read GeoJSON: {Path(path).name}") from exc
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection":
        raise OpenContextExtractError(
            f"GeoJSON must be a FeatureCollection: {Path(path).name}"
        )
    return value


def write_geojson(value: Mapping[str, object], path: str | Path) -> Path:
    """Write a compact UTF-8 GeoJSON object."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return target


def geojson_bounds(features: Iterable[Mapping[str, object]]) -> tuple[float, float, float, float]:
    """Return WGS84 bounds for GeoJSON features."""

    coordinates: list[tuple[float, float]] = []
    for feature in features:
        geometry = feature.get("geometry")
        if isinstance(geometry, Mapping):
            coordinates.extend(iter_geometry_coordinates(geometry))
    if not coordinates:
        raise OpenContextExtractError("GeoJSON contains no coordinates.")
    xs = [coordinate[0] for coordinate in coordinates]
    ys = [coordinate[1] for coordinate in coordinates]
    return min(xs), min(ys), max(xs), max(ys)


def iter_geometry_coordinates(
    geometry: Mapping[str, object],
) -> Iterable[tuple[float, float]]:
    """Yield coordinate pairs from Point, LineString, or polygon geometries."""

    geometry_type = str(geometry.get("type", ""))
    coordinates = geometry.get("coordinates")
    if geometry_type == "Point" and isinstance(coordinates, Sequence):
        yield float(coordinates[0]), float(coordinates[1])
        return
    if geometry_type == "LineString" and isinstance(coordinates, Sequence):
        for coordinate in coordinates:
            yield float(coordinate[0]), float(coordinate[1])
        return
    if geometry_type == "Polygon" and isinstance(coordinates, Sequence):
        for ring in coordinates:
            for coordinate in ring:
                yield float(coordinate[0]), float(coordinate[1])
        return
    if geometry_type == "MultiPolygon" and isinstance(coordinates, Sequence):
        for polygon in coordinates:
            for ring in polygon:
                for coordinate in ring:
                    yield float(coordinate[0]), float(coordinate[1])
        return
    raise OpenContextExtractError(f"Unsupported GeoJSON geometry type: {geometry_type}")


def _run_ogr2ogr(bin_dir: Path, arguments: list[str]) -> None:
    executable = bin_dir / ("ogr2ogr.exe" if os.name == "nt" else "ogr2ogr")
    env = os.environ.copy()
    gdal_data = bin_dir.parent / "apps" / "gdal" / "share" / "gdal"
    if gdal_data.exists():
        env["GDAL_DATA"] = str(gdal_data)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    output_path = next(
        (Path(argument) for argument in arguments if str(argument).lower().endswith(".geojson")),
        None,
    )
    if output_path is not None and output_path.exists():
        output_path.unlink()
    result = subprocess.run(
        [str(executable), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise OpenContextExtractError(f"ogr2ogr extraction failed: {detail}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value.lower())


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _optional_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise OpenContextExtractError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )
