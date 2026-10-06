# Mae Sai v1 optical disagreement diagnosis

This is an exploratory diagnosis of the **frozen** 15 September 2024 automated optical reference. It does not alter the pre-registration, the reference, the evaluation, or the consumed final holdout. Pixel counts describe agreement between automated methods, **not flood-map accuracy**.

Run `uv run python scripts/diagnose_automated_optical_v1.py` from the repository root. The script verifies the pre-registration commit, the reference receipt and label raster, the event asset hashes, the two method raster hashes and their grid, and recomputes the reported A/B agreement. It writes a machine-readable table to `outputs/automated_optical_v1_diagnostics.json`, a true-colour disagreement map to `outputs/automated_optical_v1_disagreement.png`, and three deterministic 1.8 km chips to `outputs/automated_optical_v1_chips.png`. The external workspace supplies the original COGs and frozen method rasters.

## What the pixels show

Of 720,023 observable AOI cells, both methods call 353 water, A alone calls 3,556, B alone calls 5,895, and both call 710,219 dry. The frozen Dice is 0.0695 and kappa is 0.0633, below their respective 0.60 and 0.50 limits.

| Sentinel-2 SCL class | Neither water | A only | B only | Both water |
| --- | ---: | ---: | ---: | ---: |
| 4 vegetation | 481,324 | 100 | 6 | 1 |
| 5 not vegetated | 223,339 | 3,453 | 3,024 | 337 |
| 6 water | 3,448 | 0 | 2,695 | 14 |
| 7 unclassified | 2,108 | 3 | 170 | 1 |

SCL water is **an automated context class, not flood truth**. Still, the difference is worth investigating: A marks 14 of the 6,157 observable SCL-water cells, and B marks 2,709. A-only cells are concentrated in SCL class 5 (3,453 of 3,556). B-only cells split between SCL class 5 (3,024) and class 6 (2,695). Neither fact proves which method is correct.

The fixed spectral conjunction rejects 3,525 of the 3,556 A-only cells at its MNDWI threshold, and 3,191 at its AWEIsh threshold. The A-only median raw DN is 2,044 for green and 3,617 for bilinear-resampled SWIR16, consistent with its median MNDWI of −0.383. The B-only medians are 1,542 green and 388 SWIR16, consistent with its median MNDWI of 1.000 after conversion. Converted SWIR16 reflectance is exactly zero in 4,591 of the 5,895 B-only cells, with blue zero in 4,567. These are **zeros after the pre-registered scale, offset and clipping**, not proof of a data error; dark water can also have low SWIR. Inspect original DN and local image context before changing this conversion in any later protocol.

Only 231 of the 5,895 B-only cells lie within 20 m of an A-water cell. Only 765 of 3,556 A-only cells lie within 20 m of B-water. A small registration shift or boundary tolerance therefore cannot explain most disagreement. The A input was reduced from the 1,109 × 957 reference grid to 512 × 442 pixels before model inference, so the model resolution remains a priority for a separately declared experiment.

The inspected local GeoAI/OmniWaterMask package confirms output band 1 means water prediction, with binary values 0/1. Its default composite includes **both** a pretrained model branch and an internally optimized NDWI branch; it unions their predictions. Method A is thus a distinct combined method, not a model-only prediction. A future ablation should examine those branches separately.

The deterministic chips place the densest A-only cluster in bright, dense urban/nonvegetated imagery, the densest B-only cluster in an agricultural-looking area, and the densest shared cluster beside masked clouds. They are **visual leads**, not a decision that any cell is water or dry. SCL classes 1 and 2 have zero cells inside this AOI scene, so adding those codes to a future mask cannot change this particular result. It can still be a sensible general rule for other scenes if declared before their evaluation.

## Next investigation

1. Inspect A-only and B-only clusters at native image scale, including original DN, reflectance, SCL, the three spectral predicates, and the model output. The quicklook is a locator, not a visual validation sample.
2. Test native-grid tiled OmniWaterMask inference with overlap as a **new research version**. Record model input and output transforms, tile edges, and predictions by SCL class. Do not replace v1 artifacts.
3. If a new quality mask or spectral rule is justified, specify it before comparison on a fresh event. Do not select exclusions or thresholds by maximizing agreement on this consumed case.
4. Seek independent date-compatible flood evidence and a fresh holdout before making validation claims. More agreement between A and B by itself cannot establish accuracy.

All artifacts remain non-operational. Human review was not performed. The result is agreement with an automated optical map, not accuracy.
