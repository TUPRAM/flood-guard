# Reviewer A Workbench and human-workflow guide

Status: **practice and workflow guidance**  
Intended reader: I Putu Pramana Putra, proposed FloodGuard Reviewer A and project
operator  
Formal evidence status: **none created by this guide or the practice workbench**

## Read this first

The new Reviewer A Workbench is a learning tool. It gives you a much more usable
way to study the existing synthetic SAR cases, paint a 32 x 32 label grid, record
your reasoning, lock a practice attempt, and then reveal the synthetic feedback.

It is deliberately **not** the formal Mae Sai annotation system. In particular:

- it does not appoint you as Reviewer A;
- it does not open the 12-query calibration;
- it does not open any of the first 20 formal queries;
- it does not create an expert reference or a second independent review;
- it does not append anything to the canonical annotation log;
- it does not create labels that may be joined to the 874,496-row feature pool;
- it does not train the logistic/HGB query committee; and
- it does not create an FPPS, dashboard, warning, or operational flood input.

The persistent `PRACTICE ONLY` and `Formal lane locked` messages are therefore
safety information, not temporary decoration. They should remain visible while
the current formal hold is active.

The short version of your present position is:

1. You may practise now.
2. You are the proposed Reviewer A, but you are not yet an appointed formal
   reviewer.
3. Because you built and inspected parts of FloodGuard, your future Reviewer A
   lane cannot be described as completely unseen or independent.
4. You cannot also act as Reviewer B, Reference Authority, or Adjudicator C.
5. Formal work needs at least two other people: an independent Reviewer B and a
   qualified Reference Authority. The Reference Authority may also serve as
   Adjudicator C if that dual role is explicitly declared.

## 1. Why the project uses several human roles

Flood interpretation from SAR imagery contains genuine ambiguity. Darkening may
be open water, but it may also be terrain shadow or another acquisition effect.
Urban flooding can become brighter through double-bounce. Crops, wet soil,
vegetation, and small alignment differences can also change the radar return.

For that reason, one person should not create the answer, review the answer,
resolve disagreement with themselves, and then call the result independent
evidence. FloodGuard separates those responsibilities:

| Role | Main responsibility | What the role must not do |
| --- | --- | --- |
| Reference Authority | Approves the calibration design and evidence display; creates or supervises the confidential best-available calibration reference; decides how prior exposure is managed | Must not be Reviewer A or B; must not use weak-label or model outputs as calibration truth |
| Reviewer A | Independently interprets the approved evidence and labels each assigned query | Must not see the hidden reference, Reviewer B's work, weak labels, model scores, or selection reasons |
| Reviewer B | Provides the genuinely independent second interpretation | Must be a different, non-operator human and must not see A's work or prohibited evidence |
| Adjudicator C | Resolves every queued conflict between locked A and B reviews | Must not be A or B; initially sees the two human reviews without model outputs |
| Technical operator | Builds and validates packages, runs imports and QA, preserves checksums and access separation | Must not turn technical access into authority to invent human decisions or open confidential evidence early |

The data-rights owner and technical operator are governance/engineering
responsibilities, not substitutes for any of the four formal roles.

### 1.1 Your allowed designation

You may eventually serve as Reviewer A, subject to all of the following:

- your prior access to the weak mask, model results, acquisition logic, and query
  geography is disclosed accurately;
- the conflict is recorded rather than erased;
- a qualified, appointed Reference Authority approves substantive controls;
- you complete the same unseen calibration as Reviewer B;
- both reviewers pass; and
- formal work starts no earlier than the receipt's not-before timestamp.

The correct lane name is:

```text
authority_approved_mitigated_non_independent
```

That name is intentionally frank. It means your review can still be useful for a
limited research pilot, but the project must not claim that Reviewer A was fully
independent or completely unseen.

### 1.2 Roles you cannot self-fill

You cannot use another account, another browser profile, or a later repeat of
your own work as Reviewer B. A repeated self-review measures only your own
repeatability.

You also cannot be the Reference Authority or Adjudicator C for reviews in which
you are Reviewer A. You cannot create your own answer key, compare yourself with
it, and call that expert calibration. You cannot adjudicate a disagreement
between your review and another person's review.

