# Study-Area Data Acquisition Inventory

This document is a planning catalog only. This change does not download real data and does not implement remote-sensing model code.

Use `docs/source_registry.md` as the source-of-truth list for candidate data providers, license notes, and confidence caveats.

## Chiang Rai / Mae Sai 2024

### Role

Validation tile for the first real flood-mapping and decision-layer validation.

### Needed Flood Reference

- Identify legally usable GISTDA, UN-SPIDER, academic, or other reference flood masks for the September 2024 Chiang Rai / Mae Sai event.
- Record geometry format, temporal coverage, validation method, license/access terms, and citation requirements.
- Do not claim operational accuracy from secondary summaries unless the underlying validation mask and method are available.

### Sentinel-1 Acquisition Task

- Identify pre-event and post-event Sentinel-1 GRD acquisitions that bracket the flood window.
- Record acquisition timestamp, orbit direction, polarization, relative orbit, processing level, and whether the acquisition likely captured peak or post-peak conditions.
- Record any cloud-independent SAR limitations, including urban layover, shadow, steep terrain, paddy/wet-soil false positives, and permanent-water filtering needs.
- Planning metadata query target: Mae Sai point `POINT(99.88 20.43)`, mission `SENTINEL-1`, product type `IW_GRDH_1SDV`, date window 2024-09-01 through 2024-09-25.
- CDSE source links: [Products OData endpoint](https://catalogue.dataspace.copernicus.eu/odata/v1/Products) and [Sentinel-1 collection description](https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-1).
- Access/license status: CDSE metadata online=true at planning time; download not performed; Copernicus attribution required.

### Candidate Sentinel-1 Products

| Acquisition date | Product name | CDSE product id | Online status | Candidate role | Blocker note |
| --- | --- | --- | --- | --- | --- |
| 2024-09-03 23:16:00Z | `S1A_IW_GRDH_1SDV_20240903T231600_20240903T231625_055507_06C5C9_4262_COG.SAFE` | `062a0809-b421-447c-904d-b08923cf412b` | online=true at planning time | pre-event candidate | exact flood peak/reference mask not locked |
| 2024-09-03 23:16:00Z | `S1A_IW_GRDH_1SDV_20240903T231600_20240903T231625_055507_06C5C9_72F7.SAFE` | `aaaef3af-fa49-4115-bf0f-f54175e7aedf` | online=true at planning time | pre-event SAFE alternative | acquisition-pair choice needs flood-date confirmation |
| 2024-09-06 11:31:06Z | `S1A_IW_GRDH_1SDV_20240906T113106_20240906T113131_055544_06C73C_CDAF.SAFE` | `5261e2a9-ea2a-43ca-a9a1-b3ee8b787432` | online=true at planning time | pre-event candidate | exact flood peak/reference mask not locked |
| 2024-09-06 11:31:06Z | `S1A_IW_GRDH_1SDV_20240906T113106_20240906T113131_055544_06C73C_B53D_COG.SAFE` | `b09f96ca-4a60-43e7-9b8d-158022f0e5bf` | online=true at planning time | pre-event COG candidate | acquisition-pair choice needs flood-date confirmation |
| 2024-09-15 23:16:01Z | `S1A_IW_GRDH_1SDV_20240915T231601_20240915T231626_055682_06CCBA_82A9_COG.SAFE` | `20a9c3b8-37df-46d5-81d8-d63c7e460225` | online=true at planning time | post-event COG candidate | validation mask licensing unresolved |
| 2024-09-15 23:16:01Z | `S1A_IW_GRDH_1SDV_20240915T231601_20240915T231626_055682_06CCBA_08DA.SAFE` | `5251b74b-0bbd-4365-9eb4-fa33292e175a` | online=true at planning time | post-event SAFE alternative | validation mask licensing unresolved |
| 2024-09-18 11:31:07Z | `S1A_IW_GRDH_1SDV_20240918T113107_20240918T113132_055719_06CE27_00F2_COG.SAFE` | `6a02d487-68fa-4be7-9628-f312b9049967` | online=true at planning time | post-event candidate | acquisition-pair choice needs flood-date confirmation |
| 2024-09-18 11:31:07Z | `S1A_IW_GRDH_1SDV_20240918T113107_20240918T113132_055719_06CE27_2B7D.SAFE` | `f9348e20-5d61-4456-be70-d0c1328128ff` | online=true at planning time | post-event SAFE alternative | validation mask licensing unresolved |

### Context Layers

- Administrative boundaries: confirm official or HDX/OCHA boundary vintage and subdistrict identifiers.
- Population: evaluate WorldPop residential population and available older-adult proxy data.
- Roads and facilities: start with OSM, then identify official road, bridge, shelter, hospital, clinic, and school lists if available.
- Terrain and hydro context: use Copernicus DEM GLO-30 and document slope/relative-elevation assumptions.
- Rainfall context: use ERA5 as coarse event context only; do not treat it as a local rain-gauge replacement.

### Licensing Questions

- Can the reference flood mask be redistributed in this repository?
- Can official boundaries, roads, shelters, or facilities be redistributed, or only referenced externally?
- What attribution is required for Sentinel-1, WorldPop, OSM, HDX/OCHA, ERA5, Copernicus DEM, and any GISTDA product?

### Current Blockers

- Exact Sentinel-1 acquisition pair is not selected because the exact flood peak/reference mask is not locked.
- Legally usable validation mask is not confirmed and validation mask licensing remains unresolved.
- Official road/shelter/facility layers are not confirmed.
- Subdistrict boundary version is not locked.

## Hat Yai / Songkhla 2025

### Role

Story and urban stress-test tile for road, service, access, shelter, and equity disruption.

### Needed Flood Reference

- Inventory International Charter Activation 1004 products and determine whether geometry can be accessed and cited.
- Inventory Sentinel Asia products for the heavy-rain flood event beginning 19 November 2025.
- Check whether GISTDA or other official flood/damage assessments are available and usable for validation or narrative support.

### Road And Facility Disruption Evidence

- Identify reported road cuts, bridge disruptions, hospital/clinic access issues, school impacts, utility disruptions, and evacuation-center use.
- Record source timestamp and whether each reference supports validation, demo narrative, or only contextual evidence.
- Prioritize evidence that can be tied to a subdistrict, road segment, facility, or shelter.

### Shelter And Facility Needs

- Build a candidate shelter list with capacity, operating status, source timestamp, and verification status.
- Build a candidate hospital/clinic list with service-continuity relevance where possible.
- Flag any facility records that come from OSM only and need official verification.

### Licensing Questions

- Are Charter or Sentinel Asia product geometries redistributable, or only viewable/citable?
- Can official road-damage and shelter records be redistributed?
- What attribution is required for all event-specific products?

### Current Blockers

- Charter and Sentinel Asia product geometry access is not confirmed.
- Official road closure and facility disruption data are not confirmed.
- Shelter capacities and operating windows are not confirmed.
- A clean subdistrict-level story boundary is not selected.
