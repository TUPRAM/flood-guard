# Purpose review of the 2024 age counts, before any public derivative (draft v1)

Status: **PENDING** (draft, pending an answer from both owners)

For Putu and Rachmania. Written by an AI coding agent on 5 October 2026. The team rule is "agents draft, humans sign":
this page is not a decision. No code reads it. Until you answer and the answer is in the decision log, the planning
builders keep the age counts at the rights level `local`, exactly as they do today, and
`tests/test_owner_unblocker_records.py` fails if that changes while this page is pending.

Nothing was computed for this page. Every figure below is copied from a committed file, which is named.

## 1. Why this review exists

Protocol v1b is signed. Where it lists the age rasters, it says
(`national_vulnerability_anchors.inputs.age_rasters.rights`):

> Public catalog says CC BY 4.0. Public derivatives require purpose-specific review.

No such review is recorded anywhere in the repository. Plan task E8 therefore holds the age counts at `local`, and
every result that uses them is `local` too. That is open point **E8-OP5**: "The owners record the review, or say that
it is not needed for these derivatives, and their answer has to cover the E7 table that is already committed"
(`outputs/planning_v1/README.md`).

"Purpose-specific" is the project's own rule: permission to download a data set is not permission for every use of
it. `docs/proposal_execution/SOURCES_AND_RIGHTS.md` lists the uses that are judged one by one, among them derived
metrics, hosted display, downloads and downstream decisions.

## 2. Which data

| | |
|---|---|
| Source | WorldPop, University of Southampton |
| Product | WorldPop Global2 R2025A v1, Thailand, 2024, constrained total-sex age counts, 30 arc-seconds (about 1 km), `1km_ua` |
| What it holds | An estimate of how many people of each of 20 age bands have their home in each 1 km cell. Modelled, not counted. It holds no names, no addresses and no households. |
| Files | 20 rasters, 51,593,135 bytes, published 1 September 2025, acquired on 23 September 2026 by `scripts/acquire_worldpop_age.py` |
| Identity | Acquisition manifest SHA-256 `f7a169877177a374bc461724dcb93b6ec96d76451347cd2e98dc2fc7b0f8356c`; each raster by SHA-256 in `outputs/planning_v1/age_exposure_mae_sai_v1_receipt.json` |
| Where it is kept | Outside Git |
| Product page | https://hub.worldpop.org/geodata/summary?id=98910 |

**The licence, as the repository records it.** Three files say almost the same thing:

- Protocol v1b: "Public catalog says CC BY 4.0. Public derivatives require purpose-specific review."
- `scripts/acquire_worldpop_age.py`, which wrote the acquisition manifest: "Public catalog says CC BY 4.0; ODbL may
  apply to OSM/building-derived datasets. Public derivatives require purpose-specific review."
- `docs/proposal_execution/SOURCES_AND_RIGHTS.md` (checked 23 September 2026): the catalogue states CC BY 4.0 "with an
  ODbL caveat for some building/OSM-derived products; hosted age derivatives still await product-specific
  attribution/share-alike review."

The credit the builders write today is "WorldPop (www.worldpop.org), University of Southampton"
(`scripts/build_planning_assessment.py`).

**To be checked by the owners against the provider's page.** No file in the repository settles these three points,
and nothing here is quoted from memory:

