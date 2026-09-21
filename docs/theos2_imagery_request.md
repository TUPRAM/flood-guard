# THEOS-2 Imagery Request v2 (cloud-scouted)

Request ID: `FG-THEOS2-REQ-001`
Prepared: 2026-09-17
Channel: reply to Pimnipa Thanupran (GISTDA), THEOS-2 imagery request thread, 2026-09-16
Portal: https://awagad.gistda.or.th/v2/p

This memo holds the AOI definitions, acquisition windows, and the additional-data
asks that accompany the THEOS-2 request. It does not grant any permission by
itself. Nothing here changes `processing_allowed` for any source; delivered
imagery stays blocked until terms, local path, and SHA-256 checksum are recorded
under the existing ingestion gates.

**v2 changes.** Every date range and cloud limit in v1 was an informed guess.
They have now been replaced with measured values from
`scripts/scout_theos2_aoi_cloud.py`, which read the Sentinel-2 Scene
Classification band clipped to each AOI across all 18 AOI/window combinations.
Full results: `outputs/theos2_aoi_cloud_scout.csv` (336 date rows). Three windows
were narrowed, two were added, one was widened, and two AOI priorities changed.

## 1. What the cloud scout measured, and why it matters

The scout queries the Microsoft Planetary Computer STAC API for Sentinel-2 L2A,
reads the SCL band **windowed to each AOI**, and reports the fraction of the AOI
obscured by cloud, cirrus, or cloud shadow. Sentinel-2 is used purely as a cloud
climatology proxy for THEOS-2 tasking; it produces no flood mask, no label, and
no decision input.

### Finding 1 — scene-level cloud cover is the wrong filter

This is the single most important thing to tell GISTDA. A Sentinel-2 tile is
~110 km across; these AOIs are 10–24 km. The two numbers diverge badly in **both
directions**:

| Date | AOI | Scene cloud | AOI-clipped cloud | Effect of a scene-level filter |
| --- | --- | --- | --- | --- |
| 2024-11-21 | Rangsit | 62.5% | **0.8%** | A 10% filter discards an essentially clear scene |
| 2025-02-04 | Rangsit | 51.0% | **0.1%** | Discarded |
| 2025-02-19 | Rangsit | 46.3% | **0.1%** | Discarded |
| 2025-01-28 | Mae Sai | 41.9% | **0.3%** | Discarded |
| 2024-10-12 | Bang Ban | 60.5% | **11.2%** | Discarded |
| 2025-12-03 | Hat Yai | 27.9% | **39.3%** | A 30% filter wrongly admits it |
| 2025-12-01 | Hat Yai | 27.6% | **63.8%** | Wrongly admits it |

**Implication for the request:** the cloud percentage we care about and the
cloud percentage the portal filters on are different numbers, and the AOI value
must never be typed into the portal field.

`scripts/theos2_portal_thresholds.py` computes the translation. For each window
it finds the dates meeting our AOI-cloud limit, then reports the lowest
scene-level threshold that still returns all of them
(`outputs/theos2_portal_cloud_thresholds.csv`):

| Window | AOI cloud limit | Portal filter to enter | Dates lost if the AOI value were used |
| --- | --- | --- | --- |
| Mae Sai W1-pre-immediate | 40% | 40% | 0 |
| Mae Sai W2-event | 95% | 95% | 0 |
| Mae Sai W3-post | 10% | **45%** | 1 |
| Mae Sai W4-post-early | 10% | **40%** | 2 |
| Hat Yai W1-event | 70% | 70% | 0 |
| Hat Yai W2-pre | 15% | **25%** | 1 |
| Hat Yai W3-post | 10% | **30%** | 3 |
| Chao Phraya W1-event-2024 | 25% | **75%** | 3 |
| Chao Phraya W2-event-2025 | 70% | **90%** | 2 |
| Chao Phraya W3-dry | 10% | **55%** | 5 |

**17 of the dates we want would be discarded** by entering the AOI values. The
worst cases are the ones that matter most: the Chao Phraya dry baseline would
lose 2025-02-04 and 2025-02-19 — both 0.1% cloud over the AOI but ~50% at scene
level — and the 2024 flood window would lose 2024-10-12 and 2024-10-17, two of
the few near-clear flood-period dates in the entire request.

