from __future__ import annotations

import pandas as pd
import pytest

from floodguard.decision_safety import DecisionInputSafetyError
from floodguard.scoring import score_subdistricts


def _fpps_input() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "subdistrict_id": "S1",
                "subdistrict_name": "Example",
                "confidence_class": "low",
                "flood_likelihood_0_100": 20,
                "exposure_0_100": 10,
                "access_gap_0_100": 5,
                "road_criticality_0_100": 5,
                "vulnerability_context_0_100": 5,
            }
        ]
    )


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("query_model_only", True),
        ("model_purpose", "query_ranking"),
        ("source_type", "positive_unlabeled_weak_seed"),
        ("logistic_query_score", 0.9),
        ("eligible_for_fpps", False),
    ],
)
def test_fpps_ingress_rejects_label_factory_query_evidence(
    column: str, value: object
) -> None:
    frame = _fpps_input()
    frame[column] = value

    with pytest.raises(DecisionInputSafetyError):
        score_subdistricts(frame)


def test_existing_provenance_free_fpps_fixture_remains_supported() -> None:
    result = score_subdistricts(_fpps_input())
    assert "fpps_0_100" in result.columns
