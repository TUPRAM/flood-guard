# Reply to GISTDA (Pimnipa T.), draft of 9 October 2026, second version

Drafted by the agent for Callixta to send; nothing was sent by the agent.
This version was written after reading GISTDA's six attachments (catalogue
screenshots with the footprint of each scene over our area). It replaces the
first draft of the same day, which was written without them.
Attach the three GeoJSON files named at the end.

---

**Subject:** Re: THEOS-2 imagery for Mae Sai: confirmed scenes, separate AOI files and priorities

Dear Pimnipa,

Thank you for checking our request so carefully. The footprints in your attachments were very helpful: they showed us that our first choice was not the best one. Here are the answers you asked for.

**1. Scene for 16 September 2024**

You are right: the scene we named (`…_000640`) lies outside our area. We took the ID from the catalogue list by its date and could not check its footprint. Please use the one you suggest instead:

`SC_T2V_202409160336048_VXB_E100N20_001280` (16 September 2024, about 22% cloud)

From your Attachment 2 we understand that it covers the south-east part of our area. We would still like it: it was taken about four hours after the Sentinel-1 pass we use, which makes it the best scene for checking our radar flood detection.

One question on this strip: the catalogue list also shows a third scene of 16 September at the same time, with about 50% cloud. Is it the next scene to the north, and does it cover Ko Chang subdistrict (our priority 1 box below)? If it does, we would like it as well, even with the cloud.

**2. Our choices, in order of priority**

Having seen the footprints, we would like to change our order:

| Priority | Scene | Why |
|---|---|---|
| 1 | **THEOS-2, 17 September 2024**, the clear scene shown in your attachment "17092024 - scene" (0 to 3% cloud) | It covers Mae Sai town and the west and centre of the district almost without cloud, one day after the radar pass. This is now our first choice. |
| 2 | **THEOS-2, 16 September 2024**, `…_001280` | Closest in time to the radar pass (see above). |
| 3 | **THEOS-2, 14 January 2025**, the two cloud-free scenes | They cover the east of Ko Chang. We would use them to map roads and embankments without water. |
| 4 | **THEOS-2, 21 September 2024**, the left scene (about 13% cloud) | Only if it is little extra work. It covers the west of Ko Chang nine days after the flood peak. |

If you can prepare only two scenes, priorities 1 and 2 are the ones we need most.

We no longer need the **THEOS-1** scene of 17 September: from your attachment, it touches only the south-east corner of our area. Thank you for checking it.

For all scenes the same product as the hackathon samples would suit us best: ORTHO PMS, 4 bands including NIR.

**3. Separate AOI files**

Three GeoJSON files are attached, one polygon in each. In our first file the small box lay inside the large one, which is why only one rectangle appeared.

| File | Area | Size |
|---|---|---|
| `floodguard_aoi_priority1_ko_chang_2026-10-09.geojson` | Ko Chang subdistrict and the roads into it | about 12 x 10 km |
| `floodguard_aoi_priority2_mae_sai_town_2026-10-09.geojson` | Mae Sai town, border crossing and Sai River strip | about 11 x 9.5 km |
| `floodguard_aoi_priority3_mae_sai_district_2026-10-09.geojson` | Whole Mae Sai district (it contains the other two) | about 24 x 23 km |

The first box is new: since our first email, our analysis has shown that the main result depends on the roads of Ko Chang. For every scene, we only need the part that falls inside the district box. If a scene must be cut smaller, the parts inside the first two boxes matter most.

**4. Pléiades**

Understood, and thank you for the clear answer. We will not request Pléiades imagery.

**Two short questions**

- May we show a reduced overview picture of the imagery, and figures derived from it, in our final presentation, with credit to GISTDA? The imagery itself would not be shared or published.
- We understand that preparation takes at least a week. If the scenes can be delivered in steps, could the 17 September scene come first?

If we have misread any footprint, please correct us and we will follow your advice on which scenes fit best.

Thank you again for your help. We know this is extra work for your team and we appreciate it very much.

Best regards,
Callixta Fidelia C.
TeamBits

---

## Attachments

- `outputs/theos2_request/floodguard_aoi_priority1_ko_chang_2026-10-09.geojson`
- `outputs/theos2_request/floodguard_aoi_priority2_mae_sai_town_2026-10-09.geojson`
- `outputs/theos2_request/floodguard_aoi_priority3_mae_sai_district_2026-10-09.geojson`

## What the agent read from GISTDA's attachments (not for the email)

Read from six catalogue screenshots by eye, against the district box; positions are good to about a kilometre.

| Scene | What it covers of the district | What it is good for |
|---|---|---|
| THEOS-2 16 Sep 2024 `…_000640` (the one we asked for) | Nothing: it lies south-east of the district box | Not usable |
| THEOS-2 16 Sep 2024 `…_001280` (GISTDA's suggestion) | A narrow strip in the south-east: east of about 99.96 E and south of about 20.37 N. It stops just south of Ko Chang and does not reach Mae Sai town | Radar check on farmland four hours after the pass |
| THEOS-2 16 Sep 2024, third scene, about 50% cloud | Not shown; probably the next scene north in the same strip, which would lie over the east of Ko Chang | Asked in the email |
| THEOS-2 17 Sep 2024, 0 to 3% cloud | The west two-thirds of the district: Mae Sai town, the west and centre, and Ko Chang only as far east as about 99.96 to 99.97 E. The road in Si Mueang Chum that the road sheet names first (99.948 E, 20.397 N) is inside, about a kilometre from the edge | The clearest scene. Town flood, the key road, a radar check one day after the pass |
| THEOS-2 21 Sep 2024, left (13%) and right (about 61 to 72%) | The north-east: the left scene a strip over the west of Ko Chang, the right scene the rest of Ko Chang under heavy cloud | Ko Chang nine days after the peak |
| THEOS-2 14 Jan 2025, two scenes, no cloud | The east of Ko Chang, east of about 100.0 E | Roads and embankments in the dry season, east part only |
| THEOS-1 17 Sep 2024 | Only the south-east corner | Not needed |

Consequences for the project:

- No scene of 16 or 17 September covers most of Ko Chang clearly. The check of the Ko Chang roads on the study event will rest on the west edge (17 September), on a cloudy scene if the third 16 September scene exists there, and on 21 September.
- The 17 September scene is what work package 6 should be built on: the town and the key road, 28.6 hours after the radar pass.
- At least one week of preparation means delivery around 16 to 17 October at the earliest, at the freeze of 18 October. Work package 6 would run after the freeze as a report-only addition.