**A single portal value of 95% is safe for every window.** Because we are
supplying explicit target dates, the cleanest approach is to set the cloud filter
permissively and select by date; the max-cloud field is the wrong instrument when
the exact dates are already known.

### Finding 2 — the Mae Sai flood date is unobtainable optically, but 2024-09-05 is not

Every Sentinel-2 date in the Mae Sai flood window is obscured. The flood peak,
2024-09-10, measured **100% AOI cloud**; the best date in the whole window was
2024-09-30 at 89.2%.

But **2024-09-05 measured 12.5% AOI cloud** — five days before the peak, at full
AOI coverage. That is a near-clear, *seasonally matched* immediate pre-event
baseline, which pairs far better for change detection than the January baseline
proposed in v1 (same vegetation state, same agricultural cycle, same river
stage). This date has been promoted to a window of its own and is now the
highest-value single acquisition for the Mae Sai event.

### Finding 3 — Hat Yai has a real flood-period opportunity

**2025-12-03 measured 39.3% AOI cloud, inside the requested window.** Roughly 60%
of the AOI was visible during the flood period. 2025-12-01 follows at 63.8%.
Neither is clean, but partial flood-period optical coverage of Hat Yai is
genuinely achievable, so the cloud limit was lowered from 80% to 70% and the
window narrowed to concentrate on those two dates.

### Finding 4 — the Hat Yai pre-event request as written would have failed

Only **1 of 38 observed dates** between 2025-03-01 and 2025-07-31 fell below 10%
AOI cloud. The v1 ask (five months at ≤10%) would have returned almost nothing.
The window is now narrowed to 2025-03-25 → 2025-04-05 at ≤15%, targeting
2025-03-31 (3.0%). Southern Thailand is far cloudier year-round than the north,
and the v1 "dry season" assumption was wrong there.

### Finding 5 — the Chao Phraya AOIs carry the best flood-period imagery in the request

**2024-11-11 measured 6.5% AOI cloud at Bang Ban/Sena and 0.8% at Rangsit**, with
2024-10-12 at 11.2% and 2024-10-17 at 13.8%. Clear optical imagery *during the
flood season* demonstrably exists here, which is not true for either Mae Sai or
Hat Yai. The 2024 event window cloud limit dropped from 80% to 25%, and AOI-05
was promoted to P1 / AOI-06 to P2 on the strength of this.

The 2025 repeat is much weaker (0 of 20 dates below 10%; AOI-05 best in-window
42.7%), so it has been demoted.

### Finding 6 — the northern baselines are excellent

Mae Sai, 2025-01-13 / 01-18 / 01-23 all measured **0.0% AOI cloud**. 11 of 17
observed dates in the November–January range fell below 10%. The post-event
window was narrowed to January, with an early-November alternative split out
separately for cases where proximity to the event matters more than clarity.

## 2. What THEOS-2 can and cannot do for this project

**THEOS-2 is optical**, and Findings 2–4 above quantify the consequence: at the
peak of a Thai monsoon flood, cloud cover over the target is usually total.

**The high-probability, high-value ask is clear-sky imagery either side of the
event**, because that unblocks work the project is actually stuck on:

| Current gap | What 0.5 m THEOS-2 PMS resolves |
| --- | --- |
| 42 Mae Sai facilities in `outputs/mae_sai_facilities.geojson` carry `candidate_status` = unverified, all OSM-derived. `/public` therefore cannot show facility locations at all. | Visual confirmation of hospital, school, and shelter locations and their access points. |
| 4,458 road segments in `outputs/mae_sai_road_risk.geojson` use OSM-derived class and bridge flags that drive the access-loss model. | Confirms road existence, surface, width, and bridge presence at the segments that carry the routing result. |
| The Sentinel-1 SAR change detector has no optical screen for false positives. Smooth tarmac, wet paddy, and aquaculture ponds return like open water. | A dry-season optical baseline is the standard screen for those classes. |
| Exposure weighting has no built-up extent layer beyond WorldPop. | Built-up footprint and land cover at sub-metre scale. |

