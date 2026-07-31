# Mae Sai Real-Data Validation Summary

Report status: Weak-reference candidate metrics are integrity-bound; official validation remains blocked.

Strict use statement: Cross-border calibration metrics against a manually digitized weak-reference mask; not Mae Sai Thailand ADM3 validation. Non-operational. Not official validation. Not field validated.

## Data Status

- Official processing allowed: false
- Official blocking reason: Sentinel Asia MBRSC Mae Sai public shapefile candidate: processing_allowed is not true, license_status is not confirmed, source_license_status is not confirmed, reference_mask_status is not confirmed; CDSE Sentinel-1 Mae Sai pre-event original SAFE: processing_allowed is not true, reference_mask_status is not confirmed; CDSE Sentinel-1 Mae Sai post-event original SAFE: processing_allowed is not true, reference_mask_status is not confirmed
- Official IoU, F1/Dice, precision, recall, and area error remain pending.
- Weak-reference candidate metrics available: true
- Weak-reference source integrity verified: true
- Source imagery and manual GeoPackage files stay outside Git; this report stores only derived metadata and metrics.
- Real-data ML remains blocked because the weak-reference mask is not an official or cleared label source.

## Sentinel-1 Product IDs

- Pre-event Sentinel-1 product id: `aaaef3af-fa49-4115-bf0f-f54175e7aedf`
- Post-event Sentinel-1 product id: `5251b74b-0bbd-4365-9eb4-fa33292e175a`
- Post-event source timestamp: 2024-09-15T23:16:01Z
- Pre-event source name: CDSE Sentinel-1 Mae Sai pre-event original SAFE
- Post-event source name: CDSE Sentinel-1 Mae Sai post-event original SAFE
- Source integrity recorded by run manifest: verified_sha256_before_raster_read

## Integrity And Spatial Scope

- Source integrity status: verified_sha256_before_raster_read
- Pre-event SHA-256: `42433d6cfb55118abe21e6faabef56343cefc9f28817cd31eb9386d32f56543d`
- Post-event SHA-256: `ff4a604f57c9eb88421904659c7201d07b54b35a3bff6f3447ee548c40f6755b`
- Reference SHA-256: `d64e8441dd08ce42323ae283398e5dc1a7225282caa040d0f5981b3a9c8637ce`
- Manual-mask attribute integrity: valid
- Manual-mask attribute blockers: none recorded
- Manual-mask spatial relation: cross_border_calibration_only
- Manual-mask in-study-area overlap: False
- Manual-mask distance to study area: 5.965378 km
- Thailand ADM3 candidate overlap: false.
- Cross-border status: nearby cross-border calibration evidence only.
- Interpretation: these weak-reference metrics do not validate flood extent inside Mae Sai Thailand ADM3 reporting polygons.
- Context-manifest assumptions: Manual weak-reference bbox is north of the COD-AB Thailand boundary and is retained only as nearby cross-border calibration evidence.

## Manual Reference Mask Metadata

- Reference id: `MS-MANUAL-CROSSBORDER-001`
- Study area: Chiang Rai / Mae Sai 2024
- Confidence: low
- Source basis: Sentinel-1 pre/post visual interpretation; OSM/DEM context; UNOSAT report area sanity check
- Digitized by: [blank]
- Digitized at: 2026-07-09
- Notes: Obvious floodplain/water-like polygons only; uncertain areas excluded. Geometry is a nearby cross-border calibration candidate and does not overlap the eight Mae Sai ADM3 reporting units.
- Layer name: manual_flood_extent
- Geometry type: MULTIPOLYGON
- CRS: EPSG:4326
- Feature count: 1
- Bounding box: 99.814174, 20.483303, 99.825109, 20.491447
- SHA-256 status: recorded
- Not-official status: confirmed_true
- Reference-mask status: weak_reference_candidate
- Candidate readiness: ready_for_candidate_metrics
- Candidate validation metrics allowed: True
- Allowed use: cross-border calibration metrics only; visual QA; non-operational demo reporting
- Not allowed use: official validation truth; official warning; redistributed source data claim; unqualified ML labels
- Identity disclosure: `[blank]` means the digitizer identity was explicitly not recorded; it is not reviewer qualification.

