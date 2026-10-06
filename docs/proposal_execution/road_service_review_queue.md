# Lower Chao Phraya road and service review queue

**Status:** candidate graph analysis for independent review; no field decision, observed closure, surveyed entrance, verified operating hospital, accepted access result or operational route claim. AOI-05 and AOI-06 have completed staging finals receipts. This queue selects questions for reviewers; the numeric impacts are separate one-edge deletion experiments and **must not be summed**.

The source is the new external staging run `Project Support/FloodGuard/execution/2026-09-23/proposal-release-staging-v1/study_finals/`, in case directories `aoi-05_chao_phraya_bang_ban_sena/` and `aoi-06_chao_phraya_rangsit/`. The analysis uses a projected 10 km routing buffer while retaining each core AOI's original demand cells and reporting assignments. OSM graph objects are candidates; a graph bridge is an edge whose deletion disconnects a graph component, **not** proof of a physical bridge, road closure or sole real-world access. The audit field “accepted graph connector” means a connector passing the model's geometric rule; it conveys no human or downstream acceptance. WorldPop 2020 is modelled residential context. The OSM retrieval time records the source snapshot, not a 2024/2025 event observation.

## Source and run identity

| Case | Frozen input/output identity from completed finals receipt | Evidence boundary |
| --- | --- | --- |
| AOI-05 Bang Ban/Sena | AOI SHA-256 `b548f3e30c88ec0ec5492f5cd4f8dfbd8e87cdcaa3047f5fb0b928ba4c959fcc`; build receipt file `ce4c781120465bc56057eb6f7e0e64854126fa1c4bf36c3d3dfed35bd728833a`; analysis file `efb4624af400f8bd2d99baded40de1004d02ffd9690045b48aacbb9515a8ba6c` (internal canonical analysis SHA-256 `9b22c16c7e1ae627c80a9825a18fa22f81f4e22a80e2a65a6cbc642402c94acf`); walking context canonical SHA-256 `4d978dd353969f427dd80fc7232922dd5e6e19f038b486029e39c1bc62456575`; modelled-vehicle context `cd6c88f1649a621315bc45b7ebcb47590d6a3c30a54616d781571e1ae9d940ec`. Receipt generated `2026-09-23T12:56:29.0519497Z`. | `lower_basin_10km_epsg32647_v1`; routing selection canonical SHA-256 `c72b0f6ede4281f67df079b076942b2233b402a728d93b720db438d7a6bdf5cf`; selected buffer geometry SHA-256 `ecd287b621515276e125958cd4185ac38934755af89486df390d1fa56230d1e0`; fixed demand roster SHA-256 `cc5b474dd47e64dde706b1943ae4ab3124cba4539c64445e9ecd317ae97fd481`. |
| AOI-06 Rangsit | AOI SHA-256 `0a7d32aab4a94cc88260071312b7f346bfc05914600e33b0df713e57f3f2dee3`; build receipt file `0be8cb624b7fc6d344465f75d88e6f0685edd193a585860ea11268c8308f7b38`; analysis file `39ed3d08be04bfb80155ce2aeeb51f5ed84c7caa6b714e29324b591c68b8997e` (internal canonical analysis SHA-256 `48029181270b3f5f1833daa170c09f52486252e3f99f3ec9d3c7157fe795cb6f`); walking context canonical SHA-256 `8b5810382c46e89905c3d0f142b6745d9f6f56dd38392ce236799ed6e82c7ac4`; modelled-vehicle context `a1c3d5bb1afe93a6ea6b241bfecc4d2db1d2283a8d96f67963a879f9e1283121`. Receipt generated `2026-09-23T13:07:29.7859972Z`. | `lower_basin_10km_epsg32647_v1`; routing selection canonical SHA-256 `2b18528e3a4656ef02b42fc99212f33b39067b98067441a6bf6d8bcbe061eecc`; selected buffer geometry SHA-256 `eec66d4a52b44cc2b5b45857881a2309627631f35b049fb74ba52d3697f27692`; fixed demand roster SHA-256 `74b330ad0de176e3959070eb644720baed8661bf7347b888394d941fb8b34aae`. |

