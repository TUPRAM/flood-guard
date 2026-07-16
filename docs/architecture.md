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
- `validation.py`: metric and validation report helpers.

## Data Boundaries

- Raw source data must stay outside production modules.
- Fixtures under `tests/fixtures/` are small, open, and deterministic.
- Production functions accept dataframes or paths explicitly; they do not assume local file locations.
- Outputs must include provenance fields where relevant: `source_name`, `source_timestamp`, `confidence_class`, and `assumptions`.