The one permitted dual-role combination is:

```text
Reference Authority = Adjudicator C
```

That combination must be declared in the human-role package, and the person must
be distinct from Reviewers A and B.

### 1.3 Minimum future team

If you remain Reviewer A, the practical minimum team is three people:

1. **I Putu Pramana Putra — Reviewer A**, using the mitigated non-independent
   lane;
2. **one separate Reviewer B**, genuinely independent, blinded, and sufficiently
   capable of SAR flood interpretation; and
3. **one qualified Reference Authority who also serves as Adjudicator C**, with
   the dual role declared and with no Reviewer A/B assignment.

A stronger design uses four people by separating the Reference Authority and
Adjudicator C as well. The three-person configuration is the minimum allowed
combination, not automatically the strongest scientific design.

## 2. Practice and formal work are different evidence lanes

This distinction is the most important rule in the project.

### 2.1 Practice lane

Practice exists so that you can learn safely. You may:

- study VV, VH, dB change, terrain, permanent water, and land cover;
- use the 20 synthetic teaching cases;
- paint class decisions on a conceptual 32 x 32 grid;
- record confidence, ambiguity, reasoning, and time;
- lock a practice attempt before seeing feedback;
- compare the locked attempt with the synthetic answer; and
- identify personal error patterns and topics to study again.

Practice outputs remain practice even when they are correct. A high score does
not appoint you, create flood truth, or pass formal calibration.

If real Mae Sai geography is ever used for coached practice, every touched query
must be recorded in the practice-exclusion ledger and permanently excluded from
calibration, training, development, and test. Synthetic practice is preferred
because it does not consume scarce real queries.

### 2.2 Formal lane

Formal work uses rights-cleared, checksum-bound, aligned real evidence and a
versioned human-role package. Formal work requires:

- accepted and evidenced human roles;
- approved evidence-display and calibration designs;
- an unseen calibration reserve;
- a confidential fixed reference;
- separate A and B workspaces;
- real UTC start, finish, creation, and lock times;
- immutable reviewer records;
- code-generated calibration, agreement, adjudication, QA, and release receipts;
  and
- exact source, grid, protocol, taxonomy, and checksum lineage.

Nothing may be copied from the practice workbench into this lane.

## 3. Build and open the practice workbench

Run the following from the Flood Guard repository in PowerShell. The command uses
the existing synthetic case package and the authoritative formal-hold file.

```powershell
$pilot = "C:\Users\iputu\Documents\FloodGuard_external_data\label_factory\mae_sai_pilot_v1"
$createdUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

python scripts/build_reviewer_a_practice_workspace.py `
  --source-directory "$pilot\human_coordination_v2\synthetic_cases_v1" `
  --output-directory "$pilot\human_coordination_v2\reviewer_a_practice_workspace_v1" `
  --reviewer-display-name "I Putu Pramana Putra" `
  --created-at-utc $createdUtc `
  --formal-hold-path "$pilot\human_coordination_v2\FORMAL_REVIEW_HOLD.json"
```

If this repository is being run through its `uv` environment, the equivalent
launcher is:

```powershell
uv run python scripts/build_reviewer_a_practice_workspace.py `
  --source-directory "$pilot\human_coordination_v2\synthetic_cases_v1" `
  --output-directory "$pilot\human_coordination_v2\reviewer_a_practice_workspace_v1" `
  --reviewer-display-name "I Putu Pramana Putra" `
  --created-at-utc $createdUtc `
  --formal-hold-path "$pilot\human_coordination_v2\FORMAL_REVIEW_HOLD.json"
```

Open the generated page:

```powershell
Start-Process "$pilot\human_coordination_v2\reviewer_a_practice_workspace_v1\index.html"
```

The output directory is a generated practice artifact. If the builder refuses to
overwrite it, preserve the existing version and choose a new versioned directory,
for example `reviewer_a_practice_workspace_v2`. Do not delete an earlier locked
practice record merely to obtain a cleaner result.

### 3.1 What you should see

