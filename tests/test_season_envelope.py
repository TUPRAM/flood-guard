"""Pure helpers of the season-envelope comparison (``floodguard.season_envelope``), on synthetic masks.

A season envelope is a scenario layer (SCN-ENV): setting the modelled water beside it is a plausibility comparison,
not a validation. These tests pin the three ratios (overlap over union, the share of the modelled water inside the
envelope, the share of the envelope the model reaches), the per-zone figures, the residents count, the change
notice and the licence notice, and the rules a published document must keep.
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

from floodguard.replay_manifest import ENVELOPE_CHECK_ROLE
from floodguard.season_envelope import (
    AGREEMENT_KEYS,
    COMPARISON_ROLE,
    COMPARISON_USE,
    ENVELOPE_LANE,
    OTHER_INPUT_KEYS,
    RESIDENT_COUNT_RULES,
    SeasonEnvelopeError,
    credit_holders,
    document_problems,
    fill_change_notice,
    largest_differences,
    licence_notice,
    mask_agreement,
    other_input_problems,
    residents_inside,
    share_inside,
    zone_agreement,
    zone_areas,
)

CREDIT = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009"
TEMPLATE = ("Changed by FloodGuard: clipped to Mae Sai district ({clip_geometry}); geometry repaired ({repair_method}; {repair_count} parts repaired); "
            "reprojected from {source_crs} to {target_crs}; rasterised to {cell_size_m} m cells. Source: UNOSAT and GISTDA, FL20240912THA, "
            "UNOSAT product 4009, CC BY-SA 4.0.")


def grid(rows: list[str]) -> np.ndarray:
    """A boolean mask from rows of ``#`` (inside) and ``.`` (outside)."""
    return np.array([[cell == "#" for cell in row] for row in rows])


MODEL = grid(["####....",
              "####....",
              "####....",
              "........"])
ENVELOPE = grid(["..####..",
                 "..####..",
                 "........",
                 "..####.."])


# --- The three ratios ----------------------------------------------------------------------------------------


def test_mask_agreement_counts_overlap_union_and_the_three_ratios() -> None:
    # Model 12 cells, envelope 12 cells, 4 in both, 20 in either; one cell is 0.25 km2.
    result = mask_agreement(MODEL, ENVELOPE, 0.25)
    assert result == {
        "model_km2": 3.0, "envelope_km2": 3.0, "overlap_km2": 1.0, "union_km2": 5.0, "model_only_km2": 2.0, "envelope_only_km2": 2.0,
        "agreement_iou": 0.2, "containment_model_in_envelope": 0.333, "containment_envelope_in_model": 0.333,
    }
    assert set(AGREEMENT_KEYS) <= set(result) and not any("precision" in key or "recall" in key or "accuracy" in key for key in result)
    # The two containment shares are not the same thing: a small model wholly inside a large envelope.
    small = grid(["........", "..##....", "........", "........"])
    inside = mask_agreement(small, ENVELOPE, 1.0)
    assert (inside["containment_model_in_envelope"], inside["containment_envelope_in_model"], inside["agreement_iou"]) == (1.0, round(2 / 12, 3), round(2 / 12, 3))
    # Identical masks agree fully; disjoint masks not at all.
    assert mask_agreement(MODEL, MODEL, 1.0)["agreement_iou"] == 1.0
    apart = mask_agreement(grid(["##..", "...."]), grid(["....", "..##"]), 1.0)
    assert (apart["agreement_iou"], apart["containment_model_in_envelope"], apart["containment_envelope_in_model"], apart["overlap_km2"]) == (0.0, 0.0, 0.0, 0.0)
    # Swapping the masks swaps the two shares and keeps the ratio of overlap to union.
    swapped = mask_agreement(ENVELOPE, small, 1.0)
    assert swapped["agreement_iou"] == inside["agreement_iou"]
    assert (swapped["containment_model_in_envelope"], swapped["containment_envelope_in_model"]) == (inside["containment_envelope_in_model"], 1.0)


