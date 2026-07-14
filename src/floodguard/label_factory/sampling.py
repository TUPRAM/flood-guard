"""Auditable active-learning acquisition and batch selection.

The functions in this module build *review queues*. They do not create flood
labels and they are never an input to FPPS.  The implementation deliberately
keeps uncertainty, model disagreement, boundary impurity, diversity, and lane
assignment as separate fields so a selected region always has an inspectable
reason for being selected.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import hashlib
import math
from typing import Literal

from floodguard.label_factory.contracts import DatasetRole

QUERY_POOL_ROLE = DatasetRole.TRAINING_AND_QUERY_POOL.value
ACTIVE_FRACTION = 0.60
HARD_STRATUM_FRACTION = 0.20
RANDOM_CONTROL_FRACTION = 0.20

DisagreementMetric = Literal["absolute", "jensen_shannon"]
SelectionLane = Literal["active", "hard_stratum", "random_control"]


class SamplingError(ValueError):
    """Raised when an acquisition score or review batch is unsafe or invalid."""


@dataclass(frozen=True)
class AcquisitionComponents:
    """Unnormalised, independently inspectable scores for one query region."""

    uncertainty: float
    absolute_disagreement: float
    jensen_shannon_disagreement: float
    boundary_impurity: float

    def to_dict(self) -> dict[str, float]:
        """Return stable manifest-friendly component names."""

        return {
            "uncertainty": self.uncertainty,
            "absolute_disagreement": self.absolute_disagreement,
            "jensen_shannon_disagreement": self.jensen_shannon_disagreement,
            "boundary_impurity": self.boundary_impurity,
        }


@dataclass(frozen=True)
class QueryCandidate:
    """A query-eligible region and the metadata needed to de-duplicate it.

    ``bounds`` uses ``(xmin, ymin, xmax, ymax)`` in the event's projected CRS.
    ``overlap_group`` is for regions whose cores share pixels even when bounds
    are not available. ``near_duplicate_group`` can encode a precomputed
    semantic or source-scene duplicate cluster.
    """

    region_id: str
    dataset_role: str | DatasetRole
    components: AcquisitionComponents
    diversity_features: tuple[float, ...]
    event_id: str = ""
    crs: str = ""
    major_land_cover_stratum: str = "unspecified"
    hard_stratum: bool = False
    bounds: tuple[float, float, float, float] | None = None
    center: tuple[float, float] | None = None
    overlap_group: str | None = None
    near_duplicate_group: str | None = None


@dataclass(frozen=True)
class ScoredQueryCandidate:
    """Candidate with rank-normalised acquisition components."""

    candidate: QueryCandidate
    uncertainty_rank: float
    disagreement_rank: float
    boundary_rank: float
    active_score: float
    disagreement_metric: DisagreementMetric

    @property
    def region_id(self) -> str:
        """Return the stable query-region identifier."""

        return self.candidate.region_id

    def to_dict(self) -> dict[str, object]:
        """Return all raw and normalised scoring fields for a manifest."""

        return {
            "region_id": self.region_id,
            "event_id": self.candidate.event_id,
            "crs": self.candidate.crs,
            "major_land_cover_stratum": self.candidate.major_land_cover_stratum,
            "dataset_role": _dataset_role_value(self.candidate.dataset_role),
            **self.candidate.components.to_dict(),
            "uncertainty_rank": self.uncertainty_rank,
            "disagreement_rank": self.disagreement_rank,
            "boundary_rank": self.boundary_rank,
            "active_score": self.active_score,
            "disagreement_metric": self.disagreement_metric,
        }


@dataclass(frozen=True)
class BatchQuotas:
    """Requested lane allocation for a review batch."""

    active: int
    hard_stratum: int
    random_control: int

    @property
    def total(self) -> int:
        """Return the total batch size represented by the quotas."""

        return self.active + self.hard_stratum + self.random_control

    def to_dict(self) -> dict[str, int]:
        """Return manifest-friendly lane counts."""

        return {
            "active": self.active,
            "hard_stratum": self.hard_stratum,
            "random_control": self.random_control,
        }


@dataclass(frozen=True)
class SelectedQuery:
    """One selected query region with its audit lane and selection order."""

    scored_candidate: ScoredQueryCandidate
    lane: SelectionLane
    selection_order: int
    sampling_stratum: str = ""
    sampling_stratum_population: int | None = None
    sampling_stratum_quota: int | None = None
    inclusion_probability: float | None = None

    @property
    def region_id(self) -> str:
        """Return the stable region identifier."""

        return self.scored_candidate.region_id

    def to_dict(self) -> dict[str, object]:
        """Return an acquisition-manifest row."""

        return {
            **self.scored_candidate.to_dict(),
            "selection_lane": self.lane,
            "selection_order": self.selection_order,
            "sampling_stratum": self.sampling_stratum,
            "sampling_stratum_population": self.sampling_stratum_population,
            "sampling_stratum_quota": self.sampling_stratum_quota,
            "inclusion_probability": self.inclusion_probability,
        }


@dataclass(frozen=True)
class BatchSelection:
    """Deterministic selected batch and both requested and achieved quotas."""

    selected: tuple[SelectedQuery, ...]
    requested_quotas: BatchQuotas
    random_seed: int

    @property
    def achieved_quotas(self) -> BatchQuotas:
        """Return actual lane counts after safe quota reallocation."""

        return BatchQuotas(
            active=sum(item.lane == "active" for item in self.selected),
            hard_stratum=sum(item.lane == "hard_stratum" for item in self.selected),
            random_control=sum(item.lane == "random_control" for item in self.selected),
        )


def normalized_binary_entropy(probability: float) -> float:
    """Return Bernoulli entropy normalised to ``[0, 1]``.

    Entropy is zero for probabilities 0 and 1 and one at 0.5. Inputs outside
    ``[0, 1]`` are rejected rather than clipped because clipping would hide a
    model-contract error.
    """

    p = _probability(probability, "probability")
    if p in (0.0, 1.0):
        return 0.0
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def absolute_probability_disagreement(
    first_probability: float,
    second_probability: float,
) -> float:
    """Return absolute probability disagreement in ``[0, 1]``."""

    first = _probability(first_probability, "first_probability")
    second = _probability(second_probability, "second_probability")
    return abs(first - second)


def jensen_shannon_disagreement(
    first_probability: float,
    second_probability: float,
) -> float:
    """Return normalised Jensen-Shannon divergence for two Bernoulli scores.

    Logarithms are base two, so the result is already normalised to ``[0, 1]``.
    This is query-by-committee disagreement, not BALD.
    """

    first = _probability(first_probability, "first_probability")
    second = _probability(second_probability, "second_probability")
    midpoint = 0.5 * (first + second)
    value = normalized_binary_entropy(midpoint) - 0.5 * (
        normalized_binary_entropy(first) + normalized_binary_entropy(second)
    )
    # Guard against tiny negative floating-point residue at equality.
    return min(1.0, max(0.0, value))


def top_tail_mean(values: Sequence[float], *, fraction: float = 0.20) -> float:
    """Return the mean of the largest ``ceil(n * fraction)`` finite values."""

    if not values:
        raise SamplingError("top-tail aggregation requires at least one value.")
    if not math.isfinite(fraction) or not 0.0 < fraction <= 1.0:
        raise SamplingError("top-tail fraction must be finite and in (0, 1].")
    numeric = [_finite_float(value, "top-tail value") for value in values]
    count = max(1, math.ceil(len(numeric) * fraction))
    tail = sorted(numeric, reverse=True)[:count]
    return sum(tail) / len(tail)


def compute_region_acquisition_components(
    logistic_probabilities: Sequence[float],
    boosted_probabilities: Sequence[float],
    *,
    boundary_impurity: float,
    top_tail_fraction: float = 0.20,
) -> AcquisitionComponents:
    """Aggregate pixel scores into transparent region-level components."""

    if not logistic_probabilities or not boosted_probabilities:
        raise SamplingError("both model probability sequences must be non-empty.")
    if len(logistic_probabilities) != len(boosted_probabilities):
        raise SamplingError("model probability sequences must have equal length.")
    boundary = _unit_interval(boundary_impurity, "boundary_impurity")
    uncertainty: list[float] = []
    absolute: list[float] = []
    jensen_shannon: list[float] = []
    for index, (logistic, boosted) in enumerate(
        zip(logistic_probabilities, boosted_probabilities)
    ):
        first = _probability(logistic, f"logistic_probabilities[{index}]")
        second = _probability(boosted, f"boosted_probabilities[{index}]")
        uncertainty.append(normalized_binary_entropy(0.5 * (first + second)))
        absolute.append(absolute_probability_disagreement(first, second))
        jensen_shannon.append(jensen_shannon_disagreement(first, second))
    return AcquisitionComponents(
        uncertainty=top_tail_mean(uncertainty, fraction=top_tail_fraction),
        absolute_disagreement=top_tail_mean(absolute, fraction=top_tail_fraction),
        jensen_shannon_disagreement=top_tail_mean(
            jensen_shannon,
            fraction=top_tail_fraction,
        ),
        boundary_impurity=boundary,
    )


def binary_boundary_impurity(
    predicted_grid: Sequence[Sequence[int | bool]],
) -> float:
    """Return the fraction of horizontal/vertical neighbour pairs that differ.

    The input is a rectangular query-core prediction grid.  Diagonal contacts
    are intentionally excluded so the score has a simple, stable denominator.
    This is a fragmentation/boundary diagnostic, not a label or accuracy metric.
    """

    if not predicted_grid or not predicted_grid[0]:
        raise SamplingError("predicted_grid must be a non-empty rectangle.")
    width = len(predicted_grid[0])
    normalized: list[list[int]] = []
    for row_index, row in enumerate(predicted_grid):
        if len(row) != width:
            raise SamplingError("predicted_grid must be rectangular.")
        normalized_row: list[int] = []
        for column_index, value in enumerate(row):
            if isinstance(value, bool):
                normalized_row.append(int(value))
            elif isinstance(value, int) and value in {0, 1}:
                normalized_row.append(value)
            else:
                raise SamplingError(
                    "predicted_grid values must be binary; found "
                    f"{value!r} at row {row_index}, column {column_index}."
                )
        normalized.append(normalized_row)
    differing = 0
    neighbour_pairs = 0
    for row_index, row in enumerate(normalized):
        for column_index, value in enumerate(row):
            if column_index + 1 < width:
                neighbour_pairs += 1
                differing += value != row[column_index + 1]
            if row_index + 1 < len(normalized):
                neighbour_pairs += 1
                differing += value != normalized[row_index + 1][column_index]
    return float(differing / neighbour_pairs) if neighbour_pairs else 0.0


def score_query_candidates(
    candidates: Sequence[QueryCandidate],
    *,
    disagreement_metric: DisagreementMetric = "absolute",
) -> tuple[ScoredQueryCandidate, ...]:
    """Rank-normalise components and calculate the documented 45/45/10 score."""

    validated = _validate_candidates(candidates)
    if disagreement_metric not in ("absolute", "jensen_shannon"):
        raise SamplingError(
            "disagreement_metric must be 'absolute' or 'jensen_shannon'."
        )
    uncertainty_ranks = _stratified_midranks(
        validated,
        lambda item: item.components.uncertainty,
    )
    disagreement_ranks = _stratified_midranks(
        validated,
        lambda item: (
            item.components.absolute_disagreement
            if disagreement_metric == "absolute"
            else item.components.jensen_shannon_disagreement
        ),
    )
    boundary_ranks = _stratified_midranks(
        validated,
        lambda item: item.components.boundary_impurity,
    )
    scored = []
    for index, candidate in enumerate(validated):
        uncertainty_rank = uncertainty_ranks[index]
        disagreement_rank = disagreement_ranks[index]
        boundary_rank = boundary_ranks[index]
        scored.append(
            ScoredQueryCandidate(
                candidate=candidate,
                uncertainty_rank=uncertainty_rank,
                disagreement_rank=disagreement_rank,
                boundary_rank=boundary_rank,
                active_score=(
                    0.45 * uncertainty_rank
                    + 0.45 * disagreement_rank
                    + 0.10 * boundary_rank
                ),
                disagreement_metric=disagreement_metric,
            )
        )
    return tuple(scored)


def compute_batch_quotas(batch_size: int) -> BatchQuotas:
    """Allocate 60/20/20 lanes with safe small-batch rounding.

    The random-control lane is mandatory for every non-empty batch. For the
    documented dry-run size of eight, the result is 5 active, 2 hard-stratum,
    and 1 random-control region; for 40 it is 24/8/8.
    """

    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise SamplingError("batch_size must be an integer.")
    if batch_size <= 0:
        raise SamplingError("batch_size must be positive.")
    active = math.floor(batch_size * ACTIVE_FRACTION + 0.5)
    hard = math.floor(batch_size * HARD_STRATUM_FRACTION + 0.5)
    random_control = batch_size - active - hard
    if random_control < 1:
        # Preserve a random audit stream even when rounding a tiny batch.
        if active > 0:
            active -= 1
        elif hard > 0:
            hard -= 1
        random_control += 1
    if random_control < 1 or min(active, hard) < 0:
        raise SamplingError("could not allocate safe review-batch quotas.")
    quotas = BatchQuotas(active, hard, random_control)
    if quotas.total != batch_size:
        raise SamplingError("review-batch quota allocation did not preserve size.")
    return quotas


def select_review_batch(
    candidates: Sequence[QueryCandidate],
    *,
    batch_size: int,
    random_seed: int = 0,
    disagreement_metric: DisagreementMetric = "absolute",
    minimum_center_distance: float = 0.0,
    near_duplicate_feature_distance: float | None = 1e-9,
    maximum_per_event: int | None = None,
    maximum_per_land_cover_stratum: int | None = None,
) -> BatchSelection:
    """Select a deterministic 60/20/20 review batch.

    Random-control regions are chosen first using a stable hash of the seed and
    region id, so their inclusion does not depend on active scores. Hard-stratum
    and active lanes are then chosen with a dependency-free greedy k-center
    procedure. Overlapping or near-duplicate candidates are never co-selected.

    If the requested size cannot be achieved without violating those rules,
    the function fails closed instead of silently returning a smaller batch.
    """

    quotas = compute_batch_quotas(batch_size)
    scored = list(
        score_query_candidates(candidates, disagreement_metric=disagreement_metric)
    )
    if batch_size > len(scored):
        raise SamplingError(
            f"batch_size {batch_size} exceeds {len(scored)} query candidates."
        )
    minimum_distance = _non_negative(
        minimum_center_distance,
        "minimum_center_distance",
    )
    if near_duplicate_feature_distance is not None:
        feature_threshold = _non_negative(
            near_duplicate_feature_distance,
            "near_duplicate_feature_distance",
        )
    else:
        feature_threshold = None
    event_limit = _optional_positive_integer(maximum_per_event, "maximum_per_event")
    stratum_limit = _optional_positive_integer(
        maximum_per_land_cover_stratum,
        "maximum_per_land_cover_stratum",
    )

    standardised = _standardised_diversity_vectors(scored)
    chosen: list[tuple[ScoredQueryCandidate, SelectionLane]] = []

    # The random-control lane is intentionally selected without active scores.
    _take_stratified_random(
        scored,
        quotas.random_control,
        chosen,
        random_seed=random_seed,
        minimum_center_distance=minimum_distance,
        near_duplicate_feature_distance=feature_threshold,
        maximum_per_event=event_limit,
        maximum_per_land_cover_stratum=stratum_limit,
    )

    hard_pool = [item for item in scored if item.candidate.hard_stratum]
    _take_diverse(
        hard_pool,
        quotas.hard_stratum,
        "hard_stratum",
        chosen,
        standardised,
        minimum_center_distance=minimum_distance,
        near_duplicate_feature_distance=feature_threshold,
        maximum_per_event=event_limit,
        maximum_per_land_cover_stratum=stratum_limit,
    )

    _take_diverse(
        scored,
        quotas.active,
        "active",
        chosen,
        standardised,
        minimum_center_distance=minimum_distance,
        near_duplicate_feature_distance=feature_threshold,
        maximum_per_event=event_limit,
        maximum_per_land_cover_stratum=stratum_limit,
    )

    # Safely reallocate an unavailable hard-stratum quota to the active lane.
    deficit = batch_size - len(chosen)
    if deficit:
        _take_diverse(
            scored,
            deficit,
            "active",
            chosen,
            standardised,
            minimum_center_distance=minimum_distance,
            near_duplicate_feature_distance=feature_threshold,
            maximum_per_event=event_limit,
            maximum_per_land_cover_stratum=stratum_limit,
        )

    if len(chosen) != batch_size:
        raise SamplingError(
            "could not fill the requested batch without selecting overlapping "
            "or near-duplicate query regions."
        )
    random_population: dict[str, int] = {}
    for item in scored:
        key = _audit_stratum(item.candidate)
        random_population[key] = random_population.get(key, 0) + 1
    random_quota: dict[str, int] = {}
    for item, lane in chosen:
        if lane == "random_control":
            key = _audit_stratum(item.candidate)
            random_quota[key] = random_quota.get(key, 0) + 1
    selected_rows: list[SelectedQuery] = []
    for index, (item, lane) in enumerate(chosen, start=1):
        if lane == "random_control":
            stratum = _audit_stratum(item.candidate)
            population = random_population[stratum]
            quota = random_quota[stratum]
            probability = quota / population
        else:
            stratum = ""
            population = None
            quota = None
            probability = None
        selected_rows.append(
            SelectedQuery(
                item,
                lane,
                index,
                sampling_stratum=stratum,
                sampling_stratum_population=population,
                sampling_stratum_quota=quota,
                inclusion_probability=probability,
            )
        )
    selected = tuple(selected_rows)
    if not any(item.lane == "random_control" for item in selected):
        raise SamplingError("random-control lane is mandatory for every batch.")
    return BatchSelection(
        selected=selected,
        requested_quotas=quotas,
        random_seed=random_seed,
    )


def _validate_candidates(
    candidates: Sequence[QueryCandidate],
) -> tuple[QueryCandidate, ...]:
    if not candidates:
        raise SamplingError("at least one query candidate is required.")
    validated: list[QueryCandidate] = []
    seen_ids: set[str] = set()
    feature_size: int | None = None
    for candidate in candidates:
        if not isinstance(candidate, QueryCandidate):
            raise SamplingError("all candidates must be QueryCandidate instances.")
        region_id = candidate.region_id.strip()
        if not region_id:
            raise SamplingError("candidate region_id must not be blank.")
        if region_id in seen_ids:
            raise SamplingError(f"duplicate query region_id: {region_id}")
        seen_ids.add(region_id)
        try:
            dataset_role = DatasetRole(candidate.dataset_role)
        except (TypeError, ValueError) as exc:
            raise SamplingError(
                f"candidate {region_id} has unknown dataset role "
                f"{candidate.dataset_role!r}."
            ) from exc
        if not dataset_role.allows_active_selection:
            raise SamplingError(
                f"candidate {region_id} has non-query dataset role "
                f"{dataset_role.value!r}; calibration, development, and test "
                "regions must never enter acquisition."
            )
        if not isinstance(candidate.crs, str) or not candidate.crs.strip():
            raise SamplingError(f"candidate {region_id} must declare crs.")
        if not isinstance(candidate.major_land_cover_stratum, str) or not (
            candidate.major_land_cover_stratum.strip()
        ):
            raise SamplingError(
                f"candidate {region_id} must declare major_land_cover_stratum."
            )
        _unit_interval(candidate.components.uncertainty, "uncertainty")
        _unit_interval(
            candidate.components.absolute_disagreement,
            "absolute_disagreement",
        )
        _unit_interval(
            candidate.components.jensen_shannon_disagreement,
            "jensen_shannon_disagreement",
        )
        _unit_interval(candidate.components.boundary_impurity, "boundary_impurity")
        if not candidate.diversity_features:
            raise SamplingError(
                f"candidate {region_id} must provide diversity_features."
            )
        vector = tuple(
            _finite_float(value, f"diversity feature for {region_id}")
            for value in candidate.diversity_features
        )
        if feature_size is None:
            feature_size = len(vector)
        elif len(vector) != feature_size:
            raise SamplingError("all diversity feature vectors must have equal length.")
        if candidate.bounds is not None:
            if len(candidate.bounds) != 4:
                raise SamplingError(f"candidate {region_id} bounds must have four values.")
            xmin, ymin, xmax, ymax = (
                _finite_float(value, f"bounds for {region_id}")
                for value in candidate.bounds
            )
            if not xmin < xmax or not ymin < ymax:
                raise SamplingError(
                    f"candidate {region_id} bounds must satisfy xmin<xmax and ymin<ymax."
                )
        if candidate.center is not None:
            if len(candidate.center) != 2:
                raise SamplingError(f"candidate {region_id} center must have two values.")
            for value in candidate.center:
                _finite_float(value, f"center for {region_id}")
        validated.append(candidate)
    return tuple(validated)


def _midranks(values: Sequence[float]) -> list[float]:
    """Return deterministic midranks normalised to [0, 1]."""

    if len(values) == 1:
        return [0.5]
    indexed = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        average_position = 0.5 * (cursor + end - 1)
        normalised = average_position / (len(values) - 1)
        for position in range(cursor, end):
            ranks[indexed[position][0]] = normalised
        cursor = end
    return ranks


def _stratified_midranks(
    candidates: Sequence[QueryCandidate],
    value_getter: Callable[[QueryCandidate], float],
) -> list[float]:
    """Return midranks within event and major-land-cover strata."""

    groups: dict[tuple[str, str], list[int]] = {}
    for index, candidate in enumerate(candidates):
        key = (
            candidate.event_id.strip() or "unspecified_event",
            candidate.major_land_cover_stratum.strip(),
        )
        groups.setdefault(key, []).append(index)
    output = [0.0] * len(candidates)
    for indices in groups.values():
        values = [value_getter(candidates[index]) for index in indices]
        ranks = _midranks(values)
        for index, rank in zip(indices, ranks):
            output[index] = rank
    return output


def _take_in_order(
    pool: Sequence[ScoredQueryCandidate],
    count: int,
    lane: SelectionLane,
    chosen: list[tuple[ScoredQueryCandidate, SelectionLane]],
    *,
    minimum_center_distance: float,
    near_duplicate_feature_distance: float | None,
    maximum_per_event: int | None,
    maximum_per_land_cover_stratum: int | None,
) -> None:
    if count <= 0:
        return
    for item in pool:
        if len([selected for selected in chosen if selected[1] == lane]) >= count:
            break
        if _already_selected(item, chosen):
            continue
        if _has_conflict(
            item,
            [selected[0] for selected in chosen],
            minimum_center_distance=minimum_center_distance,
            near_duplicate_feature_distance=near_duplicate_feature_distance,
            maximum_per_event=maximum_per_event,
            maximum_per_land_cover_stratum=maximum_per_land_cover_stratum,
        ):
            continue
        chosen.append((item, lane))


def _take_stratified_random(
    pool: Sequence[ScoredQueryCandidate],
    count: int,
    chosen: list[tuple[ScoredQueryCandidate, SelectionLane]],
    *,
    random_seed: int,
    minimum_center_distance: float,
    near_duplicate_feature_distance: float | None,
    maximum_per_event: int | None,
    maximum_per_land_cover_stratum: int | None,
) -> None:
    if count <= 0:
        return
    strata: dict[str, list[ScoredQueryCandidate]] = {}
    for item in pool:
        strata.setdefault(_audit_stratum(item.candidate), []).append(item)
    for items in strata.values():
        items.sort(
            key=lambda item: (
                _stable_random_key(random_seed, item.region_id),
                item.region_id,
            )
        )
    order = sorted(
        strata,
        key=lambda value: (_stable_random_key(random_seed, value), value),
    )
    selected_count = 0
    while selected_count < count:
        progress = False
        for stratum in order:
            candidates = strata[stratum]
            while candidates:
                item = candidates.pop(0)
                if _already_selected(item, chosen) or _has_conflict(
                    item,
                    [selected[0] for selected in chosen],
                    minimum_center_distance=minimum_center_distance,
                    near_duplicate_feature_distance=near_duplicate_feature_distance,
                    maximum_per_event=maximum_per_event,
                    maximum_per_land_cover_stratum=maximum_per_land_cover_stratum,
                ):
                    continue
                chosen.append((item, "random_control"))
                selected_count += 1
                progress = True
                break
            if selected_count == count:
                return
        if not progress:
            return


def _take_diverse(
    pool: Sequence[ScoredQueryCandidate],
    count: int,
    lane: SelectionLane,
    chosen: list[tuple[ScoredQueryCandidate, SelectionLane]],
    standardised: dict[str, tuple[float, ...]],
    *,
    minimum_center_distance: float,
    near_duplicate_feature_distance: float | None,
    maximum_per_event: int | None,
    maximum_per_land_cover_stratum: int | None,
) -> None:
    if count <= 0:
        return
    remaining = [item for item in pool if not _already_selected(item, chosen)]
    remaining.sort(key=lambda item: (-item.active_score, item.region_id))
    # Only diversify within a high-value shortlist, matching the 5B policy.
    remaining = remaining[: min(len(remaining), max(count * 5, count))]
    selected_in_lane = 0
    while remaining and selected_in_lane < count:
        compatible = [
            item
            for item in remaining
            if not _has_conflict(
                item,
                [selected[0] for selected in chosen],
                minimum_center_distance=minimum_center_distance,
                near_duplicate_feature_distance=near_duplicate_feature_distance,
                maximum_per_event=maximum_per_event,
                maximum_per_land_cover_stratum=maximum_per_land_cover_stratum,
            )
        ]
        if not compatible:
            break
        references = [selected[0] for selected in chosen]
        if not references:
            next_item = min(
                compatible,
                key=lambda item: (-item.active_score, item.region_id),
            )
        else:
            next_item = min(
                compatible,
                key=lambda item: (
                    -_minimum_standardised_distance(item, references, standardised),
                    -item.active_score,
                    item.region_id,
                ),
            )
        chosen.append((next_item, lane))
        selected_in_lane += 1
        remaining = [item for item in remaining if item.region_id != next_item.region_id]


def _already_selected(
    item: ScoredQueryCandidate,
    chosen: Sequence[tuple[ScoredQueryCandidate, SelectionLane]],
) -> bool:
    return any(existing.region_id == item.region_id for existing, _lane in chosen)


def _has_conflict(
    item: ScoredQueryCandidate,
    selected: Sequence[ScoredQueryCandidate],
    *,
    minimum_center_distance: float,
    near_duplicate_feature_distance: float | None,
    maximum_per_event: int | None,
    maximum_per_land_cover_stratum: int | None,
) -> bool:
    if maximum_per_event is not None:
        event_count = sum(
            other.candidate.event_id == item.candidate.event_id for other in selected
        )
        if event_count >= maximum_per_event:
            return True
    if maximum_per_land_cover_stratum is not None:
        stratum_count = sum(
            (
                other.candidate.event_id == item.candidate.event_id
                and other.candidate.major_land_cover_stratum
                == item.candidate.major_land_cover_stratum
            )
            for other in selected
        )
        if stratum_count >= maximum_per_land_cover_stratum:
            return True
    return any(
        _candidates_conflict(
            item.candidate,
            other.candidate,
            minimum_center_distance=minimum_center_distance,
            near_duplicate_feature_distance=near_duplicate_feature_distance,
        )
        for other in selected
    )


def _candidates_conflict(
    first: QueryCandidate,
    second: QueryCandidate,
    *,
    minimum_center_distance: float,
    near_duplicate_feature_distance: float | None,
) -> bool:
    if first.region_id == second.region_id:
        return True
    same_spatial_frame = (
        first.event_id == second.event_id
        and first.crs.strip().upper() == second.crs.strip().upper()
    )
    if same_spatial_frame and (
        first.overlap_group
        and second.overlap_group
        and first.overlap_group == second.overlap_group
    ):
        return True
    if (
        first.near_duplicate_group
        and second.near_duplicate_group
        and first.near_duplicate_group == second.near_duplicate_group
    ):
        return True
    if same_spatial_frame and first.bounds is not None and second.bounds is not None:
        if _bounds_overlap(first.bounds, second.bounds):
            return True
    if same_spatial_frame and minimum_center_distance > 0.0:
        first_center = _candidate_center(first)
        second_center = _candidate_center(second)
        if first_center is not None and second_center is not None:
            if _euclidean(first_center, second_center) < minimum_center_distance:
                return True
    if near_duplicate_feature_distance is not None:
        if (
            _euclidean(first.diversity_features, second.diversity_features)
            <= near_duplicate_feature_distance
        ):
            return True
    return False


def _bounds_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    first_xmin, first_ymin, first_xmax, first_ymax = first
    second_xmin, second_ymin, second_xmax, second_ymax = second
    return (
        min(first_xmax, second_xmax) > max(first_xmin, second_xmin)
        and min(first_ymax, second_ymax) > max(first_ymin, second_ymin)
    )


def _candidate_center(candidate: QueryCandidate) -> tuple[float, float] | None:
    if candidate.center is not None:
        return candidate.center
    if candidate.bounds is None:
        return None
    xmin, ymin, xmax, ymax = candidate.bounds
    return (0.5 * (xmin + xmax), 0.5 * (ymin + ymax))


def _standardised_diversity_vectors(
    candidates: Sequence[ScoredQueryCandidate],
) -> dict[str, tuple[float, ...]]:
    width = len(candidates[0].candidate.diversity_features)
    columns = [
        [candidate.candidate.diversity_features[index] for candidate in candidates]
        for index in range(width)
    ]
    means = [sum(column) / len(column) for column in columns]
    scales = []
    for index, column in enumerate(columns):
        variance = sum((value - means[index]) ** 2 for value in column) / len(column)
        scale = math.sqrt(variance)
        scales.append(scale if scale > 0.0 else 1.0)
    return {
        candidate.region_id: tuple(
            (value - means[index]) / scales[index]
            for index, value in enumerate(candidate.candidate.diversity_features)
        )
        for candidate in candidates
    }


def _minimum_standardised_distance(
    candidate: ScoredQueryCandidate,
    references: Sequence[ScoredQueryCandidate],
    standardised: dict[str, tuple[float, ...]],
) -> float:
    vector = standardised[candidate.region_id]
    return min(
        _euclidean(vector, standardised[reference.region_id])
        for reference in references
    )


def _euclidean(first: Sequence[float], second: Sequence[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def _stable_random_key(random_seed: int, region_id: str) -> str:
    payload = f"{random_seed}:{region_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _audit_stratum(candidate: QueryCandidate) -> str:
    return (
        f"{candidate.event_id.strip() or 'unspecified_event'}|"
        f"{candidate.major_land_cover_stratum.strip()}"
    )


def _dataset_role_value(value: str | DatasetRole) -> str:
    try:
        return DatasetRole(value).value
    except (TypeError, ValueError) as exc:
        raise SamplingError(f"unknown dataset role: {value!r}") from exc


def _probability(value: float, label: str) -> float:
    return _unit_interval(value, label)


def _unit_interval(value: float, label: str) -> float:
    numeric = _finite_float(value, label)
    if not 0.0 <= numeric <= 1.0:
        raise SamplingError(f"{label} must be in [0, 1].")
    return numeric


def _non_negative(value: float, label: str) -> float:
    numeric = _finite_float(value, label)
    if numeric < 0.0:
        raise SamplingError(f"{label} must be non-negative.")
    return numeric


def _finite_float(value: float, label: str) -> float:
    if isinstance(value, bool):
        raise SamplingError(f"{label} must be numeric, not boolean.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise SamplingError(f"{label} must be numeric.") from exc
    if not math.isfinite(numeric):
        raise SamplingError(f"{label} must be finite.")
    return numeric


def _optional_positive_integer(value: int | None, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SamplingError(f"{label} must be a positive integer or None.")
    return value
