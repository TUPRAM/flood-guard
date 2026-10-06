# Automated optical v2: development and one-use event holdout

This is **automated method agreement, not flood-detection accuracy**. Human
qualification and blind review were not performed. The accepted observation,
FPPS, action class and decision-layer authorization remain unavailable;
`official_warning=false` and `operational_status=non_operational`.

## Frozen protocol and source identity

The [v2 pre-registration](preregistration_v2.json) was committed alone as
`efc69f5f66dfe8c2d667a9827566126709f1cab9` before v2 inference. Its
separate stricter positive-count gate was committed as
`09a4e03c14da9a9bd72cb70f0c7711f703fc9c0d` before the event holdout.
Mae Sai 2024 was already inspected development evidence. The fresh,
single-use Chaiyaphum event was fixed as Earth Search item
`S2B_47PRT_20210928_1_L2A`, with 18 September item
`S2B_47PRT_20210918_1_L2A` as dry context. This did not reopen the consumed
Mae Sai SAR holdout. The scoring implementation was committed as `bcce21d`
before Chaiyaphum preparation; the separate read-only artifact verifier was
committed as `b60be36` after the result.

The 16 source COGs per episode were acquired outside Git. Their exact URLs,
byte counts, SHA-256 values, SAFE product URIs, processing baselines and STAC
tile-sensing times are in the [development](../../../outputs/earth_search_automated_optical_v2_development_assets.csv)
and [holdout](../../../outputs/earth_search_automated_optical_v2_holdout_assets.csv)
manifests. The original SAFE SHA-256 is not recorded. Every band uses its own
recorded scale and offset; the selected N0500 holdout uses `0.0001` and
`-0.1`. The v2 receipt uses the Earth Search **tile sensing time**:
2024-09-15 04:02:41.830 UTC for Mae Sai and 2021-09-28 03:53:49.285 UTC for
Chaiyaphum. The frozen Mae Sai v1 receipt used the product-name start time
03:45:29 UTC; it remains separately recorded and must not be conflated with
the STAC tile time.

Method A runs GeoAI 0.41.1 / OmniWaterMask 0.5.0 on a native 10 m grid. Its
package defaults combine the pretrained model with optimized NDWI; it is not
a model-only classifier. Method B remains the fixed MNDWI > 0.1, AWEIsh > 0,
NDVI < 0.2 spectral conjunction. Both methods receive optical inputs only.
OmniCloudMask 1.7.1, a tiling dependency, was checked at runtime and pinned
in the separate research-environment requirements for replay **after** the
run; the frozen plan had specified GeoAI, OmniWaterMask and package-default
tiling, while the preparation receipts record the actual dependency version.
The requested tiles were 512 px with 128 px overlap. Its deterministic
high-nodata rule used **478 px** on Mae Sai and **450 px** on Chaiyaphum, both
with 128 px overlap; no 10 m grid downsampling or after-result threshold
change was made. The preparation receipts record requested/effective sizes,
nodata fractions and dependency versions.

## Recorded results

| Event and role | Observable / AOI cells | A water | B water | Shared water | Dice | Kappa | Limits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Mae Sai, inspected development | 720,023 / 1,047,320 (68.75%) | 987 | 6,248 | 827 | 0.2286 | 0.2268 | Dice and kappa **fail**; coverage passes |
| Chaiyaphum, fresh final holdout | 398,441 / 855,127 (46.59%) | 110,129 | 126,255 | 106,361 | 0.8999 | 0.8580 | Dice and kappa pass; coverage **fails** |

The frozen floors are Dice ≥ 0.60, kappa ≥ 0.50, event observable fraction
≥ 0.50. Chaiyaphum also passes the predeclared feasibility gate of at least
100 water cells per method and 100 shared cells. **Neither episode passes all
limits.** The high Chaiyaphum agreement concerns only observable cells;
the same result fails representativeness coverage. It cannot promote Mae Sai
v1, establish accuracy or authorize a flood observation.

| Episode | Code 0 both dry | Code 1 new relative to dry date | Code 2 water on both dates | Code 3 uncertain | Code 4 unobservable |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mae Sai | 713,615 | 196 | 32 | 6,180 | 327,297 |
| Chaiyaphum | 268,418 | 21,853 | 1,374 | 106,796 | 456,686 |

Code 2 proves persistence across the two selected optical dates, **not
permanent water**. The 18 September Chaiyaphum scene precedes the selected
28 September event, but a single earlier image cannot establish a stable dry
baseline or rule out earlier flooding. Of 106,361 event shared-water cells,
82,645 lack observable dry context, 489 have dry-method disagreement, 1,374
are water on both dates and 21,853 are dry on the earlier date. The first two
groups remain uncertain rather than being called temporary flood.

Chaiyaphum's coverage shortfall comes from the frozen mask and radiometry:
271,619 AOI cells have excluded event SCL codes, the 20 m buffer adds 32,259,
and another 152,808 fail the spectral denominators after per-asset scale,
offset and clipping. All six source-band digital numbers were positive in
that last group. **80,286** of those denominator exclusions carry event SCL
class 6 (Sentinel-2's automated water class), or **41.3%** of all 194,491
SCL-water AOI cells. These
cells may preferentially be dark water, so the exclusion could inflate
agreement among the remaining cells; the size of that bias is unknown. The
high agreement must be read alongside the excluded fraction. The methods
and mask remain unchanged after seeing this result.

The development [result](../../../outputs/automated_optical_v2_development.json),
[diagnostic](DIAGNOSTICS_V2_DEVELOPMENT.md), and [quicklook](../../../outputs/automated_optical_v2_development.png)
remain separate from the [holdout result](../../../outputs/automated_optical_v2_holdout.json)
and [quicklook](../../../outputs/automated_optical_v2_holdout.png).
The holdout result self-hash is
`d326d19117d9cbaed47316986d2a8394f5f1b2e49fc49b4f4a49cbd224d7b9a8`.
Its exclusive consumption marker is outside Git at
`<external-data-workspace>/proposal_execution/automated_track/v2/automated_optical_holdout_consumption.json`.
The marker was created before the first holdout water-score read. The result
and its source/raster/marker hashes were verified after scoring without a
second metric run. A second holdout score is refused.

## Interpretation and next evidence

The [Mae Sai pixel diagnosis](DIAGNOSTICS_V2_DEVELOPMENT.md) shows a real
remaining method gap at native resolution. The [M2 SAR diagnosis](SAR_M2_ABSTENTION_DIAGNOSIS.md)
shows that all 81 windows failed the frozen histogram quality test, while
its pilot footprint covered only part of AOI-01. Optical A/B agreement does
not repair SAR abstention. The [independent-source search](independent_evidence_candidates_v2.md)
found contextual UNOSAT reports, later GISTDA THEOS imagery, and a same-day
GISTDA ALOS-2 flood polygon in Mae Sai. The complete AOI vector, processing
lineage and reuse terms remain unverified, so this is not established pixelwise
truth. A future study needs
an independently dated and licensed reference, a defensible dry baseline and
a **new** event holdout with methods and limits frozen before predictions.

Reproduce source acquisition with
`uv run python scripts/acquire_earth_search_automated_optical_v2.py --scene development`
or `--scene final_holdout`; the script rehashes completed local COGs. The
`scripts/run_automated_optical_v2.py` `prepare` and `score` commands are
described in its `--help`. **Do not run final-holdout score again**: the
exclusive marker is consumed. The saved result can be verified read-only with
`floodguard.automated_optical_v2.validate_result_artifacts`.
