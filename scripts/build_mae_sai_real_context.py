"""Build real Mae Sai open-context decision inputs from outside-Git sources."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.exports import write_priority_geojson  # noqa: E402
from floodguard.mae_sai_context import (  # noqa: E402
    MaeSaiContextError,
    build_access_hotspot_geojson,
    build_context_quality_report,
    build_facility_geojson,
    build_mae_sai_context_outputs,
    build_road_risk_geojson,
)
from floodguard.open_context_extract import (  # noqa: E402
    OpenContextExtractError,
    extract_mae_sai_vector_context,
    read_geojson,
    standardize_mae_sai_admin,
    validate_open_context_files,
    write_geojson,
)
from floodguard.open_context_manifest import DEFAULT_EXTERNAL_DATA_ROOT  # noqa: E402
from floodguard.sar_raster_extract import (  # noqa: E402
    SARRasterExtractError,
    build_sentinel1_inputs_from_manifests,
    summarize_sar_probability_by_geometries,
)
from floodguard.scoring import score_subdistricts  # noqa: E402


def main() -> None:
    """Validate context sources, derive joins, score FPPS, and write outputs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--open-context-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "open_context_data_file_manifest.csv",
    )
    parser.add_argument(
        "--mae-sai-file-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_real_data_file_manifest.csv",
    )
    parser.add_argument(
        "--manual-reference-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "manual_reference_mask_manifest.csv",
    )
    parser.add_argument(
        "--external-data-root",
        type=Path,
        default=DEFAULT_EXTERNAL_DATA_ROOT,
    )
    parser.add_argument(
        "--derived-work-dir",
        type=Path,
        default=(
            DEFAULT_EXTERNAL_DATA_ROOT / "derived_context" / "mae_sai_2024"
        ),
    )
    parser.add_argument("--qgis-bin", type=Path, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs",
    )
    parser.add_argument(
        "--skip-checksum-verification",
        action="store_true",
        help="Use only for iterative local debugging; committed runs must verify checksums.",
    )
    parser.add_argument(
        "--git-commit",
        default=None,
        help=(
            "Forty-character source-code commit to bind into the scenario receipt. "
            "Defaults to the current Git HEAD."
        ),
    )
    parser.add_argument(
        "--generated-at",
        default=None,
        help=(
            "UTC generation timestamp. Defaults to the current UTC time; pass an "
            "explicit value when rebuilding immutable release evidence."
        ),
    )
    args = parser.parse_args()

    git_commit = _validated_git_commit(args.git_commit or _current_git_commit())
    generated_at = _validated_utc_timestamp(
        args.generated_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )

    try:
        context_manifest = _read_csv(args.open_context_manifest)
        source_paths = validate_open_context_files(
            context_manifest,
            external_data_root=args.external_data_root,
            verify_checksums=not args.skip_checksum_verification,
        )
        vector_paths = extract_mae_sai_vector_context(
            source_paths,
            args.derived_work_dir,
            qgis_bin=args.qgis_bin,
        )
        admin_geojson = standardize_mae_sai_admin(read_geojson(vector_paths["admin"]))
        roads_geojson = read_geojson(vector_paths["roads"])
        points_geojson = read_geojson(vector_paths["points"])

        file_manifest = _read_csv(args.mae_sai_file_manifest)
        manual_manifest = _read_csv(args.manual_reference_manifest)
        sentinel_inputs = build_sentinel1_inputs_from_manifests(
            file_manifest,
            manual_manifest,
            external_data_dir=args.external_data_root,
        )
        sar_summary = summarize_sar_probability_by_geometries(
            sentinel_inputs,
            admin_geojson["features"],
            output_shape=(128, 128),
        )
        outputs = build_mae_sai_context_outputs(
            admin_geojson,
            roads_geojson,
            points_geojson,
            sar_summary,
            worldpop_path=str(source_paths["worldpop_population"]),
            dem_path=str(source_paths["copernicus_dem_glo30"]),
        )
        road_risk_geojson = build_road_risk_geojson(
            roads_geojson,
            outputs.road_risk,
        )
        facility_geojson = build_facility_geojson(outputs.facilities)
        access_hotspot_geojson = build_access_hotspot_geojson(
            admin_geojson,
            outputs.access_loss,
            outputs.equity_gap,
        )
        scored = score_subdistricts(outputs.decision_inputs)
    except (
        FileNotFoundError,
        MaeSaiContextError,
        OpenContextExtractError,
        SARRasterExtractError,
        ValueError,
    ) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "admin": write_geojson(admin_geojson, output_dir / "mae_sai_admin_context.geojson"),
        "sar": _write_csv(sar_summary, output_dir / "mae_sai_adm3_sar_context.csv"),
        "population": _write_csv(
            outputs.population_context,
            output_dir / "mae_sai_population_context.csv",
        ),
        "population_nodes": _write_csv(
            _scenario_population_nodes(outputs.population_nodes),
            output_dir / "mae_sai_population_nodes.csv",
        ),
        "roads": _write_csv(outputs.road_risk, output_dir / "mae_sai_road_risk.csv"),
        "access_edges": _write_csv(
            _scenario_access_edges(outputs.road_edges),
            output_dir / "mae_sai_access_edges.csv",
        ),
        "road_geometry": write_geojson(
            road_risk_geojson,
            output_dir / "mae_sai_road_risk.geojson",
        ),
        "facilities": _write_csv(
            outputs.facilities,
            output_dir / "mae_sai_facility_context.csv",
        ),
        "facility_geometry": write_geojson(
            facility_geojson,
            output_dir / "mae_sai_facilities.geojson",
        ),
        "access": _write_csv(
            outputs.access_loss,
            output_dir / "mae_sai_access_loss.csv",
        ),
        "access_hotspots": write_geojson(
            access_hotspot_geojson,
            output_dir / "mae_sai_access_hotspots.geojson",
        ),
        "equity": _write_csv(
            outputs.equity_gap,
            output_dir / "mae_sai_equity_gap.csv",
        ),
        "decision": _write_csv(
            outputs.decision_inputs,
            output_dir / "mae_sai_subdistrict_flood_inputs.csv",
        ),
        "context_decision": _write_csv(
            outputs.decision_inputs,
            output_dir / "mae_sai_real_context_decision_inputs.csv",
        ),
        "quality": _write_csv(
            outputs.quality_summary,
            output_dir / "mae_sai_context_quality_summary.csv",
        ),
    }
    paths["scenario_manifest"] = _write_scenario_input_manifest(
        population_path=paths["population_nodes"],
        edge_path=paths["access_edges"],
        facility_path=paths["facilities"],
        output_path=output_dir / "mae_sai_scenario_inputs_manifest.json",
        git_commit=git_commit,
        source_timestamp=str(sar_summary["source_timestamp"].max()),
        generated_at=generated_at,
    )
    priority_path = write_priority_geojson(
        paths["admin"],
        scored,
        output_dir / "mae_sai_priority_subdistricts.geojson",
    )
    quality_report_path = output_dir / "mae_sai_context_quality_report.md"
    quality_report_path.write_text(
        build_context_quality_report(outputs.quality_summary, outputs.decision_inputs),
        encoding="utf-8",
    )
    for path in paths.values():
        print(f"Wrote {path}")
    print(f"Wrote {priority_path}")
    print(f"Wrote {quality_report_path}")
    print("Source rasters, PBF, GDB ZIP, SAFE ZIPs, and vector extracts remain outside Git.")


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required manifest does not exist: {path.name}")
    return pd.read_csv(path, dtype=str).fillna("")


