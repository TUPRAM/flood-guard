# Prospective Thai event: source and eligibility screen

**Decision on 25 September 2026: no event selected; no Thai detector score run.**
The [selection protocol](thai_event_selection_protocol_v1.json) was committed
first at `a4b4e46f403dae2fcf318a15b039f072499018a2`. It fixes the eligibility
rules independently of any new-event detector/reference comparison. A complete
method and numerical-limit pre-registration is still required in a later commit
**before** any selected event is scored. None has been written for an
unqualified event.

This screen is about the actual ingredients. A catalog footprint, a clear
illustrative box, or a polygon depicting flood alone is insufficient to claim
that an event has a usable full-AOI flood/dry/unknown reference. The proposed
studies are non-operational and would report agreement with a dated automated
map, not flood accuracy.

## Candidate checks

| Event and possible track | Radar and timing | Optical coverage | Independent reference and rights | Gate |
| --- | --- | --- | --- | --- |
| **Ayutthaya, 23 October 2022** | Sentinel-1A ascending orbit 172, VV/VH at 11:29 UTC. The event scene and same-orbit 21 March, 20 May, 24 August and 17 September scenes cover both the repository's illustrative 0.12° box and AOI-05 by catalog geometry. Pre-event *dry status* and processed-grid validity are unverified. September 17 is especially unsuitable as a presumed dry baseline because [GISTDA reported provincial flooding by 10 September](https://www.gistda.or.th/th/news/ดาวเทียมชี้น้ำท่วมขังแล้ว). | Sentinel-2B T47PPR at 03:54 UTC is about 7 h 35 min before radar. The original scan's 82.3% clear figure was for a **different small illustrative box**. A full AOI-05 screen of the Earth Search N0400 SCL COG gives **802,088 / 1,718,599 = 46.671%** observable 10 m cells after SCL 0/1/2/3/8/9/10 and a 20 m Euclidean buffer. Reflectance validity was not yet applied and can only reduce this fraction. Thus AOI-05 fails the frozen 50% optical requirement. | [GISTDA's 23 October flood PDF](https://www.thaiwater.net/uploads/contents/current/2022/NORU2022/NORU2022/Satellite/gistdaReport/gistda-20221023-S1A_IW_GRDH_1SDV_20221023_1837.pdf) used Sentinel-1 from the tested pass, so it is source-correlated. The public [Sentinel Asia TanDEM-X map](https://sentinel-asia.org/EO/2022/article20221019TH.html) is an image, without an obtained dated flood/dry/unknown GIS layer or verified derived-use rights. A NASA daily MODIS candidate has explicit classes and permissive LAADS data use, but the HDF has not been obtained or inspected. | **No selection.** Optical cross-review fails on AOI-05; radar-only remains conditional on a complete independent reference and verified pre-event data. |
| **Doi Tao, 5–6 October 2024** | Sentinel-1A ascending orbit 70 at 5 October 11:38 UTC and same-orbit 11 September and 30 August scenes each cover **100%** of UNOSAT's actual analysis polygon by catalog geometry. The candidate pre-scenes' dry status and processed grids remain unverified. UNOSAT's Gaofen-1 image was taken 6 October 06:16 UTC, about 18 h 37 min after radar. | The 5 October two-tile Sentinel-2 mosaic is about 7 h 35 min before radar and covers the polygon. A 10 m SCL screen gives **1,431,361 / 7,781,950 = 18.393%** observable cells with the frozen classes and 20 m buffer, using T47QMV first and T47QMA only for nodata. Reversing tile priority gives about 19.0%; both fail 50%. A 24 March dry-context optical scene has about 99.87% SCL observability but is seasonally distant. | The [UNOSAT product](https://unosat.org/products/4001) provides an actual [Gaofen-derived Shapefile ZIP](https://unosat.org/static/unosat_filesystem/4001/FL20240912THA_SHP.zip): one analysis polygon of about 779 km² and one flood polygon of about 54 km². The original ZIP SHA-256 is `1f91a46bbc7784b03f3d94584992f680a24dc2a98c6d3c77353c85f31ed5cc0b`. The [map PDF](https://unosat.org/static/unosat_filesystem/4001/UNOSAT_A3_Natural_Portait_FL20240912THA_DOITAO_CHIANGMAI_THAILAND_06OCT2024.pdf) calls the assessment preliminary and not field validated. The ZIP metadata does not say whether analysis-polygon cells outside the flood polygon are verified dry, cloud-obscured, or unmapped, and it supplies no product-specific derived-use licence. | **No selection.** Radar-only is promising, but mapped dry/unknown semantics, rights, dry baseline and processed validity are unresolved. Optical cross-review fails. |
| **Sukhothai, 29–31 August 2024** | The earlier [repository imagery scan](../gate_research/thai_s1_s2_coincidence_scan_v1.json) found a Sentinel-1 pass on 29 August and Sentinel-2 on 31 August. Full reference-defined AOI coverage and a same-orbit dry baseline are unverified. | The optical scene is about **28 h 55 min** after radar, beyond the frozen 24-hour limit even though the small-box buffered SCL screen was about 60%. | No dated georeferenced independent flood/dry/unknown reference with usable rights was found in this screen. | **No selection.** Optical timing and reference requirements fail or remain unverified. |

The Doi Tao ZIP and its metadata were inspected outside Git. The PDF states
that the Gaofen-1 source image was acquired at 06:16 UTC on 6 October, and
credits NSOAS/CNSA and contributing data providers. A public download does
not itself grant rights to create or publish derived comparison results. Nor
does the phrase “analysed area” prove that every non-flood cell was observed
as dry. The approximately 18.6-hour image gap also permits flood movement.

The Ayutthaya AOI-05 optical screen used the committed
[`aoi-05_chao_phraya_bang_ban_sena.geojson`](../../../resources/aoi/aoi-05_chao_phraya_bang_ban_sena.geojson),
the [Earth Search item](https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2B_47PPR_20221023_0_L2A),
nearest-neighbour SCL resampling to a snapped EPSG:32647 10 m grid, polygon
pixel centres, and a 30 m read halo around the AOI before applying the 20 m
buffer. Its processing edition is the Element84 COG of product
`S2B_MSIL2A_20221023T033809_N0400_R061_T47PPR_20221023T064206.SAFE`;
the exact original SAFE was not downloaded for this screen. The method is a
source-feasibility calculation, not an optical flood classification. It
explains why the earlier small-box 82.3% figure must not be used as an AOI-05
eligibility claim.

## Independent-reference acquisition route

NASA's [MCDWD_L3 historical Global Flood Product](https://www.earthdata.nasa.gov/global-flood-product)
has daily HDF maps through 2025. Its [user guide](https://www.earthdata.nasa.gov/s3fs-public/2025-04/MCDWD_VCDWD_UserGuide_RevE_04.22.25.pdf)
defines 1-day classes 0 no water, 1 surface water matching reference water,
2 recurring flood, 3 unusual flood and 255 insufficient data. The guide notes
that code 2 was not yet populated in Release 1; the actual archive version
must be checked. Its 1-day layer can include cloud-shadow false positives.
It is an **automated 250 m MODIS
reference**, independent of Sentinel-1 but neither field truth nor a 10 m
reference. A comparison would aggregate the radar result onto the MODIS grid
and report source-map agreement with resolution and date limitations.

For Ayutthaya 23 October, the exact LAADS granule is
[`MCDWD_L3.A2022296.h28v07.061.2025279161042.hdf`](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/61/MCDWD_L3/2022/296/MCDWD_L3.A2022296.h28v07.061.2025279161042.hdf),
8,461,826 bytes with provider MD5 `734a1fb5ce51625568fb2e1311193d34`.
Its actual AOI class counts, validity, input MODIS observation times and
georeferencing have **not** been verified because LAADS requires Earthdata
Login for the file. The user has been given the exact link and asked to supply
the downloaded local path without sharing credentials. The
[LAADS data-use policy](https://modaps.modaps.eosdis.nasa.gov/services/faq/LAADS_Data-Use_Citation_Policies.pdf)
states that subsequent use and redistribution are unrestricted and asks for
NASA LAADS acknowledgment and data citation. This does not imply that an
uninspected file has useful flood/dry/unknown coverage on AOI-05. A daily
composite date alone does not establish that every contributing source pixel
falls within 24 hours of the radar pass.

For Doi Tao, the exact 5 and 6 October granules are
[`MCDWD_L3.A2024279.h27v07.061.2025279130431.hdf`](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/61/MCDWD_L3/2024/279/MCDWD_L3.A2024279.h27v07.061.2025279130431.hdf)
(15,887,774 bytes, MD5 `e6d6b8c773056d36875bfdca5bfd36ac`) and
[`MCDWD_L3.A2024280.h27v07.061.2025279130445.hdf`](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/61/MCDWD_L3/2024/280/MCDWD_L3.A2024280.h27v07.061.2025279130445.hdf)
(17,570,996 bytes, MD5 `d3b274b59dc1f91fade82aa6ec4e349e`). Both
also require Earthdata Login. Their AOI class coverage is unknown.

## Conditions for advancing

1. Obtain and hash a complete candidate reference. Verify its AOI-specific
   mapped flood, mapped non-flood and unknown inventory, pixel acquisition
   time, georeferencing, source lineage and applicable derived-result rights.
   For Doi Tao, ask UNOSAT to state explicitly how analysis-area cells outside
   flood polygons and clouds were treated, and what reuse of the vector allows.
2. Declare the complete study AOI from the reference footprint and event
   geography, commit its hash, then verify full pre/post Sentinel-1 footprint,
   calibrated valid grids and a genuinely dry pre-event acquisition. If optical
   cross-review is included, verify the chosen event Sentinel-2 scene's full
   AOI coverage, 24-hour match and at least 50% observability.
3. Select by the frozen source-only ranking. Commit exact product editions,
   processing, method versions, class mapping, partitions, metrics and numeric
   acceptance limits before reading any new-event detector/reference score.
   Preserve a one-use final holdout and report abstention or weak agreement as
   observed. No output can become an official warning or accepted FPPS input.

The GISTDA historical flood catalogue is another possible source, but its
[official dataset record](https://opendata.gistda.or.th/dataset/flood-disaster-data)
has no specified licence, and a complete independent flood/dry/unknown export
for these candidate AOIs has not been verified. The user has a signed-in
portal route to investigate; portal access alone does not close this gate.