def test_mask_agreement_inside_an_area_and_without_a_denominator() -> None:
    left = np.zeros(MODEL.shape, dtype=bool)
    left[:, :4] = True
    result = mask_agreement(MODEL, ENVELOPE, 1.0, left)
    # Left half: model 12 cells, envelope 6 (columns 2 and 3 of three rows), 4 in both.
    assert (result["model_km2"], result["envelope_km2"], result["overlap_km2"], result["union_km2"]) == (12.0, 6.0, 4.0, 14.0)
    assert (result["agreement_iou"], result["containment_model_in_envelope"], result["containment_envelope_in_model"]) == (round(4 / 14, 3), 0.333, 0.667)
    # No modelled water in the area: there is no share of it inside the envelope, which is not zero.
    right = ~left
    nothing = mask_agreement(MODEL, ENVELOPE, 1.0, right)
    assert nothing["model_km2"] == 0.0 and nothing["containment_model_in_envelope"] is None
    assert nothing["containment_envelope_in_model"] == 0.0 and nothing["agreement_iou"] == 0.0
    empty = mask_agreement(np.zeros((2, 2), bool), np.zeros((2, 2), bool), 1.0)
    assert [empty[key] for key in AGREEMENT_KEYS] == [None, None, None]
    # Integer and 0/1 arrays count like booleans.
    assert mask_agreement(MODEL.astype(np.uint8), ENVELOPE.astype(int), 0.25) == mask_agreement(MODEL, ENVELOPE, 0.25)


def test_mask_agreement_refuses_masks_on_different_grids_and_a_bad_cell_area() -> None:
    with pytest.raises(SeasonEnvelopeError, match="share one grid"):
        mask_agreement(MODEL, ENVELOPE[:, :4], 1.0)
    with pytest.raises(SeasonEnvelopeError, match="share one grid"):
        mask_agreement(MODEL, ENVELOPE, 1.0, np.ones((2, 2), bool))
    for bad in (0, -1.0, float("nan")):
        with pytest.raises(SeasonEnvelopeError, match="cell_km2 must be positive"):
            mask_agreement(MODEL, ENVELOPE, bad)


# --- Zones, shares and residents --------------------------------------------------------------------------------


def test_zone_figures_follow_the_zone_raster() -> None:
    zones = np.zeros(MODEL.shape, dtype=np.uint8)
    zones[:, :4] = 1
    zones[:, 4:6] = 2  # The last two columns belong to no zone.
    ids = ["west", "east"]
    assert zone_areas(ENVELOPE, zones, ids, 0.5) == {"west": 3.0, "east": 3.0}
    assert zone_areas(MODEL, zones, ids, 0.5) == {"west": 6.0, "east": 0.0}
    rows = zone_agreement(MODEL, ENVELOPE, zones, ids, 1.0)
    assert [row["zone_id"] for row in rows] == ids
    assert rows[0] == {"zone_id": "west", **mask_agreement(MODEL, ENVELOPE, 1.0, zones == 1)}
    assert (rows[1]["model_km2"], rows[1]["envelope_km2"], rows[1]["agreement_iou"], rows[1]["containment_model_in_envelope"]) == (0.0, 6.0, 0.0, None)
    # The zones add up to the district, so do their overlaps.
    whole = mask_agreement(MODEL, ENVELOPE, 1.0, zones > 0)
    assert sum(row["overlap_km2"] for row in rows) == whole["overlap_km2"]
    with pytest.raises(SeasonEnvelopeError, match="share one grid"):
        zone_areas(ENVELOPE, zones[:2], ids, 1.0)


def test_largest_differences_name_the_zones_in_order_and_skip_small_ones() -> None:
    rows = [{"zone_id": "a", "envelope_only_km2": 0.4, "model_only_km2": 7.2}, {"zone_id": "b", "envelope_only_km2": 11.5, "model_only_km2": 5.6},
            {"zone_id": "c", "envelope_only_km2": 5.6, "model_only_km2": 3.0}, {"zone_id": "d", "envelope_only_km2": 3.7, "model_only_km2": 10.5},
            {"zone_id": "e", "envelope_only_km2": 0.9, "model_only_km2": 0.0}]
    assert largest_differences(rows, "envelope_only_km2") == ["b", "c", "d"]
    assert largest_differences(rows, "model_only_km2") == ["d", "a", "b"]
    assert largest_differences(rows, "envelope_only_km2", minimum_km2=5.0) == ["b", "c"]
    assert largest_differences(rows, "envelope_only_km2", limit=5) == ["b", "c", "d", "e"]  # 0.4 km2 is under the minimum.
    assert largest_differences([], "model_only_km2") == []


