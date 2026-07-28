"""Tests for the anchored decision bridge (T0.3).

The central property under test is **scale invariance**: a unit's flood
likelihood must depend only on that unit's own observation and terrain, never on
how the other units in the batch happened to score. The previous implementation
divided by the district maximum, so the wettest tambon always scored ~96 -- in a
drought as much as in a flood. That is the failure these tests exist to prevent
from returning.
"""

from __future__ import annotations

import pandas as pd
import pytest

from geoai_runner.realpipeline.aggregate import (
    DEFAULT_EXPOSURE_ANCHOR,
    DEFAULT_FLOOD_ANCHOR,
    AggregationError,
    ExposureAnchor,
    FloodLikelihoodAnchor,
    build_fpps_input_table,
    compute_exposure,
    fuse_flood_likelihood,
    load_subdistrict_context,
    normalise_subdistrict_id,
    osm_completeness,
    signal_agreement,
)


# --------------------------------------------------------------------------- #
# Scale invariance -- the defect this replaced
# --------------------------------------------------------------------------- #
def test_likelihood_is_independent_of_other_units():
    """The same inputs must score the same regardless of batch composition."""

    alone = fuse_flood_likelihood(0.0129, 0.906)[0]
    # Under max-normalisation this unit would score ~96 when it is the wettest
    # and far less when a wetter unit is present. Absolute anchors cannot vary.
    assert fuse_flood_likelihood(0.0129, 0.906)[0] == alone
    assert alone == pytest.approx(47.3, abs=0.1)


def test_dry_conditions_cannot_produce_a_top_score():
    """With zero observed inundation the score is the prior term only."""

    score, terms = fuse_flood_likelihood(0.0, 0.906)
    assert terms["observed_term"] == 0.0
    # 0.30 weight x a near-top prior = ~29, nowhere near the old constant 95.8.
    assert score == pytest.approx(29.2, abs=0.2)
    assert score < 35.0


def test_observed_term_saturates_at_the_declared_share():
    at = fuse_flood_likelihood(DEFAULT_FLOOD_ANCHOR.observed_saturation_share, 0.65)
    beyond = fuse_flood_likelihood(0.5, 0.65)
    assert at[1]["observed_term"] == 1.0
    assert beyond[1]["observed_term"] == 1.0
    assert at[0] == beyond[0]


def test_prior_is_centred_on_the_district_reference():
    neutral = fuse_flood_likelihood(0.0, DEFAULT_FLOOD_ANCHOR.prior_reference_mean)
    assert neutral[1]["prior_term"] == pytest.approx(0.5)
    # Centring is what restores discrimination between tambons that all sit near
    # 0.90 susceptibility and one that sits at 0.55.
    high = fuse_flood_likelihood(0.0, 0.906)[1]["prior_term"]
    low = fuse_flood_likelihood(0.0, 0.549)[1]["prior_term"]
    assert high - low > 0.6


def test_prior_does_not_clip_over_the_observed_susceptibility_range():
    """A saturating prior would re-destroy the discrimination centring restored.

    Mae Sai's tambon susceptibility means span 0.549 to 0.917. If the gain pushes
    the top of that range past 1.0, the four riverside tambons all clip to the
    same value and the prior stops distinguishing them.
    """

    priors = [
        fuse_flood_likelihood(0.0, susceptibility)[1]["prior_term"]
        for susceptibility in (0.549, 0.578, 0.604, 0.732, 0.904, 0.906, 0.908, 0.917)
    ]
    assert max(priors) < 1.0, "prior clips at the top of the observed range"
    assert min(priors) > 0.0
    # The four ~0.90 tambons must remain distinguishable from one another.
    assert len({round(p, 3) for p in priors[-4:]}) == 4


def test_a_genuine_flood_produces_high_confidence_and_a_high_score():
    """Guards against a degenerate scale that can only ever return low confidence.

    On the committed Sept-2024 acquisition every tambon lands in action class E,
    because a 4-day-stale snapshot genuinely cannot support life-safety
    prioritisation. That must be a property of the *data*, not of the scale -- so
    a unit with real inundation on flood-prone terrain has to come out high.
    """

    likelihood, terms = fuse_flood_likelihood(0.06, 0.90)
    confidence, gap = signal_agreement(terms["observed_term"], terms["prior_term"])
    assert likelihood > 90.0
    assert confidence == "high"
    assert gap < 0.35


