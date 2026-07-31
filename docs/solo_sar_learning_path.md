# Solo SAR learning path for the FloodGuard label factory

Status: learning and protocol-rehearsal guidance only.

This guide is for a solo project operator who is new to machine learning and
satellite radar. It explains how to learn the workflow without turning practice
answers into formal FloodGuard evidence. Nothing created during solo practice is
an expert reference, a second independent review, a released label, an operational
flood map, an FPPS input, or a warning.

## 1. The safety boundary

A solo operator may:

- inspect the source and processed rasters;
- learn the label taxonomy;
- complete synthetic exercises;
- rehearse drawing and uncertainty decisions in a separate sandbox;
- record personal observations and time;
- later serve as Reviewer A only after genuine calibration **and** an explicit
  Reference-Authority disposition of any prior exposure to the weak mask, model
  outputs, selection evidence, or formal-query geography.

A solo operator may not:

- use a second identity as Reviewer B;
- treat a repeated self-review as independent agreement;
- create their own answer key and call it expert truth;
- adjudicate their own disagreement as independent Adjudicator C;
- import practice records into the canonical annotation log;
- use practice cells for training, development, test, release, FPPS, or warnings.

If real Mae Sai material is ever labelled for practice, every touched query must
be permanently excluded from later calibration, training, development, and test
roles. Synthetic exercises are preferred because they do not consume scarce real
queries or contaminate the formal evidence pool.

The project operator and a formally blinded reviewer are not automatically the
same role. Prospective bundle blinding cannot erase information already seen. If
the operator has material prior exposure, record it precisely. The strongest
design is then to keep the operator as coordinator/trainee and recruit two other
humans as Reviewers A and B. A lower-budget pilot may use the operator as A only
if the Reference Authority explicitly accepts the disclosed limitation; that
lane must not be described as fully independent or unseen.

## 2. The complete data chain in plain language

```text
Sentinel-1 observations
  -> orbit correction, thermal-noise removal and Beta0 calibration
  -> terrain flattening to Gamma0 and Range-Doppler terrain correction
  -> one common 10 m grid
  -> pre-event and event-time VV/VH dB rasters
  -> change features and reviewer context
  -> two independent human reviews
  -> human adjudication of conflicts
  -> consensus, QA and an immutable label release
  -> a label-bound training table
  -> logistic and shallow boosted query models
  -> active-learning priorities compared with a random-control lane
```

The satellite supplies measurements, not flood truth. Processing makes the two
dates comparable. Context helps a human interpret the evidence. Independent human
review and adjudication create the best-available candidate reference labels;
they are not absolute ground truth. Only a released labelset may join the model
features.

The exact recorded Mae Sai sequence is:

```text
Apply-Orbit-File
  -> ThermalNoiseRemoval
  -> Calibration(Beta0)
  -> Terrain-Flattening(Gamma0)
  -> Range-Doppler Terrain-Correction with Copernicus GLO-30
  -> bilinear reprojection of linear Gamma0
  -> dB conversion
```

No explicit speckle-filtering step is recorded. Spatial coherence, paired dates,
both polarizations, masks, context, and human uncertainty handling are therefore
important; do not assume that grain-like speckle was automatically removed.

### Current project snapshot

- Two Sentinel-1 SAFE acquisitions are registered: 3 September and 15 September
  2024. The four processed SAR assets are VV and VH from each date, not four
  separate satellite scenes.
- The common grid uses 10 m output spacing in `EPSG:32647`. Grid spacing does not
  imply 10 m independent sensor detail, 10 m positional accuracy, or newly created
  10 m detail in coarser JRC or terrain sources.
- The governed canonical pool has 20 parent tiles and 854 fully supported,
  non-overlapping 32 x 32 cores.
- All 854 cores are still unreviewed and unselected. There are zero released
  training labels and zero trained real-data query-committee models.
- The canonical-grid check is ready, the weak reference is seed-only, and six
  critical readiness checks remain blocked.
- Machine fields such as `eligible_for_human_annotation=true`,
  `eligible_for_review_queue=true`, and `production_readiness_eligible=true`
  describe structural admission to a gated workflow. They do not assign people,
  authorize formal review, create labels, or make the project operational.

## 3. What each Mae Sai dataset contributes

