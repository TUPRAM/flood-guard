# FloodGuard Thailand — THEOS-2 Imagery Request

**Request reference:** FG-THEOS2-REQ-001
**Date:** 17 September 2026
**Submitted to:** GISTDA, THEOS-2 imagery request
**Contact:** [name], [institution / affiliation], [email]

---

## 1. About the project

FloodGuard Thailand is a non-operational research and preparedness prototype. It
converts flood extent or flood probability into subdistrict-level decision
support: exposed population, likely road disruption, evacuation access loss, an
equity gap measure, and a flood preparedness priority score.

The project does not publish official warnings, does not claim real-time flood
detection, and does not redistribute source imagery. It is not a replacement for
GISTDA, DDPM, TMD, RID, ONWR, or local agency judgement.

**Data handling.** Any imagery provided would be held in a controlled workspace
outside version control, tracked by SHA-256 checksum. Only derived analytical
outputs are retained in the project repository. Source imagery is never
redistributed. Citation and attribution will follow whatever form GISTDA
specifies.

---

## 2. Areas of interest

Six areas across three flood events. All bounds are WGS84 (EPSG:4326), given as
`min_lon, min_lat, max_lon, max_lat`. Scene counts assume a ~10.3 km THEOS-2 PMS
footprint.

Accompanying file: **`floodguard_theos2_aoi_v1.geojson`** (all six AOIs).
Individual per-AOI files are also provided.

| AOI | Priority | Area | Province / District | Bounding box (WGS84) | Size | ~Scenes |
| --- | --- | --- | --- | --- | --- | --- |
| AOI-01 | **1** | Mae Sai core — town, border crossing, Sai River | Chiang Rai / Mae Sai | `99.8384, 20.3705, 99.9441, 20.4563` | 11.0 × 9.5 km | ~2 |
| AOI-02 | 2 | Mae Sai district — all 8 subdistricts | Chiang Rai / Mae Sai | `99.8107, 20.2577, 100.0368, 20.4651` | 23.6 × 22.9 km | ~9 |
| AOI-03 | **1** | Hat Yai core — municipality, U Taphao canal | Songkhla / Hat Yai | `100.4300, 6.9650, 100.5200, 7.0550` | 9.9 × 10.0 km | ~1 |
| AOI-04 | 3 | U Taphao basin — extended | Songkhla | `100.3800, 6.9000, 100.5800, 7.1200` | 22.1 × 24.3 km | ~9 |
| AOI-05 | **1** | Bang Ban / Sena — lower Chao Phraya | Ayutthaya | `100.4000, 14.2500, 100.5200, 14.3700` | 12.9 × 13.3 km | ~4 |
| AOI-06 | 2 | Rangsit / Thanyaburi | Pathum Thani | `100.6000, 13.9800, 100.7200, 14.0800` | 13.0 × 11.1 km | ~4 |

---

## 3. Requested acquisitions

Date ranges were selected by measurement, not estimation. For every area and
candidate period we queried Sentinel-2 archive imagery and computed the cloud
fraction **clipped to the AOI polygon**, rather than relying on scene-level cloud
percentage. The ranges below are narrowed around dates that were demonstrably
clear over the target area.

**Two cloud figures are given, and they are not interchangeable.** "Cloud over
our area" is the measured cloud fraction within the AOI polygon, which is what
determines whether an image is usable to us. "Portal filter" is the scene-level
value we believe should be entered in the ordering portal so that the dates we
want are actually returned. The note "Why two cloud figures" below explains the
difference.

| Areas | Date range | Cloud over our area | Portal filter | Purpose | Most promising dates |
| --- | --- | --- | --- | --- | --- |
| AOI-01, 02 | 2024-09-01 → 2024-09-08 | 40% | 40% | Immediate pre-flood baseline | **2024-09-05** |
| AOI-01, 02 | 2024-09-09 → 2024-09-30 | 95% | 95% | Flood extent (opportunistic) | — |
| AOI-01, 02 | 2025-01-05 → 2025-01-31 | 10% | **45%** | Clear reference baseline | **2025-01-13, 01-18, 01-23** |
| AOI-01, 02 | 2024-11-01 → 2024-11-20 | 10% | **40%** | Early post-event baseline | **2024-11-04, 11-14** |
| AOI-03, 04 | 2025-11-28 → 2025-12-08 | 70% | 70% | Flood extent | **2025-12-03**, 12-01 |
| AOI-03, 04 | 2025-03-25 → 2025-04-05 | 15% | **25%** | Pre-event baseline | **2025-03-31** |
| AOI-03, 04 | 2026-03-15 → 2026-04-15 | 10% | **30%** | Clear reference baseline | **2026-03-21, 03-26, 04-12** |
| AOI-05, 06 | 2024-10-07 → 2024-11-15 | 25% | **75%** | Flood extent, 2024 | **2024-11-11**, 2024-10-12 |
| AOI-05, 06 | 2025-10-15 → 2025-11-20 | 70% | **90%** | Flood extent, 2025 | 2025-11-16 |
| AOI-05, 06 | 2025-01-15 → 2025-02-20 | 10% | **55%** | Dry-season baseline | **2025-02-04, 02-14, 02-19** |

**If a single filter value is easier to apply, 95% is safe for every window
above.** Because we have supplied specific target dates, selecting by date rather
than by cloud threshold will give the most reliable result.

### Preferred product

`ORTHO` `PMS` — pan-sharpened multispectral, 4-band (Blue / Green / Red / NIR).

