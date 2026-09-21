# FloodGuard Thailand — evidence, model and decision methodology

The current Mae Sai presentation starts at `/studio/brief/`. It compares explicit
access interventions and explains missing evidence. `/studio/library/` contains
the underlying source and quality review. `/studio/` retains method experiments;
`/command/` retains an earlier research workspace. A calculation appearing in
either historical workspace is not an accepted event-response priority.

This document replaces the earlier description that called all components
measured and presented the legacy GeoAI table as an accepted action list. Original
research JSON, images and calculations remain unchanged for reproducibility.
The current claim boundary is in [the finals guide](mae_sai_finals_guide.md).

## Evidence lanes

| Lane | What it establishes | What it does not establish |
|---|---|---|
| Published observation | What a source observed, within its stated time and footprint | Complete coverage, independent validation or reuse rights unless documented |
| Historical/static context | Terrain, rivers, residential population, boundaries or facility identity at their recorded vintage | Conditions or availability during the flood |
| Satellite candidate | A method-dependent interpretation of specified imagery | A validated flood mask or calibrated probability |
| Analytical scenario | The effect of a declared network, destination, demand or capacity assumption | Observed closure, safe evacuation or actual shelter demand |
| Qualified decision input | A source that passes its applicable reference, permission and evidence gates | Operational authority or an official warning |
| Archived research comparator | Earlier methods, arithmetic and limitations | Permission to replace missing accepted inputs with the old score |

Source dates, retrieval dates, release dates and event dates remain separate.
Outside an analysis footprint is unobserved, not dry. Unknown inputs remain null.

## Mae Sai observation question

The case concerns September 2024 flooding. The recorded RTC experiment uses
August 22 and September 15, 2024; the original SAFE amplitude comparator uses
September 3 and September 15. A September 15 candidate concerns the conditions
visible at that acquisition; it cannot reconstruct the month's maximum extent.
The original checksum-bound SAFE comparator uses transformed uncalibrated
amplitude. A separate legacy GeoAI archive describes a Planetary Computer RTC
workflow. These are different processing lanes and must not inherit each other's
calibration, dates, metrics or eligibility.

