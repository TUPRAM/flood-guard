"""Export a reproducible, non-operational planning rehearsal from the existing engine.

Run with ``uv run --project services/api python scripts/build_mae_sai_planning_demo.py``.
Use ``--check`` to compare regeneration with the committed browser package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from floodguard.access import _build_graph, _facility_minutes_by_node
from floodguard_api.config import RepositoryPaths
from floodguard_api.dataset_registry import MaeSaiCandidateAdapter
from floodguard_api.models import ScenarioRunRequest

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "apps/web/src/data/mae-sai-planning-demo.json"
CASE_VERSION = "mae-sai-planning-rehearsal-v1"
# Release-record time, not a claim that the historical source was observed now.
GENERATED_AT = "2026-09-16T06:07:49Z"


def canonical_sha256(payload: dict[str, Any]) -> str:
    """Hash JSON without the self-referential package digest."""
    unsigned = {**payload, "meta": dict(payload["meta"])}
    unsigned["meta"].pop("package_sha256", None)
    data = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _load(root: Path, relative: str) -> dict[str, Any]:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _source(root: Path, relative: str, role: str) -> dict[str, str]:
    return {
        "path": relative,
        "sha256": hashlib.sha256((root / relative).read_bytes()).hexdigest(),
        "role": role,
    }


def build_case(root: Path = ROOT) -> dict[str, Any]:
    """Regenerate the bounded case with the checksum-validating candidate adapter."""
    adapter = MaeSaiCandidateAdapter(RepositoryPaths(root=root))
    population, edges, facilities, input_manifest = adapter._scenario_inputs()
    baseline_access, baseline_equity = adapter._scenario_baseline(
        population, edges, facilities
    )
    scenarios = []
    descriptions = {
        "close_road": {
            "title": "Close one candidate connection",
            "description": "Remove the registered graph connection from the disrupted network and recompute access.",
            "changed_assumption": "Candidate edge MS-EDGE-0008687 is unavailable; this is a hypothetical closure, not an observation.",
            "verification_need": "Verify the connection's real identity, event-time passability and alternative routes with a responsible local reviewer before changing a plan.",
        },
        "add_temporary_shelter": {
            "title": "Add a candidate service location",
            "description": "Add the registered candidate facility to the normal and disrupted networks using the existing nearest-facility engine.",
            "changed_assumption": "A hypothetical facility exists at N-99.9742609-20.4457677. It is not an approved shelter; no capacity or transport allocation is calculated.",
            "verification_need": "Verify site suitability, permission, actual function, operating status and access. The model treats all facility types as interchangeable destinations.",
        },
    }
    for scenario_id, description in descriptions.items():
        result = adapter.run_scenario(
            ScenarioRunRequest(
                study_area="mae_sai_candidate_v1", scenario_id=scenario_id
            )
        ).model_dump(mode="json")
        scenarios.append(
            {
                "scenario_id": scenario_id,
                **description,
                "run_id": result["run_id"],
                "overall": result["overall"],
                "areas": result["areas"],
                "assumptions": result["assumptions"],
            }
        )

    baseline_rows = [
        {
            **row,
            "scenario_people_losing_30_min_access": row[
                "baseline_people_losing_30_min_access"
            ],
            "change_people_losing_30_min_access": 0,
            "scenario_equity_gap_ratio": row["baseline_equity_gap_ratio"],
            "change_equity_gap_ratio": 0
            if row["baseline_equity_gap_ratio"] is not None
            else None,
        }
        for row in scenarios[0]["areas"]
    ]
    summary = scenarios[0]["overall"]
    baseline_scenario = {
        "scenario_id": "baseline",
        "title": "Candidate disruption baseline",
        "description": "Existing heuristic disruption times compared with the same graph's normal travel times.",
        "changed_assumption": "No additional closure or facility is introduced. Baseline already includes heuristic disruption.",
        "verification_need": "Check historical road and facility conditions; the candidate disruption is not an observed event reconstruction.",
        "run_id": "mae-sai-candidate-baseline-v1",
        "overall": {
            "baseline_people_losing_30_min_access": summary[
                "baseline_people_losing_30_min_access"
            ],
            "scenario_people_losing_30_min_access": summary[
                "baseline_people_losing_30_min_access"
            ],
            "change_people_losing_30_min_access": 0,
            "baseline_max_equity_gap_ratio": summary["baseline_max_equity_gap_ratio"],
            "scenario_max_equity_gap_ratio": summary["baseline_max_equity_gap_ratio"],
            "change_max_equity_gap_ratio": 0,
        },
        "areas": baseline_rows,
        "assumptions": list(input_manifest.assumptions),
    }
    normal_distances = _facility_minutes_by_node(
        _build_graph(edges, "normal_minutes", allow_closed=False),
        set(facilities["node_id"].astype(str)),
    )
    underserved = (
        population.loc[
            population["node_id"].map(normal_distances).fillna(float("inf")) > 30
        ]
        .groupby("subdistrict_id")["total_population"]
        .sum()
    )
    priority_path = "outputs/mae_sai_priority_subdistricts.geojson"
    priorities = {
        feature["properties"]["subdistrict_id"]: feature["properties"]
        for feature in _load(root, priority_path)["features"]
    }
    baseline_index = baseline_access.set_index("subdistrict_id")
    equity_index = baseline_equity.set_index("subdistrict_id")
    areas = []
    for row in baseline_rows:
        area_id = row["area_id"]
        priority = priorities[area_id]
        areas.append(
            {
                "area_id": area_id,
                "name_en": priority["subdistrict_name"],
                "name_th": priority["subdistrict_name_th"],
                "baseline": {
                    "total_population": round(
                        float(baseline_index.loc[area_id, "total_population"]), 3
                    ),
                    "people_losing_30_min_access": row[
                        "baseline_people_losing_30_min_access"
                    ],
                    "baseline_underserved_30_min": round(
                        float(underserved.get(area_id, 0)), 3
                    ),
                    "equity_gap_ratio": row["baseline_equity_gap_ratio"],
                },
                "existing_priority": {
                    "fpps": float(priority["fpps_0_100"]),
                    "action_class": priority["action_class"],
                    "total_population": float(priority["total_population"]),
                    "people_losing_30_min_access": float(
                        priority["people_losing_30_min_access"]
                    ),
                },
            }
        )
        # The API's published ratio must match the same engine's unrounded table.
        assert row["baseline_equity_gap_ratio"] == float(
            equity_index.loc[area_id, "equity_gap_ratio"]
        )

    manifest_path = "services/api/data/study_area_bundles/mae_sai_candidate_v1.json"
    bundle_manifest = _load(root, manifest_path)
    scenario_manifest_path = "outputs/mae_sai_scenario_inputs_manifest.json"
    scenario_manifest = _load(root, scenario_manifest_path)
    source_specs = [
        (manifest_path, "historical case identity"),
        (scenario_manifest_path, "immutable graph inputs and receipt"),
        (priority_path, "unchanged historical priority context"),
    ]
    source_specs.extend(
        (f"outputs/{artifact['relative_path']}", artifact["role"])
        for artifact in scenario_manifest["artifacts"]
    )
    source_specs.extend(
        (path, "Python computation")
        for path in [
            "src/floodguard/access.py",
            "src/floodguard/equity.py",
            "src/floodguard/scenarios.py",
            "services/api/src/floodguard_api/dataset_registry.py",
            "services/api/src/floodguard_api/scenario_registry.py",
            "scripts/build_mae_sai_planning_demo.py",
        ]
    )
    payload = {
        "meta": {
            "case_id": "mae-sai-2024-historical-planning-demo",
            "case_version": CASE_VERSION,
            "study_area_id": "mae_sai_candidate_v1",
            "event_label": "Mae Sai · September 2024 historical planning rehearsal",
            "source_timestamp": scenario_manifest["source_timestamp"],
            "source_processing_timestamp": scenario_manifest["generated_at"],
            "generated_at": GENERATED_AT,
            "operational_status": "non_operational",
            "confidence_class": "low",
            "fpps_recalculated": False,
            "local_accuracy_status": "unqualified_local_accuracy",
            "can_feed_decision_layer": False,
            "official_warning": False,
        },
        "scope": {
            "description": "Eight Mae Sai subdistricts, one committed candidate graph and two server-registered assumptions.",
            "population_basis": "WorldPop 2020 modelled population snapped to the candidate OSM network. Fractional estimates are not a headcount; API access-loss counts round each result to whole people.",
            "graph_population": round(float(population["total_population"].sum()), 3),
            "graph_node_count": len(set(edges["from_node"]) | set(edges["to_node"])),
            "graph_edge_count": len(edges),
            "facility_count": len(facilities),
            "threshold_minutes": 30,
            "priority_scope_note": "Scenario results use the complete committed cross-area graph. Its baseline access-loss counts match the archived ADM3 summaries within whole-person rounding. Original FPPS, action classes and source population estimates are retained separately and never recalculated; small population differences reflect source rounding.",
        },
        "areas": areas,
        "scenarios": [baseline_scenario, *scenarios],
        "sources": [_source(root, relative, role) for relative, role in source_specs],
        "source_components": [
            {
                "name": component["source_name"],
                "timestamp": component["source_timestamp"],
                "temporal_meaning": component["temporal_meaning"],
            }
            for component in bundle_manifest["source_components"]
        ],
        "assumptions": [
            *scenario_manifest["assumptions"],
            "New access loss counts only residents who had normal-network access within 30 minutes and lose it under disruption. Baseline underserved residents already lack normal-network access and are reported separately.",
            "The 2024 Sentinel-1 observation, 2020 population and July 2026 OSM extract are not date-aligned. This is a reproducible planning rehearsal, not a validated reconstruction of September 2024 conditions.",
            "The temporary facility exists in both normal and disrupted graphs in the existing engine, so its delta is a comparison of scenario-specific access-loss definitions; it is not a fixed-cohort estimate of people rescued.",
            "Routes are undirected shortest-path travel-time estimates; service types are pooled and capacity, queueing, vehicle availability and flood-safe navigation are not modelled.",
            "A high or low equity ratio concerns a terrain/remoteness proxy, not independently measured demographic disadvantage; zero losses can yield a ratio of 1 by convention.",
            "No research model has been promoted into planning. Existing FPPS and action classes remain unchanged; scenario results are candidate review evidence only.",
        ],
        "validation": {
            "status": "Local scientific and operating-partner validation not completed",
            "measured": [
                "Deterministic recomputation of the existing access/equity engine on checksum-bound committed inputs; not independent scientific accuracy."
            ],
            "not_measured": [
                "Date-aligned Mae Sai observation accuracy",
                "Actual event-time road passability or facility operation",
                "Demographic equity, shelter capacity or safe routes",
                "Decision usefulness with an operating partner",
            ],
            "required_next_steps": [
                "Agree an intended claim and a permitted, date-aligned independent reference.",
                "Predefine sampling, unknown areas and held-out evaluation before measuring local water or inundation accuracy.",
                "Check road passability, facility operating status and pre-existing access disadvantage separately from pixel accuracy.",
                "Run a supervised planning exercise and record interpretation errors, decisions and unresolved evidence before considering a bounded pilot.",
            ],
        },
    }
    payload["meta"]["package_sha256"] = canonical_sha256(payload)
    return payload


def main() -> None:
    """Write the deterministic package or fail when committed output has drifted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    serialized = (
        json.dumps(build_case(), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    if arguments.check:
        if not TARGET.exists() or TARGET.read_bytes() != serialized.encode("utf-8"):
            raise SystemExit(
                "Mae Sai planning package is stale; regenerate it with this script."
            )
        print("Mae Sai planning package is reproducible and current.")
    else:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_bytes(serialized.encode("utf-8"))
        print(TARGET.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