This matches the `IMG_T2V_*_ORTHO_PMS_*` samples already available to us from the
hackathon dataset. The near-infrared band is important: it is what makes optical
water discrimination possible and allows us to screen false positives in our
Sentinel-1 radar analysis. Panchromatic-only imagery would be considerably less
useful for this work.

### Why two cloud figures

Our areas of interest are 10–24 km across; a satellite scene covers a far larger
footprint. As a result, scene-level cloud cover and the cloud actually sitting
over our area diverge substantially — in both directions:

| Date | Area | Scene-level cloud | Cloud over our area |
| --- | --- | --- | --- |
| 2024-11-21 | AOI-06, Pathum Thani | 62.5% | **0.8%** |
| 2025-02-04 | AOI-06, Pathum Thani | 51.0% | **0.1%** |
| 2025-02-19 | AOI-06, Pathum Thani | 46.3% | **0.1%** |
| 2025-01-28 | AOI-01, Mae Sai | 41.9% | **0.3%** |
| 2024-10-12 | AOI-05, Ayutthaya | 60.5% | **11.2%** |
| 2025-12-03 | AOI-03, Hat Yai | 27.9% | **39.3%** ← reverse case |

The practical consequence: if the cloud figure we care about were entered
directly into a scene-level filter, **17 of the dates we are asking for would be
excluded.** The clearest example is 2025-02-04 and 2025-02-19 over Pathum Thani —
essentially cloud-free over our area at 0.1%, but around 50% at scene level, so a
10% filter would reject both.

This is why the table above gives a separate, higher "portal filter" value. Those
values are calculated to be the lowest scene-level threshold that still returns
every date we want.

### Note on the Mae Sai flood window

We have set the cloud limit to 95% for the September 2024 Mae Sai flood window
deliberately. Our measurements show the flood peak was completely overcast
(2024-09-10 measured 100% cloud over the area), so we expect nothing there and a
nil result is entirely acceptable.

The acquisition of 2024-09-05, five days before the peak, is considerably more
valuable to us — it provides a seasonally matched pre-flood baseline. For Hat Yai
and the lower Chao Phraya, by contrast, our measurements suggest that usable
imagery during the flood period may genuinely exist.

### If capacity is limited

Our four highest-value acquisitions, in order:

1. **AOI-01, January 2025** (13th, 18th or 23rd) — clear imagery of our primary
   study area.
2. **AOI-01, 2024-09-05** — the pre-flood baseline for Mae Sai.
3. **AOI-05, 2024-11-11 or 2024-10-12** — imagery during the Chao Phraya flood
   period.
4. **AOI-03, 2025-12-03** — partial imagery during the Hat Yai flood.

---

## 4. Additional data request

Alongside the imagery, the following datasets would substantially strengthen the
work. We understand that some may sit with other agencies, or may not be
shareable. Any pointer to the appropriate contact would be very welcome.

| Priority | Dataset | Period required |
| --- | --- | --- |
| **1** | **Official flood extent / flood map products** | Mae Sai: 2024-09-09 → 2024-09-25<br>Hat Yai: 2025-11-19 → 2025-12-15<br>Chao Phraya: 2024-09-25 → 2024-11-30 and 2025-09-20 → 2025-11-30 |
| **2** | Official shelter / evacuation-centre locations (DDPM or provincial) | Current register, plus the register as it stood in September 2024 and November 2025 if historical versions are retained |
| 3 | GISTDA Sentinel-1 derived water-extent products | Event periods as above, plus pre-event reference: Mae Sai 2024-08-15 → 2024-09-08; Hat Yai 2025-10-15 → 2025-11-18; Chao Phraya 2024-08-01 → 2024-09-24 |
| 4 | Flood hazard or recurrence-zonation maps | Latest vintage; a series from 2011 onward if available |
| 5 | Water-level and rainfall station data (RID / TMD) | Mae Sai: 2024-08-01 → 2024-10-15<br>Hat Yai: 2025-10-01 → 2026-01-15<br>Chao Phraya: 2024-08-01 → 2024-12-31 and 2025-08-01 → 2025-12-31<br>Hourly resolution or finer if held |
| 6 | Official subdistrict (ADM3) boundaries | Version valid as at 2024-09-01, and the current 2026 version |
| 7 | Field-verified flood observations, high-water marks, survey points | Mae Sai: 2024-09-10 → 2024-12-31<br>Hat Yai: 2025-11-19 → 2026-03-31<br>Chao Phraya: 2024-10-01 → 2025-01-31 |
| 8 | Building footprints or official subdistrict population | Latest available vintage, plus any 2024 or 2025 update |

### Licensing questions

For any flood extent product, we would need written confirmation of the
following. Our project applies a strict data-governance rule: any dataset whose
terms are unresolved is blocked from entering the analysis, so we are unable to
proceed on an informal basis even where permission is likely.

1. Whether the geometry or raster may be used for local research validation.
2. Whether derived validation metrics may be published.
3. Whether it may be used as training labels for a machine-learning model.
4. Whether the source product may be redistributed, or must remain
   reference-only.
5. Required citation, attribution, and any disclaimers.

We had previously written to GISTDA on 3 July 2026 with a similar enquiry. If
that request is better directed elsewhere, we would be grateful for a pointer to
the right team.

---

## 5. Accompanying files

| File | Contents |
| --- | --- |
| `floodguard_theos2_aoi_v1.geojson` | All six areas of interest, WGS84, with priority, purpose and requested windows in the feature properties |
| `aoi-01_mae_sai_core.geojson` … `aoi-06_chao_phraya_rangsit.geojson` | Individual area files, if one AOI per request is preferred |

---

*FloodGuard Thailand is a non-operational research prototype. It is not an
official emergency warning system and does not claim guaranteed real-time flood
detection.*