**Archive constraint.** THEOS-2 launched in October 2023, so the usable archive
starts around late 2023. All revised windows now sit in or after September 2024,
which removes the v1 risk of requesting dates near the archive boundary.

## 3. Table A — THEOS-2 AOI and acquisition request

Bounds are WGS84 decimal degrees, `min_lon, min_lat, max_lon, max_lat`. Scene
counts assume a ~10.3 km THEOS-2 PMS footprint.

| AOI | Pri | Event | Province / District | BBox (WGS84) | Size | ~Scenes |
| --- | --- | --- | --- | --- | --- | --- |
| AOI-01 `mae_sai_core` | **P1** | Mae Sai flood, Sep 2024 | Chiang Rai / Mae Sai | `99.8384, 20.3705, 99.9441, 20.4563` | 11.0 × 9.5 km | ~2 |
| AOI-02 `mae_sai_district` | P2 | Mae Sai flood, Sep 2024 | Chiang Rai / Mae Sai | `99.8107, 20.2577, 100.0368, 20.4651` | 23.6 × 22.9 km | ~9 |
| AOI-03 `hat_yai_core` | **P1** | Hat Yai flood, Nov 2025 | Songkhla / Hat Yai | `100.4300, 6.9650, 100.5200, 7.0550` | 9.9 × 10.0 km | ~1 |
| AOI-04 `hat_yai_basin` | P3 | Hat Yai flood, Nov 2025 | Songkhla / U Taphao basin | `100.3800, 6.9000, 100.5800, 7.1200` | 22.1 × 24.3 km | ~9 |
| AOI-05 `chao_phraya_bang_ban_sena` | **P1** ↑ | Lower Chao Phraya, 2024 | Ayutthaya / Bang Ban, Sena | `100.4000, 14.2500, 100.5200, 14.3700` | 12.9 × 13.3 km | ~4 |
| AOI-06 `chao_phraya_rangsit` | P2 ↑ | Lower Chao Phraya, 2024 | Pathum Thani / Thanyaburi | `100.6000, 13.9800, 100.7200, 14.0800` | 13.0 × 11.1 km | ~4 |

↑ = priority raised in v2 on cloud-scout evidence.

### Acquisition windows — measured, not assumed

Two different cloud columns, and they are not interchangeable. **AOI cloud** is
the measured AOI-clipped limit that determines usability
(`outputs/theos2_aoi_cloud_scout.csv`). **Portal filter** is the scene-level
value to enter in the GISTDA ordering portal
(`outputs/theos2_portal_cloud_thresholds.csv`).

| AOI | Window | Purpose | Date range | AOI cloud | Portal filter | Measured best dates | Odds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 01, 02 | W1-pre-immediate **(new)** | Immediate pre-flood baseline | **2024-09-01 → 2024-09-08** | 40% | 40% | **2024-09-05 @ 12.5%** (14.7% on AOI-02) | High |
| 01, 02 | W2-event | Flood extent | 2024-09-09 → 2024-09-30 | 95% | 95% | 2024-09-30 @ 89.2%; peak 09-10 @ 100% | Very low |
| 01, 02 | W3-post | Clear baseline | **2025-01-05 → 2025-01-31** | 10% | **45%** | **01-13, 01-18, 01-23 all @ 0.0%** | Very high |
| 01, 02 | W4-post-early **(new)** | Early post-event baseline | **2024-11-01 → 2024-11-20** | 10% | **40%** | 11-04 @ 0.2%, 11-14 @ 0.2% | High |
| 03, 04 | W1-event | Flood extent | **2025-11-28 → 2025-12-08** | 70% | 70% | **2025-12-03 @ 39.3%**, 12-01 @ 63.8% | Medium |
| 03, 04 | W2-pre | Pre-event baseline | **2025-03-25 → 2025-04-05** | 15% | **25%** | 2025-03-31 @ 3.0% (only clear date in 5 months) | Medium |
| 03, 04 | W3-post | Clear baseline | **2026-03-15 → 2026-04-15** | 10% | **30%** | 04-12 @ 0.1%, 03-21 @ 0.2%, 03-26 @ 0.2% | High |
| 05, 06 | W1-event-2024 | Flood extent 2024 | **2024-10-07 → 2024-11-15** | 25% | **75%** | **2024-11-11 @ 6.5% / 0.8%**; 10-12 @ 11.2% | High |
| 05, 06 | W2-event-2025 | Flood extent 2025 | **2025-10-15 → 2025-11-20** | 70% | **90%** | 11-16 @ 3.4% (AOI-06); AOI-05 best 42.7% | Low |
| 05, 06 | W3-dry | Dry baseline | **2025-01-15 → 2025-02-20** | 10% | **55%** | 02-04 @ 0.1%, 02-19 @ 0.1%, 02-14 @ 0.2% | Very high |

