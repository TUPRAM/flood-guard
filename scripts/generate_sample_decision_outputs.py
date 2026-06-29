"""Generate sample road-risk, access, equity, and GeoJSON outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.access import calculate_access_loss  # noqa: E402
from floodguard.equity import compute_equity_gap, equity_input_from_access_loss  # noqa: E402
from floodguard.exports import write_priority_geojson, write_road_risk_geojson  # noqa: E402
from floodguard.road_risk import score_road_disruption  # noqa: E402
from floodguard.scoring import score_subdistricts  # noqa: E402


def main() -> None:
    """Generate all fixture-backed decision-layer sample outputs."""

    fixture_dir = REPO_ROOT / "tests" / "fixtures"
    output_dir = REPO_ROOT / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    roads = _geojson_properties(fixture_dir / "sample_roads.geojson")
    flood_probability = pd.read_csv(fixture_dir / "sample_flood_probability.csv")
    road_risk = score_road_disruption(roads, flood_probability)
    road_risk_path = output_dir / "sample_road_risk.csv"
    road_risk.to_csv(road_risk_path, index=False)

    access_loss = calculate_access_loss(
        population=pd.read_csv(fixture_dir / "sample_population_nodes.csv"),
        edges=pd.read_csv(fixture_dir / "sample_access_edges.csv"),
        facilities=pd.read_csv(fixture_dir / "sample_facilities.csv"),
    )
    access_loss_path = output_dir / "sample_access_loss.csv"
    access_loss.to_csv(access_loss_path, index=False)

    equity_input = equity_input_from_access_loss(access_loss, threshold=30)
    equity_gap = compute_equity_gap(equity_input)
    equity_gap_path = output_dir / "sample_equity_gap.csv"
    equity_gap.to_csv(equity_gap_path, index=False)

    priority = score_subdistricts(pd.read_csv(fixture_dir / "sample_population.csv"))
    write_priority_geojson(
        fixture_dir / "sample_admin.geojson",
        priority,
        output_dir / "priority_subdistricts.geojson",
    )
    write_road_risk_geojson(
        fixture_dir / "sample_roads.geojson",
        road_risk,
        output_dir / "road_risk.geojson",
    )

    print(f"Wrote {road_risk_path}")
    print(f"Wrote {access_loss_path}")
    print(f"Wrote {equity_gap_path}")
    print(f"Wrote {output_dir / 'priority_subdistricts.geojson'}")
    print(f"Wrote {output_dir / 'road_risk.geojson'}")


def _geojson_properties(path: Path) -> pd.DataFrame:
    geojson = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame(
        [feature.get("properties", {}) for feature in geojson.get("features", [])]
    )


if __name__ == "__main__":
    main()
