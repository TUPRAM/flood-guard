# GEOID-Flood S1GRD radar diagnostic v1

**Result: complete abstention.** The frozen Mae Sai M2 change and Otsu quality
rule, adapted to GEOID-Flood's S1GRD linear Sigma0, produced no classified
cells in the selected sample event. This is a negative research result, not a
zero flood-overlap score. Flood IoU, Dice, precision and recall are undefined
because evaluated coverage is zero.

## What was run

The [protocol](geoid_sar_benchmark_protocol_v1.json) was committed alone at
65cde436967f3ea2e47c4f8b57062bb93d93f01f before any benchmark label
comparison. It selected all 29 tiles of EMSR712-3 in the GEOID-Flood sample,
fixed the M2 256-pixel windows, 128-pixel stride, 0.4 VV / 0.6 VH dB change,
and all existing histogram and darkening gates. No parameters were adjusted
after looking at the result.

The 58 paired GRD rasters, 29 labels and 29 validity rasters total 572,940,276
bytes. All 116 files matched the publisher's SHA256SUMS at pinned dataset
revision 868407460bf3db492f50730a57585916baa71dc6. Source images,
candidate masks, per-tile QC and the self-hashed full result remain outside Git
under the external data workspace. The small
[result summary](../../../outputs/geoid_s1grd_sigma0_benchmark_summary_v1.json)
binds the exact full result by its file SHA-256
753433f7ab37837056c97dcec62e2256e3bc6658a3154a667ed70eb3b1efafaf
and self-hash
6f2c0a9b90627e63c7287b7b76949104f217efb0bb41bd60493342b349528461.
The 29 candidate raster hashes also verify against that full result.
To reproduce the run, install the repository's evidence extra and invoke
scripts/benchmark_geoid_flood_sar.py with --source-root pointing to the
directory containing sample/geoid-flood/EMSR712-3, --sha256sums pointing to
the publisher's pinned SHA256SUMS, and --output-directory pointing to a new
external directory. The runner refuses incomplete or changed source assets
and an existing output directory.

This separate adapter converts finite positive linear Sigma0 VV/VH to dB and
then uses the frozen M2 Otsu kernel and darkening gates. It does **not** run the
Mae Sai SNAP Gamma0 preprocessing, or reproduce its layover, slope and
independent permanent-water masks. The label, validity and label-derived
permanent-water rasters are never available to prediction; label and validity
are read only after each candidate is produced.

## Observed outcome

| Measure | Frozen result |
| --- | ---: |
| Reference background / permanent water / mapped flood / invalid cells | 16,378,552 / 454,889 / 962,756 / 12,612,507 |
| Source-radiometrically valid cells | 30,357,888 |
| Otsu windows qualified | 0 / 1,421 |
| Window rejection reason | 1,421 unimodal or unstable histogram |
| Between-variance fraction, min / median / max | 0.531781 / 0.614333 / 0.712422 |
| Frozen minimum between-variance fraction | 0.72 |
| Evaluable mapped cells, flood versus all mapped nonflood | 17,796,197 |
| Covered evaluable cells | 0 |
| Evaluated coverage | 0% |
| Flood IoU / Dice / precision / recall | undefined / undefined / undefined / undefined |

The outcome is an abstention, not evidence that the ground is dry or that the
algorithm has zero flood agreement. The same 0.72 histogram quality gate that
vetoed all 81 Mae Sai M2 windows also vetoed all 1,421 windows here. Only
three windows reached 0.70 and one reached 0.71, so the failure is not
explained by one narrowly missed cutoff. A lower cutoff chosen from this
scored event cannot become a confirmatory result for this event. Because
this test uses S1GRD Sigma0 instead of Mae Sai's Gamma0 and lacks the M2
context masks, it does not prove the exact M2 implementation would abstain on
all other events. It does show that the transferred frozen decision rule did
not yield a usable classification on this mapped event.

## Reference meaning and limits

The GEOID-Flood label combines a manually checked Copernicus Emergency
Management Service (CEMS) flood delineation with modelled permanent water.
For AOI03 MONIT04, all 268 observedEventA flood features in the
[official CEMS vector package](https://rapidmapping.emergency.copernicus.eu/backend/EMSR712/AOI03/DEL_MONIT04/EMSR712_AOI03_DEL_MONIT04_v2.zip)
cite the **3 January 2024 05:34 UTC Sentinel-1 acquisition**, the same pass
as the benchmark GRD post image. Any future non-abstaining score on this
sample would be **agreement with a CEMS-derived map from the input pass, not
independent flood accuracy**. The publisher's sample "train" and "test" AOIs
also share EMSR712, so this is not a new-event holdout. The benchmark's
background class is mapped background, not field-confirmed dry land.

The [GEOID-Flood dataset card](https://huggingface.co/datasets/links-ads/geoid-flood)
identifies S1GRD as linear Sigma0 and describes the classes, validity and
license. Its [paper](https://arxiv.org/html/2608.02315v1) explains the CEMS
label source and same-pass Sentinel-1 selection. The sample RTC post image
has a different acquisition date from the GRD and CEMS delineation, so the
temporally matched GRD was selected. The GRD pre image dates to 8 September
2023 and the post delineation to 3 January 2024; this long pre/post gap is
another limitation. Copernicus and CEMS attribution notices in the dataset
card apply to redistributed derivatives. Attribution for these outputs:
"Modified Copernicus Sentinel-1 data (2016-2026)" and "Copernicus Emergency
Management Service Rapid Mapping products, © European Union." See the
[CEMS citation guidance](https://mapping.emergency.copernicus.eu/about/citation-guidelines/)
for product-specific references.

## Next research step

Audit why the frozen between-variance quality test rejects every window using
source imagery and independent development events. If the cutoff or feature
construction changes, record a new method and limits **before** evaluating an
untouched event. Keep this v1 abstention, Mae Sai's v1/v2 outcomes and the
consumed Chaiyaphum holdout intact. A future event with a reference derived
from another sensor or field evidence is needed for an independent physical
flood-accuracy claim.

This benchmark is non-operational: human_reviewed_by_floodguard=false,
accepted_observation=false, official_warning=false, and
can_feed_decision_layer=false. It does not produce accepted FPPS or an
accepted action class.
