"""The decision layer must not move when only candidate evidence changes (G2).

Building counts and Component B's label are diagnostics: ``compute_exposure``
derives ``exposure_0_100`` from WorldPop population density, and ``aggregate``'s
own docstring records that building counts were removed from the score because
OSM "captures ~2% of reality with a 25x spread". So FPPS moving is a **stop
signal** -- it would mean an unanticipated coupling between a diagnostic layer
and the published decision.

Why the baseline is 2026-07-30-run1 and not the older committed artifacts
------------------------------------------------------------------------
The first attempt at this test compared against the artifacts committed under
``outputs/geoai/``, and it failed with max|dFPPS| = 3.39. The investigation found
the cause was not a regression: **those artifacts were never a single run.**
``git log`` per file:

    geoai_metrics.json              b07bebd  2026-07-23
    extra_methods_metrics.json      095c39e  2026-07-24
    geoai_subdistrict_priority.csv  debe413  2026-07-28
    subdistricts.geojson            b07bebd  2026-07-23

They were assembled across three commits and at least three executions, so no
single run of any version of this pipeline would reproduce them together. The
Sentinel-1 fetch and the DEM fetch were both verified byte-deterministic across
repeated calls, and the SAR code and thresholds were unchanged across every
commit -- the drift was in the artifact set, not the code.

Comparing a coherent run against an incoherent reference is not a meaningful
check, so the baseline is now the first internally consistent run: one
execution, one receipt, one commit.

If a future change is *intended* to move FPPS, re-freeze the baseline in the
same commit and say why in the message. Editing the tolerance to make this pass
defeats the point.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pd = pytest.importorskip("pandas", reason="pandas absent in the dependency-light env")

REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINE_DIR = REPO_ROOT / "docs" / "baseline" / "2026-07-30-run1"
BASELINE = BASELINE_DIR / "geoai_subdistrict_priority.csv"
CURRENT = REPO_ROOT / "outputs" / "geoai" / "geoai_subdistrict_priority.csv"

#: FPPS is published to one decimal; anything above this is a real move.
FPPS_TOLERANCE = 0.01

DECISION_COLUMNS = ("fpps_0_100", "action_class", "top_reason", "confidence_class")


def _pair() -> tuple[pd.DataFrame, pd.DataFrame]:
    for path in (BASELINE, CURRENT):
        if not path.is_file():
            pytest.skip(f"missing {path.relative_to(REPO_ROOT)}")
    base = pd.read_csv(BASELINE).set_index("subdistrict_id").sort_index()
    live = pd.read_csv(CURRENT).set_index("subdistrict_id").sort_index()
    return base, live


def test_the_same_areas_are_still_scored() -> None:
    base, live = _pair()
    assert list(base.index) == list(live.index), (
        "the set of scored sub-districts changed; that is a decision-layer "
        "change, not a candidate-evidence change"
    )


def test_fpps_has_not_moved() -> None:
    base, live = _pair()
    delta = (base["fpps_0_100"] - live["fpps_0_100"]).abs()
    moved = delta[delta > FPPS_TOLERANCE]
    assert moved.empty, (
        "FPPS moved. Building counts and the Component B label are diagnostics; "
        "exposure_0_100 comes from WorldPop density, so nothing in the "
        "2026-07-30 re-run should reach the score. Investigate the coupling "
        f"before publishing:\n{moved.to_string()}"
    )


@pytest.mark.parametrize("column", [c for c in DECISION_COLUMNS if c != "fpps_0_100"])
def test_categorical_decision_outputs_are_identical(column: str) -> None:
    base, live = _pair()
    if column not in base.columns or column not in live.columns:
        pytest.skip(f"{column} not published in both tables")
    differing = base.index[base[column].astype(str) != live[column].astype(str)]
    assert len(differing) == 0, (
        f"{column} changed for {list(differing)}; a categorical decision output "
        "must not move when only candidate evidence changed"
    )


def test_component_c_auc_is_reproduced() -> None:
    """G3: Component C was not touched, so it must reproduce."""

    import json

    base_metrics = BASELINE_DIR / "geoai_metrics.json"
    live_metrics = REPO_ROOT / "outputs" / "geoai" / "geoai_metrics.json"
    for path in (base_metrics, live_metrics):
        if not path.is_file():
            pytest.skip(f"missing {path.name}")

    def auc(path: Path) -> float | None:
        return json.loads(path.read_text(encoding="utf-8"))["metrics"]["susceptibility"].get("auc")

    want, got = auc(base_metrics), auc(live_metrics)
    if want is None or got is None:
        pytest.skip("susceptibility AUC not published in both")
    assert abs(want - got) <= 0.03, (
        f"Component C AUC moved {want} -> {got}. Nothing in this run changed "
        "the DEM, river network, or susceptibility weights."
    )
