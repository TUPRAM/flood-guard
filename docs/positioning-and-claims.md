# FloodGuard Positioning And Claims

Stage 1 implementation record, September 12, 2026. This is a source-backed
local claims boundary, not agency authorization, human design approval,
formative user research, scientific acceptance, or deployment approval.
The supplied review is design input; its descriptions of older published
screens were rechecked rather than assumed to describe this checkout.

## Positioning

FloodGuard is a flood-planning prototype that connects flood evidence with
communities, road networks, and essential services, helping users examine
potential access disruption and understand why an area may need attention.

The page must separate three levels:

1. **General problem:** flood exposure and loss of access are different questions.
2. **Illustrated concept:** one explicitly synthetic home-to-facility network demonstrates an assumed interruption, its consequence, and a reviewable planning question.
3. **Available historical demo:** the current Mae Sai candidate package, its bounded planning views, source dates, and evidence limitations.

The illustrative scene is not a historical reconstruction, a current road
closure, an observed household, or an interactive scenario feature available
inside the published planning workspace. The concept may explain a method
without pretending to execute that method for a visitor's location.

## Audit Basis

- Source checkout: the isolated `fg-landing` worktree; the original Documents checkout was not edited.
- Browser audit: existing local competition development server, `/public/`, `/command/`, and `/studio/`, English display preference, fresh disposable browser contexts.
- No report submission, household-plan modification, geolocation, operational mutation, or external API configuration was performed.
- Actual workspace data came from the committed same-origin offline bundle and geospatial JSON files; no `/api/v1/` request was observed during this audit.
- Raw text, controls, GET requests, browser exceptions, and location-call count are recorded in `apps/web/test-results/landing-v4/product-captures/product-audit.json`.
- The route components themselves were inspected, not inferred from screenshots alone.

## Claim Matrix

| Proposed benefit | Current screen or artifact | Maturity | Required qualification | Honest CTA |
| --- | --- | --- | --- | --- |
| Understand why a dry home can still lose a useful connection | New controlled illustrative story; stable household, road link, and facility identities | Illustrated concept | Synthetic scenario. One link is assumed disrupted, not observed closed. Facility operation and other options are not confirmed. | How it works, to the story's real connection anchor |
| Inspect historical area priorities and their reasons | `/command/`: eight ranked areas, map selection, FPPS, source time, confidence, modelled access/equity summaries, planning-action text | Available in this local demo | Historical candidate, low confidence, planning only. Do not present scores as verified urgency or a current emergency ranking. | Explore the planning demo -> `/command/` |
| Inspect road, facility, and access context | `/command/` layer controls; `offline-demo/mae-sai/roads.json`, `facilities.json`, `access-hotspots.json` | Available context, not verified operational status | Road evidence inherits area summaries; per-segment risk/current road status remain unavailable. Facility roles, operation, capacity, and accessibility need confirmation. | Inspect planning context -> `/command/` |
| Examine assumptions behind access estimates | `/command/`, Facilities & access and Data & method tabs; `command-workspace.tsx` | Available in this demo | Nearest-facility/selected-facility shortest-path threshold analysis, not capacity-aware service availability or verified safe routing. | Review the planning evidence -> `/command/` |
| Change a road closure or temporary-facility scenario interactively | Scenario code exists behind runtime/data gates, but current offline Mae Sai view exposes a disabled Baseline selector | Not available in this published-view configuration | Say the landing animation is illustrative. Do not promise a scenario editor or comparison tool at this destination. | No capability-specific CTA; use Explore the planning demo with limitation nearby |
| Build and review a household preparedness plan | `/public/`, Prepare tab; `household-plan-builder.tsx`, `use-household-plan.ts` | Available local-device feature; read-only builder view inspected | A broad planning area is not an exact household location. Local-device plan/checklist, not evacuation instructions, verified safe routing, or guaranteed preparedness. | Open Public preparedness -> `/public/` |
| Review locally saved needs, tailored actions, and bilingual plan options | Public Prepare builder and text-export implementation | Implemented; controls/source inspected without changing a household plan | No account, exact address, medical diagnosis, or named household is needed by this builder. A completed checklist is not proof of safety. Do not imply the capture contains a submitted or completed plan. | Open Public preparedness -> `/public/` |
| Find a verified operating shelter or live safe route | Public filters exclude unconfirmed emergency roles; committed shelters list is empty | Not substantiated as current availability | Do not infer safe/open status from OSM identity, a gray road, or a planning symbol. Follow current official/local instructions. | No landing promise of nearest safe shelter or live evacuation navigation |
| Inspect a specific historical evidence record and its unresolved gates | `/studio/`: exact active context, source components, decision matrix, Data quality, Governance, Files & history | Available read-only evidence report | Current context has no qualified evaluation and no operational authorization. A checksum proves record integrity, not accuracy. | Inspect the evidence -> `/studio/` |
| Explain a planning finding with its reason, uncertainty, and next review step | New synthetic finding panel; actual Command summary/verification views as a separate product example | Illustrated concept plus an available, explicitly limited product view | Label the illustrative finding at point of display. No invented Mae Sai quantities or claim that a new scenario finding was computed by the current published workspace. | Illustrative finding -> See the historical planning demo; historical context -> Inspect the evidence |
| Deliver verified predictive accuracy, operational impact, or real-time warnings | Current evidence record explicitly blocks authorization and has no bound qualified model evaluation | Unsupported | Do not claim validated case study, live warning service, rescue coordination, agency endorsement, automatic deployment, or measurable impact. | None |
| Outperform all existing flood-map systems or provide a unique worldwide solution | No current comparative evaluation or deployment coverage evidence inspected | Unestablished | Describe the intended integrated workflow, not exclusive superiority or global operational readiness. | None |

