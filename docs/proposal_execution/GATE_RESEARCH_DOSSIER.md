# Gate research dossier — Mae Sai reference, review, evaluation and multi-event gates

## 24 September 2026 track decision

The project owner chose an end-to-end **automated research track** for this Mae
Sai comparison. The human qualification and blind-review programme documented
below is retained as a historical plan and is **not pursued** in this run. No
automated receipt is a human appointment, signature, qualified label release or
accepted observation. The automated track has its own pre-registration, rights
basis, optical reference, two-method cross-review and one-use hold-out result.
Scores against that reference mean **agreement with an automated optical map,
not accuracy**. The measured reference, development and final-holdout results,
including failed limits, are recorded below.

### 24 September 2026 optical v2 follow-up — overall FAIL

The new [optical v2 result](automated_track/OPTICAL_V2_RESULT.md) tests the
pixel-diagnosis lead without changing the frozen v1 reference or reopening its
SAR hold-out. V2 pre-registration commit
`efc69f5f66dfe8c2d667a9827566126709f1cab9` fixed native 10 m model
inference, per-asset radiometry, the enlarged SCL quality mask and the
unchanged spectral rule. A stricter positive-cell gate was committed as
`09a4e03c14da9a9bd72cb70f0c7711f703fc9c0d` before the fresh-event
hold-out. The package requested 512 px patches, but its recorded
OmniCloudMask 1.7.1 high-nodata rule used 478 px for Mae Sai and 450 px for
Chaiyaphum. It did not downsample the 10 m grid.

| Optical v2 episode | A/B water Dice; limit ≥ 0.60 | Cohen's kappa; limit ≥ 0.50 | Observable AOI; limit ≥ 0.50 | Overall |
| --- | ---: | ---: | ---: | --- |
| Mae Sai, already-inspected development | 0.228611 **FAIL** | 0.226780 **FAIL** | 720,023 / 1,047,320 = 0.687491 **PASS** | **FAIL** |
| Chaiyaphum 28 September 2021, one-use event hold-out | 0.899900 **PASS** | 0.857963 **PASS** | 398,441 / 855,127 = 0.465944 **FAIL** | **FAIL** |

The Chaiyaphum methods marked 110,129 and 126,255 observable cells as water
and shared 106,361; all positive-cell minima of 100 pass. The hold-out score
was recorded once after its exclusive marker was created. High two-method
agreement on the scored subset is **agreement with an automated optical map,
not accuracy** and cannot cancel the failed coverage limit. The expanded
event SCL mask excluded 271,619 AOI cells and its 20 m buffer another 32,259.
Per-asset scale/offset and clipping left spectral denominators zero on a
further 152,808 cells, including 80,286 carrying SCL class 6, an automated
water class. This selection could inflate apparent agreement; its effect is
unknown. Only 21,853 of the 106,361 shared event-water cells were also
classified dry by both methods on the earlier date; 82,645 lacked observable
dry context, so they stayed uncertain. Code 2 records water on both dates,
not independently established permanent water.

The [v1 pixel diagnosis](automated_track/DIAGNOSTICS_V1.md), [v2 development
diagnosis](automated_track/DIAGNOSTICS_V2_DEVELOPMENT.md) and [M2 abstention
diagnosis](automated_track/SAR_M2_ABSTENTION_DIAGNOSIS.md) are separately
reproducible. The SAR M2 candidate still has zero classified cells because all
81 windows failed its frozen histogram test; v2 optical work does not repair
that candidate. The [independent-source search](automated_track/independent_evidence_candidates_v2.md)
found contextual UNOSAT reports and later GISTDA imagery but no verified,
same-time, legally reusable Mae Sai pixelwise truth. Human-track gates remain
not pursued, and no v2 output is an accepted observation, official warning or
downstream FPPS input.

### Automated optical reference result

