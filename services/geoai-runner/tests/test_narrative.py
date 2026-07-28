"""Property tests for the deterministic narrative generator (T3.2).

The reason this component exists is auditability, so the tests are about
traceability and non-suppressibility rather than prose quality: every number
must appear, every caveat must fire when it should, and the same inputs must
always produce the same bytes.
"""

from __future__ import annotations

import itertools
import json

import pytest

from geoai_runner.realpipeline.narrative import (
    ACTION_LABELS_EN,
    ACTION_LABELS_TH,
    MAX_TRUSTED_PEAK_OFFSET_DAYS,
    MOONDREAM_EVALUATION_RECORD,
    NARRATIVE_BANDS_V1,
    NARRATIVE_BANDS_VERSION,
    NarrativeError,
    NarrativeInputs,
    generate_narratives,
    narrative_inputs_from_row,
    render_tambon_narrative,
)


def _inputs(**overrides) -> NarrativeInputs:
    base = {
        "tambon_name_en": "Ko Chang",
        "tambon_name_th": "เกาะช้าง",
        "flooded_pct": 1.291,
        "flood_likelihood": 48.1,
        "exposure": 14.1,
        "fpps": 40.8,
        "action_class": "D",
        "confidence_class": "high",
        "acquisition_date": "2024-09-15",
        "peak_offset_days": 4,
        "population": 6708.0,
        "osm_completeness_flag": "severely_incomplete",
        "context_source": "decision_layer_real_context",
    }
    base.update(overrides)
    return NarrativeInputs(**base)


# --------------------------------------------------------------------------- #
# Traceability
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("language", ["en", "th"])
def test_every_key_number_appears_in_the_text(language):
    text = render_tambon_narrative(_inputs(), language=language)
    assert "1.29" in text
    assert "48.1" in text
    assert "40.8" in text
    assert "2024-09-15" in text
    assert "D" in text


def test_action_label_is_rendered_in_each_language():
    assert ACTION_LABELS_EN["D"] in render_tambon_narrative(_inputs(), language="en")
    assert ACTION_LABELS_TH["D"] in render_tambon_narrative(_inputs(), language="th")


def test_population_is_stated_when_known():
    assert "6,708" in render_tambon_narrative(_inputs(), language="en")


def test_missing_population_is_stated_not_implied_as_zero():
    text = render_tambon_narrative(_inputs(population=None), language="en")
    assert "population context was unavailable" in text
    assert "0 residents" not in text


# --------------------------------------------------------------------------- #
# Caveats cannot be suppressed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("language", ["en", "th"])
def test_stale_acquisition_always_emits_a_caveat(language):
    text = render_tambon_narrative(
        _inputs(peak_offset_days=MAX_TRUSTED_PEAK_OFFSET_DAYS + 1), language=language
    )
    assert ("caution" in text.lower()) or ("ระมัดระวัง" in text)


@pytest.mark.parametrize("confidence", ["medium", "low"])
def test_non_high_confidence_always_emits_a_caveat(confidence):
    text = render_tambon_narrative(
        _inputs(confidence_class=confidence, peak_offset_days=0), language="en"
    )
    assert "caution" in text.lower()
    assert confidence in text


def test_placeholder_context_is_disclosed():
    text = render_tambon_narrative(
        _inputs(context_source="placeholder", peak_offset_days=0), language="en"
    )
    assert "placeholders, not measured" in text


def test_incomplete_osm_is_disclosed():
    text = render_tambon_narrative(
        _inputs(confidence_class="high", peak_offset_days=0), language="en"
    )
    assert "OpenStreetMap building coverage" in text


@pytest.mark.parametrize("language", ["en", "th"])
def test_non_warning_disclaimer_is_always_present(language):
    """Every rendered narrative must disclaim official-warning status."""

    for confidence, offset, context in itertools.product(
        ("high", "medium", "low"), (0, 4), ("placeholder", "decision_layer_real_context")
    ):
        text = render_tambon_narrative(
            _inputs(
                confidence_class=confidence,
                peak_offset_days=offset,
                context_source=context,
                osm_completeness_flag="usable",
            ),
            language=language,
        )
        assert ("not an official warning" in text) or ("ไม่ใช่การเตือนภัยอย่างเป็นทางการ" in text)


