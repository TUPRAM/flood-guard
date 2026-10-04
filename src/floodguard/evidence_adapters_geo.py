"""Optional geospatial evidence checks; outputs are context, never event truth."""

from __future__ import annotations

from pathlib import Path

from floodguard.evidence_adapters import _hash, _json, _read_json


def normalize_geospatial(root: Path, out: Path, aois: dict) -> dict:
    """Compute actual flood coverage, projected river lengths and terrain QA."""
    try:
        import numpy as np
        from pyproj import Transformer
        from shapely.geometry import mapping, shape
        from shapely.ops import transform, unary_union
    except ImportError as error:
        return {
            key: {
                "status": "unavailable_optional_dependency",
                "reason": str(error),
                "outputs": [],
            }
            for key in ("flood_reference", "terrain", "rivers")
        }
    project = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform

    def geometry(value: dict):
        if value.get("type") == "FeatureCollection":
            return unary_union([shape(f["geometry"]) for f in value["features"]])
        return shape(value.get("geometry", value))

    aoi_geometry = {key: geometry(value) for key, value in aois.items()}
    area = {
        key: transform(project, value).area / 1e6 for key, value in aoi_geometry.items()
    }
    flood_manifest = _read_json(root / "flood_reference" / "manifest.json", {})
    flood_layers, flood_aoi, flood_outputs, footprints = [], {}, [], {}
    for entry in flood_manifest.get("clips", []):
        path = root / "flood_reference" / Path(entry["path"]).name
        # Windows manifest paths must remain portable when read on other hosts.
        if not path.exists():
            path = (
                root
                / "flood_reference"
                / entry["path"].replace("\\", "/").rsplit("/", 1)[-1]
            )
        digest = _hash(path)
        if entry.get("sha256") and entry["sha256"] != digest:
            raise ValueError(f"Source hash mismatch: {path.name}")
        doc = _read_json(path)
        aoi = entry["aoi"]
        layer = entry["layer"]
        category = (
            "analysis_footprint"
            if "AnalysisExtent" in layer
            else "accumulated_extent"
            if "AccumulatedFlood" in layer
            else "single_date_extent"
        )
        geom = geometry(doc)
        valid = geom.is_valid
        clipped = (
            geom.intersection(aoi_geometry[aoi])
            if aoi in aoi_geometry and valid
            else geom
        )
        area_km2 = transform(project, clipped).area / 1e6 if valid else None
        layer_info = {
            "aoi_id": aoi,
            "layer": layer,
            "category": category,
            "source_sha256": digest,
            "source_timestamp": "2024-10-22"
            if category == "single_date_extent"
            else "2024-08-01/2024-10-22",
            "role": "observed_later_date"
            if category == "single_date_extent"
            else "coverage_mask"
            if category == "analysis_footprint"
            else "historical_context",
            "confidence": "source_unvalidated",
            "valid_geometry": valid,
            "empty": geom.is_empty,
            "area_km2": area_km2,
            "aoi_area_km2": area.get(aoi),
            "event_reference_accepted": False,
            "date_conflict": category == "accumulated_extent",
            "per_patch_dates_available": False,
            "layer_name_end_date": "2024-10-12"
            if category == "accumulated_extent"
            else "2024-10-22",
            "product_description_end_date": "2024-10-22",
            "assumptions": "analysis_footprint_is_observation_coverage_not_dry_land;no_September_only_extraction;source_area_fields_not_clip_areas",
        }
        filename = f"flood_{aoi}_{category}.geojson"
        properties = {**layer_info, "source_path": path.relative_to(root).as_posix()}
        _json(
            out / filename,
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": properties,
                        "geometry": mapping(clipped),
                    }
                ],
                "metadata": layer_info,
            },
        )
        flood_outputs.append(filename)
        layer_info["output"] = filename
        flood_layers.append(layer_info)
        flood_aoi.setdefault(aoi, {})[category] = layer_info
        if category == "analysis_footprint" and valid:
            footprints[aoi] = clipped
    for aoi, aoi_geom in aoi_geometry.items():
        footprint = footprints.get(aoi)
        unknown = aoi_geom if footprint is None else aoi_geom.difference(footprint)
        unknown_area = transform(project, unknown).area / 1e6
        observed_area = (
            0.0 if footprint is None else transform(project, footprint).area / 1e6
        )
        summary = flood_aoi.setdefault(aoi, {})
        summary.update(
            {
                "analysis_coverage_fraction": observed_area / area[aoi]
                if area[aoi]
                else None,
                "unobserved_area_km2": unknown_area,
                "event_reference_accepted": False,
                "missing_reference": footprint is None,
            }
        )
        filename = f"flood_{aoi}_unobserved.geojson"
        _json(
            out / filename,
            {
                "type": "FeatureCollection",
                "features": []
                if unknown.is_empty
                else [
                    {
                        "type": "Feature",
                        "geometry": mapping(unknown),
                        "properties": {
                            "aoi_id": aoi,
                            "role": "unobserved_not_dry",
                            "area_km2": unknown_area,
                            "confidence": "coverage_mask",
                            "source_timestamp": "2024-08-01/2024-10-22"
                            if footprint is not None
                            else None,
                        },
                    }
                ],
            },
        )
        summary["unobserved_output"] = filename
        flood_outputs.append(filename)
    flood = {
        "status": "normalized" if flood_layers else "unavailable",
        "layers": flood_layers,
        "aois": flood_aoi,
        "date_conflicts": sum(x["date_conflict"] for x in flood_layers),
        "source_date_conflicts": 1
        if any(x["date_conflict"] for x in flood_layers)
        else 0,
        "limitations": flood_manifest.get("limitations", []),
        "outputs": flood_outputs,
    }

    river_files, river_outputs = [], []
    for path in sorted((root / "terrain_drainage").glob("*_hydrorivers.geojson")):
        aoi = path.name.removesuffix("_hydrorivers.geojson")
        doc = _read_json(path)
        digest = _hash(path)
        features = []
        lengths, invalid = [], 0
        source_ids = {
            str(f.get("properties", {}).get("HYRIV_ID")) for f in doc["features"]
        }
        external_links = 0
        for index, feature in enumerate(doc["features"]):
            geom = shape(feature["geometry"])
            props = feature.get("properties", {})
            valid = geom.is_valid and not geom.is_empty
            invalid += int(not valid)
            length = transform(project, geom).length / 1000 if valid else None
            if length is not None:
                lengths.append(length)
            next_id = str(props.get("NEXT_DOWN", "0"))
            outside_link = next_id not in source_ids and next_id not in {
                "0",
                "None",
                "0.0",
            }
            external_links += int(outside_link)
            new_props = {
                **props,
                "record_id": f"hydrorivers:{digest}:{index}",
                "source_sha256": digest,
                "aoi_id": aoi,
                "clipped_length_km": length,
                "next_down_outside_clip": outside_link,
                "role": "generalized_drainage_context",
                "source_timestamp": "HydroRIVERS v1 static",
                "confidence": "generalized_historical_network",
                "assumptions": "original_reach_attributes_retained;clipped_length_recomputed;not_complete_local_drainage",
            }
            features.append({**feature, "properties": new_props})
        filename = f"rivers_{aoi}.geojson"
        _json(
            out / filename,
            {
                "type": "FeatureCollection",
                "features": features,
                "metadata": {
                    "analysis_crs": "EPSG:32647",
                    "role": "historical_context",
                },
            },
        )
        river_outputs.append(filename)
        river_files.append(
            {
                "aoi_id": aoi,
                "source_sha256": digest,
                "features": len(features),
                "invalid_features": invalid,
                "clipped_length_km": sum(lengths),
                "next_down_outside_clip": external_links,
                "output": filename,
            }
        )
    rivers = {
        "status": "normalized" if river_files else "unavailable",
        "layers": river_files,
        "limitations": [
            "Generalized historical rivers; local canals, culverts and urban drains incomplete",
            "External downstream links are expected at clip boundaries",
        ],
        "outputs": river_outputs,
    }

    terrain_rows, terrain_outputs = [], []
    try:
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.warp import calculate_default_transform, reproject
    except ImportError as error:
        return {
            "flood_reference": flood,
            "rivers": rivers,
            "terrain": {
                "status": "unavailable_optional_dependency",
                "reason": str(error),
                "outputs": [],
            },
        }
    for path in sorted((root / "terrain_drainage").glob("*_copdem_glo30.tif")):
        aoi = path.name.removesuffix("_copdem_glo30.tif")
        with rasterio.open(path) as src:
            source = src.read(1, masked=True)
            valid = ~np.ma.getmaskarray(source) & np.isfinite(source.filled(np.nan))
            values = np.asarray(source)[valid]
            if src.crs is None:
                terrain_rows.append(
                    {
                        "aoi_id": aoi,
                        "status": "missing_crs",
                        "source_sha256": _hash(path),
                    }
                )
                continue
            transform_out, width, height = calculate_default_transform(
                src.crs, "EPSG:32647", src.width, src.height, *src.bounds, resolution=30
            )
            projected = np.full((height, width), np.nan, dtype="float32")
            reproject(
                source=source.filled(np.nan),
                destination=projected,
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=np.nan,
                dst_transform=transform_out,
                dst_crs="EPSG:32647",
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
            )
            dy, dx = np.gradient(projected, abs(transform_out.e), abs(transform_out.a))
            slope = np.degrees(np.arctan(np.hypot(dx, dy))).astype("float32")
            # Negative values are flagged for review, never removed or made zero.
            qa = np.zeros(source.shape, dtype="uint8")
            qa[~valid] = 1
            qa[valid & (source.filled(np.nan) < 0)] = 2
            profile = src.profile.copy()
            profile.update(count=1, dtype="uint8", nodata=255, compress="deflate")
            qa_name = f"terrain_{aoi}_review_mask.tif"
            with rasterio.open(out / qa_name, "w", **profile) as dst:
                dst.write(qa, 1)
                dst.update_tags(
                    classes="0=unflagged_context;1=invalid;2=negative_review_not_automatic_error",
                    source_sha256=_hash(path),
                    source_timestamp="2021_release_historical_DSM",
                )
            slope_name = f"terrain_{aoi}_slope_degrees.tif"
            with rasterio.open(
                out / slope_name,
                "w",
                driver="GTiff",
                width=width,
                height=height,
                count=1,
                dtype="float32",
                crs="EPSG:32647",
                transform=transform_out,
                nodata=np.nan,
                compress="deflate",
            ) as dst:
                dst.write(slope, 1)
                dst.update_tags(
                    role="DSM_context_not_hydraulic_model",
                    source_sha256=_hash(path),
                    resampling="bilinear_30m",
                    source_timestamp="2021_release_historical_DSM",
                    attribution=src.tags().get(
                        "attribution", "See original Copernicus source attribution"
                    ),
                    liability=src.tags().get(
                        "liability", "See original source license"
                    ),
                )
            slope_values = slope[np.isfinite(slope)]
            terrain_rows.append(
                {
                    "aoi_id": aoi,
                    "status": "context_qa_complete",
                    "source_sha256": _hash(path),
                    "source_crs": str(src.crs),
                    "source_shape": list(source.shape),
                    "valid_pixels": int(valid.sum()),
                    "invalid_pixels": int((~valid).sum()),
                    "negative_pixels": int((qa == 2).sum()),
                    "min_m": float(values.min()) if values.size else None,
                    "max_m": float(values.max()) if values.size else None,
                    "elevation_percentiles_m": [
                        float(x) for x in np.percentile(values, [1, 50, 99])
                    ]
                    if values.size
                    else [],
                    "slope_p95_degrees": float(np.percentile(slope_values, 95))
                    if slope_values.size
                    else None,
                    "analysis_crs": "EPSG:32647",
                    "slope_resolution_m": 30,
                    "resampling": "bilinear",
                    "source_timestamp": "2021_release_historical_DSM",
                    "event_observation_interval": None,
                    "confidence": "surface_model_context",
                    "slope_output": slope_name,
                    "review_mask_output": qa_name,
                    "assumptions": "buildings_and_vegetation_present;negative_values_preserved;not_flood_depth;not_urban_drainage_model",
                }
            )
            terrain_outputs.extend([qa_name, slope_name])
    _json(
        out / "terrain_qc.json",
        {
            "rasters": terrain_rows,
            "negative_values": "retained_pending_review",
            "analysis_crs": "EPSG:32647",
        },
    )
    terrain_outputs.append("terrain_qc.json")
    return {
        "flood_reference": flood,
        "rivers": rivers,
        "terrain": {
            "status": "normalized" if terrain_rows else "unavailable",
            "rasters": terrain_rows,
            "limitations": [
                "Surface model includes buildings and vegetation",
                "Static historical elevation, not event interval",
                "Negative elevations require review, not automatic correction",
            ],
            "outputs": terrain_outputs,
        },
    }
