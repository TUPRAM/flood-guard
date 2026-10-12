# THEOS-2 on the study event: amendment 1 to plan v1

Written on 12 October 2026, before GISTDA has delivered any image of
September 2024 and before the reference stage has been run on anything.

The plan itself (`theos2_study_event_check_plan_v1.md`) is not edited: the
radar readings were frozen under its SHA-256
(`outputs/theos2_study_event_check/radar_freeze_v1.json`) and a test holds
the two together. This file stands beside it and changes one thing in its
section 4.

## What changes

**The water of a scene is read by rule v2**
(`floodguard.theos2_water_rule_v2.water_v2`, frozen on 11 October: near
infrared at or below red, cloud set aside), and the comparison of question 1
is made against it. **Rule v1**, the rule section 4 describes, is read too
and its figures are given beside those of rule v2.

## Why

On 300 points labelled by three team members
(`docs/theos2_water_label_check.md`, decision log R47):

- rule v2 gives the label on 78% of the labelled area and rule v1 on 69%:
  a difference of 8 points (4 to 13);
- rule v2 needs no threshold found on the scene, so it does not invent water
  on a scene without a flood; rule v1 called 23% of such a chip water;
- rule v2 sets aside 3% of the two reference chips where rule v1 sets aside
  14%.

## What stays as the plan has it

- No setting is made by eye.
- The look comes before the radar: each water raster is looked at beside its
  image before any radar reading is opened, and what was seen is written
  into the reference record.
- A scene on which the rule fails is set aside for question 1 before any
  comparison, with the reason. With two rules: a scene is set aside when
  rule v2 fails on it; if only rule v1 fails, its figures are left out and
  that is said.
- The radar readings, their freeze, the margin of 0.02, the sentences of
  section 5 and the road reading of section 6 are unchanged.

## Before the reference stage is run

The stage `reference` of `scripts/build_theos2_study_event_check.py` still
computes rule v1 alone. It is changed to write both rasters before it is run
on a delivered scene, and its record names this amendment with its SHA-256.

## Known before the images

- Rule v2 marks roads, roofs and concrete as water in places.
- It was developed on flat land in July; Mae Sai is a mountain valley in
  September, with terrain shadow the rule has never seen.
- It finds about seven tenths of the water people see, as rule v1 does where
  rule v1 answers.
- The three labellers agree with each other on 57% of the points. A label
  check on the delivered scene itself, with a new draw of points, would say
  more than the July chips can; whether to make one is for the owners.