The page should identify itself with all of these concepts:

- `PRACTICE ONLY`
- `Reviewer A Workbench`
- `Formal lane locked`
- `Evidence`
- `Paint labels`
- `Review details`
- `Lock practice attempt`
- `Reveal teaching answer`
- `Export draft JSON`
- `Export practice JSON`
- `Export practice CSV`

The evidence area starts with a 2 x 2 comparison of pre/event VV and VH. Clicking
any comparison image selects it in the larger paint view. The remaining layer
buttons open VV change, permanent-water, slope, and land-cover context. The
active timer can be paused for interruptions so practice time is not confused
with total wall-clock time.

The live **Pre-lock readiness** panel must show all six items as `Ready` before
the lock button becomes available:

1. all 1,024 cells have an explicit class;
2. all eight evidence layers were explicitly visited;
3. the primary assessment is supported by the painted cells;
4. confidence is recorded;
5. at least one ambiguity reason is recorded whenever code 3 or code 4 appears;
   and
6. the reasoning note contains at least 20 non-whitespace characters.

“Explicitly visited” means selecting each named layer during that case. A
thumbnail merely being visible on the page does not satisfy the check. For a
non-mixed primary assessment, at least one painted cell must have its matching
class code. `mixed_geometry` instead requires at least two distinct painted
codes; code 255 does not count. Spaces, tabs, and line breaks do not count toward
the 20-character reasoning minimum.

These are practice-quality controls added after the first real practice attempt
exposed missing evidence visits, blank reasoning, and primary/cell-map
inconsistency. Passing the checklist is not reviewer calibration, appointment,
agreement evidence, or authorization to use the cells for training.

Stop if the page suggests that it is formal calibration, a released label, or an
FPPS input. Stop also if it reveals the synthetic answer before you lock your
attempt.

### 3.2 Recommended practice routine

For each synthetic case:

1. **Select the next case.** Work in numerical order on the first pass so that
   you do not preferentially choose easy-looking examples.
2. **Start with the four SAR panels.** Explicitly select pre-event VV, event VV,
   pre-event VH, and event VH. Do not decide from one image alone.
3. **Inspect the change panel.** FloodGuard's canonical direction is
   `pre dB - event dB`; a positive value means the event return became lower or
   darker. That is evidence, not an automatic flood label.
4. **Inspect context.** Explicitly select permanent water, slope, and land cover
   to identify plausible confounders. Context is not event-time truth. Together
   with the four SAR panels and VV change, this completes all eight visits.
5. **Choose a paint class.** Paint the 32 x 32 cells using the class meanings in
   Section 4. Mixed cases may legitimately contain several classes.
6. **Complete Review details.** Record the overall primary class, confidence,
   ambiguity tags, and a substantive reasoning note of at least 20
   non-whitespace characters.
7. **Check completeness and consistency.** Look for accidental holes, accidental
   paint strokes, and class boundaries that do not match your stated reasoning.
   Confirm that the selected non-mixed primary has at least one matching cell, or
   that `mixed_geometry` contains at least two painted codes.
8. **Clear the readiness checklist.** Read every missing item rather than using
   the lock button as a trial-and-error validator.
9. **Lock practice attempt.** Treat locking as the point at which your first
   answer is complete. Read the confirmation dialog before choosing the final
   lock button. Do not adjust it after seeing feedback.
10. **Reveal feedback.** Compare the synthetic expected pattern with the locked
   attempt. Focus on why the difference occurred, not only the final score.
11. **Write one learning note.** Examples include “I confused permanent water
     with new darkening,” “I over-trusted VV,” or “I missed steep-terrain shadow.”
12. **Export backup.** Use the page's backup function after a session. Browser
     state should not be treated as a durable research archive by itself.

Complete all 20 cases at least once. Repeat only after reviewing the error
patterns from the first pass. A second practice attempt still does not become a
second reviewer.

## 4. Per-query decision logic

The safest way to interpret a query is to ask questions in a fixed order.

### Question 1: Is the location observable?

Look for no-data, severe radar shadow, layover, failed spatial support, obvious
pre/post misregistration, or another condition that makes interpretation
unreliable.

