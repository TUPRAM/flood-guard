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
| **Ayutthaya, 12 October 2024** | Sentinel-1A ascending orbit 172, VV/VH at 11:29:40 UTC. The event and same-orbit 18 September, 6 September, 25 August and 13 August scenes cover AOI-05 by **official catalog geometry**. Independent hosted RTC COGs for 12 October and 13 August have finite positive VV/VH values at all 1,718,599 AOI cells. That does not establish a dry pre-scene or validate FloodGuard's exact SNAP Gamma0 processing. [District flooding reported on 9 September](https://ayutthaya.prd.go.th/th/content/category/detail/id/9/iid/322670) makes a recent pre-scene especially unsafe to presume dry. | Sentinel-2B T47PPR at 03:54:24 UTC is about 7 h 35 min before radar. Over all AOI-05 pixel centres, **1,599,131 / 1,718,599 = 93.0485%** pass the frozen buffered SCL mask; **941,218 / 1,718,599 = 54.7666%** also pass all seven reflectance-asset and spectral-denominator validity checks. This passes the frozen 50% *source-feasibility* floor, narrowly; optical water agreement has not been tested. | NASA's 12 October MCDWD_L3 HDF is a potentially independent 250 m optical map with dry/water/insufficient-data codes and permissive LAADS data-use terms. The **actual HDF has not been obtained**: AOI class coverage, input times and georeferencing are therefore unverified. No other complete, rights-cleared flood/dry/unknown layer has been established. | **No selection yet.** Optical source availability passes, but the actual reference, dry radar baseline and exact candidate-processed grids must be checked before selection and a separate complete method/limit freeze. |
| **Ayutthaya, 16–17 October 2024** | Sentinel-1A descending orbit 62, VV/VH at 16 October 23:09 UTC; event catalog footprint covers AOI-05. Pre-scene dry status and processed-grid validity are unverified. | Sentinel-2A T47PPR at 17 October 03:54:25 UTC is about 4 h 45 min after radar. Buffered SCL alone leaves **1,521,718 / 1,718,599 = 88.5441%**; after full v2 asset and denominator validity, only **765,595 / 1,718,599 = 44.5476%** remains. This fails 50%. | A 17 October MCDWD_L3 HDF is listed, but its AOI classes and contributing times have not been inspected. Depending on its actual input times, parts of the daily composite might be more than 24 h after radar. | **No selection.** Optical cross-review fails; a radar-only study still lacks a verified independent reference and dry baseline. |
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

### Strongest source-only candidate: Ayutthaya, 12 October 2024

