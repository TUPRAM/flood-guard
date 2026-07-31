# Qualified Thai Reference and Frozen Label Release v1 status

Status as of 2026-07-23: **blocked on external evidence and qualified human
review; engineering foundation ready**.

This note defines the first P0 milestone after the shipped FloodGuard contracts,
registry, API, and Studio foundation. It is a status projection, not an
authority decision, approval, label-release receipt, operational authorization,
or official warning.

## Current decision

| Scope | Current state | What that state permits |
| --- | --- | --- |
| Source and context engineering | `processing_allowed=true` within its recorded scope | Reproducible preparation and validation of approved source/context inputs only |
| Qualified event-reference use | `processing_allowed=false` | Nothing; no qualified in-area Thai event reference is recorded |
| Controlled training or evaluation | `processing_allowed=false` | Nothing; the qualified reference, reviewer-calibration, review, and release gates have not passed |
| FPPS, A-E action class, or decision-layer use | Not allowed | No model or label output from this lane may affect these products |
| Operational use or official warning | Not allowed | `operational_authorized=false` and `official_warning=false` |

`source_processing_allowed=true` must never be read as reference validation,
training, evaluation, promotion, or operational permission. The permission is
bounded to approved source and context engineering. Every stronger use remains
false.

## Five-stage evidence sequence

| Stage | State | Recorded evidence |
| --- | --- | --- |
| 1. Engineering foundation | **Ready** | Candidate inspection, qualified-reference release tooling, blocked status projection, and fixture-only review/partition validators exist and are tested; real label-release authority and holdout custody remain separate blockers |
| 2. Qualified Thai event reference | **Blocked** | Sentinel Asia `AIT-VAP001-TH` is a real in-area event candidate, but it has not passed product-specific permission, geometry repair, independent authority, raster/grid, no-data, and permitted-use qualification |
| 3. Reviewer assignment and calibration | **Blocked** | Two independent reviewers and a separate adjudicator are not assigned; no passing calibration receipt exists |
| 4. Blind double review and adjudication | **Blocked** | No completed formal annotation set, disagreement record, or independent adjudication record exists |
| 5. Frozen label release | **Absent** | No immutable qualified label-release manifest or release checksum exists |

The checksum-bound manual QGIS geometry is real but does not change this
decision. It is nearby cross-border weak-reference calibration evidence, has no
overlap with the Thailand ADM3 candidate reporting geometry, and is explicitly
ineligible as unqualified ML labels. It is not substituted for Stage 2.

## Current in-area candidate is not yet qualified

The current evidence records Sentinel Asia `AIT-VAP001-TH` as a real flood
shapefile archive dated 14 September 2024:

- external archive SHA-256:
  `762153fe3fd22350070bb788c22f2d4e083866b5d20b1294e8ca27b97367d5d5`;
- candidate-manifest canonical SHA-256:
  `be2ce989e21f4ad3d79fe8f643ab13e7a3fc19eac1a8069bb8e83ede90878079`;
- 33,202 polygons in EPSG:32647 with EGM96 vertical context;
- 371 polygons intersect the exact Mae Sai ADM3 union;
- the intersection area is approximately 36.173 square kilometres; and
- 24 of the intersecting geometries are invalid and require an explicit,
  reproducible quarantine-or-repair decision.

These facts establish a serious in-area candidate, not qualified ground truth.
The recorded general Sentinel Asia terms allow scientific use but prohibit
modification. They do not yet resolve product-specific permission for the
rasterization, geometry repair, derived metrics, ML-label use, and retained
label artifacts required by this milestone.

Primary source records:

- Sentinel Asia event and product catalogue:
  <https://sentinel-asia.org/EO/2024/article20240910TH.html>
- Sentinel Asia site policy:
  <https://sentinel-asia.org/sitepolicy/SitePolicy.html>
- independent UNOSAT Mae Sai cumulative-water context, explicitly preliminary
  and not field validated:
  <https://unosat.org/products/3991>

`AIT-VAP003` is not bound to this manifest and must not be counted as
independent corroboration unless a separate, checksum-backed lineage comparison
is added and validated.

## Required qualified-reference record

The reference package must record and validate all of the following before
review or model work can proceed:

- exact provider and product identifier;
- source observation start and end time;
- retrieval/access date;
- immutable local artifact checksum;
- licence or written permission for local analysis, derived metrics, ML-label
  use, and the intended retention/redistribution mode;
- authority class distinguishing direct observation, qualified expert
  interpretation, weak reference, and contextual evidence;
