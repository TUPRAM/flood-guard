# Shelters in case SE1: access on foot, and listed places against the residents in reach

**What this is.** The proposal names "shelter capacity versus reachable
demand". Protocol v1b fixes how it is computed: binary two-step floating
catchment (2SFCA) at 15, 30 and 60 minutes on foot to the located DDPM
shelters, with 5, 10 and 25 percent of residents seeking a place, under the
label **"listed planned capacity; scenario"**. It was run for case SE1 on
9 October 2026.

**Why this page holds no figure.** Shelter figures are pitch level (protocol
v1b; decision D8b: participation sweeps and listed capacity stay out of public
files). This repository is public. So the result and a pitch note are written
outside Git, and what is committed is the method, the code, the tests and a
receipt that binds the two files by SHA-256.

- Receipt: `outputs/shelter_capacity/se1_mae_sai_v1_receipt.json`
- Result and pitch note (outside Git):
  `<external data root>/proposal_execution/planning_v1/se1_mae_sai/shelter_capacity/`
- Code: `src/floodguard/shelter_capacity.py`, `scripts/build_shelter_capacity.py`
- Source time: season layer of 1 August to 12 October 2024; shelter list of
  21 September 2026. Confidence: low.

## How to read it

Report-only. It is no input of the planning score and changes no class; the
protocol says of 2SFCA "not promoted". A capacity is a listed planning figure:
nobody verified that a shelter was open, or for how many. The participation
shares are assumptions, not estimates of who would go. The case is a scenario,
not a flood of any day; closures are modelled. A shelter in reach is not a
shelter that is open. It is not an official warning.

## What is computed

| Part | What |
|---|---|
| Access on foot | Residents of each tambon with a located shelter within 15, 30 and 60 minutes: before the flood, and under the three levels of closure rule v1 on the flood layer as provided |
| A stricter reading | The central level again, with every shelter whose point the flood layer covers left out: it offers no place and is no destination |
| Each shelter | Its listed places, the residents whose nearest shelter within 30 minutes it is, and the residents within 30 minutes of it |
| 2SFCA | For each shelter, listed places divided by the residents in reach who would seek a place; for each resident, the sum over the shelters in reach. Under 1 means fewer listed places than people seeking them |

The walking minutes come from the walking planning context: everyone walks,
nobody is driven. A ratio allocates nobody to a shelter.

## What was checked before anything was written

- The minutes from every demand cell to its nearest shelter are those the
  engine gives (`floodguard.access_diff.cell_minutes`), at baseline and at
  each closure level, to a billionth of a minute.
- The residents of every tambon with a shelter within 15, 30 and 60 minutes,
  before and in each flooded run, are those of the task E5 shelter table.
- The matrix form of 2SFCA gives what the reference module
  (`floodguard.two_step_access`) gives on a fixture (a test).

## The walking network

The walking context is a candidate build: it was made without a declared
compute window (open point E5-OP5). On 9 October 2026 the owner asked for the
shelter figures on it, which is taken as accepting it for report-only use
(decision log R40). The registered task E5 receipt still calls it a candidate,
and no registered run was made.

## Readings made here that the protocol leaves open

- A resident is "short of places" when the listed places in reach, shared
  among everyone in reach who would seek one, come to under one per person.
- With a participation of p percent every demand is multiplied by p/100, so
  every ratio is divided by it; one run serves the three shares.
- "Inside the layer", for a shelter, is tested on its point.

## Not done

- No allocation of residents to shelters and no optimisation.
- No verified capacity, opening status or accessibility of a shelter. Without
  them this stays a scenario, as the proposal says of capacity-aware 2SFCA.
- The 360 cells of the uncertainty ensemble that add shelters.

## To run it again

```bash
python scripts/build_shelter_capacity.py --external-data <external-data-root>
```

A second run needs `--replace --reason`. The run takes about fifteen minutes.
