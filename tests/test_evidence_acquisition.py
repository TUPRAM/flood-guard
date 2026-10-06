"""HTTP success and catalogue compatibility do not confer data acceptance."""

import json

import pytest

from floodguard.evidence_acquisition import (
    acquire_ngis_context,
    review_public_responses,
)


def test_review_distinguishes_catalogue_error_and_access_failure(tmp_path):
    routes = [
        {
            "id": "mae-sai-september-reference",
            "asset": "unosat.json",
            "http_status": 200,
        },
        {"id": "ngis-drainage", "asset": "services.json", "http_status": 200},
        {
            "id": "moph-public-register",
            "asset": None,
            "http_status": 403,
            "access": "authentication_required",
        },
        {"id": "hii-mya004", "asset": None, "http_status": 404},
        {
            "id": "provider-error",
            "asset": "error.json",
            "http_status": 200,
            "qualified_for_validation": True,
        },
    ]
    (tmp_path / "gap_register.json").write_text(json.dumps({"routes": routes}))
    (tmp_path / "unosat.json").write_text(
        json.dumps({"map_event": {"id": 3991, "shp_link": None, "kml_link": None}})
    )
    (tmp_path / "services.json").write_text(
        json.dumps(
            {"services": [{"name": "Hosted/NAT_STREAM_DWR", "type": "FeatureServer"}]}
        )
    )
    (tmp_path / "error.json").write_text(
        json.dumps({"error": {"code": 499, "message": "Token required"}})
    )
    result = review_public_responses(tmp_path)
    by_id = {r["id"]: r for r in result["routes"]}
    assert by_id["mae-sai-september-reference"]["published_vector_links"] == []
    assert by_id["ngis-drainage"]["usable_dataset_acquired"] is False
    assert (
        by_id["ngis-drainage"]["suitability"]
        == "public_service_directory_not_feature_data"
    )
    assert (
        by_id["moph-public-register"]["access"] == "access_forbidden_reason_unconfirmed"
    )
    assert by_id["hii-mya004"]["suitability"] == "station_month_absent"
    assert by_id["provider-error"]["suitability"] == "provider_error_response"
    assert all(r["qualified_for_validation"] is False for r in result["routes"])


def test_ngis_bounded_partial_response_is_not_complete(monkeypatch, tmp_path):
    pytest.importorskip("shapely")
    import requests

    class Response:
        def __init__(self, value):
            self.value = value
            self.content = json.dumps(value).encode()
            self.url = "https://ngis.go.th/published-query"

        def raise_for_status(self):
            pass

        def json(self):
            return self.value

    def get(url, params, timeout):
        assert timeout <= 20
        if params.get("returnCountOnly"):
            return Response({"count": 3})
        assert params["resultRecordCount"] == 1
        assert "owner" not in params["outFields"]
        return Response(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"fid": 1},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[99, 19], [100, 20]],
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(requests, "get", get)
    aois = {
        "test": {
            "type": "Polygon",
            "coordinates": [[[99, 19], [100, 19], [100, 20], [99, 20], [99, 19]]],
        }
    }
    result = acquire_ngis_context(tmp_path, aois, max_features=1)
    assert result["files"] == 2
    assert result["complete_responses"] == 0
    assert all(r["complete_response"] is False for r in result["records"])
    assert all(r["public_redistribution_accepted"] is False for r in result["records"])
    assert all(r["source_epoch"] is None for r in result["records"])
    with pytest.raises(ValueError, match="bound must be"):
        acquire_ngis_context(tmp_path, aois, max_features=2001)


def test_ngis_error_body_does_not_become_geojson(monkeypatch, tmp_path):
    pytest.importorskip("shapely")
    import requests

    class Response:
        content = b'{"error":{"code":500}}'

        def raise_for_status(self):
            pass

        def json(self):
            return {"error": {"code": 500}}

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())
    aois = {
        "test": {
            "type": "Polygon",
            "coordinates": [[[99, 19], [100, 19], [100, 20], [99, 20], [99, 19]]],
        }
    }
    result = acquire_ngis_context(tmp_path, aois)
    assert result["files"] == 0
    assert all(r["status"] == "provider_error" for r in result["records"])