1. The licence shown on the product page for this exact product (page: https://hub.worldpop.org/geodata/summary?id=98910).
2. Whether the ODbL caveat applies to this product and, if it does, what it asks of a table derived from it
   (pages: the product page above, and the release statement,
   https://data.worldpop.org/repo/prj/Global_2015_2030/R2025A/doc/Global2_Release_Statement_R2025A_v1.pdf).
3. The credit or citation WorldPop asks for (page: the product page above).

## 3. Which derivative

A derivative is anything worked out from the age counts. For each tambon the chain is:

1. **The dependent share.** Children aged 0 to 14 plus adults aged 60 and over, as a share of the tambon's
   residents. A 1 km cell's counts go to a tambon by the part of the cell's area inside it.
2. **The vulnerability/context component**, a value from 0 to 100. It places the tambon's dependent share between
   two national anchors (P10 = 0.351416 and P90 = 0.477677, protocol v1b).
3. **The scores and classes that include it.** The component is one of the five parts of the Flood Preparedness
   Priority Score (weight 0.10 by default). The A to E class is read from the score. So are the would-be class, the
   secondary class of rule v2 (its trigger A reads the dependent share against the national P75), the
   leave-one-component-out values and the ensemble of task E10.

Where each derivative is today:

| Derivative | Where it is today | Level the code gives it |
|---|---|---|
| The three age counts and the dependent share of each of the eight Mae Sai tambons (`outputs/planning_v1/age_exposure_mae_sai_v1.json`) | **In Git since 4 October 2026** | none stated in the file; task E8 treats it as `local` when it reads it |
| The five national anchors (P5, P10, P75, P90, P95) | **In Git**, in the signed protocol v1b and in `outputs/planning_v1/national_vulnerability_anchors_v1.json` | task E8 treats them as `public` (constants for all of Thailand) |
| The vulnerability component of each tambon | Outside Git, in the files the E8 receipts bind | `local` |
| The score, the classes and leave-one-component-out of each tambon | Outside Git; counts for the whole case are in Git | `local` |
| The ensemble results of each tambon (task E10) | Outside Git; counts for the whole case are in Git | `local` |
| The public projection (plan task E12) and the per-tambon planning briefs (plan task U5) | Not built | — |

**One thing you should know before you answer.** For case SE1 the separation is nominal. The README of
`outputs/planning_v1` says so: with the committed age table, the anchors of protocol v1b and the committed SE1 table,
"the FPPS and the binding class of each SE1 tambon can be worked out from committed files", and a review did work
out all eight. Your answer therefore also has to say what happens to the files that are already in Git (see
section 7).

## 4. The purpose

FloodGuard is a preparedness and rapid post-event prioritisation tool. The purpose you are asked to confirm is this
one sentence. It was drafted for this page; it is not quoted from a file:

> Between tambons with a similar flood likelihood, exposure, access gap and road criticality, the tambon with a
> larger share of children and older adults among its residents gets a slightly higher planning priority, so that
> preparedness work and checks after an event look there first.

The review is asked for these uses of the derivatives:

| Use | Asked for |
|---|---|
| A component value, a score and a class per tambon in the planning overlay, shown on the project's pages | yes |
| The same in a brief per tambon and in the pitch | yes |
| A download of the per-tambon table | yes |
| Input to the public priority band (plan task E12) | yes |

The purpose does **not** include, under any option below:

- any figure for an area smaller than a tambon (no cell, village, street or household);
- any statement about a person or a household: who is vulnerable, who needs help, who can or cannot evacuate;
- deciding who receives aid, a service or a visit;
- any operational decision during an event, such as an evacuation order (a class is planning guidance, not an
  official warning);
- any use by a third party that the credit and the label do not travel with.

## 5. Risks considered

For each risk: what could go wrong, and what the committed files show. The judgement is yours.

**5.1 Re-identification from a tambon aggregate.** Could a reader learn something about a known person or household?

- The source is a modelled grid, not a register of people. It holds counts per 1 km cell, in three broad groups once
  FloodGuard has added the bands up (0 to 14, 15 to 59, 60 and over).
- The smallest of the eight tambons has 3,197 modelled residents in the 2024 age table (TH570908) and 5,036 in
  WorldPop 2020. The largest has 25,362. Each tambon takes counts from 42 to 75 one-kilometre cells
  (`outputs/planning_v1/age_exposure_mae_sai_v1.json`; the 2020 figure is from the SE1 table of
  `outputs/planning_v1/README.md`).
- The age table itself reports that the age composition hardly varies inside the frame: in all eight tambons the
  cells wholly inside the tambon give the same share, 0.405551, and across Thailand 89.4% of populated cells fall in
  groups of 20 or more cells with the same share to six decimals. The README reads this as "one age composition per
  district, applied to every cell of the district"; it was not checked against district polygons. If that is right,
  a tambon's share says little more than its district's share.
- What this review did not do: no test of whether a small group can be singled out was run, and frames other than
  the eight Mae Sai tambons were not looked at. A frame with much smaller units needs its own look.

**5.2 Misuse as a statement about individuals.** A share of a tambon is easily read as a property of the people in
it: "residents of this tambon are vulnerable", or "cannot leave on their own".

- The component describes an age mix. It says nothing about any person's health, mobility, income or need. The age
  table says so in its own limits: "A dependent share is not a measure of need in any place".
- The counts are modelled for 2024 and are set beside 2020 residents, 2022 boundaries and 2026 roads. The mixed
  vintages are disclosed in the table.

**5.3 Stigma.** A map or a ranking that marks a tambon as "more vulnerable" can label a community.

- Mae Sai is a border district. Four of the eight tambons take counts from cells that straddle the national border,
  and such a cell's age mix may include residents whose homes are across the border
  (`outputs/planning_v1/README.md`, open point E7-OP1). A label on those tambons rests partly on people who are not
  their residents.
- The word "vulnerability" is the protocol's name for the component. On a page a reader may take it for a verdict.

**5.4 False confidence in a small difference.** Not one of the three risks this review was asked to consider; added
by the drafter.

- Five of the eight tambons have shares between 0.4055 and 0.4056. A component value that differs between two
  tambons may come from edge cells only (README, "What the run shows about the age grid").
- The component has weight 0.10 by default, so it moves a score by at most 10 points. In case SE1 the ensemble found
  three cells in which one class-E tambon becomes class D: the plus flood level with the anchors P5 / P95 and the
  vulnerability-heavy weights (README, task E10).

## 6. Mitigations

**Already in the design** (each is in a signed file or in code that has tests):

| Mitigation | Where |
|---|---|
| **Tambon aggregates only.** The overlay has one row per tambon. No age figure is written per cell, village or household. | protocol v1a, `scoring_frame`; `src/floodguard/planning_assessment.py` |
| **GR1: no class under 100 residents.** "A unit with fewer than 100 residents gets no class (insufficient_denominator). A ratio requires at least 50 people per group." | protocol v1a, guardrail `GR1_minimum_denominators` |
| **Labels on the data.** The component carries the caveat "Modelled 1 km age composition applied to 2020 100 m counts; not observed; within-cell composition assumed uniform." Each row of the age table has the status `modelled_research_estimate` and the table has confidence `low`. | protocol v1a, `vulnerability_context_0_100.caveat`; the age table |
| **Labels on the result.** A class is planning guidance, not an official warning. "Class E never means safe" is printed wherever E appears. | protocol v1a, `wording` |
| **The component cannot hide.** Leave-one-component-out is reported on every row, so a reader sees what the class would be without the vulnerability component. | protocol v1a; task E8 |
| **A second pair of anchors and five weight presets** are run in the ensemble, so a class that depends on the age mix is seen to depend on it. | protocol v1b, `ensemble_grid` |
| **Unknown is not zero.** Area with no age count is reported as unsupported, with no count. | the age table |

**Not in the design today.** If you want one of these, say so with your answer:

- The drafter found no rule that forbids ranking or colouring tambons by the dependent share alone.
- The per-tambon planning brief (plan task U5) is not built, so the "age caveat" that the plan puts on its page 2
  is not written.
- No wording rule covers how the component is named in public text. The shared wording lint has no rule for it.
- The age table in Git carries no licence line of its own for the age counts.

## 7. Options for the owners

Tick one. A recommendation is not a decision, so none is ticked.

- [ ] **A. Confirm for public use.** The per-tambon component, the scores and classes that include it, and the
  per-tambon age table may be shown on public pages and offered for download, for the purpose in section 4, with the
  credit and the labels of section 6.
- [ ] **B. Confirm for pitch use only.** The same derivatives may be shown in the pitch and in material handed out
  with it, with the credit and the labels. Nothing that carries the component goes under `apps/web/public/`, and
  pitch variants stay outside Git (plan 3.1).
- [ ] **C. Decline.** No derivative of the age counts is shown outside the team.

What each answer leads to. None of this is done now; each step is a later, reviewed change.

| | A. Public | B. Pitch only | C. Decline |
|---|---|---|---|
| Level of the age counts in task E8 | `public` | `pitch` | stays `local` |
| A score or class on a public page | Possible for a case whose other inputs are public. Case SE1 still needs an answer to E8-OP1 before its overlay exists; case O2 stays `local` because of its flood layer (E1-OP1). | Not possible: a score needs all five components, and one of them would be below public. | Not possible, for the same reason. |
| The pitch | May show them | May show them | May not show them |
| The age table and the SE1 table already in Git | Stay | You say whether they stay (E8-OP5, E8-OP7, E1-OP1) | You say whether they are taken out. They stay in the Git history either way. |
| The signed scoring frame | Unchanged | Unchanged | Unchanged. Taking the component out of the score would need `planning_protocol_v2` with a written reason (protocol v1b, `change_control`). |

Conditions you can attach to A or B (suggested by the drafter; strike any, add your own):

1. Tambon level or coarser only, as today.
2. Every display carries the credit and the words "modelled, not observed".
3. Public text names the component by what it measures ("share of children and older adults among residents,
   modelled"), and never says what the people of a tambon can or cannot do.
4. No map, table or sentence ranks tambons by this share alone.
5. The answers to the three licence points of section 2 are recorded with this review.

**The drafter's suggestion, for what it is worth.** The files show a coarse, modelled, openly catalogued data set
and aggregates of thousands of residents, so option A with the five conditions looks defensible. Two things only you
can settle: what the provider's page says about the licence, and whether you are comfortable with a public label on
border tambons. If either is in doubt, B keeps the pitch whole and loses nothing that exists today.

## 8. What happens after you answer

1. Your answer goes into the decision log as a new row after R18, with the date and how it was given. This page gets
   the row number and its status changes from PENDING.
2. A reviewed code change sets the level of the age counts in `scripts/build_planning_assessment.py` to the level you
   chose and cites the row. The test that today holds the level at `local` is changed in the same commit.
3. The E8 run of case SE1 is repeated with `--replace --reason`, and after it the E10 run. Both are runs on real
   units and write new receipts.

Until step 2 is merged, nothing changes: the builders refuse a public write of anything that carries the component.

## 9. Signature block

Left empty on purpose. Fill it in yourselves, or tell the agent your answer and it records the decision-log row
that says how the answer was given.

| | Putu | Rachmania |
|---|---|---|
| Option chosen (A, B or C) | | |
| Conditions (numbers from section 7, or your own) | | |
| Licence points of section 2 checked against the provider's page (yes or no, and the date) | | |
| Date | | |

Decision-log row: _none yet_

## 10. About this page

- **Source timestamp:** age counts for 2024, published 1 September 2025; the age table was generated on
  4 October 2026 at 09:12:35 UTC; the two protocol files are those in force (v1a SHA-256
  `b6dc549ce9430e0d540fcd0490db1a5dc332758b8cc0a513f773880d0951a954`, v1b SHA-256
  `6ed7d7e93c86df6ed0cf30b3a3383582632b5efbb678b377ca2ee1990fb393e7`).
- **Confidence: low.** This is a desk review by an AI coding agent from repository files. Nobody with training in
  data protection or research ethics has read it, no provider page was opened, and no affected community was asked.
- **Assumptions:** the acquired rasters are the product the manifest names; the README's reading of the age grid
  (one composition per district) is right, which was not checked against district polygons; the eight Mae Sai
  tambons are the only units this review speaks for.
- This page is not legal advice and not an official warning.
