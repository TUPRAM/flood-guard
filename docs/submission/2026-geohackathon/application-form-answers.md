# FloodGuard Thailand - application-form answers

These answers are deliberately free of team-name, contact, and demo-link
placeholders. The release build obtains those owner-supplied values only from
`submission-metadata.json` after strict validation. Current verification is
bound to tested source commit `62a4336759de55116b1bd238a5afd60ca7496895`:
1,212 root Python tests passed with one skip, 86 API tests passed, 5 contract
tests passed, 58 web-unit tests passed, the complete frontend/offline gate
passed, 84 normal GeoAI-runner tests passed, and the opt-in real-GeoAI smoke
passed.

## Project title

FloodGuard Thailand: From Flood Pixels to Equitable Local Action

## One-sentence concept

FloodGuard turns trustworthy satellite-derived flood probability into
explainable subdistrict priorities, likely road disruption, shelter and
healthcare access loss, and an Evacuation Equity Gap for preparedness and rapid
post-event planning.

## Problem and Thai relevance

Thailand has strong agencies and satellite systems that map floodwater, but
local preparedness also requires understanding which communities may become
cut off from hospitals, shelters, and main roads; which links create the most
isolation; and where field verification or limited support should be
prioritized. FloodGuard fills this last-mile decision gap. It does not replace
GISTDA, DDPM, TMD, RID, ONWR, local authorities, or official warning channels.

## Intended users and beneficiaries

Institutional users include GISTDA, DDPM and provincial disaster offices,
municipalities, hospitals and health authorities, and road agencies. A separate
Thai-first public surface supports resident and community preparedness.
Beneficiaries include flood-exposed residents, with explicit attention to
groups who may have fewer mobility or service-access alternatives. Outputs are
aggregated and uncertainty-aware.

## Proposed GeoAI approach

FloodGuard preserves a deterministic Sentinel-1 change baseline and a
weak-label logistic comparator while adding an isolated GeoAI U-Net/FPN lane.
The GeoAI runner pins Python 3.12 and `geoai-py==0.41.1`. An eight-band
pre/post VV/VH, change, terrain, and permanent-water stack is explicitly
clipped and encoded to `uint8`; raw negative SAR and terrain values never pass
through an implicit `/255` transform. The current synthetic proof exercises
real GeoAI tile export, two-class model construction, tiled prediction,
explicit class-1 probability extraction, grid/range validation, and report-only
FloodGuard aggregation. It proves integration wiring, not real flood accuracy.

A controlled real-data experiment will run only after licensed product IDs and
checksums, a qualified reference mask, reviewer calibration, immutable spatial
holdouts, and signed evidence gates pass. Metrics will include IoU, Dice/F1,
precision, recall, physical area error, Brier score, calibration, and named
error categories. The current gate receipt is blocked and no missing metric is
fabricated.

## Expected outputs

1. A provenance-bound candidate flood-probability artifact and model card.
2. Subdistrict exposure, road risk, nearest-facility access loss, and an
   Evacuation Equity Gap.
3. Transparent FPPS and A-E action classes with confidence and assumptions.
4. Thai-first mobile public preparedness PWA.
5. Desktop/tablet government command center with map, scenarios, and briefs.
6. Research/developer studio showing data gates and reproducibility evidence.
7. Offline judging bundle requiring no external API or network.

## Real-world use

FloodGuard supports field-verification prioritization, pre-positioning,
identifying links that may create isolation, comparing bounded temporary
shelter or road-failure scenarios, and preparing bilingual local briefs. It is
a preparedness and rapid post-event prioritization tool, not an official
warning system or live evacuation navigator.

## Team capability

The three-person operating model combines product/UI/frontend delivery,
backend/platform/evidence engineering, and geospatial/ML/data governance. The
final submission inserts each member's real name, two relevant skills, one
evidence item, prototype contribution, and finalist contribution from the
validated submission metadata.

## Feasibility

FloodGuard starts from an implemented decision engine, role-specific Next.js
application, typed contract package, FastAPI artifact/scenario service,
isolated GeoAI runner, static dashboard fallback, and extensive automated-test
coverage. The exact fresh, commit-bound test receipt is listed at the top of
this file. The static demo uses committed fixtures and does not depend on a
hosted API, GeoAI environment, GPU, or network.

## One-paragraph pitch

Thailand can already see floodwater from space. The harder question is who may
become cut off from help, whether access loss falls disproportionately on those
with fewer mobility options, and where limited preparedness resources should
be checked first. FloodGuard uses an isolated GeoAI workflow to create a
provenance-bound candidate probability layer and converts trustworthy inputs
into road disruption, shelter and healthcare access loss, an Evacuation Equity
Gap, and an explainable subdistrict priority. Its Thai-first public view,
government command center, and transparent studio move from pixels to policy
without pretending to replace official agencies.
