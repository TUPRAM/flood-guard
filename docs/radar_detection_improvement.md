# Improving the radar flood detection: result

**What this is.** Six changes to the radar detection were tried on data the
project had already looked at, one detector was frozen by a rule fixed
beforehand, and that detector was tested once on a THEOS-2 chip nobody had
read. The September 2024 pass at Mae Sai was then read again with it and put
through the road and access chain.

**How to read every figure.** Each figure is agreement with a reference layer:
an agency layer that was not checked in the field, or water read from a
THEOS-2 image taken 19 to 44 hours before the radar pass. None is accuracy.
Nothing here enters a planning score or changes a class, and it is not an
official warning.

- Plan, committed before any change was tried: `docs/proposal_execution/radar_detection_improvement_plan_v1.md`
- Freeze record, committed before any held-out chip was read: `outputs/radar_detection_improvement/freeze_v1.json`
- Reference of the held-out chips, committed before any radar of them was read: `…/held_out_reference_v1.json`
- The one test: `…/held_out_test_v1.json`
- The September re-read: `outputs/september_reread/mae_sai_20240915_v1.json`
- Code: `src/floodguard/radar_detection.py`, `src/floodguard/s1_rtc.py`, `scripts/build_radar_detection_improvement.py`, `scripts/build_september_reread.py`
- Confidence: low.

## The short version

1. **On the development data two things helped a great deal**: a dry-season
   baseline for the fixed change rule, and cleaning after a simple threshold.
2. **The trained trees were not kept.** With a cut each scene sets for itself
   they were best on the lowland tile and far worse at Mae Sai.
3. **The one held-out test did not confirm an improvement.** The chip that
   was left to test on shows a flooded town. There the frozen detector, the
   simple threshold and two of the fixed rules all flag about a fifth of the
   water, almost all of it correctly. By the rule fixed beforehand, the fixed
   rules stay the project's radar reading.
4. **Read again with a better detector, the September pass still does not
   cut Ko Chang off.** 290 of its 5,972 residents lose every route, against
   all of them under the season layer.

## 1. What was tried, on data already seen

Two areas were held out in turn: Mae Sai district (agency layer of 22 October
2024) and the THEOS-2 tile at Sukhothai. A change was kept only if it was
better than the step kept before it by 0.02 in intersection over union on
both.

| Step | Mae Sai: flags on water / water flagged / IoU | Sukhothai: flags on water / water flagged / IoU | Kept |
|---|---|---|---|
| Simple threshold on VH after (the baseline to beat) | 30% / 58% / 0.24 | 83% / 64% / 0.57 | baseline |
| B: the threshold with a cut per scene | 30% / 58% / 0.24 | 85% / 61% / 0.55 | no |
| B: trees without the image before, cut per scene | 5% / 100% / 0.05 | 67% / 87% / 0.61 | no |
| C: trees against the dry-season baseline, cut per scene | 13% / 100% / 0.13 | 69% / 86% / 0.62 | no |
| D: the same, trained on two label sources | 17% / 99% / 0.17 | 72% / 83% / 0.63 | no |
| **E: the simple threshold, cleaned** | **38% / 90% / 0.36** | **77% / 73% / 0.60** | **yes** |

**The frozen detector:** a cell is flagged when its VH backscatter after the
event (a 5 by 5 mean) is at or below -18.5 dB. Flags on slopes of 5 degrees or
more are dropped, then groups of fewer than 8 cells. A group that is kept
grows into touching cells that are within 1.5 dB of the threshold.

**Why the trees were not kept.** On the lowland tile, where a third of the
ground is water, a scene's own cut works and the trees gain up to 0.06. At
Mae Sai, where 1% is water, the same cut lands far too low: the trees then
flag nearly all the agency water and twenty times as much ground that is not.
The cut per scene needs water and land in the same tiles to find itself. The
plan's rule asks for a gain on both areas, and this is what it is for.

**Change A, the fixed rule with a dry-season baseline** (not part of the
ladder; it changes a rule, not the detector):

| UN-SPIDER rule, image before | Mae Sai, IoU | Sukhothai tile, IoU |
|---|---:|---:|
| One wet-season image (as in the runs so far) | 0.001 | 0.26 |
| One dry-season image (12 April 2024) | 0.33 | not run |
| Median of three dry-season passes | 0.20 | **0.53** |

On the Sukhothai tile the same fixed rule doubles its agreement when the
image before is a dry-season median. At Mae Sai the median does less well
than the single April image; three passes are few, and February and March
fields differ from April ones.

**Change F, where the radar cannot be asked.** About 40% of the compared
cells in both areas are tree cover or built-up ground. They hold 1% of the
agency water at Mae Sai and 9% of the water on the Sukhothai image. Counted
on the other cells only, the frozen detector reaches 0.38 and 0.66.

## 2. The one test

Two THEOS-2 chips of 31 July 2025 had been held out. Their water reference
was built from the images alone and looked at beside them before any radar
was read.

- **One chip was set aside at that point.** It shows hill country with
  ploughed fields and forest and holds no flood. The water rule, which splits
  the image's own values, marks its bare soil as water. It is not used as a
  reference. It is used for one thing: counting what each detector flags
  where there is no flood.
- **The chip that was tested shows a flooded town**: 7.0 km² compared, 46% of
  it water on the image. Sentinel-1 passed 19 hours later. 64% of its cells
  are built-up or tree-covered, and they hold 46% of the water.

