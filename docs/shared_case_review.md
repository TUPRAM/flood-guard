# Shared study-area review

Non-operational research scenarios. All population figures below use WorldPop 2020 within the AOI and Thai reporting coverage; they are neither flood victims nor observed isolated residents. Hospital candidates have unverified entrances and event operation. Graph bridges are cut edges, not counts of physical bridges.

| AOI | Hospital candidates | Residents | Walking within 30 min | Connected, no hospital route | No accepted connector | Graph bridges | Articulation nodes |
|---|---:|---:|---:|---:|---:|---:|---:|
| aoi-03_hat_yai_core | 7 | 264,044.9 | 104,827.1 | 59,601.9 | 1,661.5 | 38,274 | 35,367 |
| aoi-05_chao_phraya_bang_ban_sena | 1 | 50,467.3 | 6,351.3 | 37,043.5 | 3,383.4 | 20,789 | 18,585 |
| aoi-06_chao_phraya_rangsit | 8 | 564,292.6 | 108,757.5 | 340,173.3 | 2,783.4 | 24,893 | 20,882 |

## Hat Yai

Seven general-hospital candidates remain after six explicit exclusions: two point/site duplicates, a dental hospital, an unresolved clinic-tag conflict, and two military-access sites. No capacity was combined and no entrance or event availability was certified. See resources/finals/hat_yai_destinations.json. Primary care and pharmacies remain separate services; shelters remain unavailable.

The original Sentinel-1 SAFE pair was downloaded through authenticated Copernicus Browser in Chrome. Both archives match the public catalog size and MD5, pass ZIP CRC checks, cover the core AOI, and share descending relative orbit 164 with VV/VH polarization. The tracked `outputs/cdse_hat_yai_acquisition_manifest.csv` records SHA-256 and external file identifiers. Raw archives remain outside Git.

The separate candidate uses a fixed 2.25 dB weighted amplitude-drop threshold transferred from the existing Mae Sai experiment, without tuning to Hat Yai labels, roads or population. Its 20 m GCP-warped grid has complete joint pixel coverage and 7.6688 km² of candidate geometry. Acquisition dates are 11/23 November UTC (12/24 November Thailand time). Uncalibrated amplitude, georeferencing errors, permanent water and urban/terrain effects remain unresolved; this is not a reconstruction of peak flooding or an independently validated mask. Every positive-length road-centreline intersection is an imposed closure, including bridges. Candidate overlap counts are modelled WorldPop cell-centre population, not flood victims.

The fixed road shortlist loses about 757 residents within 30-minute walking access, but no resident loses every route. Removing the Songklanagarind candidate loses about 30,041 residents at that threshold; this is a hypothetical service-loss comparison, not an observed hospital outage. Temporary-site rules rank individual demand nodes; their small, disconnected components explain the small gains. These are not optimized or approved hospital locations.

The hospital network has 59,602 graph-connected modelled residents with no route and 1,662 without an accepted connector. Review the largest no-hospital component (about 19,021 residents), grade transitions and hospital entrances before interpreting this as isolation.

The candidate-driven walking experiment imposes 3,643 segment closures. It counts 10,656.9 modelled residents at cell centres inside candidate geometry, with 1,130.3 outside the clipped observation footprint (including demand-cell boundary effects); those remain unobserved. Losses are 1,476.7 / 9,940.3 / 29,000.6 residents at 15 / 30 / 60 minutes, and 24,434.1 lose every route. These measures overlap and must not be summed. The mean delay is 3.8005 minutes among 178,347.3 residents with comparable finite routes, not among only residents whose route changed. For the Hat Yai subdistrict intersection TH901101, fixed-weight FPPS sensitivity values are 9.34 / 29.34 / 49.34 under explicit 0 / 50 / 100 missing-component assumptions; all are Class E because confidence is low. They are not accepted event priorities.

Footprint QA locates all 173 unobserved demand-cell centres inside the AOI but outside the clipped raster footprint, at most 10.157 m from it. Complete validity of the selected SAR pixels is therefore not a claim of complete observation coverage for every population-cell centre. Their missing exposure is retained.

## Lower Chao Phraya dependencies

Bang Ban/Sena: the 10 km search finds ten hospital-tagged source objects while the current model includes one. Sena Hospital (OSM node 7856667725) lies about 1.27 km beyond the demand rectangle; Phra Nakhon Si Ayutthaya Hospital (way 712600876) is about 4.09 km away. These exclusions demonstrate a routing-extent limitation, not absence of healthcare. A follow-up should extend the routing context while keeping the demand/reporting boundary fixed and review duplicate identities before recomputing.

The local snapshot and public OSM way 919011362 identify the service-road geometry at the included Suphamit Sena candidate. Cutting segment 1 removes all routes for about 10,040 modelled residents, almost the same as removing the destination. This is a graph dependency; the source does not establish its only physical entrance or historical passability. No extra connectors were invented.

Rangsit: the 10 km search finds 26 hospital-tagged objects versus eight candidates included in the current rectangle. About 340,173 graph-connected residents lack a hospital route in the walking model. The largest cut-edge dependency affects about 55,665 residents. Boundary truncation, separated road levels, service identity and entrances need review before a real-world access claim.

The 2024 and 2025 lower Chao Phraya selections deliberately share the same access baseline. They are not measured year-to-year flood comparisons. Accepted flood-affected population, FPPS and demographic equity remain unavailable because admissible event extents, calibrated likelihood and compatible age/context inputs are missing.

## Shared presentation

Public research summaries at /public-cases/, Command comparisons at /command/cases/, Studio brief and evidence library load the same checksum-verified AOI/event packages. Navigation retains AOI/event; the Public summary's comparison links additionally retain service/mode. Unsupported selections show unavailable. The production profile excludes research routes. Existing qualified-reference gates and Mae Sai candidate inputs remain unchanged.

## Reproduction

Use scripts/register_hat_yai_safe.py to verify the two downloads against saved public catalog responses, then scripts/build_hat_yai_flood_candidate.py for the fixed candidate. Use scripts/build_study_area_finals.py for AOI-03, AOI-05 and AOI-06; pass the external context root, saved event_review reporting directory, output directory and tracked timeline. AOI-03 additionally uses resources/finals/hat_yai_destinations.json and --flood-candidate pointing to its generated candidate directory. Outputs remain outside Git. Run scripts/audit_mae_sai_destinations.py with --aoi-id and the same OSM PBF for the bounded 10 km inventory. Rebuild with scripts/build_evidence_library.py and verify with scripts/verify_evidence_library.py. The release handoff records full local commands and exact package identity.

The reproducibility timestamp 2026-09-22T06:00:00Z identifies the package series and is fixed across reruns; it is not the time of download or execution. Source retrieval times remain separately recorded in the acquisition manifests.

## Unresolved work

- Hat Yai: radiometric calibration, terrain correction, alignment residual review, permanent-water treatment and independent event reference. No calibrated flood likelihood or accepted event score is supplied.
- All cases: supported entrances, walking/vehicle restrictions, dated service operation, reconciled shelter activation/capacity and compatible age definitions/counts. No inferred connectors or zero-filled age groups.
- Lower Chao Phraya: expand routing context beyond reporting rectangles; review the bounded hospital inventory and highest-demand disconnected components. Event-specific flood layers are absent for both years.
- A qualified human review and second-machine rehearsal remain separate from automated software verification.
