from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).parents[1] / "docs" / "study_area_inventory.md"


def test_chiang_rai_inventory_lists_sentinel_1_candidates() -> None:
    text = DOC.read_text(encoding="utf-8")

    for product_id in (
        "062a0809-b421-447c-904d-b08923cf412b",
        "aaaef3af-fa49-4115-bf0f-f54175e7aedf",
        "5261e2a9-ea2a-43ca-a9a1-b3ee8b787432",
        "b09f96ca-4a60-43e7-9b8d-158022f0e5bf",
        "20a9c3b8-37df-46d5-81d8-d63c7e460225",
        "5251b74b-0bbd-4365-9eb4-fa33292e175a",
        "6a02d487-68fa-4be7-9628-f312b9049967",
        "f9348e20-5d61-4456-be70-d0c1328128ff",
    ):
        assert product_id in text


def test_chiang_rai_inventory_records_no_download_and_blockers() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "download not performed" in text
    assert "exact flood peak/reference mask is not locked" in text
    assert "validation mask licensing remains unresolved" in text
    assert "UNOSAT/UNITAR v1 Mae Sai flood reference target" in text
    assert "redistribution license unresolved" in text
    assert "b09f96ca-4a60-43e7-9b8d-158022f0e5bf" in text
    assert "20a9c3b8-37df-46d5-81d8-d63c7e460225" in text
    assert "docs/mae_sai_pair_decision_note.md" in text
    assert "planning pair selected, final processing blocked" in text


def test_hat_yai_inventory_lists_focused_cdse_candidates_and_access_notes() -> None:
    text = DOC.read_text(encoding="utf-8")

    for product_id in (
        "325e23d5-9ba6-439e-bac9-8d7efac83cac",
        "d80b81cb-c4aa-4dbb-a7de-8a1d01fca2dc",
        "61f1bb34-e9bd-47b5-85a3-0472b50bf620",
        "77afe9fe-ad3f-4fe1-872f-01bf801c742b",
        "96eb3dd0-0049-411b-919a-5091c94e4406",
        "99b5426b-8464-4691-9648-72cf37dd84c2",
        "443e046e-4f2b-4db6-bf3b-136f25c6f901",
        "95537190-81cf-4b8e-aee8-eae8a1b4d3dc",
        "386ccf2d-2253-40bc-99bd-fa19bbc3c6dd",
        "e641d58b-bc6d-4463-a49d-2ecebf2b64c2",
    ):
        assert product_id in text
    assert "International Charter Activation 1004" in text
    assert "Sentinel Asia Southern Thailand 2025" in text
    assert "GISTDA official assessments" in text
    assert "geometry access and license status not confirmed" in text