def test_share_inside_and_residents_inside_count_cells_of_the_mask() -> None:
    low = grid(["##......", "##......", "........", "........"])  # Four low-confidence cells of the model.
    assert share_inside(low, ENVELOPE) == 0.0
    assert share_inside(MODEL, ENVELOPE) == 0.333
    assert share_inside(MODEL & ~low, ENVELOPE) == 0.5
    assert share_inside(np.zeros(MODEL.shape, bool), ENVELOPE) is None
    left = np.zeros(MODEL.shape, dtype=bool)
    left[:, :3] = True
    assert share_inside(MODEL, ENVELOPE, left) == round(2 / 9, 3)
    # Residents: the population grid summed over the mask (inside the area), as a whole number.
    people = np.full(MODEL.shape, 2.4)
    assert residents_inside(ENVELOPE, people) == round(12 * 2.4)
    assert residents_inside(ENVELOPE, people, left) == round(3 * 2.4)
    assert residents_inside(np.zeros(MODEL.shape, bool), people) == 0
    with pytest.raises(SeasonEnvelopeError, match="share one grid"):
        residents_inside(ENVELOPE, people[:2])
    with pytest.raises(SeasonEnvelopeError, match="negative"):
        residents_inside(ENVELOPE, -people)


# --- Change notice and licence notice ----------------------------------------------------------------------------


def test_change_notice_fills_every_placeholder_or_refuses() -> None:
    notice = fill_change_notice(TEMPLATE, clip_geometry="the eight subdistricts", repair_method="make_valid", repair_count=3,
                                source_crs="EPSG:4326", target_crs="EPSG:3857", cell_size_m="about 15")
    assert notice == ("Changed by FloodGuard: clipped to Mae Sai district (the eight subdistricts); geometry repaired (make_valid; 3 parts repaired); "
                      "reprojected from EPSG:4326 to EPSG:3857; rasterised to about 15 m cells. Source: UNOSAT and GISTDA, FL20240912THA, "
                      "UNOSAT product 4009, CC BY-SA 4.0.")
    assert "{" not in notice and CREDIT in notice
    values = dict(clip_geometry="x", repair_method="make_valid", repair_count=0, source_crs="EPSG:4326", target_crs="EPSG:32647", cell_size_m=10)
    assert "0 parts repaired" in fill_change_notice(TEMPLATE, **values) and "rasterised to 10 m cells" in fill_change_notice(TEMPLATE, **values)
    for bad in ({"repair_count": -1}, {"repair_count": 2.5}, {"repair_count": True}, {"clip_geometry": " "}, {"target_crs": ""}):
        with pytest.raises(SeasonEnvelopeError):
            fill_change_notice(TEMPLATE, **{**values, **bad})
    with pytest.raises(SeasonEnvelopeError, match="placeholder this file cannot fill"):
        fill_change_notice(TEMPLATE + " Simplified to {tolerance_m} m.", **values)


OTHER_INPUTS = [
    {"id": "terrain", "name": "A terrain model", "licence": "Terrain licence (free, attribution)", "attribution": "© Terrain holders", "used_for": "The modelled water."},
    {"id": "population", "name": "A population grid", "licence": "CC BY 4.0", "attribution": "Population grid makers", "used_for": "The residents counts."},
]


def licence_arguments() -> dict:
    return {
        "title": "Licence notice for the derived files",
        "files": ["envelope.png", "envelope.json", "LICENSE"],
        "licence": {"name": "CC BY-SA 4.0", "full_name": "Creative Commons Attribution-ShareAlike 4.0 International",
                    "url": "https://creativecommons.org/licenses/by-sa/4.0/", "legal_code_url": "https://creativecommons.org/licenses/by-sa/4.0/legalcode"},
        "credit": CREDIT,
        "change_notices": {"envelope.png": "Changed by FloodGuard: clipped.", "envelope.json": "Changed by FloodGuard: clipped and counted."},
        "source_lines": ["Source name", "Archive: file.zip"],
        "limits": ["Not legal advice."],
        "other_inputs": OTHER_INPUTS,
        "other_inputs_note": "The statistics file also holds figures from the open data below; each keeps its own credit and licence.",
        "thai": {"title": "ประกาศสัญญาอนุญาต", "headings": {"files": "ไฟล์", "source": "แหล่งข้อมูล", "credit": "การให้เครดิต", "licence": "สัญญาอนุญาต",
                                                     "share_alike": "การอนุญาตแบบเดียวกัน", "changes": "สิ่งที่เปลี่ยนแปลง",
                                                     "other_inputs": "ข้อมูลนำเข้าอื่น", "limits": "ข้อจำกัด"},
                 "source_lines": ["ชื่อแหล่งข้อมูล"], "share_alike": "เผยแพร่ภายใต้สัญญาอนุญาตเดียวกัน", "limits": ["ไม่ใช่คำแนะนำทางกฎหมาย"],
                 "change_notices": {"envelope.png": "FloodGuard เปลี่ยนแปลง: ตัดตามขอบเขต", "envelope.json": "FloodGuard เปลี่ยนแปลง: ตัดตามขอบเขตและนับ"},
                 "other_inputs_note": "ไฟล์สถิติมีตัวเลขจากข้อมูลเปิดด้านล่างนี้ด้วย",
                 "other_inputs_labels": {"licence": "สัญญาอนุญาต", "credit": "เครดิต", "used_for": "ใช้สำหรับ"},
                 "other_inputs_used_for": {"terrain": "น้ำจากแบบจำลอง", "population": "จำนวนผู้อยู่อาศัย"}},
    }


