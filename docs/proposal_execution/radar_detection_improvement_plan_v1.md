# Improving the radar flood detection: plan v1

Written on 9 October 2026, after the results of work packages 3 and 7
(decision log R34, R35) and before any of the changes below was tried. It
says what will be changed, on which data each change is judged, and which
data nobody looks at until one detector is frozen.

## 1. Where the detection stands

| What was measured | Result |
|---|---|
| Three fixed radar rules on the THEOS-2 tile at Sukhothai | They flag 22% to 50% of the water the image shows; 61% to 76% of their flags are on water (IoU 0.21 to 0.38) |
| The same rules at Mae Sai, agency layer of 22 October 2024 | With a wet-season image before: almost nothing. With a dry-season image: UN-SPIDER flags 70% (IoU 0.33) |
| A trained classifier (boosted trees, all radar features) on the THEOS-2 tile | Ranks the cells best of all, but with its frozen cut flags 11% of the water (IoU 0.11) |
| A single threshold on VH backscatter after the event | Flags 64% of the water, 83% of its flags on water (IoU 0.57). One tile; not the model the plan had named |

Three causes stand out, each with a remedy that can be tested:

1. **The image before.** A single image from the wet season hides water that
   was already there. Change features built on it did not travel.
2. **The cut.** A cut learned where under 1% of the ground is water fails
   where a third of it is.
3. **The labels.** One agency layer of one date, possibly made from the same
   radar pass.

Two limits are physical and no model removes them: C-band radar does not see
water under rice, trees or between buildings, and it does not see water that
drained before the pass.

## 2. The data and its roles

**The Sukhothai tile has now been looked at.** Every method of the project
has been scored on it, so it cannot judge an improvement any more. From here
on it is development data.

| Role | Data |
|---|---|
| Development | The agency layer of 22 October 2024 in the eight training districts and Mae Sai; the THEOS-2 tile at Sukhothai (30 July 2025) |
| **Held out until one detector is frozen** | The two THEOS-2 chips of 31 July 2025, 03:51 UTC (`IMG_T2V_20250731035100_ORTHO_PMS_32-001.tif` and `-003.tif`). No water map has been read from them and no radar has been set beside them |
| Not read | Mueang Chiang Rai and Phan (reserved for cases SE2 and SE2-blind) |

If a dated reference for September 2024 arrives (the THEOS-2 scene or the
UNOSAT data asked for on 7 October), it is held out in the same way, for the
study event.

## 3. The changes, in the order they are tried

Each is tried on the development data only.

| | Change | Why |
|---|---|---|
| A | **A dry-season baseline in place of one image before.** For each cell, the median backscatter of the passes of the dry season before the event (same orbit) | Removes the dependence on one image; makes "change" mean the same thing in every scene |
| B | **A cut that is set per scene.** The value that splits each scene's own model values into two groups (Otsu on tiles that hold both water and land), with the frozen cut as a fallback when a scene shows one group only | The model's ranking carried over; its fixed cut did not |
| C | **Change features measured against the baseline of A**, with the spread of the dry-season passes as a feature, so a cell that is always dark is told apart from one that went dark | On the tile, the trees that used the image before reached 0.11; the trees without it 0.41 |
| D | **More than one source of labels.** Train on the agency layer and on the THEOS-2 water of Sukhothai together, with whole areas held out in turn | One date of residual water is a narrow teacher |
| E | **Cleaning after the cut.** Drop flags on slopes above 5 degrees and on ground more than a set height above the nearest stream; drop groups under a minimum size; let a flagged group grow into neighbouring cells that are nearly as dark | Standard practice; cheap; removes scattered false flags and fills the edges of real water |
| F | **Say where the radar cannot see.** Built-up and tree-covered cells are marked "not observable" rather than "dry", and the terrain model of work package 4 says whether water is plausible there | Turns a blind spot into a stated one; it is not counted as detection |

The simple threshold on VH after is carried through every step as the
baseline to beat. A change is kept only if it is better than the step before
it on the development data **with areas held out in turn** (train without
Sukhothai and score on it; train without a block of districts and score on
it), by 0.02 in intersection over union on both.

## 4. Freezing and the one test

1. After steps A to F, **one** detector is frozen: its features, its model,
   its cut rule and its cleaning, with a freeze record committed.
2. The water reference of the two held-out chips is then built from the
   THEOS-2 images alone, with the same rule as at Sukhothai, and committed.
3. The frozen detector, the simple threshold and the three fixed rules are
   run on the held-out chips, once.

**What will be said, fixed now.**

- "Improved" means: on the held-out chips together, the frozen detector's
  intersection over union is higher than that of the best fixed rule by 0.03
  or more, and at least 70% of its flags are on water.
- If the frozen detector is not better than the simple threshold by 0.03,
  the simple threshold is the detector the project names, and the text says
  that nothing more complex was needed.
- If neither is better than the fixed rules, the text says so and the fixed
  rules stay.
- Whatever comes out, a detector enters a planning score only through a new
  protocol version, which is not part of this plan.

## 5. What a better detector is then used for

Report-only, as work package 2 was:

- The September 2024 pass at Mae Sai is read again with the frozen detector
  and a dry-season baseline, and put through the road and access chain as one
  more row of the table of flood inputs. The question it answers: does Ko
  Chang still lose its roads when the water comes from our own detection?
- It cannot be scored for September without a dated reference. Until one
  arrives the row is labelled as unchecked.

## 6. Limits known beforehand

- Development data: one province in October 2024 and one tile in July 2025.
  The held-out chips are from the same week and region as the Sukhothai tile;
  a pass there does not prove the detector for a mountain valley in
  September.
- The THEOS-2 references are 19 to 44 hours away from the radar pass.
- Every figure is agreement with a reference layer, not accuracy.
- Time: the freeze of 18 October. Steps A, B and E come first because they
  are cheap; D and F are dropped before the test if they are not done by
  15 October.
