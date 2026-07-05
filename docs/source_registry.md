# Source Registry

This registry records candidate real-data sources before FloodGuard ingests any real study-area data. It is a seed inventory only; no external data is downloaded by the current fixture-driven pipeline.

| Source | URL / path | License or access note | Spatial resolution | Time coverage | Study-area relevance | Confidence notes |
| --- | --- | --- | --- | --- | --- | --- |
| Copernicus Sentinel-1 via CDSE | https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-1 | Open Copernicus access; cite Copernicus/ESA terms when used. | C-band SAR products; product resolution depends on mode and processing level. | Mission archive and current acquisitions. | Baseline SAR flood probability source for Chiang Rai / Mae Sai 2024 and Hat Yai / Songkhla 2025 where acquisition timing fits. | Strong official source, but acquisition timing can miss flood peak and urban SAR artifacts require confidence labels. |
| OpenStreetMap Thailand via Geofabrik | https://download.geofabrik.de/asia/thailand.html | OSM Open Database License attribution and share-alike obligations apply. | Vector roads and points of interest; completeness varies locally. | Continuously updated OSM extracts. | Prototype road network, shelter/facility candidates, and routing graph for all study areas. | Good open baseline, but official road/shelter data should replace or validate it for operations. |
| WorldPop Thailand 100m population | https://hub.worldpop.org/geodata/summary?id=6439 | Open WorldPop data; cite dataset and license terms from download metadata. | About 100 m gridded population. | Dataset-specific year from WorldPop metadata. | Population exposure and demand proxy for all study areas. | Modeled residential population; daytime and mobility-dependent populations require caveats. |
| HDX Thailand COD administrative boundaries | https://data.humdata.org/dataset/cod-ab-tha | HDX/OCHA COD access and dataset license notes apply. | Administrative vector boundaries. | Dataset-specific boundary vintage. | Province, district, and subdistrict aggregation for policy reporting. | Good open boundary candidate; production path should verify against official Thai boundary version. |
| ERA5 hourly single levels | https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels | Copernicus Climate Data Store terms apply. | Coarse reanalysis grid. | From 1940 to present per CDS dataset. | Rainfall anomaly and antecedent-condition context. | Not a replacement for local rain gauges or official warnings. |
| Copernicus DEM GLO-30 | https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM | Copernicus DEM access and attribution terms apply. | About 30 m global DEM. | Static terrain product. | Slope, relative elevation, drainage context, and flood false-positive filtering. | DSM artifacts from buildings/vegetation require filters and local review. |
| International Charter Activation 1004 - Flood in Thailand | https://disasterscharter.org/activations/flood-in-thailand-activation-1004- | Charter product access and attribution terms apply. | Event-specific crisis mapping products. | Activated for southern Thailand flooding in November 2025. | Hat Yai / Songkhla story and stress-test reference. | High value for event narrative and validation, but product availability and geometry access must be checked. |
| Sentinel Asia Southern Thailand 2025 event | https://sentinel-asia.org/EO/2025/article20251119TH.html | Sentinel Asia product access and attribution terms apply. | Event-specific satellite-derived products. | Heavy-rain flood event beginning 19 November 2025. | Hat Yai / southern Thailand detected-water or flood-proxy context. | Useful event evidence; products should be checked against GISTDA/Charter references before validation claims. |
| THEOS-2 hackathon sample imagery | Local hackathon-provided files; see `docs/theos2_inventory.md` | Project owner reported on 2026-07-03 that hackathon-provided THEOS-2 and other provided local data can be used freely for this project; selected files are checksum-tracked before preview or feature outputs. | Parsed local files indicate 0.5 m optical imagery for orthorectified PMS samples. | Local sample dates span 2024 and 2025. | Optical context, land-cover/exposure support, dashboard context, optional true thumbnails, and future optical ML experiments. | Not a legal flood reference mask and not the current Mae Sai/Hat Yai validation input; selected preview scope is optical context only. |
| Local hackathon Sentinel-1 and DEM bundles | Local provided files; see `docs/local_data_library.md` | Project owner reported hackathon-provided local data can be used freely for the project; processing still requires file-level checksums and provenance notes. | Standalone Sentinel-1 TIFF is 2-band VV/VH at `23296 x 23296`; DEM ZIP members are tiled elevation/slope TIFFs. | Filename timestamps are unresolved for Sentinel-1; DEM packages are static context. | Sentinel-1 standalone TIFF overlaps the Mae Sai MVP point; DEM tiles can support terrain and false-positive context. | Metadata-only library lane. Not a locked pre/post flood pair and not a reference mask until provenance, checksum, and gate status are recorded. |

## Study-Area Data Inventory

### Chiang Rai / Mae Sai 2024

- Target role: validation tile.
- Candidate flood references: Sentinel-1/CDSE, GISTDA flood products if available, peer-reviewed/reference masks if licensing permits.
- Candidate context layers: WorldPop, OSM roads/facilities, HDX/admin boundaries, ERA5, Copernicus DEM.
- First action: identify exact pre-event and post-event Sentinel-1 acquisition dates and a legally usable validation reference.

### Hat Yai / Songkhla 2025

- Target role: story and urban stress-test tile.
- Candidate flood references: International Charter Activation 1004, Sentinel Asia products, GISTDA assessments if available.
- Candidate context layers: OSM roads/facilities, shelter/facility lists, WorldPop, HDX/admin boundaries, ERA5, Copernicus DEM.
- First action: inventory mapped flood products and reported road/facility disruptions before any remote-sensing model work.