Bolded portal values are windows where the naive value would have lost dates. A
single filter of **95% is safe for every window** if a per-window value is
awkward to set.

**Preferred product level:** `ORTHO`, `PMS` (pan-sharpened multispectral, 4-band
B/G/R/NIR), matching the existing `IMG_T2V_*_ORTHO_PMS_*` hackathon samples
already catalogued in `outputs/local_data_library_manifest.csv`. NIR matters: it
is what makes optical water discrimination and the SAR false-positive screen
work. Panchromatic-only would be much less useful.

### If capacity is limited

Ranked by value per scene, using the measured evidence:

1. **AOI-01, W3-post** (2025-01-13/18/23) — three confirmed 0.0%-cloud dates over
   the primary study area. Unblocks facility and road verification.
2. **AOI-01, W1-pre-immediate** (2024-09-05) — the only near-clear
   seasonally-matched pre-flood image that exists for Mae Sai.
3. **AOI-05, W1-event-2024** (2024-11-11 or 2024-10-12) — the only confirmed
   near-clear *flood-period* optical imagery in the request.
4. **AOI-03, W1-event** (2025-12-03) — partial but genuine flood-period coverage
   of Hat Yai.

### Why a third event was added

The Chao Phraya AOIs are new. They are not present in committed FloodGuard
evidence, and they are requested deliberately.
`docs/immutable-multi-event-partitions-v1.md` currently has a synthetic-fixture
implementation only, and the README records that the workspace contains no
"additional processed Thailand development events". A model validated on one
border-valley flood cannot be claimed to generalise. Ayutthaya's Bang Ban / Sena
reach is chosen over Bangkok proper because it is a flat alluvial floodplain that
floods nearly every monsoon — a genuinely different hydrological regime from Mae
Sai's flashy border river and Hat Yai's urban canal basin. Finding 5 then added
an unexpected second reason: it is the only place where flood-period optical
imagery is actually obtainable.

## 4. Table B — Additional data requested from GISTDA

Ordered by how much each item unblocks. Item B-1 is by a wide margin the most
important thing in this exchange, and it is already the subject of an unanswered
request sent 2026-07-03 (see `docs/licensing_outreach_status.md`).

Date ranges are the periods we need each dataset to cover. Where a pre-event
reference period is listed, it is because change detection needs a baseline, not
just the event itself.

