"""Public open-data candidate inventory helpers.

This module records source metadata and public product links only. It does not
download imagery, crisis-map archives, masks, or other source assets.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import pandas as pd

PUBLIC_REFERENCE_COLUMNS: tuple[str, ...] = (
    "source_name",
    "source_group",
    "study_area",
    "source_url",
    "data_or_product_type",
    "candidate_role",
    "access_route",
    "license_status",
    "geometry_status",
    "redistribution_status",
    "can_use_for_validation",
    "can_use_for_ml_labels",
    "download_action",
    "repo_storage",
    "processing_scope",
    "confidence_class",
    "blocker",
    "next_action",
    "retrieved_at_utc",
)

SENTINEL_ASIA_2024_URL = "https://sentinel-asia.org/EO/2024/article20240910TH.html"


class PublicReferenceInventoryError(ValueError):
    """Raised when public reference inventory inputs are invalid."""


@dataclass(frozen=True)
class PublicLink:
    """Small public link extracted from a source page."""

    text: str
    url: str


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[PublicLink] = []
        self._href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._href = href
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        text = " ".join(" ".join(self._text_parts).split())
        self.links.append(PublicLink(text=text, url=self._href))
        self._href = None
        self._text_parts = []


def utc_now_text() -> str:
    """Return a compact UTC timestamp for source-metadata snapshots."""

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_public_reference_rows(retrieved_at_utc: str | None = None) -> list[dict[str, Any]]:
    """Return seed rows for the public/open data sources FloodGuard should inspect."""

    timestamp = retrieved_at_utc or utc_now_text()
    return [
        _row(
            "Copernicus Sentinel-1 via CDSE",
            "cdse_sentinel1",
            "Chiang Rai / Mae Sai 2024; Hat Yai / Songkhla 2025",
            "https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-1",
            "open SAR source imagery",
            "real pre/post SAR baseline source and later ML feature input",
            "CDSE OData metadata now; authenticated asset download later if selected",
            "open_sentinel_data_legal_notice",
            "source_imagery_available_after_product_download",
            "source_products_stay_outside_git",
            "no_not_a_reference_mask",
            "no_not_label_source",
            "metadata snapshot now; asset download only to external data workspace",
            "metadata_csv_only_no_SAFE_or_TIFF_assets",
            "open_source_feature_generation_after_file_manifest_gates",
            "high",
            "needs selected product download, local path, checksum, and legal reference mask",
            "query CDSE metadata profiles and lock pre/post pair against reference date",
            timestamp,
        ),
        _row(
            "Copernicus Sentinel-2 via CDSE",
            "cdse_sentinel2",
            "Chiang Rai / Mae Sai 2024; Hat Yai / Songkhla 2025",
            "https://dataspace.copernicus.eu/terms-and-conditions",
            "open optical source imagery",
            "optical context, cloud-screened exposure context, future optical features",
            "CDSE OData metadata now; authenticated asset download later if selected",
            "open_sentinel_data_legal_notice",
            "source_imagery_available_after_product_download",
            "source_products_stay_outside_git",
            "no_not_a_reference_mask",
            "no_not_label_source",
            "metadata snapshot now; asset download only to external data workspace",
            "metadata_csv_only_no_SAFE_or_TIFF_assets",
            "open_optical_context_after_file_manifest_gates",
            "medium",
            "cloud cover and no flood-label geometry; not suitable as validation mask",
            "query Sentinel-2 profiles and use only as optical context unless labels are acquired",
            timestamp,
        ),
        _row(
            "Copernicus EMS Rapid Mapping EMSR754",
            "cems_rapid_mapping",
            "Thailand flood candidate",
            "https://mapping.emergency.copernicus.eu/activations/EMSR754/",
            "rapid mapping activation",
            "public flood extent reference candidate if AOI/date/product coverage matches",
            "public activation viewer; exact product links require viewer/API product inspection",
            "public_cems_terms_subject_to_restrictions",
            "activation_public_exact_geometry_not_selected",
            "potentially_redistributable_subject_to_cems_terms",
            "potential_after_exact_product_coverage_and_terms_review",
            "not_cleared_for_ml_labels_until_product_terms_reviewed",
            "record activation metadata now; download exact products only after review",
            "activation_metadata_only_no_product_zip_or_geotiff",
            "reference_candidate_metadata_only",
            "medium",
            "exact downloadable product, AOI overlap, and date fit not locked",
            "inspect CEMS viewer/backend for AOI products and record product-level rows",
            timestamp,
        ),
        _row(
            "Copernicus EMS Rapid Mapping EMSR756",
            "cems_rapid_mapping",
            "Thailand flood candidate",
            "https://mapping.emergency.copernicus.eu/activations/EMSR756/",
            "rapid mapping activation",
            "public flood extent reference candidate if AOI/date/product coverage matches",
            "public activation viewer; exact product links require viewer/API product inspection",
            "public_cems_terms_subject_to_restrictions",
            "activation_public_exact_geometry_not_selected",
            "potentially_redistributable_subject_to_cems_terms",
            "potential_after_exact_product_coverage_and_terms_review",
            "not_cleared_for_ml_labels_until_product_terms_reviewed",
            "record activation metadata now; download exact products only after review",
            "activation_metadata_only_no_product_zip_or_geotiff",
            "reference_candidate_metadata_only",
            "medium",
            "exact downloadable product, AOI overlap, and date fit not locked",
            "inspect CEMS viewer/backend for AOI products and record product-level rows",
            timestamp,
        ),
        _row(
            "Sentinel Asia Northern Thailand 2024 event page",
            "sentinel_asia_event",
            "Chiang Rai / Mae Sai 2024",
            SENTINEL_ASIA_2024_URL,
            "public event products and maps",
            "public event evidence, possible weak reference if file geometry and terms allow",
            "public page with direct product links; requester-only Web-GIS remains restricted",
            "public_page_terms_need_product_level_review",
            "public_links_visible_exact_geometry_varies_by_product",
            "unresolved_product_level",
            "needs_file_type_geometry_and_license_review",
            "not_cleared_for_ml_labels",
            "scrape public links only; do not use requester-only Web-GIS or raw restricted imagery",
            "metadata_csv_only_no_product_zip_or_image_assets",
            "event_evidence_and_possible_reference_candidate_metadata_only",
            "medium",
            "product-level license and geometry type need inspection before validation use",
            "review scraped product rows and select only legally usable GIS geometry if present",
            timestamp,
        ),
        _row(
            "UN Thailand Mae Sai public report page",
            "unosat_public_report",
            "Chiang Rai / Mae Sai 2024",
            "https://thailand.un.org/en/280291-satellite-detected-water-extents-13-19-september-2024-over-mea-sai-district-chiang-rai",
            "public report page",
            "external citation, exposed-population sanity check, area target",
            "public web report",
            "public_report_terms_not_gis_mask_license",
            "report_only_no_downloaded_vector_mask",
            "public_page_citation_only",
            "no_report_only",
            "no_report_only_not_labels",
            "store source URL and summary only",
            "metadata_and_doc_reference_only",
            "citation_and_sanity_check_only",
            "medium",
            "public report is not a redistributable validation mask",
            "use as narrative and sanity check unless GIS geometry terms are obtained",
            timestamp,
        ),
        _row(
            "UNOSAT product 3991",
            "unosat_public_report",
            "Chiang Rai / Mae Sai 2024",
            "https://unosat.org/products/3991",
            "public product page/report",
            "reference-mask target if geometry and terms become available",
            "public product page; GIS geometry not exposed in browser DOM during inspection",
            "public_report_terms_not_gis_mask_license",
            "report_only_geometry_unresolved",
            "unresolved",
            "no_until_geometry_terms_confirmed",
            "no_until_ml_label_terms_confirmed",
            "store product id and URL only",
            "metadata_and_doc_reference_only",
            "reference_target_metadata_only",
            "medium",
            "geometry access and derivative-use terms remain unresolved",
            "wait for provider response or find public GIS download with explicit terms",
            timestamp,
        ),
        _row(
            "NASA MODIS/VIIRS NRT Global Flood Products",
            "nasa_nrt_flood",
            "Chiang Rai / Mae Sai 2024; Hat Yai / Songkhla 2025",
            "https://www.earthdata.nasa.gov/data/instruments/viirs/near-real-time-data/nrt-global-flood-products",
            "coarse global flood product",
            "coarse public flood proxy and temporal sanity check",
            "Earthdata registration may be required for downloads",
            "public_nasa_earthdata_access_with_account",
            "coarse_raster_available_after_earthdata_download",
            "source_products_stay_outside_git",
            "coarse_context_only_not_subdistrict_validation",
            "not_primary_ml_labels_for_road_subdistrict_scale",
            "metadata row now; download only to external data workspace if needed",
            "metadata_csv_only_no_raster_assets",
            "coarse_flood_context_after_file_manifest_gates",
            "medium",
            "250m-class product is too coarse for road/subdistrict validation claims",
            "use for independent temporal/context check, not final labels",
            timestamp,
        ),
        _row(
            "WorldPop Thailand 100m",
            "worldpop_population",
            "Thailand",
            "https://hub.worldpop.org/geodata/summary?id=6439",
            "population raster",
            "exposure and reachable-demand denominator",
            "public web download and metadata review",
            "generally_cc_by_4_0_with_dataset_specific_terms",
            "population_raster_available_after_download",
            "source_products_stay_outside_git",
            "no_context_denominator_not_flood_mask",
            "no_not_flood_labels",
            "metadata row now; download selected population layer outside Git",
            "metadata_csv_only_no_raster_assets",
            "exposure_context_after_file_manifest_gates",
            "high",
            "dataset year/version and license text must be recorded when selected",
            "select population year and add path/checksum in file manifest",
            timestamp,
        ),
        _row(
            "OpenStreetMap Thailand via Geofabrik",
            "osm_geofabrik",
            "Thailand",
            "https://download.geofabrik.de/asia/thailand.html",
            "OSM extract",
            "roads, bridges, facilities, routing graph candidate",
            "public Geofabrik extracts under ODbL",
            "odbl_1_0",
            "vector_extract_available_after_download",
            "odbl_share_alike_obligations",
            "no_context_network_not_flood_mask",
            "no_not_flood_labels",
            "metadata row now; download extract outside Git when routing lane starts",
            "metadata_csv_only_no_osm_pbf_assets",
            "road_and_facility_context_after_file_manifest_gates",
            "high",
            "OSM completeness varies; ODbL obligations must be respected",
            "use for prototype road graph then compare with official local sources if available",
            timestamp,
        ),
        _row(
            "Copernicus DEM GLO-30",
            "copernicus_dem",
            "Thailand",
            "https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM",
            "global DEM",
            "terrain, slope, false-positive review, susceptibility context",
            "public Copernicus DEM download route",
            "free_license_with_citation_source_obligations",
            "terrain_raster_available_after_download",
            "source_products_stay_outside_git",
            "no_context_not_flood_observation",
            "no_not_flood_labels",
            "metadata row now; use local DEM readiness lane for provided files",
            "metadata_csv_only_no_dem_raster_assets",
            "terrain_context_after_file_manifest_gates",
            "high",
            "DEM is not flood observation or reference mask",
            "continue using DEM only for terrain context and false-positive review",
            timestamp,
        ),
        _row(
            "HDX Thailand COD-AB",
            "hdx_cod_ab",
            "Thailand",
            "https://data.humdata.org/dataset/cod-ab-tha",
            "administrative boundaries",
            "province/district/subdistrict aggregation geometry",
            "public HDX dataset page and normal web/session download",
            "dataset_specific_hdx_terms",
            "admin_boundaries_available_after_download",
            "source_products_stay_outside_git",
            "no_admin_context_not_flood_mask",
            "no_not_flood_labels",
            "metadata row now; download selected boundary version outside Git",
            "metadata_csv_only_no_boundary_source_zip",
            "admin_join_context_after_file_manifest_gates",
            "high",
            "boundary vintage and official status must be recorded when selected",
            "select admin level and version for real decision-layer aggregation",
            timestamp,
        ),
        _row(
            "THEOS-2 local hackathon samples",
            "theos2_optical",
            "Local hackathon data",
            "local files; see docs/theos2_inventory.md",
            "local optical imagery",
            "optical context, exposure explanation, future optical features",
            "local user-provided files; selected checksum manifests already exist",
            "user_reported_hackathon_free_use",
            "local_imagery_available_for_selected_context_outputs",
            "source_files_stay_outside_git",
            "no_not_flood_reference_mask",
            "no_not_flood_labels",
            "use selected checksum-backed thumbnails/context only",
            "small_preview_outputs_and_metadata_only",
            "theos2_optical_context_preview_only",
            "medium",
            "not a flood validation source",
            "use in dashboard and action briefs as optical context only",
            timestamp,
        ),
        _row(
            "Local hackathon Sentinel-1 TIFF",
            "local_sentinel1_sar",
            "Chiang Rai / Mae Sai 2024 candidate overlap",
            "local files; see docs/sentinel1_local_provenance.md",
            "local SAR raster",
            "SAR context only until provenance and timing are resolved",
            "local user-provided file with selected checksum manifest",
            "user_reported_hackathon_free_use",
            "local_raster_available_but_timing_unresolved",
            "source_file_stays_outside_git",
            "no_until_provenance_timing_reference_mask_gates_pass",
            "no_until_provenance_timing_reference_mask_gates_pass",
            "quicklook context only; no real baseline use",
            "small_quicklook_outputs_and_metadata_only",
            "sentinel1_sar_context_quicklook_only",
            "low",
            "filename has placeholder timing and provenance remains unresolved",
            "do not use for real baseline until provenance resolver clears the row",
            timestamp,
        ),
        _row(
            "Local hackathon Copernicus DEM packages",
            "local_copernicus_dem",
            "Local hackathon data",
            "local files; see outputs/dem_selected_file_manifest.csv",
            "local DEM/elevation-slope packages",
            "terrain context only",
            "local user-provided ZIP packages with package checksums",
            "user_reported_hackathon_free_use",
            "local_dem_package_available_member_extraction_gated",
            "source_packages_stay_outside_git",
            "no_context_not_flood_observation",
            "no_not_flood_labels",
            "use only terrain quicklook/context after member checksum gates",
            "small_quicklook_outputs_and_metadata_only",
            "dem_terrain_context_quicklook_only",
            "medium",
            "DEM is not a flood observation, label, or reference mask",
            "keep DEM in terrain false-positive review lane only",
            timestamp,
        ),
    ]


def build_public_reference_manifest(
    include_sentinel_asia_products: bool = False,
    sentinel_asia_html: str | None = None,
    retrieved_at_utc: str | None = None,
) -> pd.DataFrame:
    """Build the public reference candidate manifest."""

    timestamp = retrieved_at_utc or utc_now_text()
    rows = default_public_reference_rows(timestamp)
    if include_sentinel_asia_products:
        html = sentinel_asia_html
        if html is None:
            html = fetch_text(SENTINEL_ASIA_2024_URL)
        rows.extend(
            sentinel_asia_product_rows(
                extract_sentinel_asia_product_links(html),
                retrieved_at_utc=timestamp,
            )
        )
    return pd.DataFrame(rows, columns=PUBLIC_REFERENCE_COLUMNS)


def write_public_reference_manifest(
    output_path: str | Path,
    include_sentinel_asia_products: bool = False,
    sentinel_asia_html: str | None = None,
    retrieved_at_utc: str | None = None,
) -> Path:
    """Write public source metadata rows to CSV."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise PublicReferenceInventoryError("Public reference manifest output must be CSV.")
    frame = build_public_reference_manifest(
        include_sentinel_asia_products=include_sentinel_asia_products,
        sentinel_asia_html=sentinel_asia_html,
        retrieved_at_utc=retrieved_at_utc,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    return target


def extract_sentinel_asia_product_links(
    html: str,
    base_url: str = SENTINEL_ASIA_2024_URL,
) -> list[PublicLink]:
    """Extract public product links from the Sentinel Asia Northern Thailand page."""

    parser = _AnchorParser()
    parser.feed(html)
    rows: list[PublicLink] = []
    seen: set[str] = set()
    for link in parser.links:
        url = urljoin(base_url, link.url)
        path = urlparse(url).path.lower()
        if "/eo/2024/article20240910th/" not in path:
            continue
        if not path.endswith((".jpg", ".jpeg", ".zip", ".kmz", ".kml", ".pdf")):
            continue
        if url in seen:
            continue
        seen.add(url)
        rows.append(PublicLink(text=link.text or Path(path).name, url=url))
    return rows


def sentinel_asia_product_rows(
    links: Iterable[PublicLink],
    retrieved_at_utc: str | None = None,
) -> list[dict[str, Any]]:
    """Convert extracted Sentinel Asia product links into manifest rows."""

    timestamp = retrieved_at_utc or utc_now_text()
    rows: list[dict[str, Any]] = []
    for link in links:
        asset_type = _asset_type(link.url)
        candidate_role = _sentinel_asia_candidate_role(link.url, asset_type)
        rows.append(
            _row(
                f"Sentinel Asia Northern Thailand 2024 product - {Path(urlparse(link.url).path).name}",
                "sentinel_asia_product",
                "Chiang Rai / Mae Sai 2024",
                link.url,
                asset_type,
                candidate_role,
                "public direct link from Sentinel Asia event page",
                "public_page_terms_need_product_level_review",
                _geometry_status_for_asset(asset_type),
                "unresolved_product_level",
                _validation_status_for_asset(asset_type),
                "not_cleared_for_ml_labels",
                "do not download into Git; inspect externally only if product terms allow",
                "metadata_csv_only_no_product_zip_or_image_assets",
                "event_product_link_inventory_only",
                "medium" if asset_type in {"shapefile_zip", "gis_zip"} else "low",
                "product-level license, geometry, and redistribution terms need review",
                "if selected, download outside Git, record checksum, inspect geometry/license, then update gates",
                timestamp,
            )
        )
    return rows


def write_sentinel_asia_product_links(
    output_path: str | Path,
    html: str | None = None,
    retrieved_at_utc: str | None = None,
) -> Path:
    """Write Sentinel Asia public product links to their own CSV."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise PublicReferenceInventoryError("Sentinel Asia product output must be CSV.")
    if html is None:
        html = fetch_text(SENTINEL_ASIA_2024_URL)
    frame = pd.DataFrame(
        sentinel_asia_product_rows(
            extract_sentinel_asia_product_links(html),
            retrieved_at_utc=retrieved_at_utc,
        ),
        columns=PUBLIC_REFERENCE_COLUMNS,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    return target


def fetch_text(url: str) -> str:
    """Fetch public HTML/text content for metadata extraction."""

    request = Request(url, headers={"User-Agent": "FloodGuard-public-metadata/0.1"})
    with urlopen(request, timeout=60) as response:  # noqa: S310 - public metadata URL
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _row(*values: Any) -> dict[str, Any]:
    return dict(zip(PUBLIC_REFERENCE_COLUMNS, values, strict=True))


def _asset_type(url: str) -> str:
    path = urlparse(url).path.lower()
    name = Path(path).name
    if name.endswith("-shp.zip") or "shp" in name and name.endswith(".zip"):
        return "shapefile_zip"
    if name.endswith(".zip"):
        return "gis_zip"
    if name.endswith((".jpg", ".jpeg")):
        return "map_or_quicklook_jpg"
    if name.endswith((".kml", ".kmz")):
        return "kml_kmz"
    if name.endswith(".pdf"):
        return "pdf_map_report"
    return "public_link"


def _sentinel_asia_candidate_role(url: str, asset_type: str) -> str:
    lower_url = url.lower()
    if asset_type in {"shapefile_zip", "gis_zip", "kml_kmz"}:
        if "flood" in lower_url or "water" in lower_url or "wbd" in lower_url:
            return "possible public flood geometry candidate"
        return "possible public GIS geometry candidate"
    if asset_type == "map_or_quicklook_jpg":
        return "public map or imagery quicklook evidence"
    return "public event evidence"


def _geometry_status_for_asset(asset_type: str) -> str:
    if asset_type in {"shapefile_zip", "gis_zip", "kml_kmz"}:
        return "possible_geometry_needs_download_outside_git_and_inspection"
    return "map_report_or_quicklook_no_machine_geometry"


def _validation_status_for_asset(asset_type: str) -> str:
    if asset_type in {"shapefile_zip", "gis_zip", "kml_kmz"}:
        return "possible_after_geometry_and_license_review"
    return "no_map_level_context_only"
