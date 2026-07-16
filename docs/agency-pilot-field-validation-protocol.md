# ระเบียบตรวจสอบภาคสนาม / Field validation protocol

Protocol version: `field-validation-v1`
Scope: bounded agency pilot, named event and study area only

## 1. Safety and authority

Field work must be authorized by the responsible agency and led by personnel
trained for the local hazard. FloodGuard never directs a person into floodwater,
onto a closed road, or through an unsafe area. Teams follow agency incident
command, weather, access, communications, and stop-work rules.

Do not collect names, phone numbers, faces, vehicle plates, medical information,
or household-level vulnerability data in the public validation artifact. If an
agency needs identifiable records, store them in its approved system and link
only a redacted receipt ID.

## 2. Preconditions

Before sampling, freeze and hash:

- official pre-event and post-event product manifests;
- processed feature stack and transform sidecar;
- qualified reference-mask receipt;
- model checkpoint and inference manifest;
- probability raster and trusted zonal receipt;
- reporting-area geometry;
- spatial holdout polygons;
- map and candidate-site package used by field teams.

Stop if licensing, product identity, timing, grid alignment, checksum, or
reference-mask status is unresolved.

## 3. Sampling design

Create immutable sampling strata before visiting sites:

1. high, medium, and low predicted flood probability;
2. mapped permanent water and non-permanent-water contexts;
3. urban, agricultural, forested, and steep-terrain contexts where present;
4. road, bridge, facility, and open-land evidence classes;
5. spatially separated holdout areas not used for model fitting or threshold
   selection.

Record the random or systematic selection seed, inclusion criteria, replacement
rules, target count per stratum, and unvisited-site handling. Convenience sites
may be recorded as qualitative evidence but must not replace the prespecified
sample.

## 4. Observation record

Each field observation uses a pseudonymous `observation_id` and records:

- sampling-stratum and holdout IDs;
- UTC observation time and permitted positional precision;
- observed class: flood, not flood, permanent water, uncertain, or inaccessible;
- observation method and evidence source;
- estimated water extent/depth only when the approved method supports it;
- temporal mismatch from the satellite acquisition;
- visibility/obstruction and uncertainty;
- reviewer role and second-review status;
- exclusion reason when unusable.

Photographs remain in the agency evidence store. Public receipts contain only a
checksum and redacted evidence ID.

## 5. Reviewer calibration

Before the main review, all reviewers independently label the same calibration
set. Record agreement and adjudication outcomes. Proceed only when the approved
calibration threshold is met. Keep calibration sites out of the untouched model
holdout unless the validation plan explicitly reserves them for evaluation.

Disagreements use these categories:

- temporal mismatch;
- permanent water;
- steep terrain or radar shadow;
- urban double bounce;
- vegetation or canopy obstruction;
- mixed pixel or boundary ambiguity;
- inaccessible/unsafe site;
- source or coordinate error;
- other, with a bounded note.

## 6. Comparison and reporting

Join observations to the frozen prediction by the approved spatial tolerance.
Report, for the untouched spatial holdout and each material stratum:

- IoU and Dice/F1;
- precision and recall;
- signed flooded-area error ratio and absolute flooded-area error ratio;
- Brier score;
- calibration curve and expected calibration error;
- confusion counts;
- missing/unvisited/excluded counts;
- error-category counts and examples;
- temporal and geographic limitations.

No threshold may be retuned on the final holdout. If a threshold changes, issue
a new model/data version and repeat evaluation on a new untouched holdout.

## 7. Field-validation receipt

Generate a canonical JSON receipt containing:

- `protocol_version = field-validation-v1`;
- study area, event ID, data version, and observation window;
- input/product/model/probability/zonal/geometry manifest SHA-256 values;
- sampling-plan and holdout SHA-256 values;
- observation and exclusion counts by stratum;
- reviewer-calibration result and evidence checksum;
- metric summary and error-category summary;
- safety incidents or stop-work events;
- data-protection and licensing confirmation;
- Thai and English reviewer decision;
- issue time and expiry/review date;
- redacted accountable-role IDs.

Hash the canonical receipt. The agency acceptance manifest binds this SHA-256;
changing any field requires a new field-validation and acceptance receipt.
The field receipt review window may not exceed 30 days. An expired, future-
dated, scope-mismatched, incomplete, rejected, or byte-substituted receipt is
not eligible for acceptance signing.

## 8. Stop conditions

Stop validation or withhold acceptance when:

- a site is unsafe or incident command suspends field work;
- sample replacement breaks the prespecified design;
- reviewer calibration fails;
- product/geometry/checksum lineage changes;
- the holdout was used for training or threshold selection;
- metrics or error categories exceed agency-approved limits;
- significant errors cluster around essential facilities, bridges, or isolated
  populations;
- privacy, licensing, or custody cannot be demonstrated.

The correct result of a failed or incomplete protocol is `planning_only` or
`non_operational`, with a recorded blocker—not a weakened acceptance criterion.