The exact 15 September event and 5 September dry-context Sentinel-2B L2A
products were acquired anonymously as 16 Element84 Earth Search COG assets.
Each asset's URL, byte count and SHA-256 are in
`outputs/earth_search_mae_sai_sentinel2_reference_assets.csv`; the original
SAFE SHA-256 is `not_recorded`. The optical rasters and model weight remain
outside Git. Two frozen optical methods produced this AOI-01 label raster on
the 10 m EPSG:32647 grid:

| Label code | Meaning | AOI cells |
| --- | --- | ---: |
| 0 | Both methods dry | 710,219 |
| 1 | Temporary flood agreed by both methods | 179 |
| 2 | Permanent water in the 5 September dry context | 5 |
| 3 | Method disagreement or indeterminate dry context | 9,620 |
| 4 | SCL/unobservable and buffered cells | 327,297 |

The 1,047,320 AOI cells include 720,023 cells on which both event methods
could be compared. Their automated water Dice is **0.0695** and Cohen's kappa
is **0.0633**. Both pre-registered cross-review limits fail (Dice ≥ 0.60,
kappa ≥ 0.50). The methods marked 3,909 and 6,248 water cells respectively;
their consensus temporary flood is sparse. No SAR data entered either optical
method, and no method threshold was changed after seeing these results.
Turbid water, cloud/shadow masking, the optical model's downsampling and the
nominal 19 h 31 min gap from the v1 product-name start to the SAR post scene
constrain interpretation. The v2 Earth Search tile sensing time makes that
gap 19 h 13 min instead; neither interval establishes water stability. The
Component ★ finding that MNDWI > 0 flagged 8.7 times the reference area on a
dry-season scene is a specific warning against treating a spectral mask as
human flood truth.

### Pre-registered development comparison

The development partition was scored against reference codes 0 and 1 only;
permanent water, uncertain and unobservable cells were excluded. The 10 m M2
Gamma0 Otsu mask abstained on all 145,048 evaluable development cells. Its
coverage is 0 and its IoU, Dice, precision, recall and area error are
unavailable; **all five** pre-registered candidate limits fail. This is an
abstaining candidate result, not evidence that the area was dry.

The 20 m raw-amplitude comparator covered 145,046 of 145,048 evaluable cells
(coverage 0.999986, the one passing limit). It had TP 6, FP 6,969, FN 33 and
TN 138,038. Agreement IoU was **0.000856**, Dice **0.001711**, precision
**0.000860**, recall **0.153846**, and absolute area error **177.846** times
the 39-cell reference flood area on covered development cells. IoU,
precision, recall and area-error limits all fail. The 33 false negatives are
logged as possible time-gap/recession candidates, not proof of recession.
These are agreement statistics against a weak automated optical map, not
flood-detection accuracy.

### Single-use final hold-out comparison

The development result was checked before opening the final partition. One
exclusive `automated_holdout_consumption` marker was created outside Git for
the frozen partition; the final result binds that marker, the development
result, the pre-registration commit and the optical reference receipt. This
hold-out was run **once**. Its result is a recorded failure, not an opportunity
to adjust thresholds or repeat the partition.

| Final-holdout measure | M2 Gamma0 Otsu, radiometrically calibrated SAR input | Raw 20 m amplitude comparator |
| --- | ---: | ---: |
| Evaluable cells | 114,588 | 114,588 |
| Covered cells / coverage | 0 / 0 | 114,517 / 0.999380 |
| TP / FP / FN / TN | 0 / 0 / 0 / 0 (abstention) | 0 / 6,405 / 3 / 108,109 |
| IoU / Dice | unavailable / unavailable | 0 / 0 |
| Precision / recall | unavailable / unavailable | 0 / 0 |
| Absolute area-error fraction | unavailable | 2,134.0 |
| Boundary F1 at 20 m | unavailable | 0.000414 |
| Pre-registered limits met | 0 of 5 | 1 of 5 (coverage only) |

