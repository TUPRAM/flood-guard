"""Build real Mae Sai open-context decision inputs from outside-Git sources."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.exports import write_priority_geojson  # noqa: E402
from floodguard.mae_sai_context import (  # noqa: E402
    MaeSaiContextError,
    build_context_quality_report,
    build_mae_sai_context_outputs,
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
    args = parser.parse_args()

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
        "roads": _write_csv(outputs.road_risk, output_dir / "mae_sai_road_risk.csv"),
        "facilities": _write_csv(
            outputs.facilities,
            output_dir / "mae_sai_facility_context.csv",
        ),
        "access": _write_csv(
            outputs.access_loss,
            output_dir / "mae_sai_access_loss.csv",
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
    frame.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    main()