| Dataset | What it measures or shows | What it must not be treated as |
| --- | --- | --- |
| Pre-event Sentinel-1 VV | Radar return before the target event in VV polarization | A dry-land truth map |
| Event-time Sentinel-1 VV | Radar return at the target event time in VV polarization | A flood mask by itself |
| Pre-event Sentinel-1 VH | Radar return before the target event in cross-polarization | A vegetation or flood label by itself |
| Event-time Sentinel-1 VH | Event-time cross-polarized radar return | Proof that a dark or bright cell is flooded |
| JRC Global Surface Water | Historical occurrence and seasonality of mapped surface water | Event-time flood truth or perfect permanent-water truth |
| ESA WorldCover | A 2021 land-cover category | A 2024 flood label |
| Copernicus DEM | A digital surface model used for processing and terrain context | Ground elevation truth at every cell or a water label |
| Slope and hillshade | Derived terrain shape and a visual terrain aid | Independent source measurements or flood truth |
| Layover/shadow mask | Cells where SAR geometry is unsupported or difficult | Dry land |

The weak Mae Sai polygon is positive-unlabelled evidence. Its interior may be a
weak positive hint. Its exterior is unreviewed, not dry.

## 4. Radar concepts a beginner needs

### Active sensing

Sentinel-1 is an active microwave instrument. It sends energy toward the Earth and
measures the portion returned to the sensor. It does not depend on daylight, and
clouds are usually much less obstructive than for visible imagery.

### Backscatter and dB

The return is called backscatter. FloodGuard stores calibrated Gamma0 backscatter
in decibels (dB). Values are commonly negative. A value moving from -10 dB to
-18 dB became darker or weaker by 8 dB; the fact that both values are negative does
not reverse the interpretation.

### VV and VH

- VV transmits and receives vertical polarization. It is often sensitive to
  surface roughness, buildings, and open-water contrast.
- VH transmits vertical polarization and receives horizontal polarization. It is
  often useful for vegetation and volume-scattering differences.

Neither polarization is sufficient by itself. Reviewers compare both dates and
both polarizations.

### Project change convention

For `sar_change_v2`, FloodGuard calculates:

```text
vv_change_db = pre_vv_db - event_vv_db
vh_change_db = pre_vh_db - event_vh_db
```

A positive value means the event-time return became lower or darker. That pattern
can be compatible with smooth open water, but it is not a flood decision. A negative
value means the event-time return became brighter. Flooded vegetation or urban
double-bounce can sometimes brighten rather than darken.

## 5. Common false-flood and missed-flood patterns

### Smooth open water

A smooth water surface often reflects energy away from the sensor and appears dark.
If a previously rough land surface becomes smooth water, VV and VH may drop.

### Urban double-bounce

Water next to vertical walls can create a strong wall-water reflection and become
brighter. A rule that only searches for darkening can miss urban flooding.

### Flooded vegetation

Water beneath upright vegetation can also increase structured scattering. VH and
VV may react differently, and the result need not look like open water.

### Radar shadow and layover

Steep terrain can hide the ground from the sensor or geometrically compress terrain.
Very dark shadow is not water. Layover can produce bright, displaced responses.

### Wet soil and agriculture

Rain, irrigation, crop growth, harvest, or ploughing can change backscatter without
inundation. A twelve-day pair can contain genuine non-flood land change.

### Speckle

Coherent radar produces grain-like variation. A single unusual pixel is weak
evidence. Spatial pattern and nearby context matter.

### Misregistration

If the two acquisitions are shifted, roads, river edges, and buildings can create
false change boundaries. The Mae Sai engineering diagnostic is below the current
0.5-pixel ceiling, but it is scene-correlation evidence rather than independent
ground-control truth.

### Temporal ambiguity

Sentinel-1 observes a specific moment. Water may have risen or receded before or
after the acquisition. A report that an area flooded during the wider event does
not prove it was inundated at the exact satellite time.

## 6. The six label states

| Code | Stored class | Beginner interpretation | Binary training treatment |
| ---: | --- | --- | --- |
| 0 | `dry_land` | Observable land with no persuasive event-time inundation | Negative only after release |
| 1 | `temporary_flood` | Persuasive event-time inundation absent or materially lower before the event | Positive only after release |
| 2 | `permanent_or_preexisting_water` | Water was already present or is normal water | Negative but retained as a separate error slice |
| 3 | `uncertain_water_change` | Change is visible but its flood meaning cannot be resolved | Excluded |
| 4 | `unobservable_or_artifact` | No-data, shadow, layover, failed evidence, or an uninterpretable cell | Excluded |
| 255 | `unreviewed` | No human decision exists | Excluded |

