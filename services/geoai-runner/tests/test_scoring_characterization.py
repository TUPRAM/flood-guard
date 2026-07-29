"""Golden characterization of the GeoAI -> FPPS bridge (D-02).

Why this exists
---------------
Routing Component A-F output through a receipt (D-02) changes the code path
that produces FPPS and the A-E action classes. The audit's stated acceptance
for that change is "re-run the pipeline and diff FPPS against the baseline" --
which is not reproducible: the committed results came from a machine that no
longer exists, and a real run needs network, the geoai extra, and ~an hour.

The committed priority table happens to carry BOTH sides of the computation:
the five score components that go in, and the fpps/action_class/top_reason that
come out, for all 8 Mae Sai tambons. That makes the bridge characterizable
offline. This test pins the current behaviour so any change to how scoring is
reached can be proven behaviour-preserving in the dependency-light environment,
which is the only place CI runs.

It deliberately asserts EXACT equality on fpps_0_100. A receipt lane that
rounds, reorders, or re-derives differently is a behaviour change and must be
justified on its own terms, not absorbed into a refactor.

If this test fails after a scoring change, do not update the golden values
without a recorded reason: the numbers are published in
apps/web/public/geoai/mae-sai-real.json and read by the Command surface.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pd = pytest.importorskip("pandas", reason="pandas is not in the dependency-light env")

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN = REPO_ROOT / "outputs" / "geoai" / "geoai_subdistrict_priority.csv"

SCORE_INPUTS = [
    "flood_likelihood_0_100",
    "exposure_0_100",
    "access_gap_0_100",
    "road_criticality_0_100",
    "vulnerability_context_0_100",
]
IDENTITY = ["subdistrict_id", "subdistrict_name", "confidence_class"]
SCORE_OUTPUTS = ["fpps_0_100", "action_class", "top_reason"]


def _golden() -> pd.DataFrame:
    if not GOLDEN.is_file():
        pytest.skip(f"committed GeoAI priority table absent: {GOLDEN}")
    return pd.read_csv(GOLDEN)


def _scoring():
    try:
        from floodguard.scoring import score_subdistricts
    except ImportError:  # pragma: no cover
        pytest.skip("floodguard.scoring unavailable in this environment")
    return score_subdistricts


def test_golden_table_carries_both_sides_of_the_bridge() -> None:
    """Guard the guard: if the columns move, this test silently stops testing."""

    df = _golden()
    missing = [c for c in IDENTITY + SCORE_INPUTS + SCORE_OUTPUTS if c not in df.columns]
    assert not missing, (
        f"the committed priority table no longer carries {missing}; this "
        "characterization test can no longer verify the scoring bridge"
    )
    assert len(df) == 8, f"expected 8 Mae Sai tambons, found {len(df)}"


def test_scoring_reproduces_the_published_fpps_exactly() -> None:
    """Feed the committed inputs back through scoring; outputs must be identical."""

    df = _golden()
    score_subdistricts = _scoring()

    recomputed = score_subdistricts(df[IDENTITY + SCORE_INPUTS].copy())

    published = df.set_index("subdistrict_id")
    actual = recomputed.set_index("subdistrict_id")

    mismatches = []
    for area_id in published.index:
        for column in SCORE_OUTPUTS:
            want, got = published.at[area_id, column], actual.at[area_id, column]
            same = abs(want - got) < 1e-9 if isinstance(want, float) else str(want) == str(got)
            if not same:
                mismatches.append(f"{area_id}.{column}: published={want!r} recomputed={got!r}")

    assert not mismatches, (
        "Scoring no longer reproduces the published Mae Sai figures. These "
        "numbers are served to the Command surface; a change here is a "
        "behaviour change, not a refactor:\n  " + "\n  ".join(mismatches)
    )


def test_action_classes_are_within_the_published_vocabulary() -> None:
    df = _golden()
    allowed = {"A", "B", "C", "D", "E"}
    unexpected = set(df["action_class"].astype(str)) - allowed
    assert not unexpected, f"action_class outside A-E: {sorted(unexpected)}"