The 2024 follow-up uses the same committed AOI-05, whose file SHA-256 is
`804972939130008c239aa659268f845ca26a8cafc0a7384124e61b1f451bfe1d`.
The [official 12 October Sentinel-1 SAFE catalog record](https://catalogue.dataspace.copernicus.eu/odata/v1/Products(0686d25a-de9e-488a-be83-c7af19d4359f))
identifies `S1A_IW_GRDH_1SDV_20241012T112927_20241012T112952_056069_06DBFB_833D.SAFE`,
11:29:27.582–11:29:52.581 UTC (midpoint 11:29:40.081 UTC), ascending relative
orbit 172 with VV/VH. Its geometry intersects 100% of AOI-05. The corresponding
[Sentinel-2 Earth Search item](https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2B_47PPR_20241012_0_L2A)
identifies source product
`S2B_MSIL2A_20241012T033609_N0511_R061_T47PPR_20241012T073749.SAFE`.
The official catalog also shows 100% AOI-05 footprint intersections for
[18 September](https://catalogue.dataspace.copernicus.eu/odata/v1/Products(c1deea2a-41d9-4567-be85-7fee6003f5a9)),
[6 September](https://catalogue.dataspace.copernicus.eu/odata/v1/Products(ad94a0bb-da09-4fe6-82cb-052d270ee21f)),
[25 August](https://catalogue.dataspace.copernicus.eu/odata/v1/Products(bd51e1ca-3e2e-487d-bfc0-da2d3331b42d))
and [13 August](https://catalogue.dataspace.copernicus.eu/odata/v1/Products(08acc579-0253-47cb-8d5c-ac0249610690))
same-orbit VV/VH pre-scene candidates. The 9 September district flood report
makes 18 September unsafe to presume dry; 6 September is close to that report.
A [26 August provincial warning](https://ayutthaya.prd.go.th/th/content/category/detail/id/9/iid/318807)
names Bang Ban lowlands as vulnerable but proves neither flood nor dryness on
25 August. The 13 August radar scene has a same-day
[Sentinel-2 optical scene](https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2B_47PPR_20240813_0_L2A)
with usable SCL coverage, making it the most plausible nearby pre-scene to
investigate, but an automated SCL water map cannot establish that the whole
AOI was dry. These catalog footprints do **not** establish processed radar
grid validity or any pre-scene's dry status.

A separate source-only read of the [13 August](https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/S1A_IW_GRDH_1SDV_20240813T112925_20240813T112950_055194_06BA2C_rtc)
and [12 October](https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/S1A_IW_GRDH_1SDV_20241012T112927_20241012T112952_056069_06DBFB_rtc)
Microsoft Planetary Computer Sentinel-1 RTC items reprojected both VV and VH
COGs by nearest neighbour to a common 10 m EPSG:32647 AOI-05 grid. The
collection describes radiometric terrain correction after ESA calibration;
VV/VH assets are linear gamma-naught **intensity**, not dB. Their float32
metadata has nodata `-32768`, scale `1` and offset `0`, so the check used
native values without conversion. Each of
the four arrays had **1,718,599 / 1,718,599 finite positive AOI cells**;
joint positive coverage was also 100%, with zero nodata, nonfinite, zero or
negative cells. To reproduce, use the two STAC items' VV/VH assets, sign
their URLs in memory without printing or saving the temporary SAS query, use
`WarpedVRT` nearest resampling on the grid snapped to 10 m AOI bounds
(1,304 × 1,337 cells), rasterize AOI-05 pixel centres, and count finite
values greater than zero and not equal to nodata. This verifies hosted RTC
pixel availability only. The
reference-independent pre-scene dry condition remains open, and the hosted
RTC processing edition cannot be substituted silently for FloodGuard's SNAP
13 Gamma0 method; exact candidate grids still need a method-specific check.

The optical screen reused `expanded_scl_unobservable` and
`spectral_validity_only` from `src/floodguard/automated_optical_v2.py` on the
10 m EPSG:32647 grid snapped to the T47PPR origin. SCL, 10 m and 20 m bands
were resampled with the v2 nearest/bilinear choices; per-asset COG scale and
offset were applied. The seven tested bands were blue, green, red, nir, nir08,
swir16 and swir22. The full check requires finite positive source DN and
valid index denominators after reflectance clipping. The masked count is
**941,218 of 1,718,599 AOI cells (54.7666%)**. The same source-only method
gives **44.5476%** for the [17 October Sentinel-2 item](https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2A_47PPR_20241017_0_L2A),
paired with the [16 October radar item](https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-grd/items/S1A_IW_GRDH_1SDV_20241016T230932_20241016T230957_056134_06DE95).
This calculation reads source quality masks and radiometry only. It makes no
water classification and uses neither candidate SAR output nor reference
labels. Original source files have not yet been acquired and hashed locally.
The study AOI will still need to be reconciled with the obtained reference's
actual analysis footprint before selection.

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

For the stronger 12 October 2024 Ayutthaya candidate, the exact LAADS granule is
[`MCDWD_L3.A2024286.h28v07.061.2025279190339.hdf`](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/61/MCDWD_L3/2024/286/MCDWD_L3.A2024286.h28v07.061.2025279190339.hdf),
15,923,177 bytes with provider MD5 `5dcc2feb4111d1ec98fd40419e2c5629`.
For the 16–17 October pair, the 17 October file is
[`MCDWD_L3.A2024291.h28v07.061.2025279190444.hdf`](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/61/MCDWD_L3/2024/291/MCDWD_L3.A2024291.h28v07.061.2025279190444.hdf),
15,641,430 bytes with provider MD5 `47f8624c844fd2abeac8e48e42edd883`.
The 12 October file is the priority because its optical source coverage clears
the pre-frozen 50% requirement. The 17 October file is optional for a
radar-only follow-up and cannot rescue that pair's optical requirement.

For the earlier Ayutthaya 23 October 2022 candidate, the exact LAADS granule is
[`MCDWD_L3.A2022296.h28v07.061.2025279161042.hdf`](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/61/MCDWD_L3/2022/296/MCDWD_L3.A2022296.h28v07.061.2025279161042.hdf),
8,461,826 bytes with provider MD5 `734a1fb5ce51625568fb2e1311193d34`.
None of these actual AOI class counts, validity, input MODIS observation times
or georeferencing have been verified because LAADS requires Earthdata Login
for the HDF files. The user has been given the 12 October link and asked to
supply the downloaded local path without sharing credentials. NASA's public
[GIBS one-day browse layer](https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/1.0.0/WMTSCapabilities.xml)
cannot substitute for that HDF: its
[official colormap](https://gibs.earthdata.nasa.gov/colormaps/v1.3/MODIS_Flood.xml)
renders both no water and no data transparent, so mapped dry and unknown
cannot be counted separately. The
[LAADS data-use policy](https://modaps.modaps.eosdis.nasa.gov/services/faq/LAADS_Data-Use_Citation_Policies.pdf)
states that subsequent use and redistribution are unrestricted and asks for
NASA LAADS acknowledgment and data citation. This does not imply that an
uninspected file has useful flood/dry/unknown coverage on AOI-05. If the
12 October file's 1-day layer uses only its stated UTC day, all contributing
times are within 24 hours of the 11:29 UTC radar pass; inspect `INPUTPOINTER`
to report actual acquisition times and confirm this assumption.

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
