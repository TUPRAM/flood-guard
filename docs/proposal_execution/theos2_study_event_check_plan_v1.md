# THEOS-2 on the study event: plan v1

Written on 9 October 2026, before GISTDA has delivered any THEOS-2 image of
September 2024 and before the radar readings below were written. It says what
will be compared with what, in which order, and which sentences will be
written whatever the figures turn out to be.

## 1. Why

Every check of the radar so far was made somewhere else (the Sukhothai tile
of July 2025) or against a layer of another date (the agency layer of
22 October 2024). The project has no dated picture of the flood it studies.
GISTDA has offered THEOS-2 scenes of September 2024 over Mae Sai district
(reply of 9 October 2026, `outputs/theos2_request/gistda_reply_2026-10-09.md`).
They answer two questions:

1. How much of the water an image of the event shows do our radar readings of
   the same days flag?
2. What does the image show of the roads that the Ko Chang road sheet names,
   above all the road in Si Mueang Chum that it names first?

## 2. The scenes and their roles

| Scene | Hours after the radar pass | Role |
|---|---:|---|
| THEOS-2, 17 September 2024, the clear scene (0 to 3% cloud) | about 28.6 | **Primary.** Town, west and centre of the district, the first road of the road sheet |
| THEOS-2, 16 September 2024, `…_001280` | about 4.3 | Second. A strip in the south-east; the closest in time |
| THEOS-2, 21 September 2024 | about 124 | Roads only (question 2). Too late for question 1: not scored against the radar |
| THEOS-2, 14 January 2025 | | Dry season. Not a flood reference and not part of this check |

The radar pass is Sentinel-1, 15 September 2024, 23:16 UTC (16 September,
06:16 local time), the one the project has used throughout. A scene that is
not delivered has no role; nothing is put in its place.

## 3. The radar side is frozen first

Before any scene is received, six readings of the pass are written on the
10 m lattice of the district and their SHA-256 is committed
(`outputs/theos2_study_event_check/radar_freeze_v1.json`):

| Reading | What it is |
|---|---|
| `frozen_detector` | The detector frozen in decision log R37: VH after at or below −18.46 dB, cleaned |
| `simple_threshold` | The same threshold, not cleaned |
| `un_spider_dry_baseline` | The UN-SPIDER quotient rule, image before = the median of three dry-season passes |
| `un_spider_last_pass_before` | The UN-SPIDER quotient rule, image before = the last pass of the same orbit before the event that the radar source holds |
| `m1_literal_last_pass_before` | Rule M1-literal, same image before |
| `m1_v2_last_pass_before` | The frozen rule M1-v2, same image before |

The last three are the **fixed rules**. Their image before is fixed by a rule,
not chosen for this event: the last pass of the same orbit before the pass of
15 September, at most 36 days earlier, in the source the project reads radar
from.

**Amended on 9 October 2026, before any reading was written and before any
image was received.** The first text of this section named the pass 12 days
earlier, the rule of the held-out test of R37. The first run of the radar
stage stopped: the source (Sentinel-1 RTC on the Planetary Computer) holds no
pass of 3 September 2024. The pass it does hold is that of 22 August 2024,
24 days earlier, which is also the image before of the dated radar check
(R34). The run of record of September 2024 used the pass of 3 September from
another processing chain; it is not one of the six readings. No reading is tuned, re-cut or cleaned again
after an image is seen: the comparison stage refuses a raster whose SHA-256
is not the frozen one.

## 4. The reference

- The water of a scene is read by the rule of the Sukhothai cross-check and of
  the held-out chips: NDWI above the upper threshold of a three-class Otsu
  split computed on the scene, bright objects unobservable, water objects
  under 1,000 square metres dropped. **No setting is made by eye.**
- It is laid on the 10 m lattice of the district. A cell is compared when the
  image shows it clearly as water or as not water; cells of permanent water,
  cells outside the district and cells the image does not show are left out.
- **The look comes before the radar.** Each reference is looked at beside its
  image before any reading is opened, and what was seen is written into the
  reference record. If the rule fails on the scene (cloud shadow or bare soil
  read as water, turbid flood water missed), the scene is set aside for
  question 1 before any comparison, with the reason. This is what happened to
  one of the two held-out chips of R37.
- The reference record is committed before the comparison is run.

## 5. Question 1: what is counted, and the sentences

For each reading, on the compared cells: the flagged area, the share of its
flags on the water of the image, the share of that water it flags, and the
intersection over union. The same again on open ground and on built-up or
tree-covered ground (WorldCover), with the share of the compared ground that
is built-up or trees.

Sentences fixed now:

- **Naming.** A new reading (`frozen_detector`, `simple_threshold`,
  `un_spider_dry_baseline`) is named as better than the fixed rules on the
  study event only if its intersection over union on the primary scene is
  higher than that of the best fixed rule by 0.02 or more. Otherwise: "no new
  reading is better than the best fixed rule; the fixed rules stay". A reading
  that is named does not replace the rules of record on the strength of one
  scene.
- **The time gap, always.** "The image was taken N hours after the radar
  pass. Water that left in between counts against the radar, so the share of
  flags on water is a lower bound; water that arrived in between counts
  against it too."
- No figure is called a measure of how right the radar is on the ground.
  Each is agreement with one image read by one rule.
- The second scene is reported in the same way and named as the second scene.
  It decides nothing the primary scene did not.

## 6. Question 2: the roads

For each of the eight roads of the road sheet
(`outputs/ko_chang_road_check/ko_chang_roads_se1_v1.json`), every piece of the
road in the planning context is laid over the 2 m water raster of the image:
the metres of centreline on water, the metres the image shows, and whether the
piece counts as seen under water (20 m of centreline on water, as in the
Sukhothai check of the closure rule).

Sentences fixed now:

- A road piece under water on the image, days after the peak, was very likely
  under water at the peak.
- A road piece that is dry on the image may still have been under water at
  the peak. **The image cannot show that a road stayed passable.**
- A road the image does not show is "not observable", never "dry".

So the image can confirm a closure of the scenario and cannot refute one. The
road sheet's question "was the first road raised, or did it stay passable"
can be answered with yes-it-was-under-water, or left open.

## 7. Order of the commits

1. This plan.
2. The radar freeze record (stage `radar`), before any scene is received.
3. For each scene: the reference record (stage `reference`), with the look
   written down.
4. For each scene: the comparison (stage `compare`), once.

Each stage refuses to run out of this order, and the comparison refuses a
plan or a freeze record whose SHA-256 has changed.

## 8. What this will not do

- It qualifies no flood map and opens none of the gates of the signed
  protocols. It is report-only: no published class changes and nothing enters
  a planning score.
- It does not turn the season scenario into an observed flood. Case SE1 stays
  a scenario.
- It trains nothing. No scene of the event is used to fit or to tune.
- The imagery stays outside Git. An overview picture is shown only if GISTDA
  says it may be.

## 9. Known weaknesses, stated before the result

- The primary scene is 28.6 hours after the pass and four to five days after
  the peak. In a flash-flood town much of the water has gone by then.
- Flood water at Mae Sai was muddy. NDWI can miss turbid water and mud left
  behind; the look of section 4 is there to catch that.
- No scene of 16 or 17 September covers most of Ko Chang. Question 2 rests on
  the west edge and, for the rest, on the scene of 21 September.
- Delivery is expected around the freeze of 18 October, so the result will be
  an addition after the freeze.