Codes 3, 4, and 255 are not alternative spellings of dry land. Preserving these
states is one of the most important safeguards in the project.

## 7. How to reason through one 32 x 32 query

A 32 x 32 core contains 1,024 cells and covers 320 x 320 metres at 10 m output-
grid spacing. A reviewer may view a larger halo for context, but only the core is
labelled. Cell spacing is not the same as independent spatial detail or geolocation
accuracy.

Use this sequence:

1. Confirm the acquisition dates, event, polarization, CRS, and query boundary.
2. Check no-data and layover/shadow support before interpreting darkness.
3. Inspect pre-event VV and event-time VV with the same display stretch.
4. Inspect pre-event VH and event-time VH with the same display stretch.
5. Inspect the change layers, remembering that positive project change means the
   event image became darker.
6. Inspect historical water, land cover, slope, and hillshade as context only.
7. Ask whether the pattern is spatially coherent and physically plausible.
8. Look specifically for urban double-bounce, terrain shadow, agriculture, speckle,
   and boundary misregistration.
9. Draw only what the evidence supports.
10. Use uncertain or unobservable rather than forcing a dry/flood decision.
11. Record assumptions and the real time spent.

Example: a low-slope river-adjacent patch becomes much darker in both VV and VH,
was not historical water, and has a coherent boundary extending from the river.
That is persuasive temporary-flood evidence. In a broader future pool, a similar
dark patch on a steep backslope inside a declared shadow mask would be
unobservable/artifact instead. The present 854-core allowlist already excludes
cores with declared layover/shadow-mask cells, but a reviewer may still identify
an unflagged artifact or see masked terrain in the surrounding context.

## 8. Learning phases and exit checks

### Phase 0 - Safety mental model, 1 to 2 hours

Learn why selection is not truth and why the tool is not an official warning.

Exit check: explain why uncertain, unobservable, and unreviewed cannot become dry.

### Phase 1 - Raster and geography basics, 2 to 3 hours

Learn pixels, bands, CRS, UTM zone 47N, affine grids, no-data, storage tiles, query
cores, and the difference between a cell centre and a displayed raster edge.

Exit check: explain why two rasters with the same width can still be misaligned.

### Phase 2 - SAR interpretation, 3 to 5 hours

Learn VV, VH, dB, darkening, brightening, speckle, double-bounce, flooded
vegetation, wet soil, shadow, and layover.

Exit check: name at least five confounders and explain when to use code 3 or 4.

### Phase 3 - Taxonomy and geometry, 2 to 3 hours

Practice non-overlapping class geometry, complete reviewed extents, explicit
uncertainty, and boundary placement.

Exit check: complete a synthetic core without overlaps or silent unreviewed cells.

### Phase 4 - Synthetic guided practice, 12 to 20 cases

Attempt each case before seeing its synthetic answer key. Record the reason for
every error and repeat with new cases. This measures learning, not real flood-map
accuracy.

FloodGuard includes a deterministic conceptual exercise generator:

```powershell
uv run python scripts/build_synthetic_sar_learning_cases.py `
  --output-directory <external_data_workspace>/label_factory/learning/synthetic_cases_v1 `
  --created-at-utc <timezone-aware-UTC-timestamp>
```

Open `index.html`, record the first attempt, and only then open
`answer_key/index.html`. The cases illustrate darkening, urban double-bounce,
terrain/shadow, flooded vegetation, agriculture, permanent water, ambiguity,
misregistration, unobservable support, boundaries, and multiclass completeness.
They are normalized teaching diagrams, not a physical Sentinel-1 simulator, real
event evidence, calibration, training data, FPPS input, or warning evidence.

### Phase 5 - Real-data orientation without labels

Inspect the full Mae Sai rasters with fixed stretches. Hide weak labels, model
outputs, acquisition scores, and formal query identities. Do not save formal class
geometry.

Follow `docs/real_data_ml_learning_guide.md` in its default
`reviewer_a_safe` lane. Aggregate SAR-change analysis is allowed, but opening
weak overlap, query priorities, or row-level model scores changes the operator's
prior-exposure status and can disqualify later blinded review of those queries.

Exit check: describe likely evidence and confounders without claiming truth.

### Phase 6 - Expert-coached scratch practice

