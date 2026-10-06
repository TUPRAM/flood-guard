# Conditional binary 2SFCA scenario method (M6)

Status: **PARTIAL — scenario tooling verified; real service accessibility not run or accepted.**

`src/floodguard/two_step_access.py` implements a versioned, binary two-step floating catchment area (2SFCA) calculation for one declared service type, travel mode, case, event and scenario. It is separate from the maximum-flow shelter allocation in `src/floodguard/evidence_scenarios.py` and the nearest-service access loss in `src/floodguard/access.py`.

For each threshold `t` in 15, **30** (primary) and 60 minutes:

```text
R_j(t) = supply_j / sum(demand_k where travel(k,j) <= t)
A_i(t) = sum(R_j(t) where travel(i,j) <= t)
```

No distance-decay weights are applied. All step-one and step-two memberships use the same binary travel threshold. `R_j` and `A_i` retain the declared `supply_unit/demand_unit`; they are neither probabilities nor allocated or served people. Summing `A_i` is not a valid allocation. A maximum-flow result must remain a separate calculation with demand and supply conservation.

## Input and abstention contract

- A `TwoStepContext` requires case/event/scenario IDs, service type, travel mode, effective UTC timestamp, demand/supply units and at least one explicit assumption. Each site must match that service and supply unit; each origin must match the demand unit. This prevents a hospital bed count from entering a shelter-place calculation through a mixed site list.
- Demand and supply must be finite nonnegative quantities or `None`. `None` means unknown, not zero. A known zero supply with positive catchment demand yields a zero ratio; unknown supply yields a null ratio. Zero catchment demand yields a null ratio with `zero_catchment_demand`, even when supply is known. A site may have multiple unavailability reasons.
- The input must supply exactly one route state for every origin–site pair. `reachable` has a finite nonnegative modelled travel time, `unreachable` is a modelled graph disconnection with null time, and `unknown` is missing coverage with null time. Omitting a pair fails validation. These statuses do not assert observed road closure or actual isolation.
- An unknown positive-demand origin–site route or reachable origin with unknown demand makes the site's denominator unknown. Unknown origin–site travel also makes the affected origin's accessibility null. A reachable site with unavailable `R_j` likewise makes `A_i` null. A known origin with no sites reachable inside a threshold has `A_i=0` only when all its travel pairs are known.
- Coverage reports known route pairs, evaluable origin count, known demand, unknown-demand origin count, and evaluable fraction **of known demand**. If any demand is unknown, `demand_coverage_status` is `incomplete_unknown_demand`; the known-demand fraction is not a full population coverage estimate.
- Output identity includes an order-independent SHA-256 of the exact context, demand, supply and travel inputs. The result declares `schema_version=binary_2sfca_scenario_v1`, `evidence_status=scenario_only`, `operational=false`, `official_warning=false`, `allocation=false` and explicit units. It does not fill FPPS or action class.

## Reproducible hypothetical check

The open test fixture has three origins with modelled demand 100, 200 and 50 people, and two hypothetical shelter supplies of 300 and 600 scenario places. Modelled travel times (minutes) are:

| Origin | Shelter s1 | Shelter s2 |
| --- | ---: | ---: |
| o1 | 10 | 40 |
| o2 | 20 | 25 |
| o3 | 50 | 55 |

At 30 minutes, the known catchment demand is 300 for s1 and 200 for s2, so `R_s1=1` and `R_s2=3` scenario places per modelled person. The `A_i` values are 1, 4 and 0 respectively. The value 4 is an accessibility ratio, not four allocated places or people. At 15 minutes s2 has zero catchment demand and a null site ratio; at 60 minutes both site denominators are 350. Tests also cover unknown supply versus zero, unknown route/demand, zero demand, validation and coverage.

Run:

```powershell
uv run --extra evidence pytest -q tests/test_two_step_access.py
uvx ruff check src/floodguard/two_step_access.py tests/test_two_step_access.py
```

## Real-data gate

This module has no real Mae Sai 2SFCA result. The current M6 FAC-01 register records unavailable verified shelter capacity and operating status. Before a real result, the team must choose a single dated service role and eligible facilities, obtain purpose-compatible capacity/supply, define in-scope demand and participation, validate route mode/topology/catchment including connectors, and review unknown coverage. A 30-minute vehicle catchment is a model choice, not measured mobility. A real 2SFCA claim remains conditional on those inputs and downstream review. Hypothetical supply presets can be run as scenarios only and cannot be renamed observed available capacity.
