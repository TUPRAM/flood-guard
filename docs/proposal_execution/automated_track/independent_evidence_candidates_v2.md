# Independent evidence and prospective v2 holdout candidates

Status: source search and later study disposition, not a reference receipt, accepted label or accuracy validation. The candidate screen was prepared from public metadata on 24 September 2026 before v2 holdout predictions were inspected; the recorded one-use result is added below.

## Mae Sai independent evidence

| Candidate | Date and source | What it can support | Why it cannot be used as the current pixelwise reference |
| --- | --- | --- | --- |
| [UNOSAT preliminary Chiang Rai assessment](https://unosat.org/static/unosat_filesystem/3969/UNOSAT_Preliminary_Assessment_Report_TC20240912THA_ChiangRai_16Sep2024.pdf) | Pléiades images dated 15 September 2024 show flooded areas in Mae Sai. | Independent visual, place-specific checks on selected disagreements. | The public product is a report with image panels, not a dated, georeferenced flood/dry/unknown raster for AOI-01. The exact image acquisition minute and spatial overlap of each panel with AOI-01 have not been independently verified here. Rights to use the underlying commercial imagery as derived machine labels have not been established. |
| [UNOSAT Mae Sai product 3991](https://unosat.org/products/3991) | Cumulative 13–19 September 2024 multi-satellite extent; public PDF. | Regional plausibility and context only. | The cumulative date window cannot be matched pixel for pixel to either the 15 September optical scene or the 15 September SAR pass. The public product page lists a PDF, not a downloadable dated GIS mask. The analysis is preliminary and not field validated. |
| [Sentinel Asia AIT product](https://sentinel-asia.org/EO/2024/article20240910TH.html) | ALOS-2 observed flood water on 14 September 2024. The repo's `outputs/ait_vap001_reference_candidate.json` records downloaded polygon members and AOI intersection. | A different radar instrument can provide contextual spatial checks with an explicit one-day time caveat. | It does not match either 15 September acquisition time, does not encode a complete dry/unknown mask, has invalid polygons, and product-specific modification/derived-use permission is unresolved. [Site terms](https://sentinel-asia.org/sitepolicy/SitePolicy.html) disallow modification of posted materials absent a separate permission. |
| [Sentinel Asia MBRSC product](https://sentinel-asia.org/EO/2024/article20240910TH.html) | Public polygon ZIP inventoried at `outputs/public_reference_file_inspection_manifest.csv`. | Compare broad spatial patterns as context. | Its provider lists Sentinel-1 imagery on 15 September as the input, so it is not independent of the tested SAR sensor. Product-level rights and label semantics remain unresolved (`outputs/mae_sai_reference_candidate_decision.md`). |

**Finding:** no verified public, date-specific, legally reusable, machine-readable Mae Sai optical flood reference independent of the tested Sentinel-1 was established. This does not bar the separate automated two-method agreement experiment, but it prevents calling that agreement accuracy.

### Further public-source check

The [Thaiwater historical flood-area index](https://www.thaiwater.net/uploads/contents/current/2024/FloodChiangrai_Sep2024/flood_area.html) links a [GISTDA ALOS-2 report dated 15 September 2024 at 00:26](https://www.thaiwater.net/uploads/contents/current/2024/FloodChiangrai_Sep2024/img_FloodChiangrai_Sep2024/gistda_20240915_ALOS2_20240915_0026.pdf). It reports mapped flooding across several northern provinces, including Chiang Rai, and directs readers to GISTDA Disaster for detailed data. The report does not state a time zone for 00:26 in the inspected text; no exact temporal offset from the 03:45:29 UTC Sentinel-2 scene is asserted here. A [GF-3 report dated the same day](https://www.thaiwater.net/uploads/contents/current/2024/FloodChiangrai_Sep2024/img_FloodChiangrai_Sep2024/gistda_20240915_GF3_SYC_UFS_20240915_0606.pdf) lists Chiang Khong, Khun Tan, and Phaya Mengrai, so its mapped districts do not establish coverage of AOI-01 in Mae Sai.

[GISTDA's historical flood STAC page](https://disaster.gistda.or.th/services/stac/flood/index) asks for login to access the full catalogue. Its [public API documentation](https://disaster.gistda.or.th/services/open-api) advertises only rolling 1-, 3-, 7-, and 30-day flood extent endpoints. This search did not establish an anonymously downloadable, dated 2024 vector layer with clear reuse terms. A source export, acquisition timestamp, footprint, class semantics, and permission would all need checking before using a GISTDA layer as an independent reference. No such file was supplied.

### AWA GAD catalogue check suggested by the owner

An anonymous search in [GISTDA's AWA GAD catalogue](https://awagad.gistda.or.th/v2/u/app)
over a Mae Sai area and 1–30 September 2024 returned 86 imagery scenes.
THEOS-2 scenes were dated 16, 17 and 21 September; THEOS-1 scenes were dated
1, 6, 11, 12, 16, 17, 27 and 29 September. No 15 September THEOS-1/2 scene
appeared in this query. A 16 September THEOS-2 scene
`SC_T2V_202409160336066_VXB_E100N20_000640` has catalogue acquisition
03:36:06–03:36:07 UTC and 21% cloud notation. A 17 September THEOS-1
multispectral scene `TH_CAT_11108316301006_2_MS_CUF_R83163_20240917T032635`
has acquisition 03:26:35 UTC and 5.49% cloud cover; its listed processed ZIP
`TH_CAT_240917041919661_1_MS_2A_R83163_20240917T032635.zip` is behind a
cart/order control. The [public landing page](https://awagad.gistda.or.th/v2/p)
describes imagery ordering. Guest access revealed no downloadable GeoTIFF,
flood-extent layer or stated open derivative licence. These later scenes are
independent visual leads if ordered with suitable rights; they are not
same-time pixelwise truth for 15 September. No order was placed.

## Preselected event holdout: Chaiyaphum, 28 September 2021 (now consumed)

The **reprocessed N0500 edition** was selected prospectively for both event and dry context and was not swapped for the older N0301 edition after seeing agreement. The [repository coincidence scan](../gate_research/thai_s1_s2_coincidence_scan_v1.json) used the illustrative box `[101.99, 15.77, 102.08, 15.85]` and measured event-box SCL clear fraction **0.6823** for this edition. That catalogue/SCL screen was not the final v2 observability calculation. The frozen v2 mask later left only **0.465944** of the AOI observable, below its 0.50 floor.

| Role | Pinned Earth Search item and product URI | Acquisition and metadata |
| --- | --- | --- |
| Event | [`S2B_47PRT_20210928_1_L2A`](https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2B_47PRT_20210928_1_L2A); `S2B_MSIL2A_20210928T033539_N0500_R061_T47PRT_20230125T034127.SAFE` | 2021-09-28 03:53:49.285 UTC; EPSG:32647; full-tile cloud cover 40.407127%; per-band reflectance scale 0.0001, offset -0.1. |
| Dry-context candidate | [`S2B_47PRT_20210918_1_L2A`](https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2B_47PRT_20210918_1_L2A); `S2B_MSIL2A_20210918T033529_N0500_R061_T47PRT_20230120T031526.SAFE` | 2021-09-18 03:53:46.794 UTC; EPSG:32647; full-tile cloud cover 29.473296%; per-band reflectance scale 0.0001, offset -0.1. V2 later found 451,280 of 855,127 AOI cells observable on this date, but absence of earlier flooding remains unverified. |
| Prospective SAR comparison | `S1B_IW_GRDH_1SDV_20210927T230011_20210927T230036_028890_0372A1` | The repository scan lists 2021-09-27 23:00:24.269 UTC, approximately 4 h 53 m before the optical pass. This is a source candidate, not a processed SAR mask or approved metric run. |

The [UNOSAT 2021 flood product](https://unosat.org/products/1250) and its [map PDF](https://unosat.org/static/unosat_filesystem/1250/UNOSAT_A3_Natural_Portrait_FL20210928THA_NortheasternPart_Thailand_29092021_05102021.pdf) corroborate a Chaiyaphum flood episode and include a Sentinel-2 28 September image inset. Their main flood extents came from later Sentinel-1 observations, so they must not become independent truth for the proposed SAR comparison. Before the hold-out, these sources did not establish that this precise box contained enough event-time positive pixels. The separately frozen 100-cell feasibility gate later passed, while coverage failed; no scene was substituted after opening.

The earlier N0301 event [`S2B_47PRT_20210928_0_L2A`](https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2B_47PRT_20210928_0_L2A) had 0.7757 clear fraction in the repo scan, but its band offset is **0**, unlike the N0500 scene's **-0.1**. A v2 loader must apply each selected STAC asset's own scale and offset and assert the pinned `s2:product_uri`, rather than reuse the Mae Sai constant. The same edition distinction applies to the 18 September dry scene.

## Evidence separation and recorded disposition

1. Use Mae Sai v1 only for development and diagnosis. Keep its preregistration, one-use holdout marker, results, and failed limits intact.
2. The v2 pre-registration fixed the event and dry item IDs/product URIs, area geometry and grid, method versions, quality mask, two-date water rule, metrics, positive-count floor, acceptance limits and unusable-scene treatment before Chaiyaphum inference. Its exact commit is `efc69f5f66dfe8c2d667a9827566126709f1cab9`; the later stricter positive-cell gate commit is `09a4e03c14da9a9bd72cb70f0c7711f703fc9c0d`, also before hold-out inference.
3. Both scenes' eight COG assets were acquired outside Git and recorded by URL, byte count, SHA-256 and item metadata in the v2 manifests. [The Sentinel data legal notice](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice) permits lawful reproduction, distribution, communication and adaptation with source notice; this legal basis applies to Sentinel data, not the commercial Pléiades imagery or Sentinel Asia derived products.
4. The frozen Chaiyaphum hold-out ran **once**. Its Dice 0.8999 and kappa 0.8580 passed their limits, but observable coverage 0.4659 failed the predeclared 0.50 floor, so the overall v2 result failed. [Full result and limitations](OPTICAL_V2_RESULT.md). If SAR is evaluated in a future study, it needs its own pre-registered source and timing controls; optical two-method agreement alone cannot qualify a SAR observation.

No user-supplied account, key, or human signature is required for the Copernicus-only experiment. Provider permission or a separately licensed source would be needed before turning the Mae Sai Pléiades or Sentinel Asia products into derived reference labels.
