from __future__ import annotations

from pathlib import Path

from floodguard.cems import parse_cems_activation


def test_parse_cems_activation_extracts_aoi_product_rows() -> None:
    response = {
        "results": [
            {
                "code": "EMSR999",
                "name": "Flood test",
                "eventTime": "2024-09-14T00:00:00",
                "activationTime": "2024-09-14T12:00:00",
                "countries": [{"name": "Thailand"}],
                "aois": [
                    {
                        "number": 1,
                        "name": "Mae Sai test",
                        "extent": (
                            "POLYGON ((99.7 20.2, 100.1 20.2, 100.1 20.6, "
                            "99.7 20.6, 99.7 20.2))"
                        ),
                        "products": [
                            {
                                "id": 12,
                                "type": "DEL",
                                "monitoring": False,
                                "monitoringNumber": 0,
                                "downloadPath": (
                                    "https://rapidmapping.example/EMSR999_AOI01_DEL_PRODUCT_v1.zip"
                                ),
                                "version": {
                                    "number": 1,
                                    "statusCode": "F",
                                    "deliveryTime": "2024-09-15T00:00:00",
                                },
                                "images": [
                                    {
                                        "sensorName": "Sentinel-1",
                                        "acquisitionTime": "2024-09-14T00:00:00",
                                    }
                                ],
                                "layers": [
                                    {
                                        "name": "EMSR999/AOI01/DEL_PRODUCT/observedEventA_v1_VT",
                                        "format": "vt",
                                    },
                                    {
                                        "name": "EMSR999/AOI01/DEL_PRODUCT/floodDepthA_v1_VT",
                                        "format": "vt",
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }

    rows = parse_cems_activation(
        response,
        source_url="https://example.test",
        retrieved_at_utc="2026-07-08T00:00:00Z",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["product_name"] == "EMSR999_AOI01_DEL_PRODUCT_v1.zip"
    assert row["mae_sai_point_in_aoi_bbox"] is True
    assert row["flood_layer_present"] is True
    assert row["observed_event_layer_present"] is True
    assert row["candidate_role"] == "possible_mae_sai_reference_candidate"
    assert row["mae_sai_reference_relevance"] == "potential_match"
    assert row["download_performed"] is False
    assert row["processing_allowed"] is False


def test_generated_cems_manifest_records_no_mae_sai_match() -> None:
    manifest = Path("outputs/cems_product_candidate_manifest.csv")
    if not manifest.exists():
        return
    text = manifest.read_text(encoding="utf-8")
    assert "download_performed" in text
    assert "not_relevant_country_or_aoi_for_mae_sai" in text
