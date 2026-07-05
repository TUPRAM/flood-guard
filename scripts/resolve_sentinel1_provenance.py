"""Resolve selected Sentinel-1 provenance from local metadata only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.sentinel1_provenance import (  # noqa: E402
    write_sentinel1_provenance_outputs,
)


def main(argv: list[str] | None = None) -> int:
    """Write the Sentinel-1 resolved provenance manifest and report."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path.home() / "Downloads",
        help="Directory containing the selected local Sentinel-1 TIFF.",
    )
    parser.add_argument(
        "--selected-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "sentinel1_selected_file_manifest.csv",
        help="Checksum-backed selected Sentinel-1 manifest.",
    )
    parser.add_argument(
        "--zip-members",
        type=Path,
        default=REPO_ROOT / "outputs" / "local_data_library_zip_members.csv",
        help="Metadata-only ZIP member catalog.",
    )
    parser.add_argument(
        "--cdse-metadata",
        type=Path,
        default=REPO_ROOT / "outputs" / "cdse_mae_sai_2024_metadata.csv",
        help="Optional no-download CDSE metadata snapshot. Missing files are skipped.",
    )
    parser.add_argument(
        "--provider-notes",
        type=Path,
        default=REPO_ROOT / "docs" / "theos2_usage_terms_log.md",
        help="Optional local provider/hackathon usage note.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "sentinel1_provenance_resolved_manifest.csv",
        help="Output resolved provenance CSV.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=REPO_ROOT / "docs" / "sentinel1_local_provenance.md",
        help="Output Markdown provenance note.",
    )
    args = parser.parse_args(argv)

    manifest_path, report_path = write_sentinel1_provenance_outputs(
        input_dir=args.input_dir,
        selected_manifest_path=args.selected_manifest,
        output_path=args.output,
        zip_members_path=args.zip_members,
        cdse_metadata_path=args.cdse_metadata,
        provider_notes_path=args.provider_notes,
        report_path=args.report_output,
    )
    print(f"Wrote {manifest_path}")
    if report_path is not None:
        print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
