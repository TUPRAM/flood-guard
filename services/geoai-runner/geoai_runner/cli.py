"""Small subprocess boundary for validation, encoding, preparation, and manifests."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .contract import ContractError, GeoAIRunContract
from .environment import EXPECTED_GEOAI_COMMIT, EnvironmentError, inspect_environment
from .manifest import ManifestError, build_public_model_run, write_public_model_run
from .prepare import (
    export_training_tiles,
    require_within_workspace,
    validate_prepared_inputs,
)
from .preprocess import PreprocessingError, encode_feature_geotiff
from .validate import RasterValidationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="floodguard-geoai",
        description="Fail-closed FloodGuard adapter for the isolated GeoAI environment.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate_contract = commands.add_parser(
        "validate-contract",
        help="Validate a run contract without importing GeoAI.",
    )
    validate_contract.add_argument("--contract", type=Path, required=True)

    encode = commands.add_parser(
        "encode",
        help="Encode a physical 6-8-band stack to the frozen uint8 contract.",
    )
    encode.add_argument("--workspace", type=Path, required=True)
    encode.add_argument("--input", type=Path, required=True)
    encode.add_argument("--output", type=Path, required=True)
    encode.add_argument("--sidecar", type=Path, required=True)

    validate_grid = commands.add_parser(
        "validate-grid",
        help="Hard-check feature/mask alignment and the declared run grid.",
    )
    validate_grid.add_argument("--contract", type=Path, required=True)
    validate_grid.add_argument("--features", type=Path, required=True)
    validate_grid.add_argument("--mask", type=Path, required=True)
    validate_grid.add_argument("--sidecar", type=Path, required=True)

    export = commands.add_parser(
        "export-tiles",
        help="Invoke GeoAI export_geotiff_tiles after all grid and permission gates.",
    )
    export.add_argument("--contract", type=Path, required=True)
    export.add_argument("--features", type=Path, required=True)
    export.add_argument("--mask", type=Path, required=True)
    export.add_argument("--sidecar", type=Path, required=True)
    export.add_argument("--output-dir", type=Path, required=True)

    manifest = commands.add_parser(
        "write-manifest",
        help="Write a redacted shared-contract model-run manifest.",
    )
    manifest.add_argument("--contract", type=Path, required=True)
    manifest.add_argument("--evidence", type=Path)
    manifest.add_argument("--output", type=Path, required=True)

    environment = commands.add_parser(
        "environment",
        help="Opt in to a real lazy GeoAI import and report the version receipt.",
    )
    environment.add_argument(
        "--geoai-commit",
        default=EXPECTED_GEOAI_COMMIT,
        help="Reviewed source receipt associated with this environment.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = _execute(args)
    except (
        ContractError,
        EnvironmentError,
        ImportError,
        ManifestError,
        OSError,
        PermissionError,
        PreprocessingError,
        RasterValidationError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if payload is not None:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _execute(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.command == "validate-contract":
        contract = GeoAIRunContract.from_json(args.contract)
        return build_public_model_run(contract)
    if args.command == "encode":
        workspace = args.workspace.resolve()
        receipt = encode_feature_geotiff(
            require_within_workspace(args.input, workspace),
            require_within_workspace(args.output, workspace),
            require_within_workspace(args.sidecar, workspace),
        )
        payload = asdict(receipt)
        payload["grid"] = asdict(receipt.grid)
        return payload
    if args.command == "validate-grid":
        contract = GeoAIRunContract.from_json(args.contract)
        grid = validate_prepared_inputs(
            contract,
            args.features,
            args.mask,
            args.sidecar,
        )
        return asdict(grid)
    if args.command == "export-tiles":
        contract = GeoAIRunContract.from_json(args.contract)
        grid = export_training_tiles(
            contract,
            args.features,
            args.mask,
            args.sidecar,
            args.output_dir,
        )
        return asdict(grid)
    if args.command == "write-manifest":
        contract = GeoAIRunContract.from_json(args.contract)
        evidence = _read_evidence(args.evidence)
        receipt = write_public_model_run(
            args.output,
            contract,
            validation_metrics=evidence.get("validation_metrics"),
            error_categories=evidence.get("error_categories", []),
        )
        return {"manifest_sha256": receipt, "run_id": contract.run_id}
    if args.command == "environment":
        return asdict(inspect_environment(declared_geoai_commit=args.geoai_commit))
    raise ValueError(f"Unknown command: {args.command}")


def _read_evidence(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Could not read validation evidence: {exc}") from exc
    if not isinstance(payload, dict):
        raise ManifestError("Validation evidence must be a JSON object.")
    unknown = sorted(set(payload) - {"validation_metrics", "error_categories"})
    if unknown:
        raise ManifestError("Unknown evidence field(s): " + ", ".join(unknown))
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
