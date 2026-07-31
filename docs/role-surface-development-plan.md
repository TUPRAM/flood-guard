# FloodGuard role-surface development plan

## Purpose and product boundary

FloodGuard has one governed decision engine and three role-specific product
surfaces. They share versioned artifacts, provenance, source time, confidence,
assumptions, and fail-closed model gates, but they do not share the same task
hierarchy.

```text
qualified or fixture inputs
        |
        v
tested FloodGuard decision engine <- isolated GeoAI integration receipts
        |
        v
FastAPI contracts / validated offline bundle
        |
        +----------------+------------------+
        |                |                  |
        v                v                  v
 /public            /command           /studio
 household          area planning      evidence review
 preparedness       and comparison     and promotion gates
```

The default demo remains `fixture_demo`, `non_operational`, and
`official_warning=false`. None of the three routes is an official warning,
live evacuation, or guaranteed real-time detection service.

## Milestone 1 — proposal role-surface pass

Status: implemented and covered by component, interaction, offline, and visual
tests.

### Public preparedness

- The first mobile viewport leads with **Build my household plan**, an explicit
  not-an-official-warning notice, an official DDPM update link, and official
  hotline actions.
- The household plan stores only a broad fixture planning-area identifier,
  checklist booleans, planning-needs booleans, and a review timestamp in local
  browser storage. It does not request an address, account, personal name,
  precise location, or medical diagnosis.
- The plan can be marked reviewed, reset, cleared, printed, and downloaded as a
  bilingual text copy.
- FPPS and action-class details remain available under a secondary evidence
  disclosure instead of dominating the citizen home screen.
- Empty or malformed area data fails closed while the general preparedness
  checklist remains usable.

### Shared geographic map

- A reusable selected-area bottom sheet synchronizes map selection, class,
  FPPS, confidence, source time, and server-produced scenario delta.
- A committed, explicitly synthetic context layer adds a river, drainage,
  principal-road, settlement, and candidate-facility frame without relying on
  an external tile provider.
- The map retains a complete accessible text alternative and labels fixture
  geometry as synthetic and not an administrative boundary.
- Context is included in the static bundle, service-worker cache, snapshot
  contract, offline bundle builder, and offline smoke tests.

### Planning command center

- The 1024 x 768 layout uses a two-column map/control workspace with a visible,
  open-by-default evidence drawer kept within the viewport.
- Area selection remains synchronized across the selector, ranked list, map,
  drawer, scenario strip, and full decision panel.
- Scenario fills and comparison evidence use only the exact values in
  `scenario_results`. The browser maps negative access-loss deltas to an
  improvement tone, positive values to a worsening tone, and zero to neutral;
  it does not recompute access, equity, FPPS, or A-E class.
- Baseline and selected scenario access/equity values, exact server delta,
  provenance, assumptions, downloads, and the unchanged score components are
  visible in the evidence workflow.

### Research studio

- The route is organized as a compact research console with a run rail,
  evidence-scope navigation, data gates, model matrix, selected model card,
  validation categories, and pilot-readiness boundary.
- Three independent states are shown above the fold:
  **Integration smoke**, **Qualified real-data evaluation**, and
  **Decision eligibility**.
- A valid synthetic receipt may prove integration execution while qualified
  evaluation remains `not_run` and decision eligibility remains blocked.
- A qualified comparison requires official inputs plus baseline, weak-label,
  and GeoAI runs with qualified masks, immutable spatial holdouts, processing
  gates, and the complete metric set. Synthetic or candidate metrics cannot be
  presented as real-event accuracy.

## Verification contract

Every role-surface change must retain all of the following:

1. Route component tests for hierarchy and evidence boundaries.
2. Pure tests for household-plan parsing, scenario presentation, and Studio
   evidence-scope classification.
3. Browser interactions covering household-plan persistence, map/area
   synchronization, command scenario synchronization, tablet drawer geometry,
   and Studio run selection.
4. Static build plus offline navigation of `/public`, `/command`, and
   `/studio` with zero external network requests.
5. Visual QA at 390 x 844, 430 x 932, 1024 x 768, 1440 x 900,
   1536 x 1024, and 2048 x 1152.
6. No private paths, unsupported live claims, missing source/confidence state,
   clipped map controls, sub-44-pixel interactive targets, horizontal overflow,
   or color-only scenario meaning.
7. Full Python, API, contracts, and isolated GeoAI normal-test suites before a
   release commit.

## Next bounded product milestones

### Milestone 2 — locally useful personalization

- Add opt-in approximate-area selection from device location only after a
  privacy review. Convert coordinates to a broad reporting area on-device or
  through a purpose-limited endpoint; do not retain precise coordinates.
- Let a household nominate a locally confirmed meeting point and contact plan
  without uploading names or addresses.
- Add plan-expiry reminders and a clear export/import flow for a household-owned
  plan copy.
- Add installability and offline-refresh guidance without suggesting that a
  cached snapshot is current.

### Milestone 3 — verified field reporting

- Do not add an unmoderated “live report” button. First define reporter roles,
  consent, location precision, duplicate detection, evidence retention,
  moderation, abuse handling, and agency escalation.
- Display field observations as a separate, time-stamped evidence layer; never
  silently treat them as flood truth or feed them into FPPS.
- Require clear observed/reported/modelled labels and an audit record for every
  status change.

### Milestone 4 — authoritative geographic and operational context

- Replace synthetic context only with licensed, product-identified,
  checksum-tracked boundaries, waterways, roads, facilities, and shelters.
- Add freshness thresholds and explicit stale/blocked/unavailable behavior per
  layer.
- Introduce agency identity, authorization, signed manifests, append-only audit
  retention, monitoring, bilingual acceptance criteria, and field validation.
- Keep non-operational defaults until a signed acceptance receipt passes the
  existing pilot gate; configuration alone cannot promote the system.

## Three-person ownership

- Product/frontend owner: citizen hierarchy, bilingual UX, responsive map and
  command interactions, screenshots, accessibility, and static deployment.
- Backend/evidence owner: API contracts, scenario registry, offline bundle,
  manifest/checksum integrity, CI, security, and release receipts.
- Geospatial/ML owner: context provenance, GeoAI runner, spatial validation,
  qualified model comparison, calibration, error categories, and promotion
  recommendations.

Each milestone requires one owner, one reviewer, green verification, visible
evidence, and a scoped commit.
