# M2 Gamma0 abstention diagnosis

The source-bound M2 result remains a failed, non-operational candidate. This
diagnosis reads its frozen receipt and mask plus the optical receipt's grid metadata. It
does not read optical label values, compare with the reference, change a
threshold, or reopen the consumed final holdout. The repeatable, self-hashed
summary is `outputs/sar_m2_abstention_diagnostic_v1.json`.

## Verified cause

The original M2 receipt file hashes to
`7814cfb5f936952a581ab72c40bde7ab14f638715834f39974dddfa81c5394fe`,
as frozen in the automated pre-registration. Its internal self-hash, candidate
mask hash and abstention-code raster hash verify. The candidate mask contains
no dry or flood classifications anywhere in its 1,280 × 1,280 pilot grid.

All **81 of 81** windows had more than the required 4,096 valid samples
(14,771–65,497). Each passed the minimum class fraction and mean-separation
checks but failed the same predeclared histogram test. The recorded
between-class variance fractions are **0.598414–0.651191**, below the frozen
minimum **0.72**. Histogram quality control explains the zero classified cells;
this diagnosis does not test geodetic accuracy or establish whether water was
present.

| Reason on the original pilot grid | Cells |
| --- | ---: |
| Unsupported input or geometry | 30,034 |
| Likely permanent-water abstention | 25 |
| Slope abstention | 671,955 |
| Histogram abstention | 936,386 |
| Classified dry or flood | **0** |

The reference AOI spans beyond that rectangular pilot grid. Counting only AOI
geometry on the optical **grid metadata**, without opening its label band,
produced:

| Status within AOI-01 | 10 m cells | Share of 1,047,320 AOI cells |
| --- | ---: | ---: |
| Outside M2 source footprint | 604,672 | 57.74% |
| Inside footprint, unsupported | 8,847 | 0.84% |
| Terrain abstention | 121,176 | 11.57% |
| Histogram abstention | 312,625 | 29.85% |
| Permanent-water abstention | 0 | 0.00% |
| Classified dry or flood | **0** | **0.00%** |

The v1 optical receipt records the Sentinel-2 **product-name start** at
15 September 2024 03:45:29 UTC and the SAR post acquisition at
23:16:01.675690 UTC, a nominal gap of **19 h 30 min 32.675690 s**.
The later Earth Search tile `datetime` recorded in the v2 acquisition manifest
is 04:02:41.830 UTC, giving **19 h 13 min 19.845690 s** to that SAR pass.
These are different timestamp semantics, not two optical scenes. Water can
change in either interval; timing alone does not show recession or
progression. The pre/post SAR span is about 12 days. Neither timing nor the
optical reference's poor two-method agreement changes the recorded M2
abstention or its failed acceptance limits.

## Next SAR work under a new protocol

1. Inspect the existing Gamma0 changes and the 20° slope exclusion by terrain,
   land cover, layover/shadow and narrow-channel strata. The histogram veto
   is measurable; lowering 0.72 simply to obtain a flood polygon would be
   selection after seeing the Mae Sai comparison.
2. Define a complete AOI footprint before a new candidate comparison. The
   current pilot grid covers only about 42% of AOI-01. A wider SNAP run needs
   exact SAFE, orbit, DEM, auxiliary, radiometry and grid provenance.
3. If physical analysis supports a different feature, speckle filter, or
   abstention policy, version and freeze that candidate and its limits before
   evaluating on a new independent event. Preserve the M2 v1 receipt and
   single-use final-holdout result as a failure.

To regenerate the summary on the machine with the external workspace, run from
the repository root (using a new output path):

```powershell
$external = '<external-data-workspace>/proposal_execution'
uv run --extra evidence python scripts/diagnose_m2_abstention.py `
  --candidate-receipt (Join-Path $external 'mae_sai_2024_gamma0_otsu_v1_20260923r3/candidate_receipt.json') `
  --expected-receipt-sha256 7814cfb5f936952a581ab72c40bde7ab14f638715834f39974dddfa81c5394fe `
  --reference-receipt outputs/automated_optical_reference_v1.json `
  --aoi resources/aoi/aoi-01_mae_sai_core.geojson `
  --output '<new-summary-path>.json'
```

The script refuses to overwrite an existing summary.