If it cannot be interpreted, use:

```text
4 = unobservable_or_artifact
```

Do not label an uninterpretable dark area as dry or flood merely to complete the
grid.

### Question 2: Was water already present before the event?

Compare both dates and use the permanent-water layer only as context. If the
evidence supports water that was already present or normally present, use:

```text
2 = permanent_or_preexisting_water
```

For the later binary temporary-flood target, this is an explicit negative, but it
is not the same physical class as dry land.

### Question 3: Is temporary inundation supported at the event acquisition?

Look for a spatially coherent change relative to the pre-event acquisition. Open
water often darkens, while urban flooding or flooded vegetation can have a more
complex or brighter response. Check both VV and VH and consider terrain and land
cover.

If persuasive event-time inundation is supported and it was absent or materially
lower before, use:

```text
1 = temporary_flood
```

### Question 4: Is the cell observable but the meaning unresolved?

If there is a real-looking water-related or land-surface change but the evidence
cannot distinguish flood from wet soil, agriculture, vegetation, boundary,
timing, or another explanation, use:

```text
3 = uncertain_water_change
```

Uncertainty is a valid reviewed outcome. It is scientifically safer than forcing
an unsupported binary answer.

### Question 5: Is observable land unsupported as event-time inundation?

Only after ruling out the conditions above should you use:

```text
0 = dry_land
```

Dry means that the cell was reviewed, was observable, and lacked persuasive
event-time inundation evidence. It does not mean “not painted” or “outside the
weak polygon.”

### The special code 255

```text
255 = unreviewed
```

Code 255 means that no human decision was made. It is not a drawable flood class
and must never be converted to dry land. In formal work it is preserved outside
a justified partial reviewed extent.

### 4.1 Taxonomy summary

| Code | Class | Use it when | Binary temporary-flood training |
| ---: | --- | --- | --- |
| 0 | `dry_land` | Observable land has no persuasive event-time inundation | Eligible target 0 after release |
| 1 | `temporary_flood` | Event-time inundation is supported and was absent or materially lower before | Eligible target 1 after release |
| 2 | `permanent_or_preexisting_water` | Water was already present or supported as normal/pre-existing | Eligible target 0 after release |
| 3 | `uncertain_water_change` | Change is observable but its flood meaning cannot be resolved | Excluded |
| 4 | `unobservable_or_artifact` | Evidence cannot support a defensible interpretation | Excluded |
| 255 | `unreviewed` | No review decision exists | Excluded |

“Eligible after release” is essential wording. A Reviewer A record alone is not a
training label. Eligibility also needs Reviewer B, adjudication where required,
consensus construction, release QA, labelset freeze, and revalidation.

## 5. Confidence and ambiguity

Confidence is your confidence in the human interpretation. It is not a model
probability and is not automatically used as a training weight.

Use:

- **High** when multiple relevant evidence views support a coherent decision and
  important alternatives are weak.
- **Medium** when the leading interpretation is supported but one important
  limitation or alternative remains.
- **Low** when the evidence is weak, boundary-sensitive, or strongly affected by
  a confounder. A low-confidence dry/flood decision should normally prompt you to
  consider code 3.

Formal uncertain and unobservable decisions require at least one ambiguity tag.
The practice workbench also uses these tags to teach consistent reasoning:

| Tag | What it records |
| --- | --- |
| `urban_double_bounce` | Bright wall-water or structure-water response may mimic or reveal flooding |
| `urban_layover` | Building geometry has displaced or mixed the radar response |
| `radar_shadow` | Terrain or structures blocked illumination and produced a dark area |
| `steep_terrain` | Slope geometry makes the observation unreliable or difficult to compare |
| `wet_soil_or_agricultural_change` | Rain, irrigation, crop growth, harvest, or soil moisture may explain change |
| `flooded_vegetation` | Water beneath or among vegetation may create a non-simple response |
| `permanent_water_boundary` | Normal water edges, seasonal position, or mixed cells complicate the decision |
| `speckle_or_isolated_response` | The apparent signal is isolated or consistent with SAR speckle |
| `pre_post_misregistration` | The two acquisitions appear spatially displaced |
| `temporal_mismatch` | Other evidence refers to a different time from the Sentinel-1 event acquisition |
| `optical_cloud_or_shadow` | Optical context is hidden or misleading because of cloud or shadow |
| `cross_border_context` | Evidence or interpretation is affected by the included cross-border setting |
| `other` | Another explicit reason; explain it in notes |

