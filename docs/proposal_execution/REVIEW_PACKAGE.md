# Mae Sai independent review and evaluation package

Prepared 23 September 2026 for a qualified Reference Authority, rights owner,
Reviewer A, Reviewer B, Adjudicator C, evaluation lead and final-holdout custodian.
No role is assigned or signed by this document. It is an intake checklist and
source-bound handoff, not a qualification, label release or FPPS acceptance.

## Observation the review must decide

AOI-01 `aoi-01_mae_sai_core` uses a declared Thai reporting geometry, not the
rectangular image search envelope. The Sentinel-1 same-track pre/post acquisitions
are 3 September 2024 23:16:00 UTC and 15 September 2024 23:16:01 UTC. The latter
is a single acquisition around 16 September 06:16 Thailand time, not the complete
flood peak. See `docs/mae_sai_pair_decision_note.md` and the exact source and
processing hashes in the M2 candidate receipt. Its 81/81 Otsu windows abstained;
candidate area is null. The new thresholds are exploratory and cannot be selected
after seeing a final reference to make a positive detection.

## Source and rights decision

| Candidate | Technical evidence | Decision needed from a real authority |
| --- | --- | --- |
| Sentinel Asia `AIT-VAP001-TH` | In-area 14 September candidate, external archive SHA-256 `762153fe3fd22350070bb788c22f2d4e083866b5d20b1294e8ca27b97367d5d5`; 371 polygons intersect the Mae Sai ADM3 union, 24 invalid. Existing frozen-reference status records its lineage. | Product-specific permission for modification, repair, rasterization, retained labels, model training, calibration, final evaluation, derived metrics, hosted/download derivatives and downstream use. Decide exact observation time, spatial support, uncertainty and scientific reference class independently of acquisition rights. |
| UNOSAT 3991 | Preliminary 13–19 September cumulative PDF only on the public product page. | Obtain exact byte-backed dated extent and permitted purpose if proposed as truth; a cumulative context map cannot silently validate one SAR date. |
| UNOSAT/GISTDA 4009 local GDB | August–October accumulated layer and 12/22 October metadata conflict. | Resolve interval and layer meaning before any September reference use. |
| Copernicus Sentinel-2B L2A `S2B_MSIL2A_20240915T034529_N0511_R104_T47QNC_20240915T065143` (CDSE `f1a638d2-3b8f-4f9a-a862-1b651d6662c3`) | Optical, 2024-09-15 03:45:29 UTC, 19.5 h before the SAR post scene; research probe measures AOI-01 SCL clear fraction 0.7346. Copernicus legal notice covers reproduction, distribution, public communication and adaptation. Added 24 September 2026; see `GATE_RESEARCH_DOSSIER.md`. | Download and hash the SAFE bytes; confirm the per-purpose rights mapping; decide whether a 19.5 h optical-before-SAR gap is acceptable for this flash-flood setting. Human labels are still required. The scene is not itself a reference. |

The current evidence and blocked status are recorded in
`docs/validation/qualified_thai_reference_frozen_label_release_v1_status.md`,
`docs/proposal_execution/SOURCES_AND_RIGHTS.md` and `UNRESOLVED.md`. A public
download or checksum alone is not a scientific reference decision. If no source
qualifies, report the Mae Sai observation evaluation as blocked; do not convert
unobserved cells to negatives or use another event's accuracy.

## Human review sequence

1. The legal/acquisition owner records per-purpose permissions for exact bytes.
2. A scientifically qualified Reference Authority, distinct from acquisition
   approval, determines temporal/spatial fitness and signs the purpose-specific
   decision with a runtime-trusted key. The existing entrypoints are
   `scripts/build_label_factory_rights_clearance.py`,
   `scripts/build_qualified_reference_release.py`, and
   `scripts/build_reference_authority_approval.py`.
3. Reviewer A and Reviewer B are separate qualified people, blind to each
   other's formal labels. Adjudicator C is a third qualified person. Identity,
   conflict checks, frozen calibration set and signed passing calibration
   precede formal review. Use the existing `label_factory` human-role,
   calibration, review-bundle, consensus and adjudication contracts; practice
   fixtures do not count as formal work.
4. Freeze source, registration, grid, included/unknown/excluded cells,
   annotations, disagreements, adjudication and release signatures. Validate the
   immutable labelset with the existing release QA tools before any evaluation.
5. A separate downstream decision authority reviews exposure, road closures,
   service roles/capacity, age uncertainty and all five FPPS components. A label
   release or selected report-only model does not grant accepted FPPS or A–E.

No reviewer names, keys, decisions, dates or approval signatures are supplied
by the handoff. The required human acts remain `BLOCKED_HUMAN_AUTHORITY`.

## Frozen evaluation before final holdout

The evaluation lead must approve a machine-readable plan before final-holdout
opening: exact observation target; baseline and candidate feature versions;
reference purpose; valid/unknown/excluded cells; spatial and event partitions
with context halos; selection and calibration rules; predeclared acceptance
limits; error strata; and opening/consumption policy. Required deterministic
metrics include confusion counts, IoU, Dice, precision, recall, signed and
absolute area error, boundary error where justified, and evaluated coverage.
Only empirically supported probabilities get Brier/NLL/ECE/reliability and
abstention analysis. Intensity normalization alone does not calibrate flood
probability. The current Otsu analysis has no independent accuracy result.

The learned-model programme additionally needs at least five qualified,
heterogeneous Thai flood events split among training, probability calibration,
development and final holdout, with a genuine custodian and no event/hash
leakage. The existing controlled-experiment policy deliberately has no default
promotion thresholds. Real holdout opening is blocked until canonical file
revalidation, trusted signed custody, replay control and immutable consumption
are proven. The three-model experiment and any performance claim remain
`NOT RUN` on qualified real labels.

## Presentable result while gates are open

The competition Preview may show a clearly marked research candidate and
explicit road/service assumptions. It may say that the corrected SAR method
abstained and explain why. It must keep accepted exposure, age-equity decision,
FPPS, A–E and operational warning null or unavailable. The ten-minute pitch
should state the difference between candidate observation, imposed closure,
modelled resident and accepted historical result.