def test_clean_inputs_still_carry_the_planning_disclaimer():
    text = render_tambon_narrative(
        _inputs(
            confidence_class="high", peak_offset_days=0,
            context_source="decision_layer_real_context", osm_completeness_flag="usable",
        ),
        language="en",
    )
    assert "caution" not in text.lower()
    assert "not an official warning" in text


# --------------------------------------------------------------------------- #
# Band table licensing
# --------------------------------------------------------------------------- #
def test_zero_inundation_uses_the_zero_phrase():
    text = render_tambon_narrative(_inputs(flooded_pct=0.0), language="en")
    assert "no observed inundation" in text


@pytest.mark.parametrize(
    "pct,phrase",
    [(0.05, "a trace of"), (0.5, "localised"), (2.0, "substantial"), (9.0, "widespread")],
)
def test_flood_bands_select_the_licensed_phrase(pct, phrase):
    assert phrase in render_tambon_narrative(_inputs(flooded_pct=pct), language="en")


def test_band_tables_are_monotonic_and_complete():
    for metric, bands in NARRATIVE_BANDS_V1.items():
        lowers = [b[0] for b in bands]
        assert lowers == sorted(lowers), metric
        assert lowers[0] == 0.0, metric
        for entry in bands:
            assert len(entry) == 3 and entry[1] and entry[2], metric


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def test_unknown_action_class_is_rejected():
    with pytest.raises(NarrativeError, match="action_class"):
        _inputs(action_class="Z")


def test_unknown_confidence_is_rejected():
    with pytest.raises(NarrativeError, match="confidence_class"):
        _inputs(confidence_class="certain")


@pytest.mark.parametrize("value", [-1.0, 101.0, float("nan")])
def test_out_of_range_scores_are_rejected(value):
    with pytest.raises(NarrativeError):
        _inputs(fpps=value)


def test_blank_name_is_rejected():
    with pytest.raises(NarrativeError, match="tambon_name_en"):
        _inputs(tambon_name_en="  ")


def test_unsupported_language_is_rejected():
    with pytest.raises(NarrativeError, match="language"):
        render_tambon_narrative(_inputs(), language="fr")


# --------------------------------------------------------------------------- #
# Artifact reproducibility
# --------------------------------------------------------------------------- #
def test_artifact_is_byte_identical_across_runs(tmp_path):
    rows = [_inputs(), _inputs(tambon_name_en="Mae Sai", tambon_name_th="แม่สาย", fpps=32.5)]
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    generate_narratives(rows, first)
    generate_narratives(rows, second)
    assert first.read_bytes() == second.read_bytes()


def test_artifact_records_provenance_and_supersession(tmp_path):
    out = tmp_path / "narratives.json"
    result = generate_narratives([_inputs()], out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["bands_version"] == NARRATIVE_BANDS_VERSION
    assert payload["method"] == "deterministic_template_narrative_v1"
    assert payload["review_status"] == "machine_generated_deterministic"
    assert payload["superseded_method"]["outcome"] == "evaluated_rejected"
    assert set(payload["narratives"]["Ko Chang"]) == {"en", "th"}
    assert result.metrics["narrative_count"] == 1


def test_moondream_rejection_is_recorded_honestly():
    assert MOONDREAM_EVALUATION_RECORD["executed"] is True
    assert MOONDREAM_EVALUATION_RECORD["caption_count_usable"] == 0
    assert MOONDREAM_EVALUATION_RECORD["outcome"] == "evaluated_rejected"


def test_row_adapter_maps_decision_table_fields():
    row = {
        "subdistrict_name": "Ko Chang",
        "ai_flood_share": 0.01291,
        "flood_likelihood_0_100": 48.1,
        "exposure_0_100": 14.1,
        "fpps_0_100": 40.8,
        "action_class": "D",
        "confidence_class": "high",
        "population": 6708.0,
        "osm_completeness_flag": "severely_incomplete",
        "context_source": "decision_layer_real_context",
    }
    inputs = narrative_inputs_from_row(
        row, acquisition_date="2024-09-15", peak_offset_days=4, tambon_name_th="เกาะช้าง"
    )
    assert inputs.flooded_pct == pytest.approx(1.291, abs=1e-3)
    assert inputs.action_class == "D"