The public UNOSAT September publication describes a cumulative September 13–19
product and says its analysis is preliminary and not field validated. A reviewed
publication or downloadable map is useful documentary evidence. Vector geometry,
observation footprint, terms and independence still need to be established before
it can support validation. See the [UN publication](https://thailand.un.org/en/280291-satellite-detected-water-extents-13-19-september-2024-over-mea-sai-district-chiang-rai).

The October 22 single-date product is a different observation. The accumulated
August–October product has an unresolved October 12 layer-name / October 22
description conflict and no patch-level dates. It cannot yield a September-only
mask. Neither differing areas nor differing windows can be compared as if they
were the same evaluation target.

Current accepted flood-affected population, FPPS and action class remain
unavailable until their required inputs become eligible. Public-source searches
may improve this status; private agency exports are not a release dependency.

## Satellite method experiments

The isolated `services/geoai-runner/` contains the model workflows. Experiment
availability in code and a passed software test do not establish a completed,
qualified event evaluation. Inspect each run's input hashes, evaluation protocol,
reference role and eligibility before citing its metrics.

| Method | Interpretation and main limitation |
|---|---|
| Two-date SAR change | Candidate darkening/brightening under acquisition and threshold assumptions. Misregistration, terrain, vegetation and urban scattering can affect interpretation. A normalized change value is not a calibrated flood probability. |
| Temporal SAR | Historical deviations under a recorded orbit, seasonal baseline and sample coverage. Implementation does not prove a qualified current run; calibration needs suitable independent reference data. |
| U-Net / optical water | Water-index agreement under its training and held-out protocol. A weak index target is not independent event truth. Previously withdrawn metrics remain withdrawn. |
| Terrain susceptibility | Relative terrain context. It is not flood depth, observation-time inundation or an independently validated event probability. |
| Building/infrastructure experiment | Source- and resolution-dependent extraction or OSM comparison. Coverage and geometry role must be explicit; it cannot establish actual occupied population or event availability. |
| Embeddings / change methods | Exploratory methods with their own labels and coverage. Do not describe feature-derived weak targets as independent truth. |
| Deterministic narrative | A textual rendering of supplied calculations. It cannot increase their evidential status. |

Any new candidate must keep extraction, threshold selection and independent
evaluation separate. Record radiometric processing, image alignment, permanent
water treatment, nodata and coverage. Preserve the original comparator rather
than silently replacing its source or metrics. No new model training is required
for the current decision demonstration.

The archived `apps/web/public/geoai/mae-sai-real.json` explicitly declares:

```text
evidence_tier = candidate
aggregation_status = report_only
can_feed_decision_layer = false
official_warning = false
```

Its subdistrict scores and D/E labels are historical arithmetic. They are not an
exception to these assertions. Studio presents them inside a closed archive
disclosure with provenance; Command directs readers to the current brief. The
archive's recorded `generated_at` value does not establish field validation or
that all inputs share an observation date.

## Access and geographic meaning

The decision pipeline runs locally and publishes precomputed results. Report the
service explicitly: hospital, primary care, pharmacy and shelter are separate
destination sets. A pharmacy cannot satisfy hospital or shelter access. Point,
building and site geometry can identify a destination, but a supported entrance
and an accepted road connection are separate requirements. A current official
identity match does not establish operation during September 2024.

For the Mae Sai finals analysis, report Thailand-side demand and destination
scope, routing context, source vintages and any excluded population. Reporting
units are administrative-boundary intersections with the AOI. A small
intersection is not a result for the entire subdistrict. Source-boundary coverage
is a fraction of area, not a missing-population percentage.

WorldPop 2020 supplies modelled residential context. Population selection,
boundary assignment and connectors are recorded; these residents are not
automatically flood exposed or evacuation demand. Network gaps remain unknown,
not observed isolation.

Travel mode and speed assumptions accompany every result. Walking and modelled
vehicle travel have different meanings. Vehicle estimates do not establish
emergency driving conditions, compliance with one-way/turn restrictions or road
passability. Connector limits remain 100 m for facilities and 250 m for
population cells, with a recorded 5 km/h connector assumption unless a separately
versioned experiment says otherwise. Proximity alone does not justify crossing
a river, connecting different road levels or selecting an entrance.

Topology changes need source evidence and before/after population accounting.
Review high-demand disconnected components and important facility approaches;
do not connect gaps simply to obtain a stronger intervention result.

## Intervention and capacity comparisons

Compare each change with its corresponding baseline and preserve exact IDs,
input hashes, selected service and travel mode. Closures are imposed experiments
unless dated evidence establishes them. Keep the original 15/30/60-minute
thresholds; report travel-time effects and newly reachable/unreachable population
as well. Zero threshold change is a result, not a reason to tune the threshold.

Means and quantiles state their population denominator. Residents with routes in
both cases are distinct from those who gain or lose any route. A large population
with a very small delay should not be described as a large evacuation benefit.
Speed and connectivity sensitivity do not constitute statistical confidence
intervals or observed outcomes.

Capacity allocation is a separate deterministic maximum-flow calculation.
Demand limits and destination capacities prevent double counting. Report assigned,
capacity-limited, unreachable and coverage-excluded demand. Unknown actual
capacity remains null; zero is an explicit scenario assumption. An experiment
using a fraction of residential population demonstrates conditional demand, not
actual evacuation need. If access addition and capacity use the same hypothetical
site, their identity must match; otherwise present them as separate experiments.

Age-group equity requires compatible definitions, denominators, year and
geographic units. Chiang Rai's missing 2024 ages, overlapping elderly groups and
failed totals remain exclusions. The terrain/remoteness proxy is separate from
age-based vulnerability. Do not allocate provincial age shares to subdistricts
and label the result observed local counts.

## Scoring and interpretation

The original scoring contract remains:

```text
FPPS = 0.30 flood likelihood + 0.25 exposure + 0.20 access gap
     + 0.15 road criticality + 0.10 vulnerability/context
```

All components are normalized to 0–100. Missing required components yield null
accepted FPPS and null action class in the evidence assessment. They do not
become zero, and weights are not redistributed. Fixed-weight bounds and explicit
0/50/100 assumptions are sensitivity experiments. A complete low-confidence
scenario passes through the existing scorer and remains Class E regardless of
its numerical score. Capacity does not introduce another component.

An uncalibrated flood signal, residential density or terrain proxy must not be
described as a measured flood probability, observed flood exposure or age
vulnerability merely because it participates in arithmetic. Versioned scaling
anchors establish reproducible arithmetic, not validity across events.

## Reproduction and presentation

Use the evidence pipeline commands and receipts in the release handoff; they bind
the external raw input hashes, configuration, package hashes and Git SHA. Do not
run old model commands solely to refresh headline metrics. The retained
`realpipeline` experiments are separate from the public evidence build and its
allowlist.

Start a finals walkthrough with the question, service, area, time and explicit
scenario. Show population coverage, one justified comparison, its assumptions
and the evidence that could change it. Use the library for drill-down. Do not
claim current organizer criteria or presentation limits from old proposal
percentages; verify published final-round instructions separately.

See [the finals guide and claim register](mae_sai_finals_guide.md),
[the current walkthrough](demo_walkthrough.md), and the versioned Python/TypeScript
evidence contracts for the active presentation boundary.
