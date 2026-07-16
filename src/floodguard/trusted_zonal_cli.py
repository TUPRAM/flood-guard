"""Safe non-interactive entry point for trusted zonal receipt generation.

Run with ``python -m floodguard.trusted_zonal_cli``.  The HMAC secret is read
only from a named environment variable containing lowercase or uppercase hex;
it is never accepted as a command-line argument or written to output.  Output
must be outside the repository and is created exclusively, so an existing
receipt cannot be overwritten.  Each JSON lineage input is parsed from the
exact bytes read from one verified regular-file descriptor; the CLI never
validates a path and then reopens it for parsing.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from floodguard.probability_aggregation import (
    PRIVATE_PATH_RE,
    ProbabilityAggregationError,
)
from floodguard.trusted_zonal_adapter import (
    _read_bound_bytes,
    create_signed_zonal_receipt,
)


DEFAULT_SIGNING_KEY_ENV = "FLOODGUARD_ZONAL_SIGNING_KEY_HEX"
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class TrustedZonalCliError(ValueError):
    """Raised for a safe, path-redacted CLI validation failure."""


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Generate one canonical signed receipt in an external workspace."""

    args = _parser().parse_args(argv)
    environment = os.environ if environ is None else environ
    try:
        signing_key = _key_from_environment(args.signing_key_env, environment)
        source_metadata = _read_json_mapping(
            args.model_run_manifest, "model-run manifest"
        )
        raster_receipt = _read_json_mapping(
            args.probability_raster_receipt, "probability-raster receipt"
        )
        geometry_receipt = _read_json_mapping(
            args.authoritative_geometry_receipt,
            "authoritative-geometry receipt",
        )
        output_path = _external_output_path(args.output)
        receipt = create_signed_zonal_receipt(
            probability_raster_path=args.probability_raster,
            authoritative_geometry_path=args.authoritative_geometry,
            source_metadata=source_metadata,
            probability_raster_receipt=raster_receipt,
            authoritative_geometry_receipt=geometry_receipt,
            signing_key=signing_key,
            key_id=args.key_id,
            generated_at=args.generated_at,
        )
        serialized = (
            json.dumps(
                receipt,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        )
        _exclusive_write(output_path, serialized)
    except (ProbabilityAggregationError, TrustedZonalCliError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    receipt_sha = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    print(
        "trusted_zonal_receipt_written "
        f"sha256={receipt_sha} key_id={receipt['key_id']} "
        f"areas={len(receipt['areas'])}"
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a signed FloodGuard probability-zonal receipt."
    )
    parser.add_argument("--probability-raster", required=True)
    parser.add_argument("--authoritative-geometry", required=True)
    parser.add_argument("--model-run-manifest", required=True)
    parser.add_argument("--probability-raster-receipt", required=True)
    parser.add_argument("--authoritative-geometry-receipt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument(
        "--signing-key-env",
        default=DEFAULT_SIGNING_KEY_ENV,
        help=(
            "Name of the environment variable containing a hex-encoded HMAC "
            f"key (default: {DEFAULT_SIGNING_KEY_ENV})."
        ),
    )
    return parser


def _key_from_environment(name: object, environ: Mapping[str, str]) -> bytes:
    if not isinstance(name, str) or not ENV_NAME_RE.fullmatch(name):
        raise TrustedZonalCliError("signing-key environment variable name is invalid.")
    encoded = environ.get(name)
    if encoded is None or not encoded.strip():
        raise TrustedZonalCliError(
            "signing-key environment variable is absent or empty."
        )
    text = encoded.strip()
    if len(text) > 512 or len(text) % 2:
        raise TrustedZonalCliError(
            "signing-key environment variable must contain valid hex."
        )
    try:
        key = bytes.fromhex(text)
    except ValueError as exc:
        raise TrustedZonalCliError(
            "signing-key environment variable must contain valid hex."
        ) from exc
    if len(key) < 32:
        raise TrustedZonalCliError(
            "signing-key environment variable must decode to at least 32 bytes."
        )
    return key


def _read_json_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        raise TrustedZonalCliError(f"{label} path is required.")
    content, _snapshot_sha = _read_bound_bytes(Path(value), label)
    document = _parse_json_snapshot(content, label)
    if not isinstance(document, Mapping):
        raise TrustedZonalCliError(f"{label} must contain a JSON object.")
    _reject_private_paths(document, label)
    return dict(document)


def _parse_json_snapshot(content: bytes, label: str) -> object:
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        raise TrustedZonalCliError(f"{label} must be valid UTF-8 JSON.") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonfinite_json,
        )
    except json.JSONDecodeError as exc:
        raise TrustedZonalCliError(f"{label} must be valid UTF-8 JSON.") from exc


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise TrustedZonalCliError(
                "JSON receipt objects must not contain duplicate keys."
            )
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> object:
    raise TrustedZonalCliError(
        f"JSON receipts must not contain non-finite constant {value!r}."
    )


def _reject_private_paths(value: object, label: str) -> None:
    if isinstance(value, str):
        text = value.strip()
        if text.lower().startswith(("http://", "https://")):
            return
        if text.startswith(("/", "\\")) or PRIVATE_PATH_RE.search(text):
            raise TrustedZonalCliError(
                f"{label} must not contain private absolute paths."
            )
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_private_paths(key, label)
            _reject_private_paths(item, label)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_private_paths(item, label)


def _external_output_path(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise TrustedZonalCliError("output path is required.")
    path = Path(value)
    if path.suffix.casefold() != ".json":
        raise TrustedZonalCliError("output must use a .json extension.")
    if path.is_symlink() or path.exists():
        raise TrustedZonalCliError(
            "output already exists; trusted receipts are never overwritten."
        )
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise TrustedZonalCliError(
            "output parent must be an existing external directory."
        ) from exc
    if not parent.is_dir():
        raise TrustedZonalCliError(
            "output parent must be an existing external directory."
        )
    repository_root = Path(__file__).resolve().parents[2]
    try:
        parent.relative_to(repository_root)
    except ValueError:
        pass
    else:
        raise TrustedZonalCliError(
            "output must be outside the FloodGuard repository workspace."
        )
    return parent / path.name


def _exclusive_write(path: Path, content: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise TrustedZonalCliError(
            "output already exists; trusted receipts are never overwritten."
        ) from exc
    except OSError as exc:
        raise TrustedZonalCliError(
            "output could not be created in the external workspace."
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise TrustedZonalCliError("output could not be written completely.") from exc


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
