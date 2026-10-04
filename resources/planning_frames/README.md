# resources/planning_frames

Planning frames of the planning overlay (restructuring plan v2, section 3.1). New frames live here, not in `resources/aoi/`, so `load_aois` still returns exactly six AOIs.

On 3 October 2026 this folder holds the frame of case SE2 and the units of case SE2-blind, built by the AI coding agent from the rules the owners adopted in decision log R12 (owner choice 15 of `docs/proposal_execution/planning_protocol_v1b_owner_choices.md`, as recommended). The sheet had asked Rachmania for the frame file; with the rule decided, the agent built it from the rule. **Rachmania reviews the frame, the routing geometry, the hospital list and the district office lookup.**

Nothing here is a flood extent, an exposure, an access result, a score or a class. Every file carries a source timestamp, a confidence class (`low`), its assumptions, `official_warning: false` and `operational_status: non_operational`; in a GeoJSON file they are in each feature's properties.

| File | What it is | Rule |
|---|---|---|
| `pf-07_mueang_chiang_rai.geojson` | Planning frame pf-07: the 16 COD-AB `tha_admin3` units of Mueang Chiang Rai district (TH5701), one feature each, geometry copied unchanged from COD-AB | Owner choice 15(a), option A |
| `pf-07_mueang_chiang_rai_routing.geojson` | SE2 routing geometry: the union of the 16 units buffered by 3 km in EPSG:32647 and clipped to Thailand (COD-AB `tha_admin0`); about 2,422 km² | Owner choice 15(b), as recommended |
| `planning_frames_v1_receipt.json` | The build receipt: the hashes of every input and output, the SE2 hospital list (every OSM hospital inside the routing geometry: 17 objects, 15 distinct named), the district office lookup for Phan and the SE2-blind unit list | Owner choices 15(b) and 15(c), option B |

The SE2-blind units are the tambon that holds the Phan district office and every Phan tambon that touches it. The office is OSM node 3840722494 (`office=administrative`, named as the district office in Thai), at 99.7405302 E, 19.5538862 N. It lies in TH570513 (Mueang Phan), which touches five Phan tambons: TH570504, TH570506, TH570508, TH570509 and TH570511.

The two GeoJSON files carry no run time, so a rebuild from the same inputs gives the same bytes. Their SHA-256 values are in protocol v1b (`corridor_polygon.se2_frame`) and in the receipt. To rebuild, or to check the committed files without writing:

```bash
python scripts/build_planning_frames.py \
    --boundaries <external data root>/open_context/hdx_cod_ab/tha_admin_boundaries.gdb.zip \
    --osm-pbf <external data root>/open_context/osm_geofabrik/thailand-latest.osm.pbf \
    --work-dir <a scratch folder outside Git> [--verify]
```

The rules are in `src/floodguard/planning_frames.py`; `tests/test_planning_frames.py` tests them on invented inputs and checks the committed files against the receipt and the protocol.
