"""Run the frozen-plan Mae Sai observation evaluation once signed labels exist.

Fails closed, before reading any metric, unless:

1. the evaluation plan is ``frozen`` (limits filled, evaluation lead named,
   decision evidence hashed);
2. the qualified label release files revalidate through the canonical
   preflight AND come back ``eligible_for_real_experiment=true``; and
3. for ``--role final_holdout``, a custodian opening receipt verifies against
   the trusted key registry and is consumed exactly once in the external ledger.

The candidate raster must share the reference raster's grid and hold 0 dry,
1 flood, 255 abstain. Output is written once and never overwritten.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.holdout_opening import (  # noqa: E402
    TrustedCustodyKey,
    consume_signed_holdout_opening,
)
from floodguard.label_factory.multi_event_preflight import (  # noqa: E402
    QualifiedReleaseFiles,
    revalidate_qualified_release_files,
)
from floodguard.observation_evaluation import (  # noqa: E402
    PARTITION_FINAL_HOLDOUT,
    ObservationEvaluationError,
    assign_partition,
    canonical_sha256,
    evaluate_observation,
    partition_sha256,
    validate_evaluation_plan,
)


def _read_raster(path: Path):
    import rasterio

    with rasterio.open(path) as ds:
        return ds.read(1), ds.transform, ds.crs


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, enforce every gate, evaluate, and write the result."""

    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--role", choices=("development", "final_holdout"), required=True)
    p.add_argument("--candidate-raster", type=Path, required=True)
    p.add_argument("--source-timestamp", required=True, help="Acquisition time(s) of the candidate and reference imagery.")
    for name in ("release-json", "formal-review-json", "human-role-package", "reviewer-calibration",
                 "labelset-manifest", "labelset-validation", "qualified-reference-json", "reference-raster", "analysis-grid"):
        p.add_argument(f"--{name}", type=Path, required=True)
    p.add_argument("--review-pair-json", type=Path, action="append", required=True)
    p.add_argument("--stratum", action="append", default=[], metavar="NAME=RASTER",
                   help="Boolean raster (non-zero = inside) for a stratum named in the plan.")
    p.add_argument("--holdout-opening-receipt", type=Path)
    p.add_argument("--trusted-keys", type=Path, help="JSON {key_id: {public_key_hex, role, valid_from_utc, valid_until_utc}}")
    p.add_argument("--holdout-ledger-dir", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)

    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    plan = validate_evaluation_plan(json.loads(args.plan.read_text(encoding="utf-8")), require_frozen=True)
    gate = revalidate_qualified_release_files(QualifiedReleaseFiles(
        release_json=args.release_json, formal_review_json=args.formal_review_json,
        human_role_package=args.human_role_package, reviewer_calibration=args.reviewer_calibration,
        labelset_manifest=args.labelset_manifest, labelset_validation=args.labelset_validation,
        review_pair_json=tuple(args.review_pair_json), qualified_reference_json=args.qualified_reference_json,
        reference_raster=args.reference_raster, analysis_grid=args.analysis_grid,
    ))
    if gate.get("eligible_for_real_experiment") is not True:
        raise SystemExit(f"blocked: label release preflight status is {gate.get('status')!r}; no evaluation run")

    reference, ref_transform, ref_crs = _read_raster(args.reference_raster)
    candidate, cand_transform, cand_crs = _read_raster(args.candidate_raster)
    if reference.shape != candidate.shape or ref_transform != cand_transform or ref_crs != cand_crs:
        raise SystemExit("blocked: candidate raster is not on the reference grid")
    strata = {}
    for item in args.stratum:
        name, _, path = item.partition("=")
        strata[name] = _read_raster(Path(path))[0] != 0

    opening = None
    if args.role == "final_holdout":
        if not (args.holdout_opening_receipt and args.trusted_keys and args.holdout_ledger_dir):
            raise SystemExit("blocked: final_holdout needs --holdout-opening-receipt, --trusted-keys and --holdout-ledger-dir")
        keys = {
            key_id: TrustedCustodyKey(bytes.fromhex(v["public_key_hex"]), v["role"], v["valid_from_utc"], v["valid_until_utc"])
            for key_id, v in json.loads(args.trusted_keys.read_text(encoding="utf-8")).items()
        }
        part = plan["partition"]
        partition = assign_partition(reference.shape, pixel_size_m=plan["pixel_size_m"], block_size_m=part["block_size_m"],
                                     halo_m=part["halo_m"], seed=part["seed"], development_fraction=part["development_fraction"])
        opening = consume_signed_holdout_opening(
            args.holdout_opening_receipt, trusted_keys=keys, now_utc=datetime.now(timezone.utc),
            partition_manifest_sha256=canonical_sha256({"partition": part, "shape": list(reference.shape), "pixel_size_m": plan["pixel_size_m"]}),
            qualified_release_set_sha256=gate["qualified_label_release_sha256"],
            final_holdout_partition_sha256=partition_sha256(partition, PARTITION_FINAL_HOLDOUT),
            external_ledger_dir=args.holdout_ledger_dir,
        )

    try:
        result = evaluate_observation(plan, gate, reference, candidate, role=args.role, strata=strata,
                                      holdout_opening=opening, source_timestamp=args.source_timestamp)
    except ObservationEvaluationError as error:
        raise SystemExit(f"blocked: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    print(f"wrote {args.output} (meets_predeclared_limits={result['acceptance']['meets_predeclared_limits']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
