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

- Exact Sentinel-1 acquisition pair is not selected.
- Legally usable validation mask is not confirmed.
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
