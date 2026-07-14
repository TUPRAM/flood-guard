"""Validate FloodGuard event, source, tile, and query manifests fail-closed."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.event_registry import (  # noqa: E402
    EventRegistryError,
    load_events,
    load_source_assets,
    validate_event_source_registry,
)
from floodguard.label_factory.manifests import (  # noqa: E402
    ManifestContractError,
    validate_grid_manifests,
)
from floodguard.label_factory.rights_clearance import (  # noqa: E402
    RightsClearanceError,
    validate_cleared_registry_binding,
)


def main() -> None:
    """Print a compact success receipt or a BLOCKED error with exit code 2."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--source-assets", type=Path, required=True)
    parser.add_argument(
        "--governance-package",
        type=Path,
        required=True,
        help=(
            "Validated governance_cleared_vN package binding the exact event "
            "and source registries used for these manifests."
        ),
    )
    parser.add_argument(
        "--processing-alignment-receipt",
        type=Path,
        required=True,
        help="Verified processed-raster and common-grid receipt used to build the manifests.",
    )
    parser.add_argument("--tiles", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument(
        "--supported-query-derivation",
        type=Path,
        help="Required when the canonical manifests used a supported-query allowlist.",
    )
    args = parser.parse_args()
    try:
        validate_cleared_registry_binding(
            args.governance_package,
            args.events,
            args.source_assets,
        )
        events = load_events(args.events)
        sources = load_source_assets(args.source_assets)
        validate_event_source_registry(events, sources)
        canonical = validate_grid_manifests(
            events,
            sources,
            args.tiles,
            args.queries,
            args.processing_alignment_receipt,
            governance_package=args.governance_package,
            supported_query_derivation=args.supported_query_derivation,
        )
    except (
        EventRegistryError,
        ManifestContractError,
        RightsClearanceError,
        OSError,
    ) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(
        "VALID: "
        f"events={len(events)}, sources={len(sources)}, "
        f"tiles={len(canonical.tiles)}, queries={len(canonical.query_regions)}"
    )
    print("Safety: query-model-only; decision layer=false; FPPS=false; warning=false")


if __name__ == "__main__":
    main()