The M2 mask contains only abstentions in the aligned footprint and fails every
limit. For the raw amplitude comparator, coverage passes ≥ 0.50; IoU fails
≥ 0.30, precision fails ≥ 0.50, recall fails ≥ 0.50, and absolute area error
fails ≤ 0.50. It predicts 640,500 m² of flood among scored cells against
300 m² in the automated optical map. The three false negatives are a possible
timing/recession diagnostic only. The optical scene preceded the SAR post scene
by a nominal 19 h 31 min from the v1 product-name start (19 h 13 min from
the v2 STAC tile time), and the reference's own two-method cross-review failed badly.
The number on the landing page is **agreement with an automated optical map,
not accuracy**. Neither candidate passes the frozen observation limits or
earns accepted observation status. The raw comparator's source manifest also
marks it `eligible_for_validation=false`; this automated comparison does not
override that source status.

## Historical human-track plan — not pursued in this run

Prepared 24 September 2026 on `codex/open-data-evidence-demo`, starting from
HEAD `e4a6a3ddd7112b9b7cdb3225411c2a23021b46ea`.

**Status of the human track: research evidence and unsigned drafts. No human
gate was opened.**
Steps 1–6 of the gate sequence each end in a decision or act by a named,
qualified person: a rights record, a Reference Authority signature, four-person
blind review, a frozen evaluation plan, custodian keys, and downstream
acceptance. The repository contracts (`REVIEW_PACKAGE.md`,
`ml_authorization.md`, `qualified-thai-reference-label-release-v1.md`) forbid
engineering or literature from standing in for those people, and so does this
dossier. What research *can* do is find the exact source, check its rights,
measure whether it is usable, and pre-fill decisions so each person only has to
review and sign. That is what follows.

Research outputs referenced below:

| File | What it is |
| --- | --- |
| `gate_research/mae_sai_s2_observability_v1.json` | Sentinel-2 L2A scene-classification (SCL) observability over AOI-01 for every scene from 1 to 25 September 2024 |
| `gate_research/thai_s1_s2_coincidence_scan_v1.json` | Sentinel-1 GRD / Sentinel-2 L2A pairs within 48 h over nine candidate Thai flood episodes, with the clear-sky fraction for each box |
| `scripts/probe_optical_reference_candidates.py` | Reproduces both files (`aoi` and `scan` subcommands); pure logic tested in `tests/test_probe_optical_reference_candidates.py` |

Both JSON files carry `evidence_tier=research_hypothesis`,
`official_warning=false`, `can_feed_decision_layer=false` and
`grants_reference_authority=false`.

## Summary by step

| Step | What the research found | What still needs a person |
| --- | --- | --- |
| 1. Exact source and use grant | A new candidate that is independent and open: the Copernicus **Sentinel-2B L2A scene of 15 September 2024, 03:45:29 UTC**, taken 19.5 h before the Sentinel-1 post scene. AOI-01 is **73.5 % clear**. The Copernicus legal notice already covers every required purpose, so no separate grant is needed for this source. | The acquisition owner downloads the SAFE product, records its SHA-256, and signs the per-purpose rights record (draft below). |
| 2. Scientific qualification | Draft parameters grounded in the literature and in measurements: timing, independence, flooded/dry/unknown rules, grid and coverage. The Sentinel-2 tile is already on the SAR analysis grid (EPSG:32647, 10 m). | The Reference Authority accepts, amends or rejects the parameters and signs. |
| 3. Four-person blind review | Nothing research can supply. | Four named, qualified, distinct people. |
| 4. Frozen evaluation | Draft target, masks, metrics and partition rule. Acceptance limits are left as explicit blanks. | The evaluation lead chooses the limits and freezes the plan before any holdout opens. |
| 5. RF/XGBoost authorization | **Six candidate Thai episodes** have an open optical scene within about 41 h of a Sentinel-1 pass and at least 30 % clear sky, spanning four regions. | A method-family decision, per-episode references and labels, and custodian keys. |
| 6. Consequences | Dated public leads for roads and shelters, with one correction to an earlier attribution. | Road/service reviewer and downstream acceptance authority. |
| 7. Release claim | Preview wording corrected in this change (see "Presentation corrections"). | Re-verify the Preview at the new commit. |

