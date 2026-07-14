"""Hard ingress guards against using label-factory query evidence as flood input."""

from __future__ import annotations

import pandas as pd


QUERY_SCORE_COLUMNS = frozenset(
    {
        "logistic_query_score",
        "boosted_query_score",
        "committee_mean_query_score",
        "normalized_entropy",
        "absolute_disagreement",
        "jensen_shannon_disagreement",
        "active_score",
        "selection_lane",
    }
)


class DecisionInputSafetyError(ValueError):
    """Raised when research/query artifacts reach a decision-layer ingress."""


def reject_label_factory_query_input(frame: pd.DataFrame, *, ingress: str) -> None:
    """Reject query-only, weak-seed, or acquisition evidence at decision ingress."""

    if not isinstance(frame, pd.DataFrame):
        raise DecisionInputSafetyError(f"{ingress} input must be a pandas DataFrame.")
    leaking_columns = sorted(QUERY_SCORE_COLUMNS.intersection(frame.columns))
    if leaking_columns:
        raise DecisionInputSafetyError(
            f"{ingress} rejects label-factory query/acquisition columns: "
            + ", ".join(leaking_columns)
        )
    if "query_model_only" in frame.columns:
        values = frame["query_model_only"].map(_strict_boolean)
        if values.isna().any():
            raise DecisionInputSafetyError(
                f"{ingress} received invalid query_model_only provenance."
            )
        if values.any():
            raise DecisionInputSafetyError(
                f"{ingress} rejects query_model_only=true evidence."
            )
    if "model_purpose" in frame.columns and frame["model_purpose"].astype(str).str.strip().eq(
        "query_ranking"
    ).any():
        raise DecisionInputSafetyError(
            f"{ingress} rejects model_purpose=query_ranking."
        )
    if "source_type" in frame.columns and frame["source_type"].astype(str).str.contains(
        "weak_seed|positive_unlabeled", case=False, regex=True
    ).any():
        raise DecisionInputSafetyError(
            f"{ingress} rejects positive-unlabeled weak-seed evidence."
        )
    for field in ("eligible_for_decision_layer", "eligible_for_fpps"):
        if field in frame.columns:
            values = frame[field].map(_strict_boolean)
            if values.isna().any() or not values.all():
                raise DecisionInputSafetyError(
                    f"{ingress} requires explicit {field}=true for provenance-bearing inputs."
                )


def _strict_boolean(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    return None