Tags explain why a decision is difficult. They do not replace the class,
confidence, geometry, or notes.

## 6. Geometry and completeness

The formal review unit is a 32 x 32 core on the canonical 10 m output grid. The
larger surrounding tile is context only. Displayed pixels and antialiased edges
do not redefine canonical membership; rasterization uses cell-centre
containment.

In practice and later formal work:

- paint only inside the query core;
- use codes 0 through 4 for actual decisions;
- allow multiple class regions when the evidence is mixed;
- do not let two different classes claim the same cell;
- use an explicit reviewed extent if the entire core genuinely cannot be
  reviewed;
- preserve cells outside that extent as 255; and
- never assume that empty geometry means dry.

Formal rasterization fails if a completed reviewed extent contains silent,
unassigned cells. The only alternative to explicitly drawing every cell is an
explicit primary-class fill rule, which should be used deliberately and checked
before lock.

## 7. What Reviewer A may and may not see

### 7.1 Reviewer-visible evidence

An authority-approved formal bundle may provide:

- pre-event VV;
- event-time VV;
- pre-event VH;
- event-time VH;
- approved, checksum-bound VV/VH change displays;
- an approved fixed-stretch change composite;
- permanent-water context;
- DEM hillshade and slope;
- land cover;
- approved rivers, roads, settlements, or lawful timestamp-compatible optical
  context;
- the query core and surrounding context boundary; and
- acquisition times, CRS, scale, confidence limitations, and assumptions.

Static context helps interpretation but is not event-time flood truth.

### 7.2 Evidence hidden from Reviewer A

During calibration and independent first-pass review, the workbench/bundle must
not expose:

- the Mae Sai weak polygon or weak-overlap fraction;
- logistic-regression probabilities;
- boosted-model probabilities;
- committee means or threshold distance;
- entropy, disagreement, boundary impurity, or diversity scores;
- selection lane, score, rank, or recommended priority;
- the confidential calibration reference;
- Reviewer B's annotation; or
- adjudication outcomes that did not yet exist when the review was locked.

Because you also operate the project, do not open an internal operator queue for
queries that you will review as A. Technical execution should be arranged so
that prohibited fields are removed before you receive the Reviewer A bundle.
Your prior exposure can be managed and disclosed, but it cannot be made unseen
after the fact.

During calibration, the reference may be opened for scoring only after all 24
reviewer-query submissions—12 from A and 12 from B—are locked. The operator must
not inspect one reviewer's return while the other reviewer can still edit.

## 8. Formal 12-query calibration

Formal calibration asks a narrow question:

> Can these exact named reviewers apply this exact protocol consistently enough
> against the same hidden, best-available reference to begin formal review?

It does not train a model and does not prove operational flood accuracy.

### 8.1 Preconditions

Before the 12 calibration queries can be delivered:

1. All owner participation, annotation-use, attribution, retention, and
   withdrawal decisions are recorded.
2. Reference Authority, Reviewer A, Reviewer B, and Adjudicator C have accepted
   with attributable local evidence.
3. Conflicts and qualifications are documented.
4. The Reference Authority approves your mitigated non-independent A lane.
5. A pre-calibration human-role package validates.
6. The Reference Authority approves one whole-parent-tile calibration reserve,
   the fixed reference procedure, and the reviewer evidence display.
7. A new immutable grid release assigns the reserve to
   `reviewer_calibration`.
8. Twelve unseen calibration queries and separate fresh-retest capacity are
   frozen.
9. The Reference Authority creates, visually checks, and freezes the hidden
   reference without seeing A or B answers.
10. Separate A and B bundles and return locations are prepared.

