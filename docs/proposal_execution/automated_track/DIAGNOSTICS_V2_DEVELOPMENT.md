# Mae Sai v2 development disagreement diagnosis

This is an exploratory diagnosis of the already-inspected Mae Sai episode under the **frozen v2 plan**. It does not revise v2, open the separate event holdout, or establish flood-map accuracy. Reproduce it with `uv run python scripts/diagnose_automated_optical_v2_development.py`. The script verifies the v2 plan and development receipts, asset and method raster hashes, label raster, grid, spectral rule, and reported agreement. It reads Mae Sai development files only.

Outputs are `outputs/automated_optical_v2_development_diagnostics.json`, `outputs/automated_optical_v2_development_disagreement.png`, and `outputs/automated_optical_v2_development_chips.png`. The first contains the exact SCL, spectral, raw-DN, and dry-context strata. Images are locators, not visual validation evidence.

## Result

| Observable pair on 15 September | Cells | SCL 5, not vegetated | SCL 6, water |
| --- | ---: | ---: | ---: |
| Neither water | 713,615 | 226,668 | 3,438 |
| A only | 160 | 124 | 10 |
| B only | 5,421 | 2,760 | 2,555 |
| Both water | 827 | 601 | 154 |

The two methods share 827 water cells among 720,023 comparable AOI cells. Method A marks 987 water cells; B marks 6,248. Dice is **0.2286**, below the pre-registered **0.60** limit, and kappa is **0.2268**, below **0.50**. The v2 event observable fraction is **0.6875**, above the **0.50** coverage floor. Compared with v1's downsampled A, native-grid A raised shared water from 353 to 827 and reduced A-only detections from 3,556 to 160, but the agreement still fails. This comparison is a development finding and cannot be used to select a new method for the same v2 holdout.

SCL is an automated scene class, **not independent flood truth**. Within observable SCL-water cells, A marks 164 and B marks 2,709; 3,438 are marked dry by both. Among B-only cells, 2,760 are SCL 5 and 2,555 are SCL 6. Only 214 of the 5,421 B-only cells fall within 20 m of A water, so a small boundary tolerance does not account for most mismatch. Event SCL has no class-1 or class-2 cells in this AOI, which explains why the v2 event quality mask has the same observable count as v1. The dry scene has 536 SCL class-2 AOI cells, so the expanded dry mask can still affect the permanent-water distinction.

The 5 September comparison is suggestive but not proof of flooding. Of 5,421 event B-only cells, 4,603 are observable on the dry date; **4,403** of those were dry according to both dry-date methods. Median B-only SWIR16 reflectance fell by **0.0594** between dry and event scenes. Median MNDWI change is **2.0**, the full range between index endpoints; the scale/offset clipping puts event SWIR16 at zero in **4,149** B-only cells. Median bilinear-resampled event SWIR16 DN is **362.5**. Thus the index change is partly saturated and should not be treated as a precise measure of water depth, flood probability, or accuracy. The densest B-only chip contains agricultural-looking ground and cyan automated detections; the densest A-only and shared chips overlap a cloud-edge area. These are investigation leads, not adjudications.

## Candidate for a future, separately frozen method

For a future **v3 research test**, consider a two-date spectral-change method centered on **red versus SWIR16** and SWIR16 suppression from a declared dry baseline, with an explicit cloud/shadow and valid-DN mask. This is meaningfully different from OmniWaterMask's RGB/NIR model-plus-NDWI composite because it uses the SWIR response and temporal change. [The RST-FLOOD Sentinel-2 study](https://www.mdpi.com/2072-4292/16/18/3450) explains that turbid floodwater can raise red reflectance while water absorption lowers SWIR reflectance; [a Sentinel-1/Sentinel-2 flood assessment](https://nhess.copernicus.org/articles/22/2473/2022/) also notes the value of pre-event comparison for distinguishing permanent water. Fixed thresholds, dry-scene suitability, treatment of clipped values, and minimum observable coverage need pre-registration **before** a fresh event comparison. Do not set them to reproduce v2 B or to maximize Mae Sai A/B agreement. Independent, date-compatible evidence is still needed to judge whether either map is correct.

This remains non-operational automated evidence. Human review was not performed. The score is agreement with an automated optical map, not accuracy.
