# THEOS-2, 17 September 2024: evidence for review of PR #69

Reviewed on 23 October 2026 against analysis commit
`7dc50d6bc8e64e005bc0d4357103f22520ae4c71` (tree
`b97f77cbfb10b6052ec93091de9cd3e29867c8d9`). This report records the existing
results and their limits. The scored stages have not been run again.

**Disposition: Q4 is complete and ready for review with caveats; Q1/Q2 are
excluded and Q3 is blocked by the rejected water reference. The four-question
programme is not complete.** The draft PR's previous description still listed
Q4 as future work, although the branch already contained its results.

This is report-only, with low confidence in interpretation: one optical image,
team interpretation of pictures, and modelled comparators. No field observation,
flood-map qualification, planning-score or action-class change follows from it.
`official_warning=false`, `can_feed_decision_layer=false`; case SE1 remains a
scenario. V-47 through V-50 still say **Waiting** for team acceptance.

## Scene and controlling records

GISTDA's four delivered products in two orders show Mae Sai on
**17 September 2024, 03:54:20 UTC (10:54:20 ICT)**, 28.6 hours after the
Sentinel-1 pass and about five days after the modelled peak. Their footprint
covers approximately 106 of the district's 305 km². Every area and road result
is limited to the ground the products cover. Other requested dates were not
delivered and have not been substituted.

The controlling documents are the [study-event plan](proposal_execution/theos2_study_event_check_plan_v1.md),
its [water-rule amendment](proposal_execution/theos2_study_event_check_plan_v1_amendment_1.md),
the [Q3/Q4 plan](proposal_execution/theos2_17sep_recession_and_mud_plan_v1.md),
and its [Q4 amendment](proposal_execution/theos2_17sep_recession_and_mud_plan_v1_amendment_1.md).
Those files and the existing analysis receipts remain unchanged. The
[review receipt](../outputs/theos2_17sep_review/review_v1.json) binds the evidence
by SHA-256 and records the verification boundary.

## Order and disposition

| Stage | Existing evidence | Disposition |
|---|---|---|
| Radar freeze | Frozen before delivery, under the study-event plan | Preserved |
| Delivery and Q3/Q4 registration | `14de6f3a`, R55 | Completed before the look |
| Reference and look | `7545598d`, R56 | Completed; water rules failed on the scene |
| Q1: radar agreement | Rejected reference; no comparison output | **NOT_RUN / EXCLUDED** |
| Q2: roads under water | Same rejected water raster | **NOT_RUN / EXCLUDED** |
| Q3: recession | R56 suspends the registered test | **BLOCKED / NOT_RUN** |
| Q4: first development and freeze | `ba637c4c`, R57 | Completed; retained as first freeze |
| Q4: amendment and second freeze | `f2923a46`, then `8d71a2ac`, R58 | Completed before test-point draw |
| Q4: 150 test points | `156d89e7`, R59 | Drawn after second freeze |
| Q4: score | `2c4a2503`, R60 | Completed once; map-use bar passed |
| Q4: section 4.5 | `7dc50d6b`, R61 | Roads, replay peak, SE1 and buildings completed once |

The original plan placed Q3 before Q4. The actual history instead records the
Q3 suspension at R56 followed by separately authorized Q4 work. This is an
explicit exception in the history, not completion of the original sequence.
No new numerical Q3 evaluation is introduced in this review.

## Q1/Q2 and Q3: the water reference failed

The [reference record](../outputs/theos2_study_event_check/reference_20240917_v1.json)
was written before any radar comparison. Rule v2 calls about 1.8 km² water in
104.9 km² of compared district ground, but the look found that much of it was
sediment, bare fields and roofs, and that it missed the brown river. Rule v1
calls about 27.4 km² water, including the town and roads. These are diagnostics
of failed rules; they are not measured flood-water areas.

The frozen rejection criterion therefore excludes this scene from Q1. Q2 was
also withheld because sediment on a road would be called water. On 23 October,
the existing `compare` command was checked and refused at the set-aside guard,
before opening the radar raster or writing a comparison output. Its nonzero
exit was the expected guard result, not a completed comparison.

Q3 is registered on that same water raster. R56 explicitly states that it is
not run until an amendment written before any Q3 figure specifies a valid basis.
The Q4 amendment does not provide that basis. The original threshold remains
**0.25 km²** of image water outside channel, permanent water and cropland on
eligible compared ground; there is no valid area to compare with it here.
The Q3 area and contradiction result are **null**, not zero or a pass.

The earlier visual look recorded no standing flood water at the inspected
scales. That is qualitative evidence and does not establish the time of
recession or satisfy the quantitative test. Neither Q4 mud nor the failed
water-rule output is substituted for water.

To resume Q3, write a separate prospective amendment specifying a defensible
water reference, its eligibility checks and exclusions before calculating any
Q3 figure. Disclose that the scene and Q4 results are already known; retain the
original test and its blocked disposition. A replacement reference has not
been chosen or authorized by this report.

## Q4: frozen mud rule and held-out label test

The original development used 160 points labelled by an AI model and retained
`mud_s0` (development F1 about 0.23). The owner-authorized amendment was written
after those scores were known and before the test points were drawn. It added
the water-before mask, a cloud-only mask and 100 m² minimum objects, with 40
new development points. `mud_s4` was then frozen on all 200 development points
(development F1 about 0.70). Development labels are not an independent reference.

