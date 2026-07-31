from __future__ import annotations

import math
from dataclasses import replace

import pytest

from floodguard.label_factory.sampling import (
    AcquisitionComponents,
    QueryCandidate,
    SamplingError,
    absolute_probability_disagreement,
    binary_boundary_impurity,
    compute_batch_quotas,
    compute_region_acquisition_components,
    jensen_shannon_disagreement,
    normalized_binary_entropy,
    score_query_candidates,
    select_review_batch,
    top_tail_mean,
)


def test_entropy_and_disagreement_have_normalized_interpretable_limits() -> None:
    assert normalized_binary_entropy(0.0) == 0.0
    assert normalized_binary_entropy(1.0) == 0.0
    assert normalized_binary_entropy(0.5) == 1.0
    assert absolute_probability_disagreement(0.2, 0.8) == pytest.approx(0.6)
    assert jensen_shannon_disagreement(0.4, 0.4) == pytest.approx(0.0)
    assert jensen_shannon_disagreement(0.0, 1.0) == pytest.approx(1.0)

    with pytest.raises(SamplingError, match=r"\[0, 1\]"):
        normalized_binary_entropy(1.01)


def test_top_tail_region_aggregation_uses_ceil_and_keeps_components_separate() -> None:
    assert top_tail_mean([0.1, 0.2, 0.3, 0.9, 1.0], fraction=0.20) == 1.0
    assert top_tail_mean([0.1, 0.2, 0.3, 0.9, 1.0], fraction=0.21) == 0.95

    components = compute_region_acquisition_components(
        [0.5, 0.1, 0.9, 0.0, 1.0],
        [0.5, 0.9, 0.1, 1.0, 0.0],
        boundary_impurity=0.35,
        top_tail_fraction=0.20,
    )

    assert components.uncertainty == pytest.approx(1.0)
    assert components.absolute_disagreement == pytest.approx(1.0)
    assert components.jensen_shannon_disagreement == pytest.approx(1.0)
    assert components.boundary_impurity == 0.35


def test_boundary_impurity_is_auditable_neighbour_disagreement_fraction() -> None:
    assert binary_boundary_impurity([[0, 0], [0, 0]]) == 0.0
    assert binary_boundary_impurity([[0, 1], [1, 0]]) == 1.0
    assert binary_boundary_impurity([[1]]) == 0.0
    with pytest.raises(SamplingError, match="rectangular"):
        binary_boundary_impurity([[0, 1], [1]])


def test_acquisition_score_exposes_raw_ranks_and_weighted_score() -> None:
    candidates = [
        _candidate(index, value=value)
        for index, value in enumerate((0.1, 0.5, 0.9))
    ]

    scored = score_query_candidates(candidates)

    assert scored[0].active_score == pytest.approx(0.0)
    assert scored[1].uncertainty_rank == pytest.approx(0.5)
    assert scored[1].disagreement_rank == pytest.approx(0.5)
    assert scored[1].boundary_rank == pytest.approx(0.5)
    assert scored[1].active_score == pytest.approx(0.5)
    assert scored[2].active_score == pytest.approx(1.0)
    assert scored[2].to_dict()["absolute_disagreement"] == 0.9


def test_acquisition_ranks_are_normalized_within_event_and_land_cover_stratum() -> None:
    candidates = [
        _candidate(0, value=0.1),
        _candidate(1, value=0.9),
        QueryCandidate(
            **{
                **_candidate(2, value=0.2).__dict__,
                "region_id": "other-stratum-low",
                "major_land_cover_stratum": "urban",
            }
        ),
        QueryCandidate(
            **{
                **_candidate(3, value=0.8).__dict__,
                "region_id": "other-stratum-high",
                "major_land_cover_stratum": "urban",
            }
        ),
    ]

    scored = {item.region_id: item for item in score_query_candidates(candidates)}

    assert scored["region-000"].uncertainty_rank == 0.0
    assert scored["region-001"].uncertainty_rank == 1.0
    assert scored["other-stratum-low"].uncertainty_rank == 0.0
    assert scored["other-stratum-high"].uncertainty_rank == 1.0


@pytest.mark.parametrize(
    ("batch_size", "expected"),
    [
        (1, (0, 0, 1)),
        (2, (1, 0, 1)),
        (3, (1, 1, 1)),
        (8, (5, 2, 1)),
        (40, (24, 8, 8)),
    ],
)
def test_batch_quotas_round_safely_and_always_keep_random_control(
    batch_size: int,
    expected: tuple[int, int, int],
) -> None:
    quotas = compute_batch_quotas(batch_size)

    assert (quotas.active, quotas.hard_stratum, quotas.random_control) == expected
    assert quotas.total == batch_size
    assert quotas.random_control >= 1


def test_batch_selection_is_deterministic_and_achieves_60_20_20() -> None:
    candidates = [_candidate(index, hard=index < 20) for index in range(40)]

    first = select_review_batch(candidates, batch_size=40, random_seed=71)
    second = select_review_batch(
        list(reversed(candidates)),
        batch_size=40,
        random_seed=71,
    )

    assert [item.region_id for item in first.selected] == [
        item.region_id for item in second.selected
    ]
    assert first.requested_quotas.to_dict() == {
        "active": 24,
        "hard_stratum": 8,
        "random_control": 8,
    }
    assert first.achieved_quotas == first.requested_quotas
    assert len({item.region_id for item in first.selected}) == 40


