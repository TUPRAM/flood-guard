from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.theos2_review import (
    THEOS2ReviewError,
    build_theos2_visual_review_checklist,
    write_theos2_visual_review_checklist,
)


def selected_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "file_name": "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif",
                "source_timestamp": "2025-07-30T03:33:31Z",
                "category": "Disaster",
                "preview_path": "theos2_previews/theos2_preview_004.svg",
                "processing_scope": "theos2_optical_context_preview_only",
                "reference_mask_status": "not_reference_mask",
                "processing_allowed": True,
            }
        ]
    )


def thumbnail_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "file_name": "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif",
                "thumbnail_path": "theos2_thumbnails/theos2_thumbnail_004.png",
                "thumbnail_format": "png",
                "raster_reader": "rasterio",
            }
        ]
    )


def test_visual_review_checklist_prefers_true_thumbnail_path() -> None:
    checklist = build_theos2_visual_review_checklist(
        selected_manifest(),
        thumbnail_manifest(),
    )

    assert len(checklist) == 1
    row = checklist.iloc[0]
    assert row["preview_path"] == "theos2_thumbnails/theos2_thumbnail_004.png"
    assert row["preview_source"] == "true_png_thumbnail_via_rasterio"
    assert row["visible_water_context"] == "not_reviewed"
    assert row["built_up_area_context"] == "not_reviewed"
    assert row["road_context"] == "not_reviewed"
    assert row["cloud_haze_status"] == "not_reviewed"
    assert row["exposure_explanation_usefulness"] == "not_reviewed"
    assert row["review_status"] == "pending_manual_review"
    assert row["flood_label_claim"] == "not_allowed"
    assert "not flood validation" in row["assumptions"]
    assert "not ML labels" in row["assumptions"]


def test_visual_review_checklist_falls_back_to_svg_preview() -> None:
    checklist = build_theos2_visual_review_checklist(selected_manifest())

    row = checklist.iloc[0]
    assert row["preview_path"] == "theos2_previews/theos2_preview_004.svg"
    assert row["preview_source"] == "metadata_svg_preview"


def test_visual_review_checklist_rejects_reference_mask_status() -> None:
    manifest = selected_manifest()
    manifest.loc[0, "reference_mask_status"] = "confirmed"

    with pytest.raises(THEOS2ReviewError, match="must not be a reference mask"):
        build_theos2_visual_review_checklist(manifest)


def test_write_visual_review_checklist_writes_csv(tmp_path: Path) -> None:
    selected_path = tmp_path / "selected.csv"
    thumbnail_path = tmp_path / "thumbnails.csv"
    output_path = tmp_path / "theos2_visual_review_checklist.csv"
    selected_manifest().to_csv(selected_path, index=False)
    thumbnail_manifest().to_csv(thumbnail_path, index=False)

    written = write_theos2_visual_review_checklist(
        selected_manifest_path=selected_path,
        thumbnail_manifest_path=thumbnail_path,
        output_path=output_path,
    )

    assert written == output_path
    checklist = pd.read_csv(output_path)
    assert checklist.loc[0, "preview_source"] == "true_png_thumbnail_via_rasterio"
