# Access loss by age group in case SE1: result

> **Update, 9 October 2026.** The comparison has since been run over the 180
> cells of the ensemble; the protocol's rule is met for the district, with older
> residents losing access slightly less often, not more. See the section added
> below. The text before it is the first result, at three closure levels.

**What this is.** The two age comparisons the protocol names, computed for the
first time for case SE1: residents of 60 and over against those under 60, and
children of 0 to 14 against residents of 15 and over. For each group: of the
residents who had the access before the flood, the share who lose it in the
season-layer scenario.

**How to read it.** Modelled, not observed, and a scenario, not a flood of any
day. The age counts are WorldPop's modelled counts on cells of 1 km. The
figures are for the eight tambons together or for one tambon. They say nothing
of what the people of a place can or cannot do. No planning score and no class
is computed, and it is not an official warning.

- Result: `outputs/equity_by_age/se1_mae_sai_v1.json`
- Code: `src/floodguard/equity_by_age.py`, `scripts/build_equity_by_age.py`
- Source time: season layer of 1 August to 12 October 2024; residents 2020; age shares 2024. Confidence: low.
- The script reproduces the committed counts of case SE1 for every tambon at every closure level before it writes.

## Result: no age gap worth the name

The eight tambons together, central closure level:

| Outcome | Group | Loss rate of the group | Loss rate of the others | Difference | Ratio |
|---|---|---:|---:|---:|---:|
| Loses a hospital within 30 minutes | 60 and over | 32.3% | 33.0% | -0.7 points | 0.98 |
| | Children 0 to 14 | 33.2% | 32.8% | +0.4 points | 1.01 |
| Loses every road route | 60 and over | 28.4% | 29.2% | -0.7 points | 0.97 |
| | Children 0 to 14 | 29.3% | 28.9% | +0.4 points | 1.01 |

The strict and the permissive level give the same picture: the differences
stay between -0.8 and -0.7 points for residents of 60 and over, and at +0.4
points for children.

**Read plainly: in this scenario, older residents and children lose access at
the same rate as everyone else, to within one share point.**

## Why the difference is so small, and why it cannot be larger

1. **Inside a tambon the age mix hardly varies.** The age counts come on
   cells of 1 km, and every home in a cell is given that cell's mix. In Ko
   Chang and Pong Pha the difference is exactly zero. In every other tambon
   but one it is a tenth of a point or less. In Mae Sai tambon it is a little
   over one point, with residents of 60 and over losing access slightly less
   often.
2. **What difference there is comes from between the tambons.** Mae Sai town
   has a smaller share of children and older residents than the rural
   tambons, and it loses a great deal of access. That pulls the rate of
   residents of 60 and over slightly below the others'. It is a statement
   about where people of different ages are modelled to live, not about age
   and access.
3. **A cell has one outcome.** Within a 100 m cell everyone keeps or loses
   the access together. A model that cannot tell a household with an older
   person from its neighbour cannot find an age gap inside a village.

## What may be said

The protocol allows a sentence about an age gap only when the ensemble of
plan task E10 excludes zero and keeps its sign in at least 60% of its runs.
That ensemble is not complete. On the three runs made here the sign is stable,
but three runs are not the ensemble, and a difference of under one point on
data that cannot resolve it is not a finding. **The sentence of the protocol
stands: "no age-group gap distinguishable from zero under the tested
assumptions".**

For the pitch: the equity question is answered for age, and the answer is that
the open age data cannot show a gap at this scale. A real answer needs
household-level or village-level data, which is a question for a local
partner, not for a model.

## Added on 9 October 2026: the same comparison over the 180 cells of the ensemble

The section "What may be said" above waited for the ensemble. It has now been
run, report-only (decision log R38), and the two comparisons were computed in
every one of its 180 cells: three flood levels, three closure levels and two
population products, each count standing for ten cells
(`outputs/equity_by_age/se1_mae_sai_ensemble_v1.json`,
`scripts/build_equity_ensemble.py`).

**The protocol's rule is met for the district as a whole, and the result is
not the one the proposal expected.**

| Loses a hospital within 30 minutes | Difference of loss rates over the 180 cells | Ratio of loss rates |
|---|---|---|
| Residents of 60 and over, against residents under 60 | **0.7 to 5.5 points lower** (median 3.0) | 0.86 to 0.98 |
| Children of 0 to 14, against residents of 15 and over | **0.4 to 3.0 points higher** (median 1.6) | 1.01 to 1.08 |

The loss of every road route gives the same picture (ratios 0.79 to 0.98 and
1.01 to 1.12). In every cell the sign is the same, so both of the rule's
conditions hold: the bounds exclude zero, and all 180 cells carry the sign of
the median.

What this says, and what it does not:

1. **In this scenario older residents lose access slightly less often than
   younger ones, and children slightly more often.** The proposal's premise,
   that older adults are cut off disproportionately, is not what the open
   data show for Mae Sai.
2. **The reason is where the modelled age groups are, not how anybody moves.**
   The cells that lose access, most of them in and around Mae Sai town, have
   a younger age mix in the 1 km age model than the cells that keep it.
   Inside a 1 km cell every age group has the same outcome by construction.
3. **The size depends on the population product.** With the WorldPop 2020
   counts the gap for older residents is 0.7 to 0.8 points; with the 2020
   counts rescaled to 2024 totals it is 5.1 to 5.5 points. The direction is
   the same in both.
4. **"Bounds" here are the lowest and the highest of 18 different counts of a
   scenario, not a statistical interval.** They say the sign does not change
   under the assumptions tested. They say nothing about error in the age
   model, which was not checked against a count on the ground.

By tambon the rule is met in Mae Sai (older residents 1.1 to 5.9 points
lower; children 0.6 to 2.7 points higher). In four other tambons it is met in
form only: every difference there is under a fifth of a point, down to a
millionth of a point. The rule sets no smallest size for a gap, which is a
gap in the rule, and no sentence is written for those tambons. In Ko Chang and
Pong Pha there is no difference at all: everyone in a group of cells shares
one outcome.

**What may be said now.** "Across the assumptions we tested, residents of 60
and over lose hospital access at 0.86 to 0.98 times the rate of younger
residents, and children at 1.01 to 1.08 times the rate of older ones. The
scenario does not show older residents being cut off more than others. The
age data are modelled on 1 km cells and cannot show differences inside a
neighbourhood." No tambon is ranked by its age mix.

To run it again:

```bash
python scripts/build_equity_ensemble.py --external-data <external-data-root> --age-dir <folder of the age rasters>
```

## Limits

- Residents are 2020 counts on 100 m cells; age shares are 2024 counts on 1 km
  cells. 158 of 27,487 demand cells (360 residents) lie in an age cell with no
  count and take their tambon's mix.
- Four of the eight tambons take age counts from cells that straddle the
  national border (decision log R21).
- One flood layer as provided, three closure levels. Not the ensemble.

## Credits

Age counts: WorldPop (www.worldpop.org), University of Southampton, DOI
10.5258/SOTON/WP00842 (CC BY 4.0); modelled, not observed. UNOSAT and GISTDA,
FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0); changed by FloodGuard, and
the figures derived from it are shared under CC BY-SA 4.0. Roads ©
OpenStreetMap contributors (ODbL 1.0). Residents: WorldPop 2020 (CC BY 4.0).

## To run it again

```bash
python scripts/build_equity_by_age.py --external-root <external-data-root> --age-dir <folder of the age rasters>
```
