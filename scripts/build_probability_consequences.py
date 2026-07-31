"""Build a signed road/facility probability-consequence receipt."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from floodguard.probability_consequences import (  # noqa: E402
    create_signed_consequence_receipt,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probability-raster", type=Path, required=True)
    parser.add_argument("--model-run-manifest", type=Path, required=True)
    parser.add_argument("--probability-raster-receipt", type=Path, required=True)
    parser.add_argument("--roads", type=Path, required=True)
    parser.add_argument("--road-geometry-receipt", type=Path, required=True)
    parser.add_argument("--facilities", type=Path, required=True)
    parser.add_argument("--facility-geometry-receipt", type=Path, required=True)
    parser.add_argument("--road-buffer-m", type=float, default=15.0)
    parser.add_argument("--facility-buffer-m", type=float, default=100.0)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument(
        "--key-id",
        default=os.environ.get(
            "FLOODGUARD_CONSEQUENCE_SIGNING_KEY_ID", "consequence-authority-v1"
        ),
    )
    parser.add_argument("--allow-report-only", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _json_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def _write_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    try:
        with path.open("x", encoding="utf-8", newline="\n") as output:
            output.write(encoded)
    except FileExistsError as exc:
        raise ValueError(
            f"Refusing to overwrite immutable consequence receipt: {path}"
        ) from exc


def main() -> int:
    args = _parse_args()
    signing_key = os.environ.get("FLOODGUARD_CONSEQUENCE_SIGNING_KEY")
    if signing_key is None:
        raise ValueError(
            "FLOODGUARD_CONSEQUENCE_SIGNING_KEY is required and must remain external."
        )
    receipt = create_signed_consequence_receipt(
        probability_raster_path=args.probability_raster,
        road_geometry_path=args.roads,
        facility_geometry_path=args.facilities,
        source_metadata=_json_object(args.model_run_manifest, "model run manifest"),
        probability_raster_receipt=_json_object(
            args.probability_raster_receipt, "probability raster receipt"
        ),
        road_geometry_receipt=_json_object(
            args.road_geometry_receipt, "road geometry receipt"
        ),
        facility_geometry_receipt=_json_object(
            args.facility_geometry_receipt, "facility geometry receipt"
        ),
        road_buffer_distance_m=args.road_buffer_m,
        facility_buffer_distance_m=args.facility_buffer_m,
        signing_key=signing_key.encode("utf-8"),
        key_id=args.key_id,
        generated_at=args.generated_at,
        allow_report_only=args.allow_report_only,
    )
    _write_new(args.output, receipt)
    print(f"aggregation_status={receipt['aggregation_status']}")
    print(f"can_feed_decision_layer={str(receipt['can_feed_decision_layer']).lower()}")
    print(f"receipt={args.output.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