Calibration queries and fresh-retest queries can never later enter training,
development, active selection, the first 20, FPPS, or warnings.

### 8.2 Reviewer execution

For each of the 12 queries, both reviewers independently:

1. confirm the correct role ID and bundle;
2. verify that the planned start time has arrived;
3. compare the approved evidence;
4. declare the reviewed extent;
5. draw every relevant class or explicitly confirm the fill rule;
6. record primary class and matching numeric code;
7. record high/medium/low confidence;
8. add required ambiguity tags;
9. record evidence layers used and assumptions;
10. record real UTC start and finish times;
11. attest that model predictions and the other reviewer were not visible; and
12. create and lock the immutable review.

Corrections use a new revision that names the superseded annotation. Earlier
bytes are not overwritten.

### 8.3 Pass thresholds

Both A and B must independently pass all of these gates:

| Calibration metric | Minimum |
| --- | ---: |
| Temporary-flood Dice | 0.75 |
| Cohen's kappa | 0.75 |
| Mean boundary F1 | 0.70 |
| Temporary-flood Dice in every declared critical stratum | 0.65 |

In beginner-friendly terms:

- **Dice** measures how strongly the reviewer's temporary-flood cells overlap the
  hidden reference flood cells.
- **Kappa** measures class agreement while accounting for agreement that could
  occur simply because one class is common.
- **Boundary F1** measures whether the flood edges are placed reasonably close
  to the reference edges.
- **Critical-stratum Dice** ensures that one difficult group—such as urban,
  steep terrain, or permanent-water boundaries—is not hidden by a good overall
  average.

If either reviewer fails, the system creates a confidential failure diagnostic,
not a passing receipt. The response is to study the failure mode on permanently
excluded practice material and use a fresh unseen retest. Do not lower the
threshold, edit the failed attempt, or reuse an exposed query as unseen evidence.

If both pass, a self-hashed calibration receipt records the exact reviewers,
queries, source/grid lineage, metrics, protocol, taxonomy, completion time, and
`formal_review_not_before_utc`. A later post-calibration human-role package must
bind that exact receipt before the first 20 can open.

## 9. The first 20 formal queries

Passing calibration permits the next gate; it does not release a labelset.

For the first 20:

1. Freeze the post-calibration role package with formal-review authorization.
2. Build separate blinded primary and secondary bundles.
3. Deliver the primary bundle only to Reviewer A and the secondary bundle only
   to Reviewer B.
4. Do not begin before the receipt's not-before time.
5. A and B independently complete and lock all 20 queries.
6. Import both returns into the shared tamper-evident annotation log.
7. Rasterize each review independently by canonical cell-centre containment.
8. Compute per-query, per-class, boundary, and critical-stratum agreement.
9. Build the machine-generated adjudication queue.
10. Send every queued item to Adjudicator C.

The first 20 use strict conflict adjudication. A conflict may be queued because
of class disagreement, geometry disagreement, reviewed-extent disagreement,
low confidence, uncertainty, or unobservability.

Adjudicator C sees both locked human records but initially no model output. C
must choose exactly one permitted outcome:

- `accept_a`
- `accept_b`
- `redraw`
- `uncertain`
- `unobservable`
- `reject`

Adjudication creates a new immutable record and never modifies A or B's source
review.

## 10. Consensus, QA, freeze, and release

After all required conflicts are resolved, the code constructs canonical
consensus cells. Direct A/B agreement is copied without invention. Adjudicated
queries follow the locked adjudication outcome. Rejected queries are omitted;
uncertain and unobservable cells retain their explicit states.

The candidate release must satisfy the stronger label-release gates:

| Release metric | Minimum or requirement |
| --- | ---: |
| Temporary-flood Dice between reviewers | 0.80 |
| Temporary-flood IoU | 0.67 |
| Cohen's kappa | 0.80 |
| Mean boundary F1 | 0.75 |
| Temporary-flood Dice in every critical stratum | 0.70 |
| Boundary metric coverage | Every formal query |
| Open adjudications | 0 |
| Required critical QA failures | 0 |

