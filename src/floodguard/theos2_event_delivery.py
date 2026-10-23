"""Metadata of the THEOS-2 scene of 17 September 2024 over Mae Sai, read without a pixel.

``scripts/build_theos2_event_delivery.py`` reads the files; the functions here are pure and tested on invented
metadata. Nothing here looks at the image.
"""

from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import Any, Iterable

ORDERS: tuple[str, ...] = ("AWG_20261014_bc7a15", "AWG_20261014_417d92")
EPSG: int = 32647
PIXEL_M: float = 0.5
GRID_M: float = 2.0
# The order of the bands in the image files, as the code of the THEOS-2 checks reads them.
FILE_BAND_COLOURS: tuple[str, ...] = ("RED", "GREEN", "BLUE", "NIR")


class DeliveryError(ValueError):
    """The delivery is not the one GISTDA described."""


def order_of(member: str) -> str:
    """The GISTDA order a member of the outer zip belongs to."""

    found = [order for order in ORDERS if order in PurePosixPath(member).parts]
    if len(found) != 1:
        raise DeliveryError(f"{member} belongs to no known order")
    return found[0]


def check_member_names(names: Iterable[str]) -> None:
    """Refuse a member that would land outside the product folder."""

    for name in names:
        path = PurePosixPath(name.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", name):
            raise DeliveryError(f"unsafe member name in the delivery: {name}")


def single(paths: Iterable[Any], what: str) -> Any:
    """The one path of ``paths``; a product with none or several is refused."""

    found = sorted(paths)
    if len(found) != 1:
        raise DeliveryError(f"expected one {what}, found {len(found)}")
    return found[0]


# ---------------------------------------------------------------------------
# The metadata of one product
# ---------------------------------------------------------------------------


def _text(root: Any, path: str) -> str:
    found = root.find(path)
    if found is None or found.text is None:
        raise DeliveryError(f"the DIM metadata has no {path}")
    return found.text.strip()


def parse_dim(xml: bytes) -> dict[str, Any]:
    """The facts of a DIMAP ``DIM_*.XML`` this work uses: time, cloud, footprint, grid, bands and angles."""

    import xml.etree.ElementTree as ElementTree

    root = ElementTree.fromstring(xml)
    polygon = None
    for extent in root.iter("Dataset_Extent"):
        if (extent.findtext("EXTENT_TYPE") or "").strip() == "Bounding_Polygon":
            polygon = [[float(_text(vertex, "LON")), float(_text(vertex, "LAT"))] for vertex in extent.findall("Vertex")]
    if not polygon or len(polygon) < 3:
        raise DeliveryError("the DIM metadata has no bounding polygon")
    display = root.find(".//Band_Display_Order")
    angles = root.find(".//Located_Geometric_Values")
    return {
        "acquired_utc": f"{_text(root, './/IMAGING_DATE')}T{_text(root, './/IMAGING_TIME')}Z",
        "cloud_coverage_percent_stated": round(float(_text(root, ".//CLOUD_COVERAGE")), 3),
        "surface_area_km2_stated": round(float(_text(root, ".//SURFACE_AREA")), 3),
        "commercial_reference": _text(root, ".//COMMERCIAL_REFERENCE"),
        "production_date_utc": _text(root, ".//PRODUCTION_DATE"),
        "processing_level": _text(root, ".//PROCESSING_LEVEL"),
        "spectral_processing": _text(root, ".//SPECTRAL_PROCESSING"),
        "radiometric_processing": _text(root, ".//RADIOMETRIC_PROCESSING"),
        "epsg": int(_text(root, ".//PROJECTED_CRS_CODE").rsplit(":", 1)[-1]),
        "upper_left_m_stated": [float(_text(root, ".//ULXMAP")), float(_text(root, ".//ULYMAP"))],
        "pixel_m": [float(_text(root, ".//XDIM")), float(_text(root, ".//YDIM"))],
        "rows": int(_text(root, ".//NROWS")), "columns": int(_text(root, ".//NCOLS")), "bands": int(_text(root, ".//NBANDS")),
        "display_bands": {} if display is None else {
            colour: (display.findtext(f"{colour.upper()}_CHANNEL") or "").strip() for colour in ("red", "green", "blue", "alpha")},
        "spectral_range_um": {_text(band, "BAND_ID"): [float(_text(band, "MIN")), float(_text(band, "MAX"))]
                              for band in root.iter("Band_Spectral_Range")},
        "radiance_gain_bias": {_text(band, "BAND_ID"): {"gain": float(_text(band, "GAIN")), "bias": float(_text(band, "BIAS"))}
                               for band in root.iter("Band_Radiance")},
        "angles_deg": {} if angles is None else {
            name.lower(): round(float(angles.findtext(f".//{name}")), 3)
            for name in ("VIEWING_ANGLE", "INCIDENCE_ANGLE", "SUN_AZIMUTH", "SUN_ELEVATION") if angles.findtext(f".//{name}")},
        "footprint_lonlat": polygon,
    }


def check_one_scene(products: list[dict[str, Any]]) -> None:
    """All products are cuts of the one ortho scene the plan names, with the band order the code reads."""

    if not products:
        raise DeliveryError("no product")
    times = {product["metadata"]["acquired_utc"] for product in products}
    if len(times) != 1:
        raise DeliveryError(f"the products were not taken at one time: {sorted(times)}")
    if {product["order"] for product in products} != set(ORDERS):
        raise DeliveryError("a GISTDA order is missing")
    for product in products:
        metadata, header = product["metadata"], product["header"]
        if metadata["epsg"] != EPSG or header["crs_epsg"] != EPSG:
            raise DeliveryError(f"{product['product']} is not in EPSG:{EPSG}")
        if (header["transform"][0], -header["transform"][4]) != (PIXEL_M, PIXEL_M) or header["count"] != 4 or header["dtype"] != "uint16":
            raise DeliveryError(f"{product['product']} is not a four-band 16-bit raster of {PIXEL_M} m")
        if tuple(header.get("band_colours", ())) != FILE_BAND_COLOURS:
            raise DeliveryError(f"{product['product']} holds its bands in another order: {header.get('band_colours')}")
        if (metadata["processing_level"], metadata["spectral_processing"]) != ("ORTHO", "PMS"):
            raise DeliveryError(f"{product['product']} is not an ORTHO PMS product")


def common_grid(headers: list[dict[str, Any]]) -> dict[str, Any]:
    """The 2 m grid all products share: their union, and a refusal if one is off the grid of another.

    ``transform`` is the affine of a header in rasterio order (a, b, c, d, e, f).
    """

    wests = [header["transform"][2] for header in headers]
    norths = [header["transform"][5] for header in headers]
    for west, north in zip(wests, norths):
        if (west - wests[0]) % GRID_M or (north - norths[0]) % GRID_M:
            raise DeliveryError("the products do not lie on one 2 m grid")
    east = max(header["transform"][2] + header["width"] * PIXEL_M for header in headers)
    south = min(header["transform"][5] - header["height"] * PIXEL_M for header in headers)
    west, north = min(wests), max(norths)
    return {"epsg": EPSG, "cell_m": GRID_M, "west": west, "north": north,
            "columns": int(-(-(east - west) // GRID_M)), "rows": int(-(-(north - south) // GRID_M)),
            "overlap_rule": "Every product's upper-left corner lies on this grid; where products overlap, the first in the order of its product name is read."}


# ---------------------------------------------------------------------------
# What the footprints cover
# ---------------------------------------------------------------------------


def coverage_context(root: Any) -> dict[str, Any]:
    """The tambons of the replay and the eight roads of the Ko Chang road sheet, from files in the repository."""

    import json

    tambons = json.loads((root / "apps/web/public/studies/mae-sai-2024-timeline/r5/tambons.geojson").read_text(encoding="utf-8"))
    sheet = json.loads((root / "outputs/ko_chang_road_check/ko_chang_roads_se1_v1.json").read_text(encoding="utf-8"))
    roads = [{"order_in_the_road_sheet": step["step"], "osm_way_id": str(step["osm_way_id"]),
              "centre_lonlat": step["centre_of_the_closed_pieces_lonlat"], "tambon": step["centre_lies_in_unit"]}
             for step in sheet["what_if_roads_stay_passable_one_after_another"]["steps"]]
    return {"tambons": [{"id": feature["properties"]["id"], "name": feature["properties"]["en"], "geometry": feature["geometry"]}
                        for feature in tambons["features"]], "roads": roads}


def coverage(products: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any]:
    """Which share of each tambon and of the district the stated footprints cover, and which road centres lie inside."""

    from pyproj import Transformer
    from shapely.geometry import Point, Polygon, shape
    from shapely.ops import transform, unary_union

    to_metres = Transformer.from_crs(4326, EPSG, always_xy=True).transform
    footprints: dict[str, list[Any]] = {}
    for product in products:
        footprints.setdefault(product["order"], []).append(transform(to_metres, Polygon(product["metadata"]["footprint_lonlat"]).buffer(0)))
    by_order = {order: unary_union(parts) for order, parts in sorted(footprints.items())}
    tambons = [(item, transform(to_metres, shape(item["geometry"]).buffer(0))) for item in context["tambons"]]
    district = unary_union([geometry for _item, geometry in tambons])

    def shares(footprint: Any) -> dict[str, Any]:
        return {
            "footprint_km2": round(footprint.area / 1e6, 2),
            "district_km2_covered": round(footprint.intersection(district).area / 1e6, 2),
            "tambons": [{"id": item["id"], "name": item["name"], "km2_covered": round(footprint.intersection(geometry).area / 1e6, 2),
                         "share_covered": round(footprint.intersection(geometry).area / geometry.area, 3)}
                        for item, geometry in tambons if footprint.intersection(geometry).area > 0],
            "roads_of_the_road_sheet_with_their_centre_inside": [
                road["order_in_the_road_sheet"] for road in context["roads"] if footprint.contains(Point(to_metres(*road["centre_lonlat"])))],
        }

    return {"district_km2": round(district.area / 1e6, 2), "all_products": shares(unary_union(list(by_order.values()))),
            "by_order": {order: shares(footprint) for order, footprint in by_order.items()},
            "basis": "Footprints as the DIM metadata states them; valid pixels and cloud are not read here."}
