# Architecture

## Pipeline

```text
flood extent or probability
  -> exposure aggregation
  -> road-disruption probability
  -> normal versus disrupted access
  -> Evacuation Equity Gap
  -> Flood Preparedness Priority Score
  -> action class
  -> dashboard-ready exports and action brief
```

## Study-area delivery boundary

The API resolves each request through a study-area dataset adapter rather than
scattering study-area conditionals across endpoints. The fixture profile and
`mae_sai_candidate_v1` are separate immutable identities. Each adapter binds
its layer paths, checksums, expected feature counts and geometry types, bounds,
join keys, attribution, confidence, assumptions, and decision-eligibility
state before returning data.

Bundle failure is fail-closed. A corrupt or substituted Mae Sai bundle returns
blocked/unavailable state; it never silently falls back to a visually plausible
fixture.

```text
study-area manifest
  -> adapter identity and checksum validation
  -> typed area/layer/scenario repository interface
  -> FastAPI response contracts
  -> API-backed provider or same-version offline bundle
  -> Public / Command / Studio safety filters
```

The Command map uses the eight Mae Sai ADM3 polygons as reporting units and
uses raster cells, road segments, bridges, facilities, access hotspots, and
routing nodes only as analysis/evidence units. This preserves administrative
meaning and the tested scoring contract.

## Model-to-decision boundary

An isolated model runner may produce a class-1 flood-probability raster and an
immutable run receipt. The trusted zonal adapter aggregates accepted raster
evidence to reporting areas. A separate probability-consequence adapter
computes road-corridor, bridge, and facility exposure evidence. Neither adapter
may establish an observed closure, safe route, facility operating state, or
official warning.

Trusted zonal receipts use schema 2.0. Version 2 binds the authoritative
geometry receipt to the exact model-run `study_area`; legacy 1.0 receipts are
not accepted at the decision boundary because they lack that anti-replay
binding.

Candidate models or candidate geometry may be evaluated only in explicit
report-only mode. Decision eligibility is derived from the full evidence chain
(product identity, licenses, checksums, qualified reference, spatial
evaluation, calibration, reviewer status, CRS/grid validation, and signatures),
never from a frontend control or a mutable deployment flag.

The additive v2 GeoAI contract separates the immutable model run, evaluation,
observation product, and study-area registry entry. Registry validation requires
exact study-area, event, source-bundle, model, evaluation, product, validity,
and acceptance bindings; a candidate or expired entry remains report-only.
Authoritative geometry is also bound to the model run's study area before zonal
aggregation. See `docs/geoai-system-design-v1.md` for the complete evidence
lanes, abstention semantics, failure model, and release gates.

The competition-mode Mae Sai offline projection is generated from the same API
builder and carries the exact referenced ModelRun v2 manifest. Its required
observation bands are checksum-bound non-raster descriptors because no
qualified Mae Sai observation product has been materialized. Studio labels
browser cryptographic status as unverified; authoritative digest and HMAC
validation remains in the repository/API resolver.

## Access-method boundary

The implemented access engine is a nearest-facility shortest-path threshold
analysis. It compares each population node's shortest travel time to any
selected facility under the normal and disrupted networks, then reports newly
lost 15-, 30-, and 60-minute access. It is not a capacity-aware two-step
floating catchment area (2SFCA) model. A 2SFCA extension remains future work
until trustworthy facility-capacity inputs and separate contract tests exist.

## Modules

- `config.py`: shared constants and lightweight configuration helpers.
- `scoring.py`: Flood Preparedness Priority Score and action classes.
- `equity.py`: vulnerable versus non-vulnerable access-loss ratios.
- `road_risk.py`: segment-level road-disruption probability.
- `access.py`: network access comparison under normal and disrupted conditions.
- `model_registry.py`: dependency-light v2 model/evaluation/product binding and
  fail-closed registry resolution.
- `trusted_zonal_adapter.py`: signed, study-area-bound raster-to-reporting-area
  aggregation for separately eligible evidence.
- `validation.py`: metric and validation report helpers.

## Data Boundaries

- Raw source data must stay outside production modules.
- Fixtures under `tests/fixtures/` are small, open, and deterministic.
- Production functions accept dataframes or paths explicitly; they do not assume local file locations.
- Outputs must include provenance fields where relevant: `source_name`, `source_timestamp`, `confidence_class`, and `assumptions`.
