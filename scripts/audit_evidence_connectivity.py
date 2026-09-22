"""Audit an immutable finals context without changing its graph or package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from floodguard.evidence_catalog import canonical_bytes
from floodguard.evidence_connectivity import audit_connectivity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument(
        "--service",
        choices=("hospital", "primary_care", "pharmacy"),
        default="hospital",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    raw = args.context.read_bytes()
    context = json.loads(raw)
    actual = hashlib.sha256(
        canonical_bytes(
            {
                k: v
                for k, v in context.items()
                if k not in ("canonical_sha256", "generated_at")
            }
        )
    ).hexdigest()
    if actual != context.get("canonical_sha256"):
        raise ValueError("Context content does not match its canonical checksum")
    sites = [
        r
        for r in context["osm_facilities"]
        if r.get("service_type") == args.service
        and r.get("candidate_destination_eligible") is True
        and r.get("within_routing_context") is True
    ]
    audit = audit_connectivity(
        context["population"],
        context["edges"],
        sites,
        source_timestamp=context.get("source_timestamp"),
    )
    audit.update(
        context_sha256=actual,
        context_file_sha256=hashlib.sha256(raw).hexdigest(),
        service_type=args.service,
        travel_mode=context["travel_mode"],
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for key, identifier in (
        ("edge_impacts", "edge_id"),
        ("articulation_impacts", "node_id"),
    ):
        rows = audit.pop(key)
        path = args.output_dir / f"{key}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(rows[0])
                if rows
                else [identifier, "residents_losing_all_routes"],
            )
            writer.writeheader()
            writer.writerows(rows)
        audit[key + "_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        audit["highest_" + key] = sorted(
            rows, key=lambda r: (-r["residents_losing_all_routes"], r[identifier])
        )[:20]
    (args.output_dir / "connectivity_audit.json").write_bytes(canonical_bytes(audit))
    print(json.dumps({k: v for k, v in audit.items() if not k.startswith("highest_")}))


if __name__ == "__main__":
    main()
