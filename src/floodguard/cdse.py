"""No-download CDSE metadata query helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CDSE_PRODUCTS_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

CDSE_OUTPUT_COLUMNS: tuple[str, ...] = (
    "acquisition_date",
    "product_name",
    "cdse_product_id",
    "online_status",
    "mission_platform_prefix",
    "product_storage_type",
    "candidate_role",
    "query_profile",
    "source_url",
    "blocker_note",
)


@dataclass(frozen=True)
class CDSEQueryProfile:
    """Configuration for a no-download CDSE metadata query."""

    name: str
    point_wkt: str
    collection: str
    product_name_contains: str
    start_datetime: str
    end_datetime: str
    default_top: int
    role_mode: str
    blocker_note: str


CDSE_PROFILES: dict[str, CDSEQueryProfile] = {
    "mae_sai_2024": CDSEQueryProfile(
        name="mae_sai_2024",
        point_wkt="POINT(99.88 20.43)",
        collection="SENTINEL-1",
        product_name_contains="IW_GRDH_1SDV",
        start_datetime="2024-09-01T00:00:00.000Z",
        end_datetime="2024-09-25T23:59:59.999Z",
        default_top=50,
        role_mode="mae_sai",
        blocker_note=(
            "download not performed; UNOSAT reference-mask geometry and "
            "redistribution license unresolved"
        ),
    ),
    "hat_yai_2025": CDSEQueryProfile(
        name="hat_yai_2025",
        point_wkt="POINT(100.47 7.01)",
        collection="SENTINEL-1",
        product_name_contains="IW_GRDH_1SDV",
        start_datetime="2025-11-17T00:00:00.000Z",
        end_datetime="2025-12-05T23:59:59.999Z",
        default_top=50,
        role_mode="hat_yai",
        blocker_note=(
            "download not performed; Charter, Sentinel Asia, and GISTDA "
            "geometry access and license status not confirmed"
        ),
    ),
}


class CDSEMetadataError(ValueError):
    """Raised when CDSE metadata input or response data is invalid."""


def get_cdse_profile(profile_name: str, top: int | None = None) -> CDSEQueryProfile:
    """Return a named CDSE query profile, optionally overriding top limit."""

    if profile_name not in CDSE_PROFILES:
        raise CDSEMetadataError(f"Unknown CDSE query profile: {profile_name}")
    profile = CDSE_PROFILES[profile_name]
    if top is None:
        return profile
    if top <= 0:
        raise CDSEMetadataError("CDSE top limit must be positive.")
    return replace(profile, default_top=top)


def build_cdse_products_url(profile: CDSEQueryProfile) -> str:
    """Build the CDSE OData Products URL for a no-download metadata query."""

    filter_text = " and ".join(
        [
            f"Collection/Name eq '{profile.collection}'",
            f"contains(Name,'{profile.product_name_contains}')",
            f"ContentDate/Start ge {profile.start_datetime}",
            f"ContentDate/Start le {profile.end_datetime}",
            f"OData.CSC.Intersects(area=geography'SRID=4326;{profile.point_wkt}')",
        ]
    )
    params = {
        "$filter": filter_text,
        "$orderby": "ContentDate/Start asc",
        "$top": str(profile.default_top),
    }
    return CDSE_PRODUCTS_URL + "?" + urlencode(params, safe="()/$=,':;")


def fetch_cdse_products(profile: CDSEQueryProfile) -> dict[str, Any]:
    """Fetch CDSE product metadata JSON. This does not download product assets."""

    url = build_cdse_products_url(profile)
    request = Request(url, headers={"User-Agent": "FloodGuard-metadata/0.1"})
    with urlopen(request, timeout=60) as response:  # noqa: S310 - public metadata URL
        return json.load(response)


def parse_cdse_products(
    response_json: dict[str, Any],
    profile: CDSEQueryProfile,
    source_url: str | None = None,
) -> list[dict[str, object]]:
    """Parse CDSE Products OData JSON into deterministic metadata rows."""

    products = response_json.get("value")
    if not isinstance(products, list):
        raise CDSEMetadataError("CDSE response JSON must include a value list.")

    rows: list[dict[str, object]] = []
    query_url = source_url or build_cdse_products_url(profile)
    for product in products:
        if not isinstance(product, dict):
            raise CDSEMetadataError("CDSE product entries must be objects.")
        name = str(product.get("Name", ""))
        product_id = str(product.get("Id", ""))
        content_date = product.get("ContentDate") or {}
        if not isinstance(content_date, dict):
            raise CDSEMetadataError("CDSE product ContentDate must be an object.")
        acquisition_date = str(content_date.get("Start", ""))
        if not name or not product_id or not acquisition_date:
            raise CDSEMetadataError("CDSE product is missing Name, Id, or ContentDate/Start.")

        storage_type = _storage_type(name)
        rows.append(
            {
                "acquisition_date": acquisition_date,
                "product_name": name,
                "cdse_product_id": product_id,
                "online_status": bool(product.get("Online", False)),
                "mission_platform_prefix": name.split("_", maxsplit=1)[0],
                "product_storage_type": storage_type,
                "candidate_role": _candidate_role(profile, acquisition_date, storage_type),
                "query_profile": profile.name,
                "source_url": query_url,
                "blocker_note": profile.blocker_note,
            }
        )
    return rows


def _storage_type(product_name: str) -> str:
    if "_COG.SAFE" in product_name:
        return "COG"
    if product_name.endswith(".SAFE"):
        return "SAFE"
    return "unknown"


def _candidate_role(
    profile: CDSEQueryProfile,
    acquisition_date: str,
    storage_type: str,
) -> str:
    suffix = "COG candidate" if storage_type == "COG" else "SAFE alternative"
    if profile.role_mode == "mae_sai":
        if acquisition_date < "2024-09-10":
            return f"pre-event {suffix}"
        if acquisition_date < "2024-09-18":
            return f"post-event {suffix}"
        return f"fallback post-event {suffix}"
    if profile.role_mode == "hat_yai":
        return f"event-window {suffix}"
    return suffix
