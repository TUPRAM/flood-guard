"""The delivery of the THEOS-2 scene of 17 September 2024: metadata read without a pixel, and the plan fixed before the look."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from floodguard import theos2_event_delivery as delivery

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "outputs" / "theos2_delivery" / "delivery_20240917_v1.json"
PLAN = ROOT / "docs" / "proposal_execution" / "theos2_17sep_recession_and_mud_plan_v1.md"

DIM = b"""<?xml version="1.0" encoding="UTF-8"?>
<Dimap_Document>
 <Dataset_Content>
  <SURFACE_AREA unit="square km">12.5</SURFACE_AREA>
  <CLOUD_COVERAGE>0.86</CLOUD_COVERAGE>
  <Dataset_Extent><EXTENT_TYPE>Bounding_Box</EXTENT_TYPE>
   <Vertex><LON>99.0</LON><LAT>20.0</LAT></Vertex><Vertex><LON>99.1</LON><LAT>20.0</LAT></Vertex><Vertex><LON>99.1</LON><LAT>20.1</LAT></Vertex>
  </Dataset_Extent>
  <Dataset_Extent><EXTENT_TYPE>Bounding_Polygon</EXTENT_TYPE>
   <Vertex><LON>99.90</LON><LAT>20.40</LAT></Vertex><Vertex><LON>99.92</LON><LAT>20.40</LAT></Vertex>
   <Vertex><LON>99.92</LON><LAT>20.42</LAT></Vertex><Vertex><LON>99.90</LON><LAT>20.42</LAT></Vertex>
  </Dataset_Extent>
 </Dataset_Content>
 <Product_Information><Delivery_Identification><PRODUCTION_DATE>2026-10-14T04:59:16Z</PRODUCTION_DATE>
  <Order_Identification><COMMERCIAL_REFERENCE>AWG_20261014_bc7a15</COMMERCIAL_REFERENCE></Order_Identification>
 </Delivery_Identification></Product_Information>
 <Coordinate_Reference_System><Projected_CRS><PROJECTED_CRS_CODE>urn:ogc:def:crs:EPSG::32647</PROJECTED_CRS_CODE></Projected_CRS></Coordinate_Reference_System>
 <Geoposition><Geoposition_Insert><ULXMAP>587911.1</ULXMAP><ULYMAP>2262392.0</ULYMAP><XDIM>0.5</XDIM><YDIM>-0.5</YDIM></Geoposition_Insert></Geoposition>
 <Processing_Information><Product_Settings><PROCESSING_LEVEL>ORTHO</PROCESSING_LEVEL><SPECTRAL_PROCESSING>PMS</SPECTRAL_PROCESSING>
  <Radiometric_Settings><RADIOMETRIC_PROCESSING>BASIC</RADIOMETRIC_PROCESSING></Radiometric_Settings></Product_Settings></Processing_Information>
 <Raster_Data><Raster_Dimensions><NROWS>8</NROWS><NCOLS>12</NCOLS><NBANDS>4</NBANDS></Raster_Dimensions>
  <Raster_Display><Band_Display_Order><RED_CHANNEL>B2</RED_CHANNEL><GREEN_CHANNEL>B1</GREEN_CHANNEL><BLUE_CHANNEL>B0</BLUE_CHANNEL><ALPHA_CHANNEL>B3</ALPHA_CHANNEL></Band_Display_Order></Raster_Display>
 </Raster_Data>
 <Radiometric_Data><Radiometric_Calibration><Instrument_Calibration><Band_Measurement_List>
  <Band_Spectral_Range><BAND_ID>B2</BAND_ID><MIN>0.641</MIN><MAX>0.707</MAX></Band_Spectral_Range>
  <Band_Radiance><BAND_ID>B2</BAND_ID><GAIN>3.0</GAIN><BIAS>3.0</BIAS></Band_Radiance>
 </Band_Measurement_List></Instrument_Calibration></Radiometric_Calibration></Radiometric_Data>
 <Geometric_Data><Use_Area><Located_Geometric_Values><TIME>2024-09-17T03:54:23Z</TIME>
  <Acquisition_Angles><VIEWING_ANGLE>28.37</VIEWING_ANGLE><INCIDENCE_ANGLE>31.34</INCIDENCE_ANGLE></Acquisition_Angles>
  <Solar_Incidences><SUN_AZIMUTH>129.4</SUN_AZIMUTH><SUN_ELEVATION>63.4</SUN_ELEVATION></Solar_Incidences>
 </Located_Geometric_Values></Use_Area>
 <Source_Identification><Strip_Source><IMAGING_DATE>2024-09-17</IMAGING_DATE><IMAGING_TIME>03:54:20</IMAGING_TIME></Strip_Source></Source_Identification>
 </Geometric_Data>
