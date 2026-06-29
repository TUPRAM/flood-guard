# Model Contract

## 1. Flood Preparedness Priority Score

Input table: one row per subdistrict.

Required columns:

- `subdistrict_id`
- `subdistrict_name`
- `flood_likelihood_0_100`
- `exposure_0_100`
- `access_gap_0_100`
- `road_criticality_0_100`
- `vulnerability_context_0_100`
- `confidence_class`

Default formula:

```text
FPPS =
  0.30 * flood_likelihood_0_100 +
  0.25 * exposure_0_100 +
  0.20 * access_gap_0_100 +
  0.15 * road_criticality_0_100 +
  0.10 * vulnerability_context_0_100
```

Output:

- `fpps_0_100`
- `action_class`
- `top_reason`
- `confidence_class`

## 2. Action Class Logic

Class A - Protect Lives Now:
High exposure and high access loss, especially where vulnerable groups are affected.

Class B - Keep Routes Open:
Critical road or bridge disruption causes isolation.

Class C - Protect Essential Services:
Hospitals, clinics, schools, or emergency facilities are exposed or unreachable.

Class D - Build Resilience:
Recurrent exposure but not immediate crisis.

Class E - Monitor and Verify:
Low exposure or high model uncertainty.

Initial implementation rule priority:

1. `E` when `confidence_class` is `low` or FPPS is below 35.
2. `A` when exposure is at least 70 and access gap is at least 70.
3. `B` when road criticality is at least 75 and access gap is at least 55.
4. `C` when exposure is at least 65 and access gap is at least 50.
5. `D` for all remaining subdistricts.

These thresholds are intentionally simple for the MVP and should be sensitivity-tested later.

## 3. Evacuation Equity Gap

For each subdistrict:

```text
vulnerable_access_loss_rate =
  vulnerable_population_losing_access / total_vulnerable_population

non_vulnerable_access_loss_rate =
  non_vulnerable_population_losing_access / total_non_vulnerable_population

equity_gap_ratio =
  vulnerable_access_loss_rate / non_vulnerable_access_loss_rate
```

Handle division by zero explicitly.

Output:

- `vulnerable_access_loss_rate`
- `non_vulnerable_access_loss_rate`
- `equity_gap_ratio`
- `interpretation_text`

Zero-denominator behavior:

- If there is no vulnerable denominator, vulnerable rate and ratio are null.
- If there is no non-vulnerable denominator, non-vulnerable rate and ratio are null.
- If non-vulnerable loss rate is zero while vulnerable loss exists, ratio is null and marked undefined.
- If both groups have zero loss, ratio is `1.0`.

## 4. Road-Disruption Probability

Road disruption probability is a fixture-level heuristic, not an observed road-closure claim.

```text
road_disruption_probability_0_1 =
  0.65 * mean_flood_probability_0_1
  + 0.20 * surrounding_inundation_0_1
  + 0.10 * road_class_factor
  + 0.05 * bridge_factor
```

The result is clamped to `0.0-1.0` and rounded to three decimals.

Road class factors:

- `motorway`, `trunk`, `primary`: `1.0`
- `secondary`: `0.75`
- `tertiary`: `0.55`
- `local`, `residential`, `unclassified`: `0.35`

Bridge factor:

- `1.0` when `bridge_flag` is true
- `0.0` when `bridge_flag` is false

## 5. Access-Loss Prototype

The fixture access model compares shortest travel time to any selected facility under two networks:

- normal network, using `normal_minutes`
- disrupted network, using `disrupted_minutes`

Blank disrupted edge times mean the edge is closed in the disrupted scenario.

A population node counts as losing X-minute access only when it had normal access within X minutes and disrupted access is missing or greater than X minutes.
