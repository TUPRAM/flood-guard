# Journey v2: the story on the real map of Mae Sai (branch `journey-v2`)

Status: in progress on branch `journey-v2` only. The owner asked on 14 October 2026 that this work stays on its own
branch: no merge into `master`, no change to `cinematic-journey-v2`. Decisions below are recorded here, not in the
decision log, so their R and V numbers do not collide with `master`.

## What changes

The `/journey/` story leaves the invented village and plays on the real map of Mae Sai town, with the water of the
published replay (revision r5, a model reconstruction of September 2024 with low confidence). The people stay
fictional.

| | Before (cinematic-journey-v2) | journey-v2 |
|---|---|---|
| Place | Invented village, one road, a swale | Mae Sai town around the Public app's example home (20.44042, 99.88718) |
| Buildings | About 20 procedural houses | Open building outlines (Google Open Buildings v3 and Microsoft, combined by VIDA), extruded with a Thai building kit; heights and looks are illustrative |
| Water | One flat level per state; one stretch of road floods | The replay's water, cell by cell: depth = k × (stage − HAND) at the hour of each beat |
| Destination | A clinic | The Mae Sai Subdistrict Municipality Office shelter (reported in use from the early hours of 11 Sep 2024), the nearest reported shelter by walk (about 1.6 km) |
| Narin and Pim | An invented office | At the Mae Sai District Office, the reported 2024 incident command centre (an illustrative operations room at its real place, in place of the real building) |
| Time | Water states | Replay hours 12, 40, 46, 48, 84 and 132, the hours of the Public app's practice scenarios |

## Facts the story rests on (read from the published files)

- Dry example home: r5 cell (col 550, row 380), code 76 (3.80 m), k = 1. Dry at every story hour. Its access node
  (0.6 m away) loses its walk to a reported shelter at 2.15 m (cut code 43): nearly cut at hour 48, cut at hour 84.
- Flooded neighbour (110 m away): cell code 55 (2.75 m), k = 1: 0.75 m of modelled water at hour 84.
- Stage by hour (numpy.interp over the r5 anchors, identical to `stageAt`): h12 0, h40 0.1, h46 1.2612902426637274,
  h48 1.8806463600440977, h84 3.5, h132 0.9.
- The usual walk (access network, stage 0) goes to R01, the Mae Sai Subdistrict Municipality Office shelter, about
  1.57 km (about 1.6 km as drawn). Its first edge to close runs from 75 m to 112 m along the walk, south of the home,
  at a stage of 2.05 m (the app's resident point: 2.15 m). Within 2 km, R01 and R03 (Wat Tham Pha Chom)
  stay reachable up to hour 48; none from a stage of about 2.2 m.
- Wat Mueang Daeng (R04) is not a shelter in this story: the record says it was itself flooded and evacuated around
  11 to 12 September 2024 and used as a shelter from 21 September. The model shows its cell dry (code 182). The story
  uses it as an example of what still needs checking (model and reports disagree).
- Mae Sai District Office (R05): relief and incident command centre from 11 September 2024 (reported). Cell code 255
  (never floods in the model).

## Data contract: `apps/web/public/journey/town/`

Baked by `scripts/build_journey_town.py --external-root <dir> --generated-at <ISO>` (deterministic; `--verify`
re-bakes into a temporary folder and compares bytes). Receipt: `docs/journey_town_input_receipt.json`.

Frame: a local plane at the dry example home. `x = (lon − 99.88718) × 111320 × cos(20.44042°)`,
`z = (20.44042 − lat) × 110540` (metres; x east, z south, y up; the constants of `groundDistanceM`).
Detail extent x −1500…900, z −800…1800. Backdrop: 8 km square of DEM relief at 60 m.

| File | Content |
|---|---|
| `mae-sai-town.json` | Manifest (provenance, timestamp, confidence, assumptions, credits, replay hashes, frame, places, beats, route) and vectors (buildings, roads, trees) as integer decimetres |
| `mae-sai-town-cells.png` | RGB 8-bit crop of the r5 `hand-codes.png` covering the detail extent, cell for cell: R code, G depth-factor byte (k = G/255 × 2.5), B 255 where low confidence |
| `mae-sai-town-relief.png` | RGB 8-bit on the same cells: R, G = uint16 (big-endian) of height in decimetres + 2000 for cells that never flood (code 255), from the Copernicus DEM above the drainage datum |
| `mae-sai-town-cover.png` | Greyscale 8-bit, 4 m cells over the detail extent: 0 open ground, 1 water (OSM), 2 road, 3 building, 4 green, 5 field |
| `mae-sai-town-backdrop.png` | RGB 8-bit, 60 m cells, 8 km square: uint16 relief as above |
| `LICENSE.txt` | Licences and credits |

Rendering rules (web): ground height of a floodable cell = k_s × code × 0.05, where k_s is k smoothed over about
30 m (channel cells, code 0, are at 0, so their drawn depth is the model's k × stage); water surface = k_s × stage; a
cell is wet exactly when stage > code × 0.05 (the model's rule; it does not depend on k). Cells that never flood take
the relief height, reached over about four cells from the nearest floodable ground and never lower than 0.5 m above
its highest water: the relief and k_s × HAND have different bases, and met directly they made cliffs of up to 29 m.
The river at a dry hour is drawn from the OSM water cover, not from channel cells (the Public map shows no water at
stage 0). Lalita's house faces the street nearest the home place (road 112) on its real outline, set back behind a
yard (`home-plot.ts`); a rectangular pad holds the house and yard at the home cell's height, the back wing keeps the
model's ground, and roads, poles and cables are not drawn on the plot. Through town the replay's channel cells run about 100 to 150 m south of the OSM river (a property of r5's
30 m surface model, recorded in the manifest's limitations), so the water rises from the model's lines, not from the
drawn river.

## Rights

Open building outlines: the provider states CC BY 4.0 and ODbL 1.0 (Google Open Buildings v3) and ODbL 1.0
(Microsoft). Until now the project published counts only (SOURCES_AND_RIGHTS.md, note of 11 October 2026). On the
owner's request of 14 October 2026 for the real buildings in the journey, this branch publishes simplified outlines
of the journey box as a derivative database under ODbL 1.0 with the credit, and the 3D scene drawn from them with the
credit. This is an engineering note on the right to use, not a legal clearance.

## The story (beats)

| Chapter | Replay time (ICT) | Scene | Phone (real Public app) |
|---|---|---|---|
| Opening | 9 Sep 12:00 | Aerial over Mae Sai: the Sai River border, the town, the hills | — |
| 01 Lalita's family | 9 Sep 12:00 | Down to the family at the example home; the usual walk to the shelter in teal | Home, "Normal day" |
| 02 Rain, and a plan | 10 Sep 16:00 | Rain; shallow water in the lowest streets by the river; the family plans | Prepare, "Shallow water on roads" |
| 03 The night | 10 Sep 22:00 to 11 Sep 01:00 | Night; water fills the streets toward the river; the walk's low points go under | Report; "Roads under water", then "Walk to a shelter nearly cut" |
| 04 Cut off · Narin | 12 Sep 12:00 | Home dry, the street not: the island; the simulated call to 1784; over the town to the District Office; Narin | "Cut off, home dry"; then the case view at hour 84 |
| 05 The district · Pim | 12 Sep 12:00 | Pim at the planning table (the real command exercise on it throughout); from above, homes cut off like hers. The story ends here | Command exercise at hour 84 |

Every beat shows its replay date and time and "model reconstruction, low confidence".