## Method Assumptions

- Method type: non-ML Sentinel-1 pre/post SAR change baseline.
- Inputs: pre-event VV/VH and post-event VV/VH from local CDSE Sentinel-1 products outside Git.
- Reference: manually digitized weak-reference flood polygon from QGIS.
- Interpretation: candidate engineering metric only, not official accuracy.
- Window strategy: manual_reference_bbox_plus_buffer
- Sample size: 256 x 256 pixels
- Georeferencing method: sentinel1_safe_gcps_affine_fit;exact_common_grid_reprojection
- Measurement domain: sentinel1_uncalibrated_amplitude
- Log transform: 20_log10_amplitude
- Radiometric calibration: not_sigma0_beta0_or_gamma0_calibrated
- Probability threshold: 0.5
- Dry-change threshold: 0.5 dB
- Flood-change threshold: 4.0 dB
- Confidence class: low
- Assumptions: Cross-border calibration metrics against a manually digitized weak-reference mask; not Mae Sai Thailand ADM3 validation. Non-operational. Not official validation. Not field validated. The active GDAL subdataset is uncalibrated amplitude, converted with 20*log10(amplitude); it is not Sigma0/Beta0/Gamma0 calibrated. Sentinel-1 SAFE GCP georeferencing is approximated for this first baseline.
- Terrain correction, calibration refinement, permanent-water masking, and threshold tuning remain future work.

## Candidate Metrics

- Status: cross-border calibration metrics generated against a manually digitized weak-reference mask.
- Metric status: candidate cross-border calibration metrics, not Mae Sai Thailand ADM3 validation.
- IoU: 0.086835
- F1/Dice: 0.159795
- precision: 0.188113
- recall: 0.138887
- area error ratio: -0.261687
- True positive pixels: 1744
- False positive pixels: 7527
- False negative pixels: 10813
- True negative pixels: 45452
- Sample pixels: 65536
- Manual weak-reference positive pixels: 12557
- Predicted positive pixels: 9271
- Source timestamp: 2024-09-15T23:16:01Z
- Confidence class: low
- Warning text: Cross-border calibration metrics against a manually digitized weak-reference mask; not Mae Sai Thailand ADM3 validation. Non-operational. Not official validation. Not field validated.

## Failure Modes

- SAR layover/shadow can look like water or hide flood signal in steep terrain.
- Permanent water confusion can inflate flood detections if baseline water is not masked.
- Urban double-bounce can make built-up flood areas brighter or inconsistent across VV/VH.
- Manual mask uncertainty affects every candidate metric because the reference is not field validated.
- Date mismatch can occur if the manual interpretation and Sentinel-1 acquisition do not capture the same flood stage.

## Safety Note

- Not official.
- Not real-time.
- Not field validated.
- Not an emergency warning.
- Do not use this report for public alerting, evacuation orders, insurance decisions, or operational response without official validation.

## Official Gate Details

### Ingestion Gate

- Processing allowed: false
- Blocking reason: Sentinel Asia MBRSC Mae Sai public shapefile candidate: processing_allowed is not true, license_status is not confirmed, source_license_status is not confirmed, reference_mask_status is not confirmed; CDSE Sentinel-1 Mae Sai pre-event original SAFE: processing_allowed is not true, reference_mask_status is not confirmed; CDSE Sentinel-1 Mae Sai post-event original SAFE: processing_allowed is not true, reference_mask_status is not confirmed
- Real IoU, F1/Dice, precision, recall, and area error are pending for official validation.

### Required Next Action

- Log UNOSAT/UNITAR or GISTDA provider response.
- Record legal reference-mask status.
- Acquire and checksum-bind the future qualified reference artifact outside Git; the active SAFE pair and cross-border manual reference are already checksum-bound.
- Rebuild `outputs/mae_sai_real_data_file_manifest.csv`.