- a separate, purpose-specific scientific Reference Authority decision with a
  detached signature, runtime-trusted key, and identity/credential distinct
  from the acquisition/legal authority;
- in-area geometry and event-window alignment;
- raster dimensions, transform, grid, CRS, geometry type, valid values, and
  no-data semantics;
- explicit `processing_allowed=true` for the qualified training/evaluation
  lane; and
- assumptions and known uncertainty or error strata.

A publicly downloadable file or a recorded checksum is insufficient by itself.
Source rights do not establish scientific authority, and scientific plausibility
does not establish permitted use.

## Required human-review record

Before annotation starts:

1. assign at least two independent reviewers and one separate adjudicator;
2. record identity, role separation, qualification basis, and conflict-of-
   interest controls;
3. freeze a qualification set and a predeclared calibration threshold;
4. calibrate each reviewer independently and require a passing signed receipt;
5. run blind double review without reviewer-to-reviewer label leakage;
6. record disagreements without overwriting either original review;
7. adjudicate disagreements independently; and
8. retain complete review and adjudication lineage in the release input.

Practice assignments and role-design templates do not count as completed
qualification, formal review, or adjudication.

## Frozen label-release gate

The immutable release must bind:

- the exact qualified reference identity and checksum;
- source timestamps and temporal window;
- grid, CRS, dimensions, transform, and no-data policy;
- reviewer-calibration receipts;
- blind-review assignments and annotation checksums;
- disagreement and adjudication records;
- final label-cell or label-raster checksum;
- inclusion, exclusion, and unknown-cell rules;
- allowed training and evaluation uses;
- release version, creation time, and signer/authority; and
- an immutable manifest checksum.

Until that release exists and validates, qualified training, calibration,
development evaluation, and final-holdout evaluation all remain blocked.

## Studio projection contract

The competition/full Mae Sai bundle carries one
`qualified_evidence_foundation` object with schema
`floodguard.qualified-evidence-foundation.v1`. The projection includes:

- a canonical SHA-256 self-hash;
- an exact binding to the blocked candidate manifest and source archive
  checksums;
- the current candidate-inspection/status-evidence time,
  `2026-07-23T12:24:48Z`;
- bundle generation time and low confidence;
- the five stage states above;
- scoped processing permissions;
- explicit blockers and ordered next actions;
- assumptions; and
- fail-closed safety flags.

The `source_timestamp` is the candidate-inspection/status-evidence time. It is
not a flood-observation time or label-creation time.

The canonical digest is computed over UTF-8 JSON with recursively sorted object
keys, compact separators, and the `canonical_sha256` field omitted. Studio
validates the shape synchronously and verifies the digest with browser
SHA-256. A missing, malformed, unverifiable, or mismatched object cannot grant
permission and is presented fail-closed.

The public Mae Sai bundle deliberately omits
`qualified_evidence_foundation`. Public-production packaging also omits the
Studio route and full staff bundle. The projection contains no private
filesystem path, source raster, reviewer identity, or provider correspondence.

## Next exact actions

1. Resolve product-specific local-analysis, rasterization, geometry-repair,
   derived-metric, ML-label, retention, and redistribution/reference-only
   permission for Sentinel Asia `AIT-VAP001-TH`.
2. Independently classify its reference authority; quarantine or repair the
   invalid geometries; then validate exact identity, checksum, timing,
   geometry, grid, CRS, temporal window, and no-data handling.
3. Assign at least two independent reviewers and one separate adjudicator under
   recorded conflict-of-interest controls.
4. Run reviewer calibration against a frozen qualification set and require the
   predeclared threshold.
5. Complete blind double review, disagreement tracking, and independent
   adjudication.
6. Freeze the immutable label-release manifest and checksum.
7. Only after all receipts validate, reconsider
   `experiment_processing_allowed`; do not infer that decision from source
   processing.

## Exit gate

The milestone passes only when all of the following are true:

- qualified-reference `processing_allowed=true` for the exact training and
  evaluation scope;
- reference identity, provenance, timing, licence, authority, checksum,
  geometry, grid, CRS, and no-data receipts validate;
- at least two independent reviewers and a separate adjudicator are qualified;
- reviewer calibration passes the predeclared threshold;
- blind double review and adjudication are complete with no unresolved
  disagreement;
- the immutable label release and checksum validate; and
- no unresolved rights, provenance, timing, CRS, reference-authority, or
  human-review blocker remains.

No outreach or approval is represented as part of this implementation.
