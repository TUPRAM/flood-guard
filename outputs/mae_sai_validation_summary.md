# Mae Sai Real-Data Validation Summary

Report status: Weak-reference candidate metrics are available; official validation remains blocked.

Strict use statement: Candidate metrics against manually digitized weak-reference mask. Non-operational. Not official validation. Not field validated.

## Data Status

- Official processing allowed: false
- Official blocking reason: Sentinel Asia MBRSC Mae Sai public shapefile candidate: processing_allowed is not true, license_status is not confirmed, source_license_status is not confirmed, reference_mask_status is not confirmed; CDSE Sentinel-1 Mae Sai pre-event COG: processing_allowed is not true, reference_mask_status is not confirmed; CDSE Sentinel-1 Mae Sai post-event COG primary: processing_allowed is not true, reference_mask_status is not confirmed
- Official IoU, F1/Dice, precision, recall, and area error remain pending.
- Weak-reference candidate metrics available: true
- Source imagery and manual GeoPackage files stay outside Git; this report stores only derived metadata and metrics.
- Real-data ML remains blocked because the weak-reference mask is not an official or cleared label source.

## Sentinel-1 Product IDs

- Pre-event Sentinel-1 product id: `b09f96ca-4a60-43e7-9b8d-158022f0e5bf`
- Post-event Sentinel-1 product id: `20a9c3b8-37df-46d5-81d8-d63c7e460225`
- Post-event source timestamp: 2024-09-15T23:16:01Z
- Pre-event source name: CDSE Sentinel-1 Mae Sai pre-event COG
- Post-event source name: CDSE Sentinel-1 Mae Sai post-event COG primary
- Source rasters were read from the external data workspace, not from Git.

## Manual Reference Mask Metadata

- Reference id: `MANUAL-QGIS-MAE-SAI-2024`
- Study area: Chiang Rai / Mae Sai 2024
- Layer name: manual_flood_extent
- Geometry type: POLYGON
- CRS: EPSG:4326
- Feature count: 1
- Bounding box: 99.814171, 20.483303, 99.825111, 20.491447
- SHA-256 status: recorded
- Not-official status: confirmed_true
- Reference-mask status: weak_reference_candidate
- Candidate readiness: ready_for_candidate_metrics
- Candidate validation metrics allowed: True
- Allowed use: candidate validation metrics; visual QA; non-operational demo reporting
- Not allowed use: official validation truth; official warning; redistributed source data claim; unqualified ML labels

## Method Assumptions

- Method type: non-ML Sentinel-1 pre/post SAR change baseline.
- Inputs: pre-event VV/VH and post-event VV/VH from local CDSE Sentinel-1 products outside Git.
- Reference: manually digitized weak-reference flood polygon from QGIS.
- Interpretation: candidate engineering metric only, not official accuracy.
- Window strategy: manual_reference_bbox_plus_buffer
- Sample size: 256 x 256 pixels
- Georeferencing method: sentinel1_safe_gcps_affine_fit
- Probability threshold: 0.5
- Dry-change threshold: 0.5 dB
- Flood-change threshold: 4.0 dB
- Confidence class: low
- Assumptions: Candidate metrics against manually digitized weak-reference mask. Non-operational. Not official validation. Not field validated. Sentinel-1 SAFE GCP georeferencing is approximated for this first baseline.
- Terrain correction, calibration refinement, permanent-water masking, and threshold tuning remain future work.

## Candidate Metrics

- Status: candidate metrics generated against a manually digitized weak-reference mask.
- Metric status: candidate weak-reference metrics.
- IoU: 0.006079
- F1/Dice: 0.012085
- precision: 0.038494
- recall: 0.007167
- area error ratio: -0.813809
- True positive pixels: 90
- False positive pixels: 2248
- False negative pixels: 12467
- True negative pixels: 50731
- Sample pixels: 65536
- Manual weak-reference positive pixels: 12557
- Predicted positive pixels: 2338
- Source timestamp: 2024-09-15T23:16:01Z
- Confidence class: low
- Warning text: Candidate metrics against manually digitized weak-reference mask. Non-operational. Not official validation. Not field validated.

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
- Blocking reason: Sentinel Asia MBRSC Mae Sai public shapefile candidate: processing_allowed is not true, license_status is not confirmed, source_license_status is not confirmed, reference_mask_status is not confirmed; CDSE Sentinel-1 Mae Sai pre-event COG: processing_allowed is not true, reference_mask_status is not confirmed; CDSE Sentinel-1 Mae Sai post-event COG primary: processing_allowed is not true, reference_mask_status is not confirmed
- Real IoU, F1/Dice, precision, recall, and area error are pending for official validation.

### Required Next Action

- Log UNOSAT/UNITAR or GISTDA provider response.
- Record legal reference-mask status.
- Record local paths and SHA-256 checksums outside Git.
- Rebuild `outputs/mae_sai_real_data_file_manifest.csv`.