After recruiting a SAR-flood expert, use a separate permanently excluded practice
set for qualitative feedback. Repeated self-review is only intra-person
consistency; it is not Reviewer B.

### Phase 7 - Formal calibration

Use 8 to 12 unseen `reviewer_calibration` queries with a fixed expert/adjudicated
reference. Both real reviewers work independently. Current minimums are temporary-
flood Dice 0.75, Cohen's kappa 0.75, mean boundary F1 0.70, and critical-stratum
Dice 0.65.

### Phase 8 - First 20 formal queries

Double-review all 20, send every conflict to a different adjudicator, and measure
reviewer and adjudication time.

Calibration passing is not label-release passing. The current thresholds are:

| Gate | Temporary-flood Dice | IoU | Kappa | Mean boundary F1 | Critical-stratum Dice |
| --- | ---: | ---: | ---: | ---: | ---: |
| Reviewer calibration | 0.75 | not a calibration gate | 0.75 | 0.70 | 0.65 |
| Candidate label release | 0.80 | 0.67 | 0.80 | 0.75 | 0.70 |

The first line asks whether a named reviewer is ready to begin formal work. The
second asks whether paired, adjudicated evidence is strong enough to release a
labelset. Passing calibration never guarantees that the later labelset will pass.

### Phase 9 - ML literacy after label release

Learn features versus labels, spatial leakage, spatial-block validation, logistic
regression, shallow gradient boosting, entropy, committee disagreement, diversity,
and matched random-control review. Use the locked model sections in
`docs/real_data_ml_learning_guide.md`; they must remain blocked until a verified
release-bound training table exists.

## 9. Why two reviewers and an adjudicator are necessary

One person has consistent blind spots. Repeating the task later can measure personal
stability but not independent agreement. Two independent reviewers expose ambiguous
instructions, unclear evidence, and systematic interpretation differences. A third
qualified adjudicator resolves conflicts without silently preferring either source.

A practical minimum team is:

- two distinct calibrated reviewers, at least one of whom is independent and
  SAR-capable; and
- one senior reference authority who may also serve as Adjudicator C if this dual
  role is declared and that person is not Reviewer A or B.

For the strongest blinding claim, both reviewers are people other than the project
operator. For a constrained pilot, the operator may be proposed as Reviewer A
after training, calibration, a complete prior-exposure declaration, and explicit
Reference-Authority approval of the resulting limitation. Until those records
exist, the operator remains a candidate, not an appointed formal reviewer.

Good low-budget recruitment targets include a remote-sensing faculty member and a
graduate student, or a qualified SAR-flood consultant. A generic ML practitioner
without SAR interpretation experience is not a substitute for the reference role.

## 10. Metrics without the jargon

- Dice asks how much the two flood areas overlap, relative to their combined size.
- IoU asks how much they overlap relative to their full union and is usually lower
  than Dice for the same pair.
- Boundary F1 asks whether the drawn edges are close, even when area overlap looks
  acceptable.
- Cohen's kappa measures agreement beyond what class prevalence could produce by
  chance.
- Area bias asks whether one method systematically maps too much or too little
  flood.
- Raw accuracy is dangerous in mostly dry regions because predicting every cell as
  dry can look numerically strong while finding no flood.

## 11. What the first ML models will and will not do

The logistic baseline learns a weighted, inspectable relationship between released
features and released labels. A shallow boosted model can learn modest nonlinear
interactions. Their committee will rank which unlabelled queries are most valuable
for humans to inspect using uncertainty, disagreement, and diversity.

The committee does not create truth. An actively selected query still receives two
independent human reviews and, when needed, adjudication. Its efficiency must be
compared with a matched stratified-random lane at equal reviewer time.

## 12. Formal-evidence checklist

Before any real model training, verify all of the following:

- source rights and exact attribution conditions are recorded;
- the processing/alignment receipt passes;
- a qualified reference authority approves an expert/adjudicated reference;
- two distinct reviewers pass the same blinded calibration;
- formal reviews start after the calibration receipt's not-before timestamp;
- every required conflict is adjudicated by a different qualified person;
- consensus, release QA, labelset freeze, and revalidation all pass;
- the training table binds the exact frozen labelset and `sar_change_v2` schema;
- the output remains query-model-only and ineligible for decision, FPPS, or warning
  use.

Stopping at a failed or missing gate is a correct result. It protects the project
from learning a confident model from uncertain evidence.
