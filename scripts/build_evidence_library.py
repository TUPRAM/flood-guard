"""Rebuild the local evidence library and its public-safe static projection."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from floodguard.evidence_pipeline import build_library


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "bundle-root",
        "locations-csv",
        "inventory-csv",
        "output-dir",
        "public-dir",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument(
        "--aoi-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "resources/aoi/upload",
    )
    parser.add_argument("--context-root", type=Path)
    parser.add_argument(
        "--generated-at", default=datetime.now(timezone.utc).isoformat()
    )
    parser.add_argument("--reuse-normalized", action="store_true")
    parser.add_argument("--check-public-routes", action="store_true")
    args = vars(parser.parse_args())
    if args.pop("check_public_routes"):
        from floodguard.evidence_acquisition import (
            acquire_ngis_context,
            check_public_routes,
            review_public_responses,
        )
        from floodguard.evidence_catalog import load_aois

        check_public_routes(args["output_dir"] / "acquisition")
        aois = load_aois(args["aoi_dir"])
        acquire_ngis_context(args["output_dir"] / "acquisition", aois)
        review_public_responses(args["output_dir"] / "acquisition", aois)
    print(json.dumps(build_library(**args), indent=2))


if __name__ == "__main__":
    main()