## Step 1 — exact source and use grant

### New candidate: Sentinel-2B L2A, 15 September 2024

| Field | Value |
| --- | --- |
| Product | `S2B_MSIL2A_20240915T034529_N0511_R104_T47QNC_20240915T065143.SAFE` |
| CDSE product id | `f1a638d2-3b8f-4f9a-a862-1b651d6662c3` (already listed in `outputs/cdse_mae_sai_2024_sentinel2_metadata.csv` as "post-event optical context candidate") |
| Sensing | Datatake start 2024-09-15 03:45:29 UTC (10:45 Thailand time); Earth Search item time 04:02:41 UTC |
| Sensor / lineage | Sentinel-2B MSI, optical multispectral; Level-2A processed by ESA Sen2Cor baseline N0511; tile T47QNC is natively UTM 47N (EPSG:32647) at 10/20/60 m |
| Relation to the tested SAR | The SAR post scene is 2024-09-15 23:16:01 UTC. The v1 optical product-name start is **nominally 19 h 31 min earlier**; the Earth Search tile sensing time gives 19 h 13 min. Both are on the same UTC day. It is a different sensor with a different physical measurement. No part of it derives from any Sentinel-1 product. |
| AOI-01 coverage (SCL, 20 m) | 261,806 pixels. Clear and observable **0.7346**. Cloud (medium + high) 0.1887, cloud shadow 0.0767, no data 0. |
| Flood presence | UNOSAT's Charter assessment of 16 September reports widespread flooding in Mae Sai "as of 15 September 2024" from Pléiades imagery taken 15 September 03:58 UTC, about 13 minutes after this Sentinel-2 pass. |
| Other September scenes | 5 Sept: 0.877 clear, but it predates the 10–16 September flood peak, so it is a useful dry-context scene. 10, 20 and 25 Sept: 0.000, 0.000 and 0.021 clear, so unusable. |

Caveat: the SCL "water" class covers only 0.63 % of the AOI. Muddy floodwater
is usually classed as bare ground or unclassified, so **SCL is an observability
screen, not a label**. The repository's own Component ★ finding (MNDWI > 0
flags 8.7× the reference area) shows why no spectral index should be treated as
the reference. Labels must come from human interpretation of the imagery.

### Rights mapped per purpose (draft for the acquisition owner to confirm)

Source: *Legal notice on the use of Copernicus Sentinel Data and Service
Information* (European Commission DG DEFIS), implementing Regulation (EU)
377/2014 and Delegated Regulation (EU) 1159/2013, Art. 7. It grants free access
for lawful **(a) reproduction; (b) distribution; (c) communication to the
public; (d) adaptation, modification and combination with other data**. It
gives no warranty of fitness.

| Purpose | Covered by | Condition |
| --- | --- | --- |
| Geometry repair, reprojection, rasterization | (d) | — |
| Human annotation and reviewer calibration | (d) | — |
| Model training and probability calibration | (d) | — |
| Final evaluation and derived metrics | (d) | — |
| Hosted Preview display and downloadable derivatives | (b), (c), (d) | Attribute "Contains modified Copernicus Sentinel data 2024" |
| Downstream decision use | Rights allow it | Rights do not qualify the data scientifically; Steps 2 and 6 still govern |

The GISTDA/GeoHackathon grant is therefore **not needed for this source**. It
matters only if the team prefers a GISTDA or THEOS-2 product; see
`outputs/theos2_request/` and `docs/theos2_usage_terms_log.md`.

**Still to do (acquisition owner):** download the SAFE product by CDSE id,
record its SHA-256 and byte count in an acquisition manifest outside Git, and
sign the rights table above. This follows the same pattern as
`scripts/acquire_cdse_mae_sai_sentinel1.py`.

