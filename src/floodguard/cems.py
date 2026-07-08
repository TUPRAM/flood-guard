"""CEMS Rapid Mapping public activation resolver."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import math
from pathlib import Path
import re
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd

CEMS_ACTIVATION_URL = (
    "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/"
    "public-activations/?code={code}"
)

CEMS_OUTPUT_COLUMNS: tuple[str, ...] = (
    "activation_code",
    "activation_name",
    "countries",
    "event_time",
    "activation_time",
    "aoi_number",
    "aoi_name",
    "aoi_bbox_lon_min",
    "aoi_bbox_lat_min",
    "aoi_bbox_lon_max",
    "aoi_bbox_lat_max",
    "mae_sai_point_in_aoi_bbox",
    "hat_yai_point_in_aoi_bbox",
    "product_id",
    "product_name",
    "product_type",
    "monitoring",
    "monitoring_number",
    "version_number",
    "version_status",
    "delivery_time",
    "download_url",
    "product_date",
    "sensor_names",
    "layer_names",
    "observed_event_layer_present",
    "flood_layer_present",
    "candidate_role",
    "mae_sai_reference_relevance",
    "download_performed",
    "processing_allowed",
    "reason_blocked",
    "source_url",
    "retrieved_at_utc",
)

MAE_SAI_POINT = (99.88, 20.43)
HAT_YAI_POINT = (100.47, 7.01)


class CEMSResolverError(ValueError):
    """Raised when CEMS public metadata cannot be resolved."""


def fetch_cems_activation(code: str) -> dict[str, Any]:
    """Fetch CEMS public activation JSON without downloading product packages."""

    url = CEMS_ACTIVATION_URL.format(code=code)
    request = Request(url, headers={"User-Agent": "FloodGuard-cems-metadata/0.1"})
    with urlopen(request, timeout=60) as response:  # noqa: S310 - public metadata URL
        return json.load(response)


def parse_cems_activation(
    response_json: dict[str, Any],
    *,
    source_url: str,
    retrieved_at_utc: str | None = None,
) -> list[dict[str, Any]]:
    """Parse CEMS activation JSON into AOI/product rows."""

    results = response_json.get("results")
    if not isinstance(results, list) or not results:
        raise CEMSResolverError("CEMS response must include at least one result.")
    activation = results[0]
    timestamp = retrieved_at_utc or _utc_now()
    countries = "|".join(country.get("name", "") for country in activation.get("countries", []))
    rows: list[dict[str, Any]] = []
    for aoi in activation.get("aois", []):
        bbox = _bbox_from_wkt(str(aoi.get("extent", "")))
        mae_sai_overlap = _point_in_bbox(MAE_SAI_POINT, bbox)
        hat_yai_overlap = _point_in_bbox(HAT_YAI_POINT, bbox)
        for product in aoi.get("products", []):
            version = product.get("version") or {}
            layers = product.get("layers") or []
            images = product.get("images") or []
            layer_names = "|".join(str(layer.get("name", "")) for layer in layers)
            sensor_names = "|".join(
                sorted({str(image.get("sensorName", "")) for image in images if image.get("sensorName")})
            )
            product_date = "|".join(
                str(image.get("acquisitionTime", "")) for image in images if image.get("acquisitionTime")
            )
            product_name = Path(str(product.get("downloadPath", ""))).name
            observed_event = "observedEvent" in layer_names
            flood_layer = "flood" in layer_names.lower()
            rows.append(
                {
                    "activation_code": activation.get("code", ""),
                    "activation_name": activation.get("name", ""),
                    "countries": countries,
                    "event_time": activation.get("eventTime", ""),
                    "activation_time": activation.get("activationTime", ""),
                    "aoi_number": aoi.get("number", ""),
                    "aoi_name": aoi.get("name", ""),
                    "aoi_bbox_lon_min": bbox[0],
                    "aoi_bbox_lat_min": bbox[1],
                    "aoi_bbox_lon_max": bbox[2],
                    "aoi_bbox_lat_max": bbox[3],
                    "mae_sai_point_in_aoi_bbox": mae_sai_overlap,
                    "hat_yai_point_in_aoi_bbox": hat_yai_overlap,
                    "product_id": product.get("id", ""),
                    "product_name": product_name,
                    "product_type": product.get("type", ""),
                    "monitoring": product.get("monitoring", ""),
                    "monitoring_number": product.get("monitoringNumber", ""),
                    "version_number": version.get("number", ""),
                    "version_status": version.get("statusCode", ""),
                    "delivery_time": version.get("deliveryTime", ""),
                    "download_url": product.get("downloadPath", ""),
                    "product_date": product_date,
                    "sensor_names": sensor_names,
                    "layer_names": layer_names,
                    "observed_event_layer_present": observed_event,
                    "flood_layer_present": flood_layer,
                    "candidate_role": _candidate_role(mae_sai_overlap, hat_yai_overlap, flood_layer),
                    "mae_sai_reference_relevance": _mae_sai_relevance(
                        activation.get("countries", []),
                        mae_sai_overlap,
                        flood_layer,
                    ),
                    "download_performed": False,
                    "processing_allowed": False,
                    "reason_blocked": (
                        "CEMS metadata resolved without product download; AOI does not "
                        "cover Mae Sai or exact product relevance is not cleared"
                    ),
                    "source_url": source_url,
                    "retrieved_at_utc": timestamp,
                }
            )
    return rows


def resolve_cems_products(
    activation_codes: list[str] | tuple[str, ...] = ("EMSR754", "EMSR756"),
    retrieved_at_utc: str | None = None,
) -> pd.DataFrame:
    """Resolve CEMS product metadata for selected activation codes."""

    rows: list[dict[str, Any]] = []
    for code in activation_codes:
        source_url = CEMS_ACTIVATION_URL.format(code=code)
        rows.extend(
            parse_cems_activation(
                fetch_cems_activation(code),
                source_url=source_url,
                retrieved_at_utc=retrieved_at_utc,
            )
        )
    return pd.DataFrame(rows, columns=CEMS_OUTPUT_COLUMNS)


def write_cems_product_manifest(
    output_path: str | Path,
    activation_codes: list[str] | tuple[str, ...] = ("EMSR754", "EMSR756"),
    retrieved_at_utc: str | None = None,
) -> Path:
    """Write CEMS AOI/product metadata rows to CSV."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise CEMSResolverError("CEMS product manifest output must be CSV.")
    frame = resolve_cems_products(activation_codes, retrieved_at_utc=retrieved_at_utc)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    return target