Calibration and label release answer different questions. Passing the 0.75
calibration Dice gate does not guarantee that the first-20 release reaches the
0.80 agreement gate.

Release then proceeds through:

1. code-generated consensus cells and lineage receipt;
2. code-generated release QA from the exact raw evidence;
3. an immutable, content-addressed frozen labelset;
4. immediate revalidation against every named external artifact; and
5. preservation of the negative decision/FPPS/warning safety flags.

Only codes 0, 1, and 2 from a fully released labelset can contribute to the
binary temporary-flood training table. Codes 3, 4, and 255 remain excluded.

## 11. Joining labels, training the committee, and selecting more reviews

Once a real labelset passes freeze and revalidation:

1. Join the released canonical cells to the existing 874,496-row
   `sar_change_v2` feature pool.
2. Derive eligible binary targets from the released labels.
3. Exclude calibration, uncertain, unobservable, unreviewed, grid-mismatched,
   development, and untouched-test rows.
4. Train the transparent logistic-regression baseline.
5. Train the shallow histogram-gradient-boosted challenger.
6. Evaluate with repeated grouped spatial cross-validation.
7. Score only the remaining unreviewed training/query pool.
8. Aggregate model entropy, logistic/HGB disagreement, boundary evidence,
   hard-stratum status, and diversity features to query level.
9. Select a controlled mix of active, hard-stratum, and random-control queries.
10. Build an internal operator queue and separate blinded reviewer bundles.

The operator queue may contain model and weak-label evidence. The reviewer bundle
must not. The query committee does not decide flood truth; it decides where human
review may be most valuable.

## 12. Equal-cost active-versus-random evaluation

Reviewer time must be measured honestly. Start/finish timestamps preserve audit
order, while an interaction ledger should measure active review minutes without
counting long pauses as annotation effort.

Every evaluated round needs a matched pair:

- one actively selected lane; and
- one stratified-random control lane.

The comparison is meaningful only when their reviewer cost is sufficiently
similar. FloodGuard's default equal-cost tolerance is 10 percent.

Track at least:

- review minutes;
- development IoU and Dice;
- reviewer Dice and kappa;
- boundary F1;
- flood-area bias;
- critical-stratum coverage;
- correction yield; and
- adjudication burden.

Pause active acquisition when reviewer agreement fails, important strata remain
uncovered, area bias persists, the latest costs are not comparable, an
adjudication backlog remains, or active selection fails to beat random at equal
cost for three comparable rounds.

After the method stabilizes on Mae Sai, process at least one additional Thailand
development event. Keep one future geographic event outside the accessible
development workspace until the method is frozen, then open it only once for the
untouched geographic test.

## 13. What remains held today

The current formal hold remains correct. At the time this guide was created, the
project did not have all of the following real evidence:

- completed owner decisions for participation, annotation use, attribution,
  retention, withdrawal, and outreach channel;
- accepted, evidence-backed Reference Authority, Reviewer A, Reviewer B, and
  Adjudicator C appointments;
- Reference-Authority approval of your mitigated Reviewer A lane;
- an immutable calibration-role grid release;
- an approved unseen 12-query calibration manifest and fresh-retest reserve;
- a fixed expert/adjudicated calibration reference;
- 24 locked blinded calibration reviews;
- a passing self-hashed calibration receipt;
- a post-calibration role package;
- double-reviewed first-20 labels;
- completed adjudication and passing release QA;
- a frozen and revalidated labelset;
- a real release-bound training table and trained committee;
- measured active/random review lanes; or
- additional-event and untouched-geographic-test evidence.

Therefore, do not start a real calibration or first-20 review from this practice
page. A blocked gate is an evidence-protection result, not a project failure.

## 14. Concrete checklists

### 14.1 Before a practice session

- [ ] I opened the generated Reviewer A Workbench, not the answer-key page.
- [ ] `PRACTICE ONLY` is visible.
- [ ] `Formal lane locked` is visible.
- [ ] The reviewer display name is correct.
- [ ] I understand that no practice output is formal evidence or training data.
- [ ] I have a place to record one learning note per case.

### 14.2 For every practice query