| # | Data | Date ranges needed | Why it matters | What we need specified |
| --- | --- | --- | --- | --- |
| **B-1** | **Official flood extent / flood map products** | Mae Sai **2024-09-09 → 2024-09-25**; Hat Yai **2025-11-19 → 2025-12-15**; Chao Phraya **2024-09-25 → 2024-11-30** and **2025-09-20 → 2025-11-30** | **The single hard blocker.** Without a licensed reference mask the project cannot compute a real validation metric, train on real labels, or leave "candidate / non-operational" status. Every model result stays unverifiable. | Product name and ID, acquisition/derivation date, format (SHP/GeoJSON/GeoTIFF), CRS, and **written terms separately for each of**: local validation use, publication of derived metrics, dashboard screenshots, ML training-label use, redistribution, required citation. |
| **B-2** | Official shelter / evacuation-centre register (DDPM or provincial) | Current register as at **2026-09**; plus the register as it stood at **2024-09** and **2025-11** if historical versions are retained | All 42 Mae Sai facilities are unverified OSM points, so `/public` is currently forbidden from showing any facility location. An official register turns a blocked surface into a usable one. | Point geometry or address list, facility type, capacity if held, validity date, update cadence, and whether locations may be displayed publicly. |
| **B-3** | GISTDA Sentinel-1 derived water-extent products | Event: as B-1. Pre-event reference: Mae Sai **2024-08-15 → 2024-09-08**; Hat Yai **2025-10-15 → 2025-11-18**; Chao Phraya **2024-08-01 → 2024-09-24** | Lets us compare our deterministic SAR baseline against an authoritative operational product on the same scenes — an external check we currently have no way to perform. | Processing chain, threshold/method, temporal resolution, known limitations, format, terms. |
| **B-4** | Flood hazard / recurrence zonation maps | Latest vintage; ideally a series spanning **2011 → 2025** | Supplies a prior for the Flood Preparedness Priority Score that is not derived from a single event. | Vintage, method, class definitions, subdistrict compatibility, terms. |
| **B-5** | Water-level and rainfall station data (RID / TMD) | Mae Sai **2024-08-01 → 2024-10-15**; Hat Yai **2025-10-01 → 2026-01-15**; Chao Phraya **2024-08-01 → 2024-12-31** and **2025-08-01 → 2025-12-31**. Hourly or finer if held. | Needed for event timing, and is the precondition for the separately typed rainfall/hydrology forecast branch (capability step 9 in `PLANS.md`). | Station list with coordinates, parameters, temporal resolution, access route, API if any, terms. |
| **B-6** | Official ADM3 subdistrict boundaries | Version valid as at **2024-09-01**, and the current **2026** version | We currently use HDX COD-AB. An official version with validity dates would let boundary changes be handled correctly rather than assumed stable. | Vintage, validity dates, ID scheme and its relationship to the `TH5709xx` codes we use, terms. |
| **B-7** | Field-verified flood observations: high-water marks, survey points, damage reports | Mae Sai **2024-09-10 → 2024-12-31**; Hat Yai **2025-11-19 → 2026-03-31**; Chao Phraya **2024-10-01 → 2025-01-31** | Reviewer calibration and adjudication under `docs/qualified-thai-reference-label-release-v1.md` needs ground evidence independent of the satellite product being validated. | Collection method, date, positional accuracy, format, terms. |
| **B-8** | Building footprints or official population by subdistrict | Latest available vintage, plus any **2024** or **2025** update | Improves exposure estimation over WorldPop raster disaggregation, and would let the age-resolved population layer currently marked "not yet in use" on the landing page be properly wired. | Vintage, source, attribute schema, terms. |

For every item, the terms question is not a formality. The repository's ingestion
gates treat "no written terms" as blocked, so an informal yes cannot be recorded
and the data cannot enter the pipeline.

## 5. Attachments to send

| File | Role |
| --- | --- |
| `resources/aoi/floodguard_theos2_aoi_v1.geojson` | All six AOIs in one FeatureCollection. Primary attachment. |
| `resources/aoi/aoi-01_mae_sai_core.geojson` … `aoi-06_*.geojson` | Individual AOI files, if GISTDA prefers one AOI per request row. |
| `outputs/theos2_aoi_cloud_scout.csv` | Optional. The 336 measured cloud rows behind the date ranges. Worth attaching if GISTDA wants to see the reasoning. |

Note on reading the CSV: its `window_id` and `window_start` / `window_end`
columns record the **v1** windows that were searched, not the revised v2 windows
in Table A. That is deliberate. The v2 windows were derived from these results,
so the CSV is the search that produced the decision, and re-running it against
the narrowed windows would discard the evidence that justified narrowing them —
for example the "1 of 38 dates below 10%" finding for Hat Yai only exists because
the original five-month range was searched. Every v2 window falls inside a range
the scout already covered, so the measurements remain valid; the
`in_requested_window` column marks dates that fell outside the v1 range, several
of which became v2 windows in their own right.

Each AOI feature carries `priority`, `event_id`, `adm3_covered`, `derivation`,
`purpose`, `approx_theos2_pms_scenes`, and the full `requested_windows` list —
including `measured_evidence` and `revision` per window — so the file is
self-describing without this memo.

