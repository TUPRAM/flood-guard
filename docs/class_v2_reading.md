# The second class reading of case SE1: result

**What this is.** The proposal's own class wording (its section 5.2) was signed
into the protocol as class rule v2: a labelled secondary axis beside the
binding rule v1. The published result of case SE1 says "not evaluated" for it,
because three of its five triggers needed stages nobody had run. They are run
here, as protocol v1b defines them.

**How to read it.** Report-only. **Class rule v1 stays binding** (decision D6):
no published class changes, and the published result file is not touched. The
case is a scenario, not a flood of any day; closures are modelled; the
critical links are unreviewed candidates; nothing was checked on the ground.
It is not an official warning.

- Result: `outputs/class_v2_reading/se1_mae_sai_v1.json`
- Code: `src/floodguard/class_v2_reading.py`, `scripts/build_class_v2_reading.py`
- Source time: season layer of 1 August to 12 October 2024. Confidence: low.

## The three triggers that were missing

| Trigger | Definition (protocol v1b) | What was found |
|---|---|---|
| B | A top-20 critical link that crosses the flood extent, closed on its own, takes every route from at least 500 residents of the tambon | Not met anywhere. Two of the twenty links cross the layer; closing either one alone cuts nobody off |
| C | A hospital or located DDPM shelter that is the nearest of its kind for at least 100 residents of the tambon lies inside the layer or loses every vehicle route; score of 35 or more; confidence not low | Met in three tambons, each time through a shelter. No hospital is inside the layer or cut off |
| D | At least 20% of the tambon's land outside permanent water has a JRC surface-water occurrence of 25% or more | Not met anywhere. The share is under 0.1% in every tambon, so the test at 10% and 30% gives the same |

## Result

| Tambon | Score | Binding class (v1) | Second reading (v2) |
|---|---:|---|---|
| Ko Chang | 78.5 | B, keep routes open | C, protect essential services |
| Mae Sai | 70.7 | D, build resilience | C, protect essential services |
| Si Mueang Chum | 59.3 | D, build resilience | C, protect essential services |
| Ban Dai | 50.2 | D, build resilience | no v2 trigger met |
| Pong Pha, Pong Ngam, Wiang Phang Kham, Huai Khrai | under 35 | E, monitor and verify | E |

The two readings differ in four of the eight tambons.

## What this says

1. **Mae Sai town reads C under the proposal's wording.** The shelter that is
   nearest for about 9,300 of its residents has no vehicle route to a main
   road in the scenario. This is the computed answer to "why is the worst-hit
   town only class D": under rule v1 the class names the kind of action the
   component values point to; under the proposal's own triggers the town is
   "protect essential services".
2. **Ko Chang reads C, not B, under v2, and the reason matters.** Trigger B
   asks whether **one** critical link, closed alone, cuts off 500 residents.
   Ko Chang is cut off by many closures at once, and the twenty top-ranked
   links are all pieces of one road. So v2's B does not fire, and C does,
   through three shelters. The road sheet shows the same thing from the other
   side: one road would reconnect more than half of Ko Chang, but no single
   closure isolates it.
3. **The recurrence trigger cannot fire here.** Outside permanent water,
   almost no land in the district has been water in a quarter of the
   satellite record.
4. **Every C comes from shelters, none from hospitals.** The shelter list is
   the DDPM's located shelters; the nearest-facility test is by vehicle time.

## What may be said, and what may not

- The binding classes do not change. Ko Chang stays "keep routes open" in
  everything published.
- The second reading may be shown as a secondary axis with the label
  "secondary", as the protocol says. In the pitch it is the answer to one
  question, about Mae Sai town.
- The second reading was not run through the uncertainty ensemble. It is one
  run at the central closure level.

## Readings made here that the protocol leaves open

- "Loses all vehicle routes", for a facility, is read as: in the flooded run
  at the central level, no vehicle route joins the facility to any main-road
  entry.
- "Inside the extent" is tested on the facility point of the planning context.
- A link "crosses the flood extent" when the season layer covers any length of
  it.

## Credits

JRC Global Surface Water (Pekel et al. 2016), occurrence 1984 to 2021,
European Commission. ESA WorldCover 2021 v200 (CC BY 4.0). UNOSAT and GISTDA,
FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0); changed by FloodGuard, and
the figures derived from it are shared under CC BY-SA 4.0. Roads ©
OpenStreetMap contributors (ODbL 1.0). Residents: WorldPop 2020 (CC BY 4.0).
Shelters: DDPM open catalogue.

## To run it again

```bash
python scripts/build_class_v2_reading.py --external-root <external-data-root>
```