### Other candidates re-examined

| Candidate | Finding | Recommendation to the authority |
| --- | --- | --- |
| UNOSAT 3969: Charter preliminary assessment, 16 Sept 2024 | Pléiades post-event image at 2024-09-15 03:58 UTC over Mae Sai town. Pre-event images are WorldView-3/GeoEye-1. Imagery is "© CNES (2024), Distribution Airbus D&S". Only a PDF is published. | Reviewers may use it as an **independent visual cross-check** when resolving disagreements, citing the PDF. Do not rasterize or redistribute it: the imagery is © CNES/Airbus and no reuse licence is published with the report. |
| UNOSAT 3991: 13–19 Sept cumulative water | Cumulative over seven days; PDF only. A probe for vector archives under the UNOSAT file store returned 404. | Reject as a single-date reference, as `REVIEW_PACKAGE.md` already concludes. |
| UNOSAT/GISTDA 4009 | Accumulated August–October, with a date conflict. UNOSAT data on HDX is generally CC BY-SA. | Reject for 15 September. If any derivative is kept, check the share-alike terms. |
| Sentinel Asia `AIT-VAP001-TH` (14 Sept) | Product-specific rights unresolved; 24 of 371 in-area polygons are invalid. | Keep as a secondary candidate. The Sentinel-2 route avoids its rights question. |
| Copernicus EMS Global Flood Monitoring (GFM) | Same legal notice as above. GFM is computed from **the same Sentinel-1 acquisitions**. | Not independent of the tested SAR result. Usable only as an algorithm comparator, never as the answer key. |
| Thammaboribal et al. 2025, *Int. J. Geoinformatics* 21(3), doi:10.52939/ijg.v21i3.4039 | UN-SPIDER Sentinel-1 VH change detection (pre 1–9 Sept, post 11–20 Sept). Threshold 1.25 chosen against 80 GISTDA ground points (93.38 %). | SAR-derived, with a threshold tuned on its validation points, so it cannot be the reference. It does show that GISTDA holds dated ground points for this event, which would make useful point checks if GISTDA shares them. |

## Step 2 — draft scientific qualification (unsigned)

Each row is a proposal for the Reference Authority. Keeping, changing or
rejecting it is their call.

| Decision | Proposed value | Basis |
| --- | --- | --- |
| Observation target | New inundation visible at 2024-09-15 23:16 UTC relative to 2024-09-03, inside AOI-01 | `STATUS.md` locked observation question |
| Reference imagery | Sentinel-2B L2A (or the matching L1C) above | Step 1 |
| Date tolerance | Accept 19.5 h, **optical before SAR**, for this single event only. Record that water receding between 03:45 and 23:16 UTC would show as reference-wet / SAR-dry disagreement. Report such cells as a separate "possible recession" stratum rather than silently counting them as SAR misses. | Tarpanelli et al. (2022, NHESS 22:2473) report that European flood events generally last under 3 days, so even same-day gaps can matter. UNOSAT 3969 confirms flooding was present on 15 September. |
| Independence | Optical sensor; labellers work from Sentinel-2 bands only; the SAR candidate output, SAR imagery and GFM stay hidden from Reviewers A and B until their labels are locked | Repository blind-review contract |
| Classes | `flooded`, `dry`, `permanent_water`, `unknown` | Sen1Floods11 (Bonafilia et al., CVPR-W 2020) uses −1 no-data / 0 / 1 with per-chip S1 and S2 dates. `permanent_water` is added because the benchmark labels mix permanent water into the target. |
| Unknown rule | SCL 0, 3, 8, 9 or 10 (no data, shadow, cloud, cirrus); plus any cell a reviewer marks ambiguous; plus a 20 m buffer around cloud edges | Measured AOI shares in `mae_sai_s2_observability_v1.json` |
| Permanent water | Water that is also present on the dry 5 September scene (0.877 clear), confirmed by a reviewer. JRC occurrence is an aid only. | Keeps the target "new inundation" |
| Turbid water | Interpret from false colour (B11/B8A/B4) and true colour; indices are aids only | SCL water 0.63 % against widespread observed flooding; Component ★ MNDWI finding |
| Geometry repair | Not applicable. Labels are drawn on the 10 m grid, so there are no vector polygons to repair. | — |
| Common grid | EPSG:32647 at 10 m, snapped to the Sentinel-2 T47QNC origin. The SNAP RTC output is already 10 m EPSG:32647, so only the grid origin needs checking. | `STATUS.md` SNAP graph description |
| Coverage rule | Evaluate only cells that are clear, inside AOI-01 and not permanent water. Report that fraction; the probe measured 0.7346 before any permanent-water or buffer exclusion. | — |
| Permitted evaluation purpose | Bounded single-event observation evaluation for Mae Sai only; not training, not transfer to another event | Keeps Step 4 separate from Step 5 |