For each case the completed receipt's `analysis_sha256` and `files["analysis.json"]` equal the independently rehashed **file** SHA-256 above. Each `analysis.json` also carries its distinct canonical content SHA-256. The receipts bind prior fixed-demand baseline context file SHA-256 values `809d0d1be9857ce5a2bec1cc9263d084815106eadde05a24896621a4a9851abb` (AOI-05) and `af5520026640cccf1a9209ff92cd6e848ae18d79a697a992f66448a17ad6e086` (AOI-06), documented hospital object review file SHA-256 values `0869fe9b34e283775cb894ceb64852b6ca6b0877f81227b314312f9c52eebc2c` and `49a66c72bba6e9434d2cff9250697a3025d86061d1fd496a5a404b3ebd5c1b90`, and reporting units SHA-256 `013194e107f14258dc51b6bb1bbc3d5df02b7566432b06ea5ee8b827e5ae2a9a`. Both modes use OSM source SHA-256 `b7f46018249638413b1d318bc86519f140c27af20cac7c00d42fe03775b7add1` (snapshot retrieved `2026-07-10T02:46:49Z`) and WorldPop source SHA-256 `fb39d85dd150c45c7b25771f29bcd548e611afa0967224ac6d8ca05727230e20` (modelled population year 2020). The AOI-05 duplicate review recorded no exclusions or ambiguous matches; it did **not** verify operation or entrances.

## AOI-05: highest modelled single-edge dependencies

The following are the five highest rows in each mode's published `connectivity_audits.highest_edge_impacts`, ordered by modelled residents losing **all** graph routes after that one edge is deleted. The values happen to match between walking and modelled-vehicle audits for these edges; the networks and other access measures still differ. Repeated segments of one OSM way describe overlapping deletion experiments, not additional affected people.