def test_licence_notice_states_licence_credit_and_changes_in_english_and_thai() -> None:
    text = licence_notice(**licence_arguments())
    assert text.endswith("\n") and "\r" not in text
    english, thai = text.split("-" * 80)
    for half in (english, thai):
        for needle in ("FloodGuard Thailand", "envelope.png", "envelope.json", "LICENSE", CREDIT, "Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)",
                       "https://creativecommons.org/licenses/by-sa/4.0/", "https://creativecommons.org/licenses/by-sa/4.0/legalcode",
                       "Changed by FloodGuard: clipped.", "Changed by FloodGuard: clipped and counted."):
            assert needle in half, needle
    assert "share your version under the same licence, CC BY-SA 4.0" in english and "Not legal advice." in english and "Archive: file.zip" in english
    assert "ประกาศสัญญาอนุญาต" in thai and "ไม่ใช่คำแนะนำทางกฎหมาย" in thai and "ชื่อแหล่งข้อมูล" in thai and "Source name" not in thai
    # What was changed is readable in Thai: the Thai half gives each notice in Thai first, then the English notice as published.
    assert "FloodGuard เปลี่ยนแปลง: ตัดตามขอบเขต" not in english
    assert thai.index("FloodGuard เปลี่ยนแปลง: ตัดตามขอบเขต") < thai.index("Changed by FloodGuard: clipped.")
    assert thai.index("FloodGuard เปลี่ยนแปลง: ตัดตามขอบเขตและนับ") < thai.index("Changed by FloodGuard: clipped and counted.")
    # The other inputs keep their own licences and credits, in both halves, each with what it was used for.
    assert "7. Other inputs (their own credits and licences)" in english and "8. Limits" in english
    assert "7. ข้อมูลนำเข้าอื่น" in thai and "8. ข้อจำกัด" in thai
    for half, labels, uses in ((english, ("Licence", "Credit", "Used for"), ("The modelled water.", "The residents counts.")),
                               (thai, ("สัญญาอนุญาต", "เครดิต", "ใช้สำหรับ"), ("น้ำจากแบบจำลอง", "จำนวนผู้อยู่อาศัย"))):
        for item, use in zip(OTHER_INPUTS, uses):
            for needle in (f"- {item['name']}", f"{labels[0]}: {item['licence']}", f"{labels[1]}: {item['attribution']}", f"{labels[2]}: {use}"):
                assert needle in half, needle
    assert "The statistics file also holds figures from the open data below" in english and "ไฟล์สถิติมีตัวเลขจากข้อมูลเปิดด้านล่างนี้ด้วย" in thai
    # A notice without a credit, a licence link or a change notice for a file it covers is refused.
    for change in ({"credit": " "}, {"files": []}, {"change_notices": {}}, {"change_notices": {"other.png": "x"}},
                   {"licence": {"name": "CC BY-SA 4.0", "full_name": "x", "url": "", "legal_code_url": "y"}}):
        with pytest.raises(SeasonEnvelopeError):
            licence_notice(**{**licence_arguments(), **change})
    # So is one without its other inputs, with an input that lacks its licence or its credit, or without the Thai of either.
    arguments = licence_arguments()
    for change in ({"other_inputs": []}, {"other_inputs_note": " "}, {"other_inputs": [{**OTHER_INPUTS[0], "licence": ""}]},
                   {"other_inputs": [{key: value for key, value in OTHER_INPUTS[1].items() if key != "attribution"}]},
                   {"thai": {**arguments["thai"], "change_notices": {"envelope.png": "FloodGuard เปลี่ยนแปลง"}}},
                   {"thai": {**arguments["thai"], "other_inputs_used_for": {"terrain": "น้ำจากแบบจำลอง"}}},
                   {"thai": {**arguments["thai"], "other_inputs_note": ""}}):
        with pytest.raises(SeasonEnvelopeError):
            licence_notice(**{**arguments, **change})