If the authority judges that 19.5 hours is too long for a flash flood in this
terrain, the correct result is **reject for this purpose**. The fallback is not
to use an accumulated map.

## Step 3 — four-person blind review

Research cannot fill any of these roles. What the people will need is already
in place:

- The review package and entry points are listed in `REVIEW_PACKAGE.md` ("Human
  review sequence").
- The frozen sets are 12 hidden qualification queries and 12 retest-reserve
  queries, drawn by `label_factory` from cells that pass the unknown rule
  above.
- The Sentinel-2 bands can be packaged per query with the existing
  review-bundle contracts, keeping the SAR layers out of the A and B bundles.

The team must supply four distinct names with conflict checks: Reference
Authority, Reviewer A, Reviewer B and Adjudicator C. Availability alone is not
a receipt.

## Step 4 — draft frozen evaluation plan (unsigned)

| Item | Draft |
| --- | --- |
| Target / products | As in Step 2. Baseline: the existing 20 m amplitude comparator and the 10 m Gamma0 abstaining Otsu. No threshold may change after the reference is seen. |
| Valid cells | Step 2 coverage rule |
| Spatial partitions | 1 km blocks over AOI-01 with a 200 m exclusion halo, assigned 50/50 development/holdout by a seeded hash of block id, fixed before labels are opened |
| Metrics | Confusion counts, IoU, Dice, precision, recall, signed and absolute area error, evaluated coverage, and a boundary F-score at 20 m tolerance. The "possible recession" stratum is reported separately. |
| Acceptance limits | **Left blank on purpose; the evaluation lead must set them.** For context, calibrated per-event benchmark IoU for the radar-only tree models ranged from 0.39 to 0.92 across three held-out events, so no single literature number transfers to Mae Sai. |
| Abstention | The current candidate abstained in 81/81 windows. Report its coverage as 0 and its accuracy as "not evaluable"; do not substitute a different method after the fact. |

## Step 5 — candidate Thai episodes for a multi-event programme

Pairs from `thai_s1_s2_coincidence_scan_v1.json` with a Sentinel-2 scene no
more than about 41 h from a Sentinel-1 GRD pass and at least 30 % clear sky in
the episode box:

| Episode | Region / flood type | Sentinel-1 GRD | Sentinel-2 L2A | Gap | Box clear |
| --- | --- | --- | --- | --- | --- |
| Mae Sai 2024 | North, mountain/border river | 2024-09-15 23:16 desc. 135 | S2B T47QNC 2024-09-15 | −19.2 h | 0.73 |
| Chiang Mai 2024 | North, urban river (Ping) | 2024-10-09 23:16 desc. 135 | S2A T47QMA 2024-10-10 | +4.8 h | 0.41 |
| Sukhothai 2024 | Lower north, lowland river (Yom) | 2024-08-29 23:08 desc. 62 | S2A T47QNU 2024-08-31 | +28.9 h | 0.64 |
| Ayutthaya 2022 | Central plain (Chao Phraya) | 2022-10-23 11:29 asc. 172 | S2B T47PPR 2022-10-23 | −7.6 h | 0.82 |
| Chaiyaphum 2021 | Northeast, tropical storm (Dianmu) | 2021-09-27 23:00 desc. 164 | S2B T47PRT 2021-09-28 | +4.9 h | 0.77 |
| Hat Yai 2025 | South, urban canal | 2025-11-29 23:02 desc. 164 | S2C T47NPH 2025-12-01 | +28.9 h | 0.35 |

No usable pair was found in the scanned boxes and windows for Nan 2024,
Narathiwat 2024 or Ubon Ratchathani 2019.

Constraints before any of these counts as a qualified episode:

1. **Flood phase.** Confirm that each pair falls inside the event's wet phase.
   Chiang Mai's Ping River flood was reported to peak in early October 2024
   (about 4–6 October), so the 9–10 October pair is probably recession-phase.
   Confirm with dated hydrological records.
2. **Independence between episodes.** The Sukhothai pass of 15 September
   (relative orbit 135) is the same datatake as Mae Sai's. The table uses the
   Sukhothai 29 August pass (orbit 62) so that no Sentinel-1 datatake is shared
   between episodes.
3. **Per-episode Steps 1–3.** Each episode needs its own rights record (all
   Copernicus, so the Step 1 mapping reuses), reference decision, blind labels
   and frozen release.
4. **Method family.** The move to RF/XGBoost still needs the explicit versioned
   decision named in `ml_authorization.md`. The benchmark tie between the two
   on GRD (0.868 vs 0.869 calibrated) is not a reason to pick either.

## Step 6 — consequence evidence leads

| Lead | Status |
| --- | --- |
| UNOSAT 3969 (16 Sept 2024): inundated transportation routes along the Kok and Mekong rivers "as of 15 September" | Verified from the PDF; a district-level observation, not segment-level passability |
| Khaosod English, 12 Sept 2024: Phahonyothin Road overflow near the Doi Wao market entrance, Koh Loi community, Kok River bridge | Search summary only; the page returned HTTP 403 to automated fetch, so it is **unverified** |
| Nation Thailand article listing four temporary shelters (Mae Sai Municipality, Wat Phromwihan, Municipal School 1, Mae Sai District Hall) | **Describes a 24 May 2025 flood, not September 2024.** It cannot support 2024 shelter activation. |

Road passability, facility operation, entrances and capacity still need the
dated review described in `road_service_review_queue.md`. News leads help
reviewers find evidence but are not receipts.

## Tooling that makes the human steps fast

Added after this dossier. Each tool fails closed; none replaces a signature.

| Tool | Status here |
| --- | --- |
| `scripts/acquire_cdse_mae_sai_sentinel2_reference.py` | Ran. Recorded `blocked_missing_cdse_credentials` in `outputs/cdse_mae_sai_sentinel2_reference_acquisition_manifest.csv`. With `CDSE_USERNAME`/`CDSE_PASSWORD` set, it downloads, validates and hashes the SAFE outside Git; `--register-existing` hashes an already-downloaded ZIP. |
| `signing_forms/` | Pre-filled forms for rights (1), roles (2), the Reference Authority decision and draft procedure v2 (3), and the evaluation plan (4). Decisions, attestations, limits and identities are left blank. |
| `scripts/evaluate_mae_sai_observation.py` (`floodguard.observation_evaluation`) | Ready. Refuses to run without a frozen plan and a label release that the canonical preflight marks eligible; the final holdout also needs a verified, consumed custodian opening. |
| `scripts/build_landing_gate_status.py` (`floodguard.landing_gate_status`) | Ran. The landing page's three indicators now come from `apps/web/src/lib/landing/gate-status.json`, which only a passing validator can switch on; all three are off today. |
| 12 + 12 calibration bundles | **Not built.** The production writer requires the approved Reference Authority package and appointed roles, and it rejects optical context. The external workspace is also not on this machine. See `signing_forms/README.md`, contract gaps. |

## Presentation corrections made in this change

These fix wording on the Preview. They do not clear any gate.

Source figures come from study `c2s-ms-20260915/r1` (`summary.json`,
`downloads/results-{sar,context}-rtc-comparison.json` on `master`).

- The column "On our Mae Sai product" is renamed **"RTC benchmark transfer IoU
  (calibrated / raw)"**. It is a 46-of-111-chip matched subset from 2 of the 3
  held-out events, run with models trained on GRD.
- A separate **"Mae Sai IoU"** column shows **unavailable** for every method.
- **XGBoost** and **Random Forest** now have separate rows:
  - GRD: 0.868 / 0.801 and 0.869 / 0.816
  - RTC: 0.374 / 0.464 and 0.328 / 0.459
- Every figure is shown as calibrated / raw. The old table mixed them: it showed
  calibrated values for GRD but raw values for RTC.
- The single "Change detection" row actually combined two different baselines.
  They are now separate rows: VH-Otsu on GRD (0.233 / 0.482) and a fixed dB
  change ramp on RTC (raw 0.032).
- The tree-model description now matches the figures shown: the radar-only arm
  uses post-event VV, VH and VV−VH only. The old text described the
  terrain/land-cover arm.
- "Three held-out countries" now reads **"three held-out events"**. The frozen
  chip metadata has no country field; the names in the study summary were
  attached later from `docs/first_ml_experiment_results.md`.
- The spread line was built from mixed figures: 0.24 was a raw XGBoost value
  and 0.90 a calibrated context-arm value. It is replaced by the calibrated
  radar-only tree range, 0.39–0.92.
- The pipeline-detail rows now state raw and calibrated figures side by side.
  They also note that calibration lowered the VH-Otsu and radar-only U-Net
  scores.

## Sources

- UNOSAT, *Preliminary Satellite-derived Flood Impact Assessment, Mae Sai, Chiang Saen, and Mueang Chiang Rai Districts* (16 Sept 2024), <https://unosat.org/static/unosat_filesystem/3969/UNOSAT_Preliminary_Assessment_Report_TC20240912THA_ChiangRai_16Sep2024.pdf>
- UNOSAT 3991 on UN Thailand, <https://thailand.un.org/en/280291-satellite-detected-water-extents-13-19-september-2024-over-mea-sai-district-chiang-rai>
- European Commission, *Legal notice on the use of Copernicus Sentinel Data and Service Information*, <https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice>
- Copernicus Data Space Ecosystem OData catalogue (query recorded in `outputs/cdse_mae_sai_2024_sentinel2_metadata.csv`)
- Element84 Earth Search STAC, <https://earth-search.aws.element84.com/v1>; Microsoft Planetary Computer STAC, <https://planetarycomputer.microsoft.com/api/stac/v1>
- Tarpanelli, A., Mondini, A. C., Camici, S. (2022). Effectiveness of Sentinel-1 and Sentinel-2 for flood detection assessment in Europe. *NHESS* 22, 2473–2489. <https://nhess.copernicus.org/articles/22/2473/2022/>
- Bonafilia, D., Tellman, B., Anderson, T., Issenberg, E. (2020). Sen1Floods11. CVPR Workshops. <https://github.com/cloudtostreet/Sen1Floods11>
- Thammaboribal, P. et al. (2025). Flood mapping and damage assessment using UN-SPIDER recommended practices in Google Earth Engine: a case study of the 2024 Chiang Rai flood. *Int. J. Geoinformatics* 21(3). doi:10.52939/ijg.v21i3.4039
- Bountos, N. I. et al. (2024). Kuro Siwo. NeurIPS Datasets and Benchmarks, <https://arxiv.org/abs/2311.12056>. A CC BY multi-event SAR flood set; Thai coverage not verified.
- Nation Thailand, 24 May 2025 Mae Sai flood report, <https://www.nationthailand.com/news/general/40050383>