The [second freeze](../outputs/theos2_17sep_mud/freeze_v2.json) precedes the
[150-point test draw](../outputs/theos2_17sep_mud/test_points_v1.json). The original
receipt records three team members as having labelled its pictures independently.
The [score](../outputs/theos2_17sep_mud/test_score_v1.json)
reports the following, area-weighted by each group and order:

| Test quantity | Existing result |
|---|---:|
| Rule-called mud labelled mud by at least two people (precision) | **0.8792** |
| Frozen minimum precision for using the map | **0.60 — PASS** |
| Labelled mud called mud by the rule (recall) | 0.6447 |
| Descriptive 95% bootstrap interval for precision | 0.7577–0.9958 |
| Precision / recall with ambiguous bare ground counted as mud | 0.8799 / 0.5804 |
| Points used in the main binary calculation | 137 of 150 |
| Three-way agreement / two-way agreement / no majority | 101 / 44 / 5 |

The threshold uses the point estimate fixed in the plan. The interval is beside
the score and does not change the criterion. Precision is agreement with the
team's labels of this image, not general flood-map accuracy. The separately
reported town-box precision is about 0.82; performance varies across the scene.
An independent arithmetic check of the existing hash-bound test key and three
label files reproduced the majority, stratum counts, main and bare-as-mud
metrics, each labeller, each pair and each order. It did not invoke the score
stage, generate another interval or change the record of the original test.

## Q4 section 4.5: what the map was compared with

The [section 4.5 receipt](../outputs/theos2_17sep_mud/section_4_5_v1.json) was
written once after the passed test. These are readings of the frozen map,
without new fitting.

**Road 1 (OSM way 206803562):** all 1,331.8 m across 15 pieces are observable.
Two pieces show mud by the fixed rule of at least 20 m of centreline within
4 m of a mud pixel. Both are closed in the modelled SE1 scenario: segment 7
has 76.8 m near mud along its 245.4 m length, and segment 11 has 25.9 m near
mud along its 32.9 m length. Across all 15 pieces, 110.6 m are near mud;
the other 13 pieces are **not shown**, not evidence of passability. Roads 6
and 8 lie outside the products and are not observable.

The 4 m radius and 20 m threshold are in the plan. The 1 m sampling, half-visible
cutoff, pixel-centre distance and building rasterization details were recorded
with implementation commit `cef3ef9c` before section 4.5 ran, after the test
score. They are not additional cutoffs registered before all results.

**District road summary:** the 53.7 of 138.9 km of model-closed roads and
95.0 of 520.4 km of model-open roads reported in R61 are the full lengths
inside the products of pieces classified `shows_mud`, divided by the full
lengths of all pieces in each model group. They are **not** the measured
metres of centreline within 4 m of mud. This review clarifies R61's wording;
the stored section 4.5 results are unchanged. The actual mud-adjacent metre
totals for the full network split by model-closed/model-open are not stored
in the receipt and are unavailable from this verification alone.

**Replay peak:** about 72% of mapped mud lies inside the modelled peak on
cells judged by the river fit, and about 39% on cells the fit did not judge.
The former is calibration-informed; only the latter is independent of the
fit's judged-cell mud target. This does not make the mud rule ground truth.
Mud outside the peak lies principally in Mae Sai and Wiang Phang Kham.

**Case SE1:** 2.4216 of 3.9552 km² (61.23%) of mapped mud in the covered part
of the district lies within the season layer. SE1 is an accumulated seasonal
scenario, not a same-time observed water extent. Bare ground and building
sites can still be false positives outside it.

**Buildings within 4 m of mapped mud:** Mae Sai 4,913 of 18,619 outlines;
Ko Chang 810 of 6,357; Wiang Phang Kham 2,904 of 20,903. These are outline
proximity counts. They establish neither indoor inundation nor affected
residents; no resident estimate is derived.

Mud supports a retrospective reading that water reached a road piece; it
gives no depth. Clearing before the image and classification error both
limit interpretation. Absence of mud never establishes that a road stayed
dry or passable. Road closures remain modelled, not field observations.

## Verification and remaining review

- **PASS:** 94 focused tests covering delivery, reference rules, record order,
  mud calculations and owner-unblocker records.
- **PASS:** 30 historical repository path/SHA-256 bindings match.
- **PASS:** the comparison set-aside guard refuses the scene before radar
  access; no comparison output was produced.
- **PASS, byte integrity only:** 67 receipt-bound external-file checks match,
  including all four delivered source TIFFs, frozen mud and reference rasters,
  sheets, keys and three scored label files. The audit covers 86 checks over
  84 unique paths, with zero missing files and zero mismatches.
- **LIMITATION:** 19 other retained-file checks have no historical expected
  digest: two look pictures, the building GeoPackage and 16 Sentinel-2 TIFF
  assets. Current hashes were captured; unchanged historical bytes cannot
  be established for those files from their receipts.
- **NOT_RUN:** new scientific evaluation, Q3, full repository/browser/production
  checks and independent field validation. No source imagery was decoded in
  this review. V-47–V-50 remain Waiting; label submission does not replace
  separate team acceptance.

The local review pack contains the external integrity manifest, arithmetic
verification, commands and review copies. It excludes imagery, sheets, label
pages, test keys and source label files. Existing evidence receipts remain
the record of the original scored runs.
