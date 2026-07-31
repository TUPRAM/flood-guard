"""Rasterize locked adjudicator redraw geometry onto canonical query cells."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.adjudication import AdjudicationError  # noqa: E402
from floodguard.label_factory.annotation_rasterization import (  # noqa: E402
    AnnotationRasterizationDependencyError,
)
from floodguard.label_factory.consensus_builder import (  # noqa: E402
    BUILDER_VERSION,
    ConsensusBuilderError,
    write_adjudicator_redraw_outputs,
)


def main() -> None:
    """Write one immutable redraw raster and checksum-bearing manifest."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--adjudication-log",
        type=Path,
        required=True,
        help="Existing hash-chained log containing at least one locked redraw outcome.",
    )
    parser.add_argument("--query-manifest", type=Path, required=True)
    parser.add_argument("--cell-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--rasterizer-version", default=BUILDER_VERSION)
    args = parser.parse_args()
    try:
        outputs = write_adjudicator_redraw_outputs(
            adjudication_log_path=args.adjudication_log,
            query_manifest_path=args.query_manifest,
            cell_output_path=args.cell_output,
            manifest_output_path=args.manifest_output,
            rasterizer_version=args.rasterizer_version,
        )
    except (
        ConsensusBuilderError,
        AdjudicationError,
        AnnotationRasterizationDependencyError,
        OSError,
        ValueError,
    ) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Wrote redraw cells: {outputs.cell_labels}")
    print(f"Wrote redraw manifest: {outputs.manifest}")


if __name__ == "__main__":
    main()