</Dimap_Document>
"""


def header(west: float, north: float, width: int = 8, height: int = 8, colours: tuple[str, ...] = delivery.FILE_BAND_COLOURS) -> dict:
    return {"crs_epsg": 32647, "width": width, "height": height, "count": 4, "dtype": "uint16",
            "transform": [0.5, 0.0, west, 0.0, -0.5, north], "band_colours": list(colours)}


def product(order: str, name: str, west: float = 0.0, north: float = 0.0, **changes) -> dict:
    metadata = delivery.parse_dim(DIM)
    metadata.update(changes)
    return {"order": order, "product": name, "metadata": metadata, "header": header(west, north)}


def test_the_dim_metadata_gives_time_cloud_footprint_bands_and_angles() -> None:
    metadata = delivery.parse_dim(DIM)
    assert metadata["acquired_utc"] == "2024-09-17T03:54:20Z" and metadata["cloud_coverage_percent_stated"] == 0.86
    assert metadata["footprint_lonlat"][0] == [99.90, 20.40] and len(metadata["footprint_lonlat"]) == 4, "the polygon, not the box"
    assert metadata["epsg"] == 32647 and metadata["radiometric_processing"] == "BASIC" and metadata["rows"] == 8
    assert metadata["display_bands"]["red"] == "B2" and metadata["radiance_gain_bias"]["B2"] == {"gain": 3.0, "bias": 3.0}
    assert metadata["angles_deg"] == {"viewing_angle": 28.37, "incidence_angle": 31.34, "sun_azimuth": 129.4, "sun_elevation": 63.4}
    with pytest.raises(delivery.DeliveryError):
        delivery.parse_dim(DIM.replace(b"Bounding_Polygon", b"Other"))


def test_only_the_two_orders_and_safe_member_names_are_taken() -> None:
    assert delivery.order_of("THEOS-2_Hackathon/AWG_20261014_417d92/T2_PRO_x.zip") == "AWG_20261014_417d92"
    with pytest.raises(delivery.DeliveryError):
        delivery.order_of("THEOS-2_Hackathon/AWG_other/T2_PRO_x.zip")
    delivery.check_member_names(["VOL_T2V/IMG/IMG_T2V.TIF", "T2_LIST.XML"])
    for unsafe in ("../outside.tif", "/etc/x", "C:/x.tif", "VOL/../../x"):
        with pytest.raises(delivery.DeliveryError):
            delivery.check_member_names([unsafe])


def test_the_products_must_be_one_scene_with_the_band_order_the_code_reads() -> None:
    good = [product(delivery.ORDERS[0], "a"), product(delivery.ORDERS[1], "b")]
    delivery.check_one_scene(good)
    with pytest.raises(delivery.DeliveryError, match="one time"):
        delivery.check_one_scene([product(delivery.ORDERS[0], "a"), product(delivery.ORDERS[1], "b", acquired_utc="2024-09-21T03:00:00Z")])
    with pytest.raises(delivery.DeliveryError, match="order is missing"):
        delivery.check_one_scene([product(delivery.ORDERS[0], "a")])
    swapped = [product(delivery.ORDERS[0], "a"), product(delivery.ORDERS[1], "b")]
    swapped[1]["header"]["band_colours"] = ["BLUE", "GREEN", "RED", "NIR"]
    with pytest.raises(delivery.DeliveryError, match="another order"):
        delivery.check_one_scene(swapped)


def test_the_products_share_one_2m_grid_and_its_union_is_given() -> None:
    grid = delivery.common_grid([header(100.0, 1000.0), header(104.0, 998.0, width=16)])
    assert (grid["west"], grid["north"], grid["columns"], grid["rows"]) == (100.0, 1000.0, 6, 3)
    with pytest.raises(delivery.DeliveryError, match="2 m grid"):
        delivery.common_grid([header(100.0, 1000.0), header(101.0, 1000.0)])


def test_coverage_counts_the_share_of_each_tambon_and_the_road_centres_inside() -> None:
    square = {"type": "Polygon", "coordinates": [[[99.90, 20.40], [99.92, 20.40], [99.92, 20.42], [99.90, 20.42], [99.90, 20.40]]]}
    east = {"type": "Polygon", "coordinates": [[[99.92, 20.40], [99.94, 20.40], [99.94, 20.42], [99.92, 20.42], [99.92, 20.40]]]}
    context = {"tambons": [{"id": "T1", "name": "Inside", "geometry": square}, {"id": "T2", "name": "Outside", "geometry": east}],
               "roads": [{"order_in_the_road_sheet": 1, "centre_lonlat": [99.91, 20.41]}, {"order_in_the_road_sheet": 2, "centre_lonlat": [99.93, 20.41]}]}
    result = delivery.coverage([product(delivery.ORDERS[0], "a")], context)
    everything = result["all_products"]
    assert [item["id"] for item in everything["tambons"]] == ["T1"] and everything["tambons"][0]["share_covered"] == pytest.approx(1.0, abs=0.001)
    assert everything["roads_of_the_road_sheet_with_their_centre_inside"] == [1]
    assert result["district_km2"] == pytest.approx(2 * everything["footprint_km2"], rel=0.01)


def test_the_delivery_record_read_no_pixel_and_binds_every_file() -> None:
    if not RECORD.exists():
        pytest.skip("the delivery has not been recorded")
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    assert record["pixels_read"] is False and record["image_looked_at"] is False
    assert record["official_warning"] is False and record["can_feed_decision_layer"] is False
    assert record["source_timestamp"] == "THEOS-2 2024-09-17T03:54:20Z" and record["confidence_class"] and record["assumptions"] and record["limits"]
    assert {item["order"] for item in record["products"]} == set(delivery.ORDERS) and len(record["products"]) == 4
    for item in record["products"]:
        assert len(item["image"]["sha256"]) == 64 and item["header"]["band_colours"] == list(delivery.FILE_BAND_COLOURS)
    assert record["coverage"]["by_order"]["AWG_20261014_417d92"]["roads_of_the_road_sheet_with_their_centre_inside"][0] == 1
    assert "GISTDA" in record["licence"] and "outside Git" in record["licence"]


def test_the_plan_fixes_the_tests_the_bars_and_the_order_before_the_look() -> None:
    plan = PLAN.read_text(encoding="utf-8")
    assert "Nobody has looked at" in plan and "delivery_20240917_v1.json" in plan
    for fixed in ("**0.25 km² or more**", "0.02 or more", "**0.60 or", "seed 20261019", "seed 20261020",
                  "No mud never means the road stayed dry or passable", "not independent", "Theil-Sen"):
        assert fixed in plan, fixed
    for candidate in ("`mud_s0`", "`mud_s1`", "`mud_s2`"):
        assert candidate in plan
    order = plan[plan.index("## 5. Order of the commits"):]
    assert order.index("This plan") < order.index("The reference of the frozen check") < order.index("Question 3") < order.index("The development points") < order.index("The test points") < order.index("Section 4.5")


def test_the_reference_of_the_scene_comes_after_this_plan() -> None:
    reference = ROOT / "outputs" / "theos2_study_event_check" / "reference_20240917_v1.json"
    if not reference.exists():
        pytest.skip("the reference of the scene has not been built")
    record = json.loads(reference.read_text(encoding="utf-8"))
    assert record["delivery"]["sha256"] == hashlib.sha256(RECORD.read_bytes()).hexdigest()
