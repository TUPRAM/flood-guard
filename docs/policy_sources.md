# The policy page: its sources, and what was checked

Written 12 October 2026 with the plain-language policy page (`/policy/`).
The list of sources itself is in one place,
`apps/web/src/lib/policy-brief.ts`, so the page and this note cannot drift
apart; a test checks that every link is on the page. This note says how the
list was made and what it does and does not support.

## What the page is built from

| Part of the page | Where it comes from |
|---|---|
| The text: three government points, three proposals, ground rules, questions | The team's policy document of 12 October 2026 |
| The example of Ko Chang and Mae Sai town | The published case SE1 (`apps/web/public/planning-overlays/mae-sai-2024/se1.json`), read through `policy-case.ts` |
| The five weights | The signed scoring frame (decision D4) and `src/floodguard/scoring.py` |
| "Does the result depend on these weights?" | `docs/fpps_weight_sensitivity.md` |
| The Thai text | Written by the project's AI assistant; not reviewed by a native speaker |

## What was checked on 12 October 2026

- **The Chiang Rai release of 15 May 2026** was opened and read. It gives the
  figures the page quotes: a permanent flood wall under study at an estimated
  2,900 million baht, about 4 hours of warning for Mae Sai and up to 9 to 12
  hours for Chiang Rai city, a tabletop exercise on 20 May with about 350
  people and a field exercise on 22 May with about 890 people (flood
  evacuation in Mae Sai, landslide evacuation in Mae Fah Luang). The headline
  of the release says "over 800"; its text says about 890.
- **Each research paper** was looked up and its record read (authors, year,
  journal, DOI, and the finding the page quotes from its abstract). The full
  text of the papers was not read.
- **The published case**: every figure of the example is printed from the
  case file, and a test fails if the page and the file differ.

## What was not checked

- **The section numbers of the 2007 Act** (12(2), 15, 16, 20, 21, 44) and
  **the chapter and indicator references to the National Plan** are as the
  team's document gives them. The copies of the Act that could be reached are
  scanned files that could not be read by machine. Someone who reads Thai
  should open the Act and the plan once and confirm each reference before the
  page is quoted to an official.
- No agency was asked whether it agrees with the reading of its text. The
  page says so: these are proposals, and no agency has adopted them.

## How the research list was chosen

Four questions a reviewer of the page would ask, and the literature for each:

1. **Is "lost access" a recognised measure?** Yes: the Sendai Framework
   counts disruption of basic services (target D), and a line of research
   pairs flood maps with road networks to find who cannot reach, or be
   reached by, a service (Coles 2017; Green 2017; Papilloud and Keiler 2021;
   Tariverdi 2023), with Logan and Guikema (2020) arguing that fair access to
   essential services is what resilience should mean.
2. **Why children and older people?** Flood deaths fall heavily on older
   people (Jonkman 2009), and age is among the drivers the reviews find
   (Rufat 2015; Cutter 2003). The same reviews name income and health, which
   the score does not have.
3. **Why should local officials decide?** The law gives them the duty, and
   the study of the 2011 floods (Marks and Lebel 2016) shows what happens
   when the duty is local and the capacity is not.
4. **Are the weights defensible?** No paper gives these five weights, and
   none could: the handbook on composite indicators (OECD and JRC 2008) and
   the reviews (Greco 2019; Moreira 2021) treat weights as value judgements
   to be declared and tested. Tate (2012) and Saisana (2005) give the method
   of the test; Becker (2017) explains why a weight is not the same as
   influence; de Brito (2018) shows the alternative of setting weights with
   local experts. The test itself is in `docs/fpps_weight_sensitivity.md`.

## Limits

- A paper on the list supports one idea of the page. None endorses
  FloodGuard and none validates the score.
- Most of the access studies are of cities in Europe and the Americas. The
  two sources on Thailand are about governance and about the 2024 flood
  extent; no study of access loss in a Thai flood was found in this search.
- The list is a search of one afternoon, not a systematic review.