| On the flooded-town chip | Flags on water | Water flagged | IoU |
|---|---:|---:|---:|
| Frozen detector | 91% | 24% | 0.23 |
| Simple threshold | 93% | 20% | 0.20 |
| Fixed rule: UN-SPIDER practice | 94% | 23% | 0.23 |
| Fixed rule: M1-literal | 62% | 62% | 0.45 |
| Fixed rule: M1-v2 | 95% | 20% | 0.20 |

| On the hill chip with no flood (9.0 km²) | Flagged |
|---|---:|
| Frozen detector | 0.02 km² |
| Simple threshold | 0.05 km² |
| UN-SPIDER practice, M1-v2 | 0 km² |
| M1-literal | 2.67 km² (30% of the chip) |

**The sentence the plan fixed beforehand:** "improved" means better than the
best fixed rule by 0.03 with at least 70% of flags on water. **Neither the
frozen detector nor the simple threshold is better than the fixed rules on
the held-out chip. The fixed rules stay.**

What the two tables say together:

- In a flooded town, every careful detector sees the same fifth to a quarter
  of the water: the open water around the buildings. What it flags is right
  nine times in ten. The rest is between and under things C-band radar does
  not see through. On the cells where radar can be asked, the frozen detector
  flags 39% of the water.
- M1-literal is the "best fixed rule" on the town chip only because it flags
  so much: the same rule flags 30% of a chip with no flood, and a third of
  Mae Sai district on a day with 1% water. Its 0.45 is not a detector to
  trust.
- The frozen detector keeps its false alarms very low (0.02 km² on 9 km² of
  dry hills) and gains a little over the plain threshold everywhere. That is
  real, and it is not the improvement the plan asked for.

Computed after the test, and so not part of it: the UN-SPIDER rule with the
dry-season median as its image before reaches 0.15 on the town chip, below
its 0.23 with the image of 12 days earlier. The baseline that doubled the
rule's agreement at Sukhothai does not help here.

## 3. The September 2024 pass at Mae Sai, read again

The pass of 15 September 2024 (16 September, 06:16 in Thailand, about four
days after the peak) was read three ways against the dry-season baseline, cut
to the eight tambons and put through closure rule v1 and the access
difference, as the flood inputs of work package 2 were. Central closure
level. **Unchecked: there is no dated reference for September 2024.**

| Flood input | Water in the district | Residents who lose every route, eight tambons | Ko Chang, of 5,972 |
|---|---:|---:|---:|
| 2024 season layer (case SE1) | | 21,798 | 5,972 |
| Radar, runs of record: UN-SPIDER / M1-v2 | | 728 / 211 | 262 / 0 |
| Radar, re-read: frozen detector | 23.8 km² | 1,704 | 290 |
| Radar, re-read: simple threshold | 20.4 km² | 1,018 | 220 |
| Radar, re-read: UN-SPIDER with the dry baseline | 11.5 km² | 599 | 144 |

The better reading finds far more water than the runs of record did, and
more than twice as many residents cut off. It does not come near the season
layer. **Ko Chang's total loss of access belongs to the season scenario, in
which everything ever mapped as flooded between August and October is flooded
at once. One radar pass four days after the peak, read as well as we now can,
cuts off one resident in twenty there.**

This does not weaken the planning result; it says what kind of result it is.
The team already calls it a scenario. It should not be told as what the radar
saw on a day.

## What follows

- **The fixed rules stay the project's radar reading**, and no radar reading
  enters a planning score.
- **Two method notes are worth keeping**: state the image before, and prefer a
  dry-season one on open farmland; clean a threshold's flags by slope, group
  size and growth. Both are cheap and both held on the development data.
- **For the pitch.** "We tried to improve our radar detection and tested it
  on an image we had locked away. On open land it improved. In a flooded town
  nothing we built sees more than a quarter of the water, and we say so: that
  is where a higher-resolution image, like THEOS-2, is needed."
- **What would change this.** A dated reference for September 2024 on the
  study area (asked for on 7 October), and a held-out tile of open farmland,
  where the changes were shown to help.

## What was not done as planned

- One of the two held-out chips could not serve as a reference (above). The
  test rests on one chip.
- Change E without the height above the nearest stream: no drainage model
  exists for the tiles. Slopes, group size and growth only.
- Change F marks and counts the cells radar cannot be asked about. The terrain
  model of work package 4 covers Mae Sai only and was not joined.
- The trees were fitted with one setting; no new tuning.

## Limits

- Development: one province in October 2024 and one lowland tile in July
  2025. Test: one chip of 7 km², a town, one event.
- The THEOS-2 references are 19 and 44 hours older than the radar passes.
  Water that drained in between counts against every detector.
- The agency layer may come from the same radar pass as the features.
- Boosted trees are scikit-learn's `HistGradientBoostingClassifier`.

## Credits

UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0); changed
by FloodGuard, and the figures derived from it are shared under CC BY-SA 4.0.
THEOS-2 sample imagery: GISTDA, for the GeoHackathon. Contains modified
Copernicus Sentinel data 2024 and 2025, processed by Microsoft Planetary
Computer. ESA WorldCover 2021 v200 (CC BY 4.0). Copernicus DEM GLO-30. Roads ©
OpenStreetMap contributors (ODbL 1.0). Residents: WorldPop 2020 (CC BY 4.0).