def test_agreement_gap_bands():
    assert signal_agreement(0.5, 0.5) == ("high", 0.0)
    assert signal_agreement(0.1, 0.6)[0] == "medium"
    assert signal_agreement(0.1, 0.9)[0] == "low"


def test_agreement_is_symmetric():
    assert signal_agreement(0.2, 0.8) == signal_agreement(0.8, 0.2)


def test_post_peak_disagreement_is_reported_as_low_confidence():
    """The committed Ko Chang case: terrain says flood-prone, image says drained."""

    _, terms = fuse_flood_likelihood(0.01291, 0.906)
    confidence, gap = signal_agreement(terms["observed_term"], terms["prior_term"])
    assert confidence == "low"
    assert gap > 0.65


def test_likelihood_is_monotonic_in_both_signals():
    base = fuse_flood_likelihood(0.01, 0.7)[0]
    assert fuse_flood_likelihood(0.02, 0.7)[0] > base
    assert fuse_flood_likelihood(0.01, 0.8)[0] > base


def test_anchor_version_is_carried():
    assert DEFAULT_FLOOD_ANCHOR.version == "fpps_flood_anchor_v1"
    assert DEFAULT_EXPOSURE_ANCHOR.version == "fpps_exposure_anchor_v1"


def test_custom_anchor_changes_the_scale():
    strict = FloodLikelihoodAnchor(observed_saturation_share=0.5)
    assert (
        fuse_flood_likelihood(0.05, 0.65, anchor=strict)[0]
        < fuse_flood_likelihood(0.05, 0.65)[0]
    )


@pytest.mark.parametrize("bad", [-0.1, 1.5, float("nan")])
def test_out_of_range_inputs_are_rejected(bad):
    with pytest.raises(AggregationError):
        fuse_flood_likelihood(bad, 0.5)
    with pytest.raises(AggregationError):
        fuse_flood_likelihood(0.5, bad)


# --------------------------------------------------------------------------- #
# Exposure from population
# --------------------------------------------------------------------------- #
def test_exposure_tracks_population_density():
    dense, terms = compute_exposure(17893.0, 21.57)
    sparse, _ = compute_exposure(6708.0, 47.44)
    assert dense > sparse
    assert terms["density_per_km2"] == pytest.approx(829.5, abs=1.0)
    assert dense == pytest.approx(82.9, abs=0.2)


def test_missing_population_yields_none_not_zero():
    """Absent data is not an absence of people."""

    score, terms = compute_exposure(None, 21.57)
    assert score is None
    assert terms["density_per_km2"] is None
    assert compute_exposure(1000.0, None)[0] is None
    assert compute_exposure(1000.0, 0.0)[0] is None


def test_exposure_saturates_at_the_anchor_density():
    anchor = ExposureAnchor(saturation_density_per_km2=1000.0)
    assert compute_exposure(2000.0, 1.0, anchor=anchor)[0] == 100.0
    assert compute_exposure(1000.0, 1.0, anchor=anchor)[0] == 100.0


# --------------------------------------------------------------------------- #
# OSM completeness diagnostics
# --------------------------------------------------------------------------- #
def test_osm_coverage_at_mae_sai_is_flagged_severely_incomplete():
    # 86 mapped buildings against ~17,893 residents.
    report = osm_completeness(86, 17893.0)
    assert report["osm_completeness_flag"] == "severely_incomplete"
    assert report["osm_completeness_ratio"] < 0.05


def test_zero_buildings_is_flagged_not_treated_as_empty():
    report = osm_completeness(0, 7157.0)
    assert report["osm_building_count"] == 0
    assert report["osm_completeness_flag"] == "severely_incomplete"


def test_plausible_coverage_is_usable():
    assert osm_completeness(2000, 8000.0)["osm_completeness_flag"] == "usable"


