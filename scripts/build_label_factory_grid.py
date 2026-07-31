"""Build canonical FloodGuard tile and query-region CSV manifests."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

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
    build_grid_manifests,
)
from floodguard.label_factory.rights_clearance import (  # noqa: E402
    RightsClearanceError,
    validate_cleared_registry_binding,
)


def main() -> None:
    """Validate the registry, then write deterministic grid manifests."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--source-assets", type=Path, required=True)
    parser.add_argument(
        "--governance-package",
        type=Path,
        required=True,
        help=(
            "Validated governance_cleared_vN package binding the exact event "
            "and source registries used for this grid."
        ),
    )
    parser.add_argument(
        "--processing-alignment-receipt",
        type=Path,
        required=True,
        help=(
            "Self-hashed receipt proving processed-file hashes, terrain correction, "
            "registration, coverage, and common-grid alignment."
        ),
    )
    parser.add_argument(
        "--tile-assignments",
        type=Path,
        required=True,
        help="CSV of explicit event/grid indices, dataset roles, and overlap groups.",
    )
    parser.add_argument(
        "--supported-query-derivation",
        type=Path,
        help=(
            "Optional self-hashed provisional support derivation. Rights, receipt, "
            "and tile coverage gates still run before its query allowlist is used."
        ),
    )
    parser.add_argument("--tile-output", type=Path, required=True)
    parser.add_argument("--query-output", type=Path, required=True)
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
        manifests = build_grid_manifests(
            events,
            args.tile_assignments,
            sources,
            args.processing_alignment_receipt,
            governance_package=args.governance_package,
            supported_query_derivation=args.supported_query_derivation,
        )
        _validate_distinct_outputs(args.tile_output, args.query_output)
        _write_csv_atomic(manifests.tiles, args.tile_output)
        _write_csv_atomic(manifests.query_regions, args.query_output)
    except (
        EventRegistryError,
        ManifestContractError,
        RightsClearanceError,
        OSError,
    ) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(f"Wrote {len(manifests.tiles)} canonical tiles: {args.tile_output}")
    print(
        f"Wrote {len(manifests.query_regions)} query cores: {args.query_output}"
    )
    print("Safety: query-model-only; decision layer=false; FPPS=false; warning=false")


def _validate_distinct_outputs(tile_output: Path, query_output: Path) -> None:
    if tile_output.resolve() == query_output.resolve():
        raise ManifestContractError(
            "--tile-output and --query-output must be different paths."
        )
    if tile_output.suffix.lower() != ".csv" or query_output.suffix.lower() != ".csv":
        raise ManifestContractError("Grid manifest outputs must be CSV files.")
    existing = [path for path in (tile_output, query_output) if path.exists()]
    if existing:
        raise ManifestContractError(
            "Canonical grid manifests are immutable and cannot be overwritten: "
            + ", ".join(str(path) for path in existing)
        )


def _write_csv_atomic(frame: object, output_path: Path) -> None:
    """Replace one CSV only after pandas has completed the temporary write."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        frame.to_csv(temporary, index=False)  # type: ignore[attr-defined]
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
