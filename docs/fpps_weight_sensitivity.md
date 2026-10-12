# The five weights of the planning score: are they reasonable, and does the result depend on them?

Written 12 October 2026. Report only: nothing here changes a score, a weight
or a class, and it is not part of the planning protocol. The weights stay the
ones of the signed scoring frame (decision D4) until the owners sign others.

Figures: `outputs/fpps_weight_sensitivity/se1_mae_sai_v1.json`, written by
`scripts/build_fpps_weight_sensitivity.py` from the published case SE1. The
arithmetic is `src/floodguard/fpps_weight_sensitivity.py`.

Case SE1 is a scenario: every area mapped as flooded in the 2024 season is
treated as flooded at once. It is not an observation of any day, its declared
confidence is medium, and the weight test adds no confidence to it.

## What the score adds up

| Part | Weight | What it counts in the published score |
|---|---|---|
| Flood likelihood | 30% | Share of a tambon's land (permanent water left out) inside the flood layer, full at 20% |
| Exposure | 25% | Share of residents whose home cell is inside the flood layer |
| Access gap | 20% | Of the residents who could reach a hospital or a main road before, the share who no longer can |
| Road criticality | 15% | Of the residents who had a road route to a hospital or main road, the share who lose every route |
| Vulnerability | 10% | Share of children under 15 and adults of 60 or over, set against the national range |

One correction to the plain wording of the policy document: the published
score does not count shelters. Access to a hospital and to a main road is in
the score; shelter access is measured beside it (the pitch-level figures stay
outside the repository). The policy page says "a hospital or a main road".

## Is there a paper that gives these weights?

No, and there cannot be one. The literature is clear on this:

- The OECD and JRC handbook on composite indicators (2008) treats weights as
  value judgements. They are set either by statistics or by the people
  concerned, and whichever way is chosen must be stated and tested.
- A review of 95 flood vulnerability indices (Moreira and others 2021) found
  equal weights to be the most common choice (24.2%). Only 9.5% of the
  studies tested sensitivity and 3.2% uncertainty.
- Tate (2012) found that an index built in levels, as ours is, is most
  sensitive to its weighting scheme.

So what can be defended is not the numbers 30, 25, 20, 15 and 10. It is three
things: that the parts are the right families, that the weights are declared
as a choice, and that the result was tested against other choices.

**The families.** Risk indices such as INFORM are built from hazard and
exposure, vulnerability, and capacity to cope. Our five parts sit in those
families: flood and exposure (55%), access and routes (35%, in the place of
coping capacity), and age (10%). Research supports each: floods cut access to
services well beyond the flooded ground (Coles 2017; Green 2017; Papilloud
and Keiler 2021; Tariverdi 2023), and deaths fall heavily on older people
(Jonkman 2009).

**Where our weights differ from common practice.**

- Flood and exposure hold 55% and move together (a tambon with more flooded
  land has more residents in it). A weight is not the same as influence
  (Becker and others 2017): parts that move together count for more than
  their weights say. The score therefore leans towards where the water is.
- Age holds 10%. Indices with good data on people usually give
  vulnerability more. Ours is low because the open age data are a coarse
  model, and the score has no measure of income, health or disability, which
  the reviews name as drivers (Rufat and others 2015).
- The weights were set by the team. The stronger practice is to set them
  with the people who will use the result (de Brito and others 2018 did it
  with 101 local experts). That is the review the page invites.

## Does the result depend on the weights?

The test adds up the published component values of the eight tambons again
with other weights. Published order: Ko Chang 78.5, Mae Sai 70.7,
Si Mueang Chum 59.3, Ban Dai 50.2, Pong Pha 31.6, Pong Ngam 21.9,
Wiang Phang Kham 5.2, Huai Khrai 4.7.

| Weighting | First | Ko Chang | Mae Sai | Same order of all eight? |
|---|---|---|---|---|
| Published: 30, 25, 20, 15, 10 | Ko Chang | 78.5 | 70.7 | (the reference) |
| Five equal weights | Ko Chang | 75.8 | 64.3 | yes |
| Three equal groups (flood and exposure, access and routes, age) | Ko Chang | 70.1 | 58.8 | no: two low tambons swap |
| Each weight halved or raised by half, one at a time (10 cases) | Ko Chang in all 10 | | | yes in all 10 |
| Flood and exposure only | Mae Sai | 68.6 | 78.1 | no |
| Published weights without the two access parts | Mae Sai | 66.9 | 72.6 | no |

Random weights: 200,000 sets drawn evenly from all sets of five weights that
sum to one (seed 20261012).

| Over the random sets | Share |
|---|---|
| Ko Chang is first | 91.2% |
| Mae Sai is first | 8.6% |
| Si Mueang Chum is first | 0.2% |
| The first three are the same three tambons | 91.5% |
| The first four are the same four tambons | 99.8% |
| The whole order of eight is the same | 46.4% |
| Rank correlation with the published order | median 0.98, 5th percentile 0.95, lowest 0.36 |

## Reading

- **The Ko Chang result does not rest on the exact weights.** It holds with
  equal weights, with every one-at-a-time change, and in nine of ten random
  weightings.
- **It rests on counting lost access at all.** Ko Chang and Mae Sai town have
  the same flood value (both saturate at 100). Mae Sai town is 19 points
  higher on exposure; Ko Chang is 32 points higher on the access gap, 34 on
  road criticality and 11 on age. Mae Sai town comes first only when exposure
  outweighs the two access parts together by about 1.7 to 1 or more, which in
  practice means leaving access out. Then the score is a flood map again, and that is
  the point of the page: a flood map alone would put Mae Sai town first.
- **The same four tambons lead under almost any weighting** (99.8%). The
  order inside the lower four is less firm, and those four are class E in
  any case.
- The share over random weightings is a measure of how much room there is,
  not a probability: nobody proposes most of those weightings.

## Limits

- Only the weights change. The components, their anchors and the modelled
  road closures are those of the published case; a component that is wrong
  stays wrong under every weighting. The uncertainty of the components is
  the subject of the ensemble (`docs/uncertainty_ensemble_rescaled_demand.md`),
  which found Mae Sai town's class unstable for another reason, the
  population product.
- A class follows rules on the components as well as the score, so this test
  says nothing about classes.
- One case, eight tambons, one district. A weighting that is harmless here
  could matter elsewhere.
- The flood part is full in four of the eight tambons; see the note below.

## A note on the flood part

The flood part is full when 20% of a tambon's land is inside the layer. In
case SE1 four tambons reach that (Mae Sai, Ko Chang, Si Mueang Chum and
Ban Dai), so among the leading four the largest weight, 30%, separates
nothing: their order is decided by the other 70%. The anchor was declared
after the data were seen, and the page of the signed frame says so.

## What to do with this

1. Keep the weights as they are for the competition; say "our choice, open
   for review" as the page does, and show this test when asked.
2. In the pilot, review the weights with Mae Sai officials before any use,
   in the way of de Brito and others (2018).
3. If better data on people arrive (registered ages by village, health or
   disability registers held lawfully), revisit the 10%.

The links to every paper named here are on the policy page and in
`apps/web/src/lib/policy-brief.ts`; how the list was made is in
`docs/policy_sources.md`.