def test_unknown_population_is_reported_as_unknown():
    assert osm_completeness(50, None)["osm_completeness_flag"] == "unknown_no_population"


# --------------------------------------------------------------------------- #
# Identifier normalisation and context loading
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,expected",
    [("TH570901", "570901"), ("570901", "570901"), (" th570901 ", "570901"), (None, "")],
)
def test_subdistrict_id_normalisation(raw, expected):
    assert normalise_subdistrict_id(raw) == expected


def test_context_loader_reads_real_committed_artifacts(repo_root):
    context = load_subdistrict_context(
        repo_root / "outputs" / "mae_sai_subdistrict_flood_inputs.csv",
        repo_root / "outputs" / "mae_sai_admin_context.geojson",
    )
    assert context.has("570901")
    assert context.has("TH570901")  # both identifier forms resolve
    assert context.population["570901"] == pytest.approx(17893.0, abs=1.0)
    assert context.area_sq_km["570901"] == pytest.approx(21.57, abs=0.1)
    # Real context genuinely discriminates: Ko Chang is the isolated riverside unit.
    assert context.components["570903"]["access_gap_0_100"] > 80.0
    assert context.components["570901"]["access_gap_0_100"] < 5.0


def test_context_loader_fails_closed_on_missing_files(tmp_path, repo_root):
    with pytest.raises(AggregationError, match="context not found"):
        load_subdistrict_context(
            tmp_path / "absent.csv", repo_root / "outputs" / "mae_sai_admin_context.geojson"
        )


# --------------------------------------------------------------------------- #
# FPPS table assembly
# --------------------------------------------------------------------------- #
def _ai_frame():
    return pd.DataFrame(
        [
            {
                "subdistrict_id": "570903",
                "subdistrict_name": "Ko Chang",
                "flood_likelihood_0_100": 48.1,
                "exposure_0_100": 14.1,
                "confidence_class": "high",
            },
            {
                "subdistrict_id": "570901",
                "subdistrict_name": "Mae Sai",
                "flood_likelihood_0_100": 31.8,
                "exposure_0_100": 82.9,
                "confidence_class": "high",
            },
        ]
    )


def test_real_context_is_joined_when_available(repo_root):
    context = load_subdistrict_context(
        repo_root / "outputs" / "mae_sai_subdistrict_flood_inputs.csv",
        repo_root / "outputs" / "mae_sai_admin_context.geojson",
    )
    table = build_fpps_input_table(_ai_frame(), context=context)
    assert set(table["context_source"]) == {"decision_layer_real_context"}
    ko_chang = table[table["subdistrict_id"] == "570903"].iloc[0]
    assert ko_chang["access_gap_0_100"] > 80.0
    assert ko_chang["confidence_class"] == "high"


def test_placeholder_context_forces_low_confidence():
    table = build_fpps_input_table(_ai_frame(), context=None)
    assert set(table["context_source"]) == {"placeholder"}
    # A fabricated context must never be presented at full confidence.
    assert set(table["confidence_class"]) == {"low"}


def test_absent_exposure_is_marked_low_confidence_not_silently_zero():
    frame = _ai_frame()
    frame.loc[0, "exposure_0_100"] = None
    table = build_fpps_input_table(frame, context=None)
    row = table.iloc[0]
    assert row["exposure_0_100"] == 0.0
    assert row["confidence_class"] == "low"


def test_table_scores_end_to_end(repo_root):
    from floodguard.scoring import score_subdistricts

    context = load_subdistrict_context(
        repo_root / "outputs" / "mae_sai_subdistrict_flood_inputs.csv",
        repo_root / "outputs" / "mae_sai_admin_context.geojson",
    )
    scored = score_subdistricts(build_fpps_input_table(_ai_frame(), context=context))
    assert scored["action_class"].isin(list("ABCDE")).all()
    assert scored["fpps_0_100"].between(0, 100).all()
    # The published headline must be the anchored value, not the old inflated one.
    ko_chang = scored[scored["subdistrict_id"] == "570903"].iloc[0]
    assert ko_chang["fpps_0_100"] == pytest.approx(40.6, abs=0.5)
