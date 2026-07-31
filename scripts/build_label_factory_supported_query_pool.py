"""Build provisional Mae Sai tile/query support evidence from aligned SAR."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.supported_query_pool import (  # noqa: E402
    ApprovedAoiWgs84,
    SupportedQueryPoolError,
    build_and_write_supported_query_pool,
)


def main() -> None:
    """Parse explicit evidence paths and publish one immutable derivation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--pre-vv", type=Path, required=True)
    parser.add_argument("--event-vv", type=Path, required=True)
    parser.add_argument("--pre-vh", type=Path, required=True)
    parser.add_argument("--event-vh", type=Path, required=True)
    parser.add_argument("--pre-layover-shadow", type=Path)
    parser.add_argument("--event-layover-shadow", type=Path)
    parser.add_argument(
        "--context-alignment-manifest",
        type=Path,
        help=(
            "Optional self-hashed aligned context manifest. When omitted, "
            "Round-0 stratum fields remain explicitly unassigned."
        ),
    )
    parser.add_argument("--aoi-min-longitude", type=float, default=99.80)
    parser.add_argument("--aoi-min-latitude", type=float, default=20.40)
    parser.add_argument("--aoi-max-longitude", type=float, default=99.90)
    parser.add_argument("--aoi-max-latitude", type=float, default=20.50)
    parser.add_argument(
        "--include-cross-border-context",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Record the explicit cross-border-context decision. Defaults to the "
            "approved Mae Sai pilot value: true."
        ),
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument(
        "--created-at-utc",
        help="Optional timezone-aware ISO timestamp for a reproducible build.",
    )
    args = parser.parse_args()

    try:
        paths = build_and_write_supported_query_pool(
            event_registry_path=args.events,
            event_id=args.event_id,
            pre_vv_path=args.pre_vv,
            event_vv_path=args.event_vv,
            pre_vh_path=args.pre_vh,
            event_vh_path=args.event_vh,
            pre_layover_shadow_path=args.pre_layover_shadow,
            event_layover_shadow_path=args.event_layover_shadow,
            context_alignment_manifest_path=args.context_alignment_manifest,
            approved_aoi=ApprovedAoiWgs84(
                min_longitude=args.aoi_min_longitude,
                min_latitude=args.aoi_min_latitude,
                max_longitude=args.aoi_max_longitude,
                max_latitude=args.aoi_max_latitude,
                cross_border_context_included=args.include_cross_border_context,
            ),
            output_directory=args.output_directory,
            created_at_utc=args.created_at_utc,
        )
    except (SupportedQueryPoolError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    for role, path in paths.as_dict().items():
        print(f"Wrote {role}: {path}")
    print(
        "Status: provisional support evidence only; processing receipt and "
        "source-rights gates still required before canonical manifests/review."
    )
    print("Safety: query-only; decision layer=false; FPPS=false; warning=false")


if __name__ == "__main__":
    main()