def test_other_inputs_need_a_name_a_licence_a_credit_and_a_use() -> None:
    assert OTHER_INPUT_KEYS == ("id", "name", "licence", "attribution", "used_for")
    assert other_input_problems(OTHER_INPUTS) == []
    assert other_input_problems(None) == other_input_problems([]) == other_input_problems("CC BY 4.0") == [
        "other_inputs must list every input besides the product, each with its licence and its credit"]
    assert other_input_problems([{**OTHER_INPUTS[0], "attribution": " "}, "WorldPop"]) == [
        "other_inputs[0] lacks attribution", *(f"other_inputs[1] lacks {key}" for key in OTHER_INPUT_KEYS)]
    # A short credit names the holders the full credit begins with.
    assert credit_holders(CREDIT) == "UNOSAT and GISTDA" and credit_holders("One holder") == "One holder" and credit_holders("") == ""


# --- What a published document must keep -------------------------------------------------------------------------


def document() -> dict:
    notice = fill_change_notice(TEMPLATE, clip_geometry="x", repair_method="make_valid", repair_count=3, source_crs="EPSG:4326",
                                target_crs="EPSG:3857", cell_size_m=15)
    return {
        "lane": ENVELOPE_LANE, "not_an_observation_for_any_replay_day": True,
        "licence": {"name": "CC BY-SA 4.0", "url": "https://creativecommons.org/licenses/by-sa/4.0/"},
        "credit": CREDIT, "map_credit": "UNOSAT and GISTDA · CC BY-SA 4.0", "change_notice": notice,
        "standard_sentence": "Unvalidated preliminary agency extent, used as provided under CC BY-SA 4.0. FloodGuard did not validate it.",
        "other_inputs": copy.deepcopy(OTHER_INPUTS),
        "source_timestamp": "2024-08-01/2024-10-22", "generated_at": "2026-10-02T18:00:00+07:00", "season_window": "2024-08-01/2024-10-22",
        "confidence": "low", "confidence_reason": "A preliminary agency product beside an illustrative model.", "assumptions": ["Used as provided."],
        "source": {"field_validation": 0},
        "official_warning": False, "operational_status": "non_operational", "can_feed_decision_layer": False,
        "comparison": {
            "role": COMPARISON_ROLE, "use": f"{COMPARISON_USE} The figures say where the two differ.", "change_notice": notice,
            "district": [{"id": "modelled_peak", **mask_agreement(MODEL, ENVELOPE, 1.0)}],
            "by_tambon": [{"tambon_id": "west", **mask_agreement(MODEL, ENVELOPE, 1.0)}, {"tambon_id": "east", **mask_agreement(MODEL & False, ENVELOPE, 1.0)}],
            "residents": {"residents_in_envelope": 120, "rule": "Population cells whose centre lies inside the envelope.",
                          "residents_in_envelope_replay_rule": 110, "replay_rule": "The replay's rule.", "model_residents_in_water": 90},
        },
    }