def _write_csv(frame: pd.DataFrame, path: Path) -> Path:
    frame.to_csv(path, index=False, lineterminator="\n")
    return path


def _scenario_population_nodes(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the path-safe population-node artifact used by server scenarios."""

    return frame.loc[
        :,
        [
            "node_id",
            "subdistrict_id",
            "total_population",
            "vulnerable_population",
            "non_vulnerable_population",
        ],
    ].copy()


def _scenario_access_edges(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the path-safe graph-edge artifact used by server scenarios."""

    return frame.loc[
        :,
        [
            "edge_id",
            "road_id",
            "from_node",
            "to_node",
            "normal_minutes",
            "disrupted_minutes",
            "road_disruption_probability_0_1",
            "candidate_closure_status",
            "subdistrict_id",
            "bridge_flag",
        ],
    ].copy()


def _write_scenario_input_manifest(
    *,
    population_path: Path,
    edge_path: Path,
    facility_path: Path,
    output_path: Path,
    git_commit: str,
    source_timestamp: str,
    generated_at: str,
) -> Path:
    """Bind compact server-scenario inputs to checksums and candidate provenance."""

    artifacts = []
    for role, path in (
        ("population_nodes", population_path),
        ("access_edges", edge_path),
        ("facility_candidates", facility_path),
    ):
        frame = pd.read_csv(path)
        artifacts.append(
            {
                "role": role,
                "relative_path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "row_count": int(len(frame)),
                "columns": list(frame.columns),
            }
        )
    payload = {
        "schema_version": "1.0",
        "study_area_id": "mae_sai_candidate_v1",
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "official_warning": False,
        "data_version": "mae-sai-candidate-2024-09-15-v1",
        "git_commit": _validated_git_commit(git_commit),
        "source_timestamp": _validated_utc_timestamp(source_timestamp),
        "generated_at": _validated_utc_timestamp(generated_at),
        "confidence_class": "low",
        "source_name": (
            "CDSE Sentinel-1 candidate change context; WorldPop Thailand 100m 2020; "
            "OpenStreetMap Thailand via Geofabrik"
        ),
        "source_licenses": [
            "Copernicus Sentinel data legal notice",
            "WorldPop CC BY 4.0",
            "OpenStreetMap ODbL 1.0",
        ],
        "processing_allowed": True,
        "can_feed_decision_layer": False,
        "reason_blocked": (
            "Scenario inputs use modeled population, unverified facility candidates, "
            "and heuristic road disruption; outputs remain candidate planning evidence."
        ),
        "processing_scope": "mae_sai_candidate_access_scenario_inputs",
        "artifacts": artifacts,
        "assumptions": [
            "Population is modeled WorldPop context snapped to a candidate OSM graph.",
            "Vulnerability is a terrain/remoteness proxy, not demographic truth.",
            "Disrupted edge times are heuristic candidates, not observed closures.",
            "Scenario outputs are planning evidence and not evacuation instructions.",
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["receipt_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output_path


def _current_git_commit() -> str:
    """Return the source revision used by the scenario artifact builder."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("Unable to resolve the FloodGuard source Git commit.") from exc
    return completed.stdout.strip().lower()


def _validated_git_commit(value: str) -> str:
    """Resolve a real source commit reachable from this repository's HEAD."""

    normalized = str(value).strip().lower()
    if re.fullmatch(r"[0-9a-f]{40}", normalized) is None:
        raise ValueError("git_commit must be a forty-character hexadecimal commit.")
    try:
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", f"{normalized}^{{commit}}"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip().lower()
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", resolved, "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(
            "git_commit must identify a commit reachable from this repository HEAD."
        ) from exc
    if resolved != normalized:
        raise ValueError("git_commit did not resolve to the supplied full commit id.")
    return resolved


def _validated_utc_timestamp(value: str) -> str:
    """Validate and normalize a timezone-aware timestamp to UTC."""

    normalized = str(value).strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid UTC timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Scenario receipt timestamps must include a UTC offset.")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