## 6. Reproducing the scout

```powershell
python scripts/scout_theos2_aoi_cloud.py
python scripts/build_theos2_aoi.py
python scripts/theos2_portal_thresholds.py
```

The first reads Sentinel-2 SCL from the Microsoft Planetary Computer STAC API
(no authentication required) and writes `outputs/theos2_aoi_cloud_scout.csv`. The
second regenerates the AOI files. The third translates each window's AOI-clipped
cloud limit into the scene-level value to enter in the portal and writes
`outputs/theos2_portal_cloud_thresholds.csv`.
`scripts/gee_theos2_aoi_cloud_scout.js` is the Earth Engine equivalent of the
first, kept for interactive map inspection.

Run order matters: `build_theos2_aoi.py` must run before
`theos2_portal_thresholds.py`, because the threshold script reads the revised
windows out of the generated GeoJSON. It derives the portal values from
`max_cloud_pct` and the scout measurements, not from the stored
`portal_scene_cloud_filter_pct`, so re-running it validates rather than echoes
the committed values.

## 7. Open item before sending

GISTDA asked for **exact filenames or complete scene specifications**. Those come
from a portal search at https://awagad.gistda.or.th/v2/p, which has not been run
yet. The scout has done the hard part — the portal search is now a narrow lookup
against ten short windows rather than an open-ended browse.

The draft below sends the AOIs and measured windows now and leaves a marked slot
for filenames, because the Table B asks are time-sensitive and should not wait on
a portal session.

## 8. Draft reply

