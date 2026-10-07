# Request to GISTDA: THEOS-2 over Mae Sai, 16 September 2024, and the Pléiades imagery of 15 September 2024

- Request ID: `FG-THEOS2-REQ-002`
- Drafted: 7 October 2026 by the AI coding agent, for Putu to read, change and send. Nothing was sent.
- Channel: reply in the THEOS-2 imagery request thread with Khun Pimnipa (GISTDA), 16 September 2026.
- Attach: `outputs/theos2_request/floodguard_mae_sai_aoi_request_2026-10-07.geojson` (two boxes, WGS84).
- Optional second attachment: `outputs/theos2_cross_check/sukhothai_20250730_v1_overview.png` (the picture the
  message describes).
- Before sending: fill the three bracketed fields; delete the words "Further to our request of 17 September" if
  that message was never sent.

This draft grants no permission by itself. Delivered imagery stays outside Git; terms, local path and SHA-256 are
recorded before any use (`docs/provider_response_logging_guide.md`).

## Draft

> Subject: Re: THEOS-2 Imagery Request – one scene over Mae Sai (16 Sep 2024) and a question on Pléiades
>
> Dear Khun Pimnipa,
>
> Thank you again for your help with the THEOS-2 portal. We are TeamBits (FloodGuard Thailand), a finalist of
> GeoHackathon 2026. Further to our request of 17 September, we would like to narrow it to one scene that would
> help us most, and to ask one question about Pléiades imagery.
>
> **1. What we have done with the THEOS-2 samples**
>
> We used the hackathon sample `IMG_T2V_20250730033331_ORTHO_PMS_32` (Sukhothai, 30 July 2025) to check our
> Sentinel-1 flood detection and our road-closure rule against what THEOS-2 shows at 0.5 m. Two results:
>
> - Where our radar methods mark water, THEOS-2 shows water in 61 to 76% of the cells, but the radar finds only
>   22 to 50% of the water that THEOS-2 shows.
> - With the THEOS-2 water extent, our road-closure rule matches the roads that are visibly under water for
>   about four roads in five. With a 10 m radar extent it cannot tell which road is flooded.
>
> In short, THEOS-2 sees which road is under water and Sentinel-1 does not. We would like to show this in our
> final presentation on 31 October, and to repeat it on our main study event.
>
> **2. The scene we ask for**
>
> | | |
> |---|---|
> | Scene | `SC_T2V_202409160336066_VXB_E100N20_000640` (AWA GAD catalogue) |
> | Acquired | 16 September 2024, 03:36:06 UTC (10:36 in Thailand), catalogue cloud 21% |
> | Area | Mae Sai district, Chiang Rai (attached GeoJSON: AOI-02 first, AOI-01 if only a clip is possible) |
> | Product | ORTHO PMS, 4 bands including NIR, as the hackathon samples |
>
> Why this scene: it was taken 4 hours 20 minutes after the Sentinel-1 pass we use for the September 2024 flood
> (15 September, 23:16 UTC). No other optical image we know of is that close in time to the radar.
>
> If more is possible, in this order:
>
> 1. the THEOS-2 scene of 17 September 2024 or 21 September 2024 over the same area;
> 2. the THEOS-1 scene `TH_CAT_11108316301006_2_MS_CUF_R83163_20240917T032635` (17 September 2024, 03:26 UTC,
>    5.5% cloud);
> 3. one clear THEOS-2 scene of the dry season over the same area (13, 18 or 23 January 2025 were cloud-free on
>    Sentinel-2), to map buildings and roads.
>
> **3. A question about Pléiades**
>
> The UNOSAT preliminary assessment of the Chiang Rai flood (16 September 2024) shows Pléiades images of Mae Sai
> dated 15 September 2024, and UNOSAT product 3991 maps the water from 13 to 19 September 2024 from several
> satellites (https://unosat.org/products/3991). Does GISTDA hold that Pléiades imagery, or a flood extent made
> from it, for example through the International Charter activation? If so, could it be shared with us for
> research checking of our flood map, under whatever terms apply? If it cannot be shared, or if another
> organisation holds it, we would be grateful for the right contact.
>
> **4. How we would use the data**
>
> - Research checking only: compare our radar flood map and our modelled road closures with the image.
> - The imagery stays in a controlled folder outside our public repository. We do not redistribute it.
> - We would publish derived figures (counts and percentages) and, if you allow it, one small overview picture
>   at reduced resolution in our presentation, with the credit you specify.
> - FloodGuard is a planning and preparedness prototype. It is not a warning system.
>
> Could you tell us in writing which of these uses are allowed: (a) local analysis, (b) publishing derived
> figures, (c) showing a reduced overview picture in the final presentation, and (d) the credit line to use? The
> same question applies to the hackathon sample imagery we already have.
>
> **5. Timing**
>
> Our second mentoring session is on 16 October and the final is on 31 October. Data that reaches us by about
> 13 October can still be used in the final result.
>
> Thank you very much for your time.
>
> Best regards,
> [name]
> [affiliation]
> [email]
> TeamBits · FloodGuard Thailand · https://flood-guard-tau.vercel.app/

## Where each fact comes from

| Statement | Source |
|---|---|
| Scene identifier, time and cloud of 16 September 2024; the THEOS-1 scene of 17 September | `docs/proposal_execution/automated_track/independent_evidence_candidates_v2.md` (anonymous AWA GAD catalogue search of 24 September 2026) |
| Sentinel-1 pass of 15 September 2024, 23:16 UTC | `docs/proposal_execution/STATUS.md` |
| Sukhothai figures | `docs/theos2_radar_cross_check.md` |
| Clear January 2025 dates | `docs/theos2_imagery_request.md`, finding 6 |
| UNOSAT product 3991: 13 to 19 September 2024, several satellites, PDF only | https://unosat.org/products/3991, read 7 October 2026. The page does not list the satellites |
| Pléiades images of 15 September 2024 | the UNOSAT preliminary assessment report named in `independent_evidence_candidates_v2.md`; the exact minute and the cover of each panel were not checked |

## What to expect

Pléiades is commercial imagery of Airbus and CNES. GISTDA may not be free to pass it on even if it holds a copy.
The likely answers are a pointer to UNOSAT or to the Charter, or a derived flood extent without the imagery. The
note to UNOSAT beside this file (`unosat_request_2026-10-07.md`) asks them directly.