## Important Corrections To The Supplied Review

The review's statement that road/facility/access layers are unavailable does
not describe the current local bundle. The live local Planning screen shows
4,458 road-network context segments, 42 facilities to verify, and access
evidence. The underlying road evidence gate is still blocked for
segment-raster intersection, and the facility verification gate is blocked.
**Available geometry is not available verified road status.**

The review's scenario-comparison limitation is still correct. The actual
selector is disabled and the page states that scenario comparison is not
included in this published planning view. API/fixture paths in the repository
do not make that capability available in the static competition demo.

An existing separate GeoAI research panel below Command uses a different
result stream from the main historical candidate. For Ko Chang, the inspected
main view showed FPPS 53.6, class E, low confidence, while the separate GeoAI
panel showed 44.0, class D, medium confidence. The landing must not merge
these into one validated result or promote the GeoAI panel's numerical
metrics as accuracy for the canonical Studio context. This discrepancy is
documented, not silently repaired within the landing scope.

## Historical Evidence Identity

The current default Studio evidence context is:

```text
evidence_context_id: mae-sai:2024-09:mae-sai-candidate-2024-09-15-v1
evidence_package_id: mae-sai-historic-planning-2024-09-v1
data_version: mae-sai-candidate-2024-09-15-v1
dataset_mode: candidate
operational_status: non_operational
model_run_id: null
evaluation_sha256: null
decision: blocked
operational_authorized: false
```

The record lists four blockers: no qualified Thailand event-flood reference
evaluation, unverified facility roles/current operation, area-summary road
evidence rather than segment-raster intersection, and no agency operational
acceptance. The displayed source time is September 16, 2024, 06:16 ICT,
corresponding to September 15, 2024, 23:16:01 UTC.

The evidence section must label source times independently:

| Source | Date or temporal meaning | Permitted explanation |
| --- | --- | --- |
| Sentinel-1 historical flood context | September 15, 2024, 23:16:01 UTC | Historical acquisition, not current conditions or peak-extent proof |
| Separate GeoAI SAR pre/post comparison | August 22 to September 15, 2024 | Research processing context; not a bound qualified evaluation of the canonical candidate |
| Sentinel-2 optical context image | February 18, 2024 | Optical context, not a simultaneous September flood image or an observed before/after pair |
| WorldPop | 2020 publication year | Historical population context, not a live resident count |
| HDX COD-AB | January 22, 2022 valid-from field | Reporting boundaries |
| OSM/Geofabrik | July 9, 2026 extract time | Roads/facility mapping context; not September 2024 or current operational confirmation |
| Copernicus DEM GLO-30 | Observation timestamp unknown in the record | Terrain context; do not invent a date |

The source bundle marks some freshness relative to its July 20, 2026 audit.
Do not reuse that `current` label as a claim of freshness on a later date.

## Destination And Capture Contract

- `/public/` is the actual entry route. Prepare is a button-driven local tab, not a routed `/public/prepare` page or a functional `#prepare` deep link. Do not invent those destinations.
- `/command/` opens the actual historical planning view. The initial ranked-area selection and tab controls are available; no area-specific URL contract was verified.
- `/studio/` opens the default canonical Mae Sai context. The Files & history tab reveals the evidence record, but tab IDs are not routed tab selection. A hash pointing to an inactive panel does not activate it.
- Product imagery must remain actual screen capture. No replacement numbers, inserted success states, synthetic resident records, omitted qualifiers that reverse meaning, or composited screenshots presented as a working UI.
- Household screenshots show the empty, unreviewed builder. A generated local display nickname is not a real participant; crop the irrelevant header rather than inventing a persona.
- Planning crops should keep low-confidence/modelled labels and the unavailable-scenario explanation. Do not use the separate GeoAI metrics panel as the landing's planning-output proof.
- Studio crops should retain the context ID, no-qualified-evaluation scope, and not-authorized state. Use the visible evidence decision matrix or Files & history record, not a fabricated pass badge.

## Implementation Acceptance Boundaries

Every major story transformation must answer a new question: identify the
dependency, distinguish flood evidence from assumed disruption, show the
modelled consequence, then expose the finding/reason/uncertainty/review step.
The scene dataset must be separate from the historical bundle. Color cannot
be the only distinction between these states.

Static frames and automated/manual local browser checks can establish an
implementation candidate. They cannot substitute for formative testing with
unfamiliar people or external owner/agency approval. Those remain explicitly
not performed unless separate evidence is supplied.

## Source Pointers

- `apps/web/src/components/command-workspace.tsx`: scenario gates, layer availability, modelled result labels, access-method limitations, and separate GeoAI panel.
- `apps/web/src/components/public-experience.tsx`: local Prepare navigation and confirmed-facility projection.
- `apps/web/src/components/household-plan-builder.tsx` and `apps/web/src/lib/household-plan.ts`: plan interaction/export semantics and safety boundaries.
- `apps/web/src/components/studio-workspace.tsx` and `apps/web/src/lib/studio-evidence.ts`: exact-context checks and explicit evidence decision states.
- `apps/web/src/lib/data-provider.ts` and `apps/web/src/lib/public-data-provider.ts`: API versus same-origin bundle behavior.
- `apps/web/public/offline-demo/mae-sai/bundle.json`: current canonical candidate, evidence record, source components, layers, readiness, and blocked model projection.
- `apps/web/public/geoai/mae-sai-real.json`: separate research outputs and February optical / August-September SAR dates.