> Subject: Re: THEOS-2 Imagery Request – Link and Submission Guidelines
>
> Dear Khun Pimnipa,
>
> Thank you very much for the portal link and the guidance. Please find our AOI
> file attached: `floodguard_theos2_aoi_v1.geojson` (WGS84 / EPSG:4326), containing
> six AOIs across three flood events. Individual per-AOI files are also attached in
> case you prefer one AOI per request.
>
> **About the project.** FloodGuard Thailand is a non-operational research and
> preparedness prototype. It converts flood extent or flood probability into
> subdistrict-level decision support: exposed population, likely road disruption,
> evacuation access loss, an equity gap measure, and a preparedness priority score.
> It does not publish official warnings, does not claim real-time detection, and
> does not redistribute source imagery. Any imagery you provide would be held in a
> controlled workspace outside version control, with only derived, checksum-tracked
> evidence retained.
>
> **How we chose the date ranges.** Rather than guess, we measured. For every AOI
> and candidate window we queried Sentinel-2 archive imagery and computed the cloud
> fraction *clipped to the AOI polygon* rather than the scene-level cloud
> percentage. The date ranges below are narrowed around dates that were
> demonstrably clear over the target area. We are happy to share the full result
> table if useful.
>
> **An important note on the cloud cover filter.** Our measurements show
> scene-level and AOI-level cloud cover diverging sharply, in both directions. Over
> our Pathum Thani area on 2024-11-21 the scene-level cloud was 62.5% while the
> area itself was 0.8% cloudy; over Hat Yai on 2025-12-03 the reverse held, 27.9%
> at scene level against 39.3% over the area.
>
> This matters practically. We have given two cloud figures in the table below: the
> cloud over our area, which is what determines whether an image is usable to us,
> and the scene-level figure to enter in the portal filter. If the area figure were
> used as the filter value, **17 of the dates we want would be excluded** — for
> example 2025-02-04 and 2025-02-19 over Pathum Thani, which are 0.1% cloudy over
> our area but around 50% at scene level.
>
> Since we are giving you specific target dates, the simplest approach may be to
> set the cloud filter permissively — **95% is safe for every one of our
> windows** — and select by date instead.
>
> **AOIs.** Priorities are marked so you can serve the most important tiles first
> if capacity is limited:
>
> | AOI | Pri | Area | BBox (WGS84) | Size |
> | --- | --- | --- | --- | --- |
> | AOI-01 | **P1** | Mae Sai core, Chiang Rai | `99.8384, 20.3705, 99.9441, 20.4563` | 11.0 × 9.5 km |
> | AOI-02 | P2 | Mae Sai district (all 8 subdistricts) | `99.8107, 20.2577, 100.0368, 20.4651` | 23.6 × 22.9 km |
> | AOI-03 | **P1** | Hat Yai core, Songkhla | `100.4300, 6.9650, 100.5200, 7.0550` | 9.9 × 10.0 km |
> | AOI-04 | P3 | U Taphao basin, Songkhla | `100.3800, 6.9000, 100.5800, 7.1200` | 22.1 × 24.3 km |
> | AOI-05 | **P1** | Bang Ban / Sena, Ayutthaya | `100.4000, 14.2500, 100.5200, 14.3700` | 12.9 × 13.3 km |
> | AOI-06 | P2 | Rangsit / Thanyaburi, Pathum Thani | `100.6000, 13.9800, 100.7200, 14.0800` | 13.0 × 11.1 km |
>
> **Date ranges and cloud limits.** The final column gives the date our
> measurements suggest is most likely to be usable, which may help narrow the
> archive search:
>
> | AOI | Date range | Cloud over our area | Portal filter to use | Purpose | Most promising date |
> | --- | --- | --- | --- | --- | --- |
> | AOI-01, 02 | 2024-09-01 → 2024-09-08 | 40% | 40% | Immediate pre-flood baseline | **2024-09-05** |
> | AOI-01, 02 | 2024-09-09 → 2024-09-30 | 95% | 95% | Flood extent (long shot) | — |
> | AOI-01, 02 | 2025-01-05 → 2025-01-31 | 10% | **45%** | Clear baseline | **2025-01-13 / 18 / 23** |
> | AOI-01, 02 | 2024-11-01 → 2024-11-20 | 10% | **40%** | Early post-event baseline | **2024-11-04 / 14** |
> | AOI-03, 04 | 2025-11-28 → 2025-12-08 | 70% | 70% | Flood extent | **2025-12-03** |
> | AOI-03, 04 | 2025-03-25 → 2025-04-05 | 15% | **25%** | Pre-event baseline | **2025-03-31** |
> | AOI-03, 04 | 2026-03-15 → 2026-04-15 | 10% | **30%** | Clear baseline | **2026-03-21 / 26, 04-12** |
> | AOI-05, 06 | 2024-10-07 → 2024-11-15 | 25% | **75%** | Flood extent 2024 | **2024-11-11**, 2024-10-12 |
> | AOI-05, 06 | 2025-10-15 → 2025-11-20 | 70% | **90%** | Flood extent 2025 | 2025-11-16 |
> | AOI-05, 06 | 2025-01-15 → 2025-02-20 | 10% | **55%** | Dry baseline | **2025-02-04 / 14 / 19** |
>
> A note on the Mae Sai flood window: we set the cloud limit to 95% on purpose.
> Our measurements show the September 2024 flood peak was completely overcast, so
> we expect nothing there and a null result is fine. The 2024-09-05 acquisition,
> five days before the peak, is far more valuable to us — it gives us a
> seasonally matched pre-flood baseline. For Hat Yai and the Chao Phraya, by
> contrast, our measurements suggest usable flood-period imagery may genuinely
> exist.
>
> Our preferred product is `ORTHO` `PMS` (pan-sharpened, 4-band including NIR),
> matching the `IMG_T2V_*_ORTHO_PMS_*` samples we already have from the hackathon
> dataset. The NIR band is important for our water-discrimination work.
>
> If capacity is limited, our four highest-value acquisitions are:
>
> 1. AOI-01, 2025-01-13 / 18 / 23 — clear imagery of our primary study area.
> 2. AOI-01, 2024-09-05 — the pre-flood baseline.
> 3. AOI-05, 2024-11-11 or 2024-10-12 — flood-period imagery over Ayutthaya.
> 4. AOI-03, 2025-12-03 — partial flood-period imagery over Hat Yai.
>
> **Scene filenames.** We are working through the portal now and will follow up
> with exact filenames and scene specifications.
>
> _[Insert scene filenames here once the portal search is complete.]_
>
> **One further request.** We previously wrote to GISTDA on 3 July 2026 asking
> about flood product access and licensing, and have not yet had a reply. Since we
> now have a direct contact, may we ask the same question here, or ask you to point
> us to the right team?
>
> Our most important need is an **official flood extent product** for these three
> events, covering:
>
> - Mae Sai, Chiang Rai: 2024-09-09 → 2024-09-25
> - Hat Yai, Songkhla: 2025-11-19 → 2025-12-15
> - Lower Chao Phraya: 2024-09-25 → 2024-11-30, and 2025-09-20 → 2025-11-30
>
> We have located public candidate geometry (the Sentinel Asia / MBRSC Northern
> Thailand 2024 shapefile), but without written terms we cannot use it as a
> validation reference. Our project rules block any data with unresolved terms from
> entering the analysis, so at present we can produce candidate results but cannot
> validate them against anything authoritative. A GISTDA flood product with clear
> terms would change that completely.
>
> Specifically, for any flood product we would need written confirmation of:
>
> 1. Whether the geometry or raster may be used for local research validation.
> 2. Whether derived validation metrics may be published.
> 3. Whether it may be used as training labels for a machine-learning model.
> 4. Whether the source product may be redistributed, or must remain reference-only.
> 5. Required citation, attribution, and disclaimers.
>
> If they are available, the following would also be valuable, in rough order of
> usefulness to us:
>
> - **Official shelter or evacuation-centre locations** for these areas — current,
>   and as they stood in September 2024 and November 2025 if historical versions
>   exist. All 42 facilities in our current Mae Sai analysis are unverified
>   OpenStreetMap points, so we cannot display them to the public.
> - **GISTDA Sentinel-1 derived water-extent products** for the event windows
>   above, plus a pre-event reference period (Mae Sai 2024-08-15 → 2024-09-08;
>   Hat Yai 2025-10-15 → 2025-11-18; Chao Phraya 2024-08-01 → 2024-09-24), as an
>   authoritative comparison for our own SAR analysis.
> - **Flood hazard or recurrence-zonation maps** — latest vintage, or a series
>   from 2011 onward if available.
> - **Water-level and rainfall station data** covering these areas: Mae Sai
>   2024-08-01 → 2024-10-15; Hat Yai 2025-10-01 → 2026-01-15; Chao Phraya
>   2024-08-01 → 2024-12-31 and 2025-08-01 → 2025-12-31, hourly if held.
> - **Official subdistrict (ADM3) boundaries** valid as at 2024-09-01 and the
>   current 2026 version.
> - **Any field-verified flood observations**, high-water marks, or survey points:
>   Mae Sai 2024-09-10 → 2024-12-31; Hat Yai 2025-11-19 → 2026-03-31; Chao Phraya
>   2024-10-01 → 2025-01-31.
> - **Building footprints or official subdistrict population**, latest vintage.
>
> We understand some of these may sit with other agencies or may not be shareable.
> Any pointer to the right contact would be very welcome.
>
> Thank you again for your help.
>
> Best regards,
> [name]
> [institution / affiliation]
> [email]
> FloodGuard Thailand — non-operational research prototype

## 9. Before sending

- Replace `[name]`, `[institution / affiliation]`, `[email]`.
- Attach `resources/aoi/floodguard_theos2_aoi_v1.geojson`, and the per-AOI files
  if sending them.
- Decide whether to run the portal search first and fill the filename slot.
- Decide whether to attach `outputs/theos2_aoi_cloud_scout.csv`.
- Confirm whether Ulwani and I Putu should stay on the thread; the original mail
  was addressed to all three.

## 10. On reply

Log the response in `docs/reference_mask_licensing_log.md` first, following
`docs/provider_response_logging_guide.md`, then update
`docs/licensing_outreach_status.md` and the relevant ingestion manifest rows.
Do not set `processing_allowed=True` for any delivered product until terms, local
path, and SHA-256 checksum are all recorded. Then run:

```powershell
uv run python scripts/check_real_data_gates.py --allow-blocked
uv run python scripts/validate_mae_sai_file_manifest.py --allow-blocked
```