def test_random_control_selection_is_independent_of_active_score() -> None:
    ordinary = [_candidate(index, value=index / 20) for index in range(20)]
    reversed_scores = [
        _candidate(index, value=(19 - index) / 20)
        for index in range(20)
    ]

    first = select_review_batch(ordinary, batch_size=8, random_seed=19)
    second = select_review_batch(reversed_scores, batch_size=8, random_seed=19)

    first_random = [item.region_id for item in first.selected if item.lane == "random_control"]
    second_random = [item.region_id for item in second.selected if item.lane == "random_control"]
    assert first_random == second_random
    assert len(first_random) == 1


def test_random_control_is_stratified_and_records_inclusion_probability() -> None:
    candidates = [
        replace(
            _candidate(index, hard=index < 5),
            major_land_cover_stratum="urban" if index < 5 else "cropland",
        )
        for index in range(10)
    ]

    result = select_review_batch(candidates, batch_size=8, random_seed=23)
    random_rows = [item for item in result.selected if item.lane == "random_control"]

    assert len(random_rows) == 1
    assert random_rows[0].sampling_stratum_population == 5
    assert random_rows[0].sampling_stratum_quota == 1
    assert random_rows[0].inclusion_probability == pytest.approx(0.2)


@pytest.mark.parametrize(
    "dataset_role",
    [
        "reviewer_calibration",
        "fixed_within_event_development",
        "untouched_geographic_test",
    ],
)
def test_acquisition_rejects_calibration_development_and_test_roles(
    dataset_role: str,
) -> None:
    candidate = _candidate(0, dataset_role=dataset_role)

    with pytest.raises(SamplingError, match="must never enter acquisition"):
        score_query_candidates([candidate])


def test_selection_never_returns_overlapping_or_near_duplicate_regions() -> None:
    candidates = [
        _candidate(0, hard=True, overlap_group="overlap-a"),
        _candidate(1, overlap_group="overlap-a"),
        _candidate(2, hard=True, near_duplicate_group="duplicate-b"),
        _candidate(3, near_duplicate_group="duplicate-b"),
        _candidate(4, hard=True),
        _candidate(5),
    ]

    selected = select_review_batch(candidates, batch_size=4, random_seed=2)
    ids = {item.region_id for item in selected.selected}

    assert not {"region-000", "region-001"}.issubset(ids)
    assert not {"region-002", "region-003"}.issubset(ids)
    assert len(ids) == 4


def test_selection_fails_closed_when_only_overlapping_regions_can_fill_batch() -> None:
    candidates = [
        _candidate(0, hard=True, overlap_group="same-core"),
        _candidate(1, hard=True, overlap_group="same-core"),
    ]

    with pytest.raises(SamplingError, match="overlapping or near-duplicate"):
        select_review_batch(candidates, batch_size=2, random_seed=0)


def test_selection_rejects_exact_semantic_duplicates_by_default() -> None:
    first = _candidate(0, hard=True)
    second = QueryCandidate(
        region_id="region-duplicate",
        dataset_role="training_and_query_pool",
        event_id="TH-MAESAI-2024-09",
        crs="EPSG:32647",
        components=AcquisitionComponents(0.8, 0.8, 0.8, 0.8),
        diversity_features=first.diversity_features,
        hard_stratum=True,
        bounds=(1_000.0, 0.0, 1_050.0, 50.0),
    )

    with pytest.raises(SamplingError, match="overlapping or near-duplicate"):
        select_review_batch([first, second], batch_size=2)


def test_optional_event_and_land_cover_quotas_are_enforced() -> None:
    candidates = []
    for index in range(16):
        base = _candidate(index, hard=index < 6)
        candidates.append(
            replace(
                base,
                event_id="EVENT-A" if index < 8 else "EVENT-B",
                major_land_cover_stratum=(
                    "urban" if index % 2 == 0 else "cropland"
                ),
            )
        )

    result = select_review_batch(
        candidates,
        batch_size=8,
        random_seed=4,
        maximum_per_event=4,
        maximum_per_land_cover_stratum=2,
    )

    selected = [item.scored_candidate.candidate for item in result.selected]
    assert sum(item.event_id == "EVENT-A" for item in selected) == 4
    assert sum(item.event_id == "EVENT-B" for item in selected) == 4
    assert all(
        sum(
            other.event_id == item.event_id
            and other.major_land_cover_stratum == item.major_land_cover_stratum
            for other in selected
        )
        <= 2
        for item in selected
    )


def _candidate(
    index: int,
    *,
    value: float | None = None,
    hard: bool = False,
    dataset_role: str = "training_and_query_pool",
    overlap_group: str | None = None,
    near_duplicate_group: str | None = None,
) -> QueryCandidate:
    component = min(1.0, max(0.0, value if value is not None else (index + 1) / 50))
    x_min = float(index * 100)
    return QueryCandidate(
        region_id=f"region-{index:03d}",
        dataset_role=dataset_role,
        event_id="TH-MAESAI-2024-09",
        crs="EPSG:32647",
        components=AcquisitionComponents(
            uncertainty=component,
            absolute_disagreement=component,
            jensen_shannon_disagreement=component,
            boundary_impurity=component,
        ),
        diversity_features=(
            float(index),
            math.sin(index + 0.1),
            math.cos(index + 0.1),
        ),
        hard_stratum=hard,
        bounds=(x_min, 0.0, x_min + 50.0, 50.0),
        overlap_group=overlap_group,
        near_duplicate_group=near_duplicate_group,
    )