def _bbox_from_wkt(wkt: str) -> tuple[float, float, float, float]:
    numbers = [float(match) for match in re.findall(r"-?\d+(?:\.\d+)?", wkt)]
    if len(numbers) < 4 or len(numbers) % 2 != 0:
        return (math.nan, math.nan, math.nan, math.nan)
    lon_values = numbers[0::2]
    lat_values = numbers[1::2]
    return (
        round(min(lon_values), 8),
        round(min(lat_values), 8),
        round(max(lon_values), 8),
        round(max(lat_values), 8),
    )


def _point_in_bbox(
    point: tuple[float, float],
    bbox: tuple[float, float, float, float],
) -> bool:
    if any(math.isnan(value) for value in bbox):
        return False
    lon, lat = point
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def _candidate_role(mae_sai_overlap: bool, hat_yai_overlap: bool, flood_layer: bool) -> str:
    if mae_sai_overlap and flood_layer:
        return "possible_mae_sai_reference_candidate"
    if hat_yai_overlap and flood_layer:
        return "possible_hat_yai_reference_candidate"
    if flood_layer:
        return "flood_product_outside_current_mvp"
    return "non_flood_or_context_product"


def _mae_sai_relevance(
    countries: list[dict[str, Any]],
    mae_sai_overlap: bool,
    flood_layer: bool,
) -> str:
    country_names = {country.get("name", "") for country in countries}
    if mae_sai_overlap and flood_layer:
        return "potential_match"
    if "Thailand" not in country_names:
        return "not_relevant_country_or_aoi_for_mae_sai"
    if not mae_sai_overlap:
        return "thailand_related_but_aoi_does_not_cover_mae_sai"
    return "needs_manual_review"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