def test_a_complete_document_has_no_problem() -> None:
    assert COMPARISON_ROLE == ENVELOPE_CHECK_ROLE == "season_envelope_plausibility"
    assert COMPARISON_USE == "Plausibility against a season envelope, not a validation."
    assert document_problems(document(), licence_name="CC BY-SA 4.0", credit=CREDIT) == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(lane="OBS"), "lane must be SCN-ENV"),
        (lambda d: d.update(not_an_observation_for_any_replay_day=False), "not an observation for any replay day"),
        (lambda d: d["licence"].update(name="CC BY 4.0"), "licence must be CC BY-SA 4.0"),
        (lambda d: d.pop("licence"), "licence must be CC BY-SA 4.0"),
        (lambda d: d.update(credit="GISTDA"), "credit must be the rights record's attribution text"),
        (lambda d: d.update(map_credit="UNOSAT and GISTDA"), "map_credit must name the licence"),
        (lambda d: d.update(map_credit="CC BY-SA 4.0"), "map_credit must name the holders of the product"),
        (lambda d: d.update(map_credit="GISTDA · CC BY-SA 4.0"), "map_credit must name the holders of the product"),
        (lambda d: d.pop("standard_sentence"), "standard_sentence must say"),
        (lambda d: d.update(standard_sentence="Preliminary agency extent under CC BY-SA 4.0."), "standard_sentence must say"),
        (lambda d: d.pop("other_inputs"), "other_inputs must list every input besides the product"),
        (lambda d: d["other_inputs"][1].pop("licence"), "other_inputs[1] lacks licence"),
        (lambda d: d["other_inputs"][0].update(attribution=""), "other_inputs[0] lacks attribution"),
        (lambda d: d["comparison"]["residents"].pop("rule"), "comparison.residents must give residents_in_envelope with its rule in rule"),
        (lambda d: d["comparison"]["residents"].pop("residents_in_envelope_replay_rule"), "must give residents_in_envelope_replay_rule with its rule in replay_rule"),
        (lambda d: d.update(change_notice="Changed by FloodGuard: clipped to {clip_geometry}."), "change_notice must be filled"),
        (lambda d: d.update(change_notice=""), "change_notice must be filled"),
        (lambda d: d["comparison"].pop("change_notice"), "comparison.change_notice must be filled"),
        (lambda d: d.pop("source_timestamp"), "missing source_timestamp"),
        (lambda d: d.update(generated_at=" "), "missing generated_at"),
        (lambda d: d.pop("confidence"), "missing confidence"),
        (lambda d: d.update(assumptions=[]), "missing assumptions"),
        (lambda d: d.update(official_warning=True), "non-operational"),
        (lambda d: d.update(can_feed_decision_layer=True), "non-operational"),
        (lambda d: d.pop("comparison"), "missing comparison"),
        (lambda d: d["comparison"].update(role="independent_magnitude_check"), "comparison.role must be season_envelope_plausibility"),
        (lambda d: d["comparison"].update(use="Agreement with the season envelope."), "plausibility against a season envelope, not a validation"),
        (lambda d: d["comparison"].update(district=[]), "comparison.district must hold at least one row"),
        (lambda d: d["comparison"]["district"][0].update(agreement_iou=1.2), "agreement_iou must be a share between 0 and 1"),
        (lambda d: d["comparison"]["by_tambon"][0].pop("containment_envelope_in_model"), "containment_envelope_in_model must be a share"),
        (lambda d: d["comparison"]["district"][0].update(precision=0.6), "$.comparison.district[0].precision names a measure"),
        (lambda d: d["comparison"]["district"][0].update(recall=0.7), "recall names a measure"),
        (lambda d: d["comparison"].update(model_accuracy=0.48), "model_accuracy names a measure"),
        (lambda d: d["comparison"].update(validated=True), "validated names a measure"),
        (lambda d: d["comparison"].update(corroboration_share=0.59), "corroboration_share names a measure"),
        (lambda d: d.update(accepted_fpps=None), "accepted_fpps names a measure"),
        (lambda d: d["comparison"].update(action_class="B"), "action_class names a measure"),
    ],
)
def test_document_rules_name_each_break(change, message: str) -> None:
    broken = copy.deepcopy(document())
    change(broken)
    problems = document_problems(broken, licence_name="CC BY-SA 4.0", credit=CREDIT)
    assert any(message in problem for problem in problems), problems


def test_a_null_ratio_is_allowed_and_the_products_own_attribute_name_is_not_a_measure() -> None:
    # A subdistrict with no modelled water has no share to state; "field_validation" is the product's attribute.
    value = document()
    assert value["comparison"]["by_tambon"][1]["containment_model_in_envelope"] is None
    assert document_problems(value, licence_name="CC BY-SA 4.0", credit=CREDIT) == []
    # A comparison without a residents block is allowed; one with a count gives each count its rule.
    assert RESIDENT_COUNT_RULES == {"residents_in_envelope": "rule", "residents_in_envelope_replay_rule": "replay_rule"}
    value["comparison"].pop("residents")
    assert document_problems(value, licence_name="CC BY-SA 4.0", credit=CREDIT) == []