| Graph edge ID | OSM source way | Walking residents | Modelled vehicle residents | Review focus |
| --- | --- | ---: | ---: | --- |
| `osm-way-919011362-segment-1` | [way 919011362](https://www.openstreetmap.org/way/919011362) | 10,040.35 | 10,040.35 | Check actual crossing, road level and alternative connection. |
| `osm-way-919011362-segment-0` | [way 919011362](https://www.openstreetmap.org/way/919011362) | 10,004.38 | 10,004.38 | Same source way; do not add to previous row. |
| `osm-way-617211467-segment-23` | [way 617211467](https://www.openstreetmap.org/way/617211467) | 357.64 | 357.64 | Check segment continuity, grade and modeled connector. |
| `osm-way-617211467-segment-22` | [way 617211467](https://www.openstreetmap.org/way/617211467) | 332.56 | 332.56 | Same source way; separate deletion experiment. |
| `osm-way-617211467-segment-21` | [way 617211467](https://www.openstreetmap.org/way/617211467) | 302.06 | 302.06 | Same source way; separate deletion experiment. |

The walking graph has 2,548 connected components and ten eligible candidate hospital connectors; 2,539 components have no eligible hospital in the extracted graph. The vehicle graph has 2,211 components and ten candidate hospital connectors; 2,202 have no eligible hospital. These are **graph components, not isolated villages**. Candidate baseline residents with a hospital route are 10,040.35 in both modes; another 37,134.89 walking / 37,134.23 vehicle modelled residents connect to roads but have no hospital route, and 3,292.01 / 3,292.67 have no accepted graph connector. Those categories do not measure flood isolation.

| Highly populated graph component | Walking residents / nodes | Vehicle residents / nodes | Eligible hospital object IDs in component | Review question |
| --- | ---: | ---: | --- | --- |
| `osm-node-0003293e85ef26ca9afc` | 10,399.47 / 29,449 | 10,401.47 / 28,900 | None | Are mapped roads, crossings or destination connectors missing, or is this truly disconnected for the intended mode? |
| `osm-node-00336cc7ccb9074d188d` | 10,040.35 / 3,304 | 10,040.35 / 3,286 | `OSM-node-7856667724` | Inspect the candidate hospital entrance and the high-impact way 919011362 without assuming operation. |
| `osm-node-000292418d80094202dc` | 6,207.54 / 7,737 | 6,208.52 / 7,690 | None | Check road continuity, restrictions and whether a legitimate hospital destination lies outside the buffer. |
| `osm-node-000bcbf72dbd26f67dc9` | 4,348.45 / 2,254 | 4,332.94 / 2,220 | None | Check grade/barrier and endpoint topology before interpreting absent routes. |
| `osm-node-00004ef48780361783a3` | 3,750.39 / 4,105 | 3,775.16 / 4,066 | None | Check local access and candidate destination completeness. |

### AOI-05 candidate hospital source objects

These ten OSM hospital-tagged objects are `eligible` **only in the candidate destination filter**. Their event availability is `unknown` and actual capacity is null. A connector within the model's 100 m rule is not a surveyed entrance. Primary care and pharmacy remain separate services; shelters are unavailable in this finals analysis and must not substitute for hospitals.

| Candidate OSM ID | Mapped name | Source |
| --- | --- | --- |
| `OSM-node-13172400977` | Unnamed OSM candidate | [OSM node](https://www.openstreetmap.org/node/13172400977) |
| `OSM-node-7856667667` | โรงพยาบาลบางไทร | [OSM node](https://www.openstreetmap.org/node/7856667667) |
| `OSM-node-7856667700` | โรงพยาบาลวัดสระแก้ว | [OSM node](https://www.openstreetmap.org/node/7856667700) |
| `OSM-node-7856667724` | โรงพยาบาลศุภมิตรเสนา | [OSM node](https://www.openstreetmap.org/node/7856667724) |
| `OSM-node-7856667725` | โรงพยาบาลเสนา | [OSM node](https://www.openstreetmap.org/node/7856667725) |
| `OSM-way-1359634335` | โรงพยาบาลบางปะอิน | [OSM way](https://www.openstreetmap.org/way/1359634335) |
| `OSM-way-712600876` | โรงพยาบาลพระนครศรีอยุธยา | [OSM way](https://www.openstreetmap.org/way/712600876) |
| `OSM-way-725901082` | โรงพยาบาลราชธานี | [OSM way](https://www.openstreetmap.org/way/725901082) |
| `OSM-way-746174419` | โรงพยาบาลสมเด็จพระสังฆราช นครหลวง | [OSM way](https://www.openstreetmap.org/way/746174419) |
| `OSM-way-785862866` | โรงพยาบาลพีรเวช | [OSM way](https://www.openstreetmap.org/way/785862866) |

## AOI-06: highest modelled single-edge dependencies

The AOI-06 core retains 564,292.56 modelled residents from the fixed 2020 demand roster. The table includes the five highest walking rows and six highest modelled-vehicle rows in `connectivity_audits.highest_edge_impacts`, plus the next distinct source way in each mode (walking rank 9, vehicle rank 7). Walking and modelled-vehicle have different graph topologies, so each mode has its own priority list. Several consecutive segments or ways have the same affected residents; these experiments overlap and are not additive.

| Mode | Graph edge ID | OSM source way | Modelled residents losing all graph routes if this one edge is deleted | Review focus |
| --- | --- | --- | ---: | --- |
| Walking | `osm-way-159520345-segment-25` | [way 159520345](https://www.openstreetmap.org/way/159520345) | 55,877.87 | Inspect mapped continuity, crossing level, barriers and plausible alternatives. |
| Walking | `osm-way-159520345-segment-26` | [way 159520345](https://www.openstreetmap.org/way/159520345) | 54,450.45 | Same source way; separate deletion experiment. |
| Walking | `osm-way-159520345-segment-27` | [way 159520345](https://www.openstreetmap.org/way/159520345) | 54,255.03 | Same source way; separate deletion experiment. |
| Walking | `osm-way-159520345-segment-28` | [way 159520345](https://www.openstreetmap.org/way/159520345) | 54,155.88 | Same source way; separate deletion experiment. |
| Walking | `osm-way-159520345-segment-29` | [way 159520345](https://www.openstreetmap.org/way/159520345) | 54,155.88 | Same source way; separate deletion experiment. |
| Walking (rank 9) | `osm-way-150571826-segment-10` | [way 150571826](https://www.openstreetmap.org/way/150571826) | 35,156.70 | Next distinct source way after three further segments of way 159520345; inspect crossings and alternatives. |
| Modelled vehicle | `osm-way-628169696-segment-0` | [way 628169696](https://www.openstreetmap.org/way/628169696) | 30,691.71 | Check road level and restrictions for the component with candidate `OSM-node-10216759749`. |
| Modelled vehicle | `osm-way-628169696-segment-1` | [way 628169696](https://www.openstreetmap.org/way/628169696) | 30,691.71 | Same source way; separate deletion experiment. |
| Modelled vehicle | `osm-way-628169718-segment-0` | [way 628169718](https://www.openstreetmap.org/way/628169718) | 30,691.71 | A second source way with the same modelled resident impact. |
| Modelled vehicle | `osm-way-628169718-segment-1` | [way 628169718](https://www.openstreetmap.org/way/628169718) | 30,691.71 | Same source way; separate deletion experiment. |
| Modelled vehicle | `osm-way-968239926-segment-10` | [way 968239926](https://www.openstreetmap.org/way/968239926) | 30,691.71 | A third source way in the tied set; confirm topology and passability independently. |
| Modelled vehicle | `osm-way-968239926-segment-9` | [way 968239926](https://www.openstreetmap.org/way/968239926) | 30,691.71 | Same source way; separate deletion experiment. |
| Modelled vehicle (rank 7) | `osm-way-43520595-segment-26` | [way 43520595](https://www.openstreetmap.org/way/43520595) | 10,416.52 | Next distinct source way; check vehicle restrictions and alternate connections. |

The walking graph has 3,843 connected components, including 3,828 without an eligible candidate hospital; it has 25 eligible candidate destination connectors. Its candidate baseline has 271,375.79 modelled residents with a hospital route, 290,214.37 connected to roads but without one, and 2,702.40 with no graph connector meeting the model rule. The vehicle graph has 3,340 components, including 3,326 without an eligible candidate hospital; it also has 25 connectors. Its corresponding figures are 267,312.34, 294,277.81 and 2,702.40. A component count is a graph diagnostic, **not a count of isolated settlements**, and these baseline categories do not measure event flood isolation.

| Highly populated graph component | Walking residents / nodes | Vehicle residents / nodes | Candidate hospital object IDs in component | Review question |
| --- | ---: | ---: | --- | --- |
| `osm-node-000763385fa6c4064401` | 130,082.63 / 10,082 | 126,366.41 / 9,697 | `OSM-way-220678392`, `OSM-way-946916178`, `OSM-way-946918104`, `OSM-way-946921280` | Verify separate hospital objects, actual access points and alternative routes. |
| `osm-node-0000b85f8d3c1de385ae` | 77,884.30 / 12,045 | 78,120.28 / 11,919 | `OSM-node-7856667655`, `OSM-way-700625446` | Verify distinct service roles and entrance/road connections. |
| `osm-node-0012d90dc553371d069c` | 71,543.37 / 12,437 | 71,543.37 / 12,407 | None | Check network continuity and whether a legitimate destination lies beyond the context. |
| `osm-node-00057bf76294128e5bac` | 50,050.52 / 8,406 | 50,100.93 / 8,311 | None | Check crossings, barriers and destination completeness. |
| `osm-node-0009021bcb76efca9307` | 43,451.50 / 8,020 | 43,447.38 / 8,164 | None | Check disconnected road fragments and access restrictions. |
| `osm-node-00036c90bb85f0fb688b` | 30,691.71 / 7,866 | 30,691.71 / 7,789 | `OSM-node-10216759749` | Verify the source object and the tied vehicle cut ways above. |

### AOI-06 candidate hospital source objects

The 25 hospital-tagged objects below passed the finals candidate destination filter. Their event-period operation, entrances and usable capacity remain **unknown**; these are not verified hospitals or accepted service access. A source object can be hospital-tagged while its real service role requires review. The source URL for each ID follows `https://www.openstreetmap.org/node/<number>` or `/way/<number>`.

| Eligible node IDs | Eligible way IDs |
| --- | --- |
| `OSM-node-10216759749`, `OSM-node-3090738848`, `OSM-node-7856667651`, `OSM-node-7856667655`, `OSM-node-7856667657`, `OSM-node-7856667658`, `OSM-node-7856667660` | `OSM-way-1009343708`, `OSM-way-1464127074`, `OSM-way-1466422180`, `OSM-way-1467500243`, `OSM-way-1485266147`, `OSM-way-1491851992`, `OSM-way-217790222`, `OSM-way-220646069`, `OSM-way-220678392`, `OSM-way-228704824`, `OSM-way-368093241`, `OSM-way-678967140`, `OSM-way-700625446`, `OSM-way-946916178`, `OSM-way-946918104`, `OSM-way-946921280`, `OSM-way-946923662`, `OSM-way-946941118` |

Review first the destination objects listed in the high-population components: [way 220678392](https://www.openstreetmap.org/way/220678392), [way 946916178](https://www.openstreetmap.org/way/946916178), [way 946918104](https://www.openstreetmap.org/way/946918104), [way 946921280](https://www.openstreetmap.org/way/946921280), [node 7856667655](https://www.openstreetmap.org/node/7856667655), [way 700625446](https://www.openstreetmap.org/way/700625446), and [node 10216759749](https://www.openstreetmap.org/node/10216759749). Also verify whether [node 3090738848, mapped as AIT Medical Clinic](https://www.openstreetmap.org/node/3090738848), and [way 946923662, mapped as a drug treatment and rehabilitation institute](https://www.openstreetmap.org/way/946923662) meet the hospital service definition. This is a role question, not an instruction to remove them.

The documented AOI-06 object review excluded [node 1402895609](https://www.openstreetmap.org/node/1402895609) as a same-name point contained by [way 1436320285](https://www.openstreetmap.org/way/1436320285); the site itself remains outside the 10 km routing context and has no candidate connector. Four more hospital-tagged site objects (`OSM-way-1028860550`, `OSM-way-1529333348`, `OSM-way-238296741`, `OSM-way-485325764`) are likewise outside the routing context. The review establishes OSM object identity for this extract only; it does not establish hospital operation, entrance or capacity. AOI-06 primary care (18 candidates), pharmacy (41) and shelter (unavailable) remain separate from the 25 hospital connectors.

## Questions requiring real review

1. **Road level and barrier:** At each high-impact OSM way/segment, do independently dated imagery, surveyed geometry or agency road records support the mapped junction, bridge/culvert, grade separation, turn and walking/vehicle restrictions? A same-coordinate graph crossing is not automatically a junction.
2. **Passability:** For the specific 2024 and 2025 event intervals, is there dated evidence that the segment was flooded, closed, restricted or open? Record observation time, source and uncertainty. Flood-polygon intersection alone is an imposed closure assumption.
3. **Alternative context:** Does the 10 km buffer omit a material path or destination? If so, describe the needed larger context and rerun with the **same demand roster** before comparing impacts; do not silently extend the population denominator.
4. **Hospital object and service:** Is each OSM object a distinct hospital rather than a duplicate mapped point/site? Check role, event-period operation, public access, actual entrance, effective interval and usable capacity separately. Unknown capacity is not zero. Primary care, pharmacy and shelter require their own service evidence.
5. **Decision authority:** A qualified reviewer must record any topology correction or service exclusion with source identity, time, purpose and signature under the repository's evidence contracts. Recompute both modes and all downstream hashes after a correction; no candidate count becomes an accepted event access or FPPS result by this queue alone.
