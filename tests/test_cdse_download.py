from __future__ import annotations

import pandas as pd

from floodguard.cdse_download import (
    MAE_SAI_SELECTED_PRODUCT_IDS,
    build_cdse_mae_sai_acquisition_manifest,
    build_cdse_product_download_url,
)


def test_cdse_download_url_targets_odata_value_endpoint() -> None:
    url = build_cdse_product_download_url("b09f96ca-4a60-43e7-9b8d-158022f0e5bf")

    assert url.endswith(
        "Products(b09f96ca-4a60-43e7-9b8d-158022f0e5bf)/$value"
    )


def test_cdse_acquisition_manifest_blocks_without_credentials() -> None:
    metadata = pd.DataFrame(
        [
            {
                "acquisition_date": "2024-09-06T11:31:06Z",
                "product_name": "S1A_PRE_COG.SAFE",
                "cdse_product_id": MAE_SAI_SELECTED_PRODUCT_IDS[0],
                "candidate_role": "pre-event COG candidate",
            },
            {
                "acquisition_date": "2024-09-15T23:16:01Z",
                "product_name": "S1A_POST_COG.SAFE",
                "cdse_product_id": MAE_SAI_SELECTED_PRODUCT_IDS[1],
                "candidate_role": "post-event COG candidate",
            },
        ]
    )

    manifest = build_cdse_mae_sai_acquisition_manifest(
        metadata,
        access_token="",
        username="",
        password="",
        dry_run=False,
        retrieved_at_utc="2026-07-08T00:00:00Z",
    )

    assert len(manifest) == 2
    assert set(manifest["download_status"]) == {"blocked_missing_cdse_credentials"}
    assert set(manifest["sha256_status"]) == {"not_recorded"}
    assert set(manifest["processing_allowed"]) == {False}
    assert manifest["reason_blocked"].str.contains("CDSE_ACCESS_TOKEN").all()
