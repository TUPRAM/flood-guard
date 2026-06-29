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