- [ ] I compared pre/event VV.
- [ ] I compared pre/event VH.
- [ ] I checked change direction and did not treat it as automatic truth.
- [ ] I checked permanent-water, slope, and land-cover context.
- [ ] The live checklist confirms that I explicitly visited all eight layers.
- [ ] I first asked whether the evidence was observable.
- [ ] I distinguished temporary flood from pre-existing water.
- [ ] I used uncertainty rather than forcing an unsupported 0 or 1.
- [ ] I painted all 1,024 cells and checked mixed boundaries.
- [ ] My non-mixed primary has a matching painted cell, or my mixed primary has
      at least two distinct painted codes.
- [ ] I selected high, medium, or low confidence.
- [ ] I added appropriate ambiguity tags.
- [ ] I wrote a rationale containing at least 20 non-whitespace characters.
- [ ] All six pre-lock readiness items show `Ready`.
- [ ] I locked before revealing feedback.
- [ ] I recorded the main reason for any disagreement.
- [ ] I exported a backup at the end of the session.

### 14.3 Before formal calibration may begin

- [ ] Owner participation and data-use decisions are complete.
- [ ] Real attributable acceptances and local evidence hashes exist.
- [ ] A and B are different humans.
- [ ] Reference Authority/C is not A or B.
- [ ] My operator exposure and conflict are fully disclosed.
- [ ] The Reference Authority approved substantive mitigation controls.
- [ ] The pre-calibration role package validates.
- [ ] The reserve, procedure, and evidence display are authority-approved.
- [ ] Twelve unseen queries and a disjoint fresh-retest reserve are frozen.
- [ ] The confidential reference was created without seeing reviewer answers.
- [ ] A and B have separate delivery and return locations.
- [ ] No model, weak-label, selection, reference, or other-reviewer evidence leaks
      into either bundle.

### 14.4 Before the first 20 may begin

- [ ] A completed all 12 calibration queries.
- [ ] B completed all 12 calibration queries.
- [ ] All 24 reviewer-query submissions are locked.
- [ ] Both reviewers pass every calibration threshold.
- [ ] The passing receipt is self-hashed and revalidates.
- [ ] Reviewer identities, protocol, and taxonomy exactly match the receipt.
- [ ] The post-calibration human-role package authorizes formal review.
- [ ] The planned start is not earlier than `formal_review_not_before_utc`.
- [ ] Separate first-20 A and B bundles were built and validated.

### 14.5 Before any model training

- [ ] Both reviewers completed every in-scope formal query.
- [ ] Reviewer rasters and agreement evidence reproduce from locked geometry.
- [ ] Every queued conflict has an independent C resolution.
- [ ] Open adjudications equal zero.
- [ ] Agreement passes the stronger release thresholds.
- [ ] Code-generated consensus, QA, freeze, and revalidation all pass.
- [ ] The training join binds the exact frozen labelset and validation receipt.
- [ ] Only released codes 0, 1, and 2 enter the binary target.
- [ ] Calibration, codes 3/4/255, development, and untouched-test rows are
      excluded.
- [ ] Query-model, decision-layer, FPPS, and warning safety fields remain fixed as
      required.

## 15. When to stop and ask for help

Stop the review rather than guessing if:

- the practice/formal status is unclear;
- a supposedly blinded page displays model scores, weak labels, a reference, or
  another reviewer;
- the four SAR panels use unclear dates, polarization, scale, or stretch;
- the query core cannot be distinguished from its context;
- a geometry tool silently fills unpainted cells as dry;
- an uncertain/unobservable decision cannot retain its ambiguity;
- the interface permits changing a locked attempt without a new revision;
- an expected checksum or role/timing gate fails;
- someone asks you to create Reviewer B or adjudicator evidence yourself;
- a failed calibration is being rewritten or its thresholds are being lowered;
  or
- anyone proposes sending label-factory output directly to FPPS or the warning
  layer.

In this project, preserving uncertainty and stopping at a failed gate is a
successful safety behaviour. The objective is not to produce the greatest number
of flood pixels. The objective is to produce evidence whose meaning, limitations,
human lineage, and allowed use are all clear.
