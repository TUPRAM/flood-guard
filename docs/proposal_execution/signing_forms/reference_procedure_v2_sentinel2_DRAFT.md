# Reference procedure v2 (Sentinel-2 optical reference): DRAFT

**Status: DRAFT for the Reference Authority. Not fixed.** When the authority
approves a final text, freeze it as `reference_procedure_v2.md` without this
banner. Its SHA-256 then goes into `reference_procedure_decision.document_sha256`
in form 3. Changing one byte afterwards needs a new version.

Basis: `GATE_RESEARCH_DOSSIER.md` Step 2. Every parameter below is a proposal.

1. **Event and target.** `TH-MAESAI-2024-09`, AOI-01 (`aoi-01_mae_sai_core`).
   The target is new inundation visible at the Sentinel-1 post acquisition
   (2024-09-15 23:16:01 UTC), relative to 2024-09-03 23:16:00 UTC.
2. **Reference imagery.** Sentinel-2B L2A
   `S2B_MSIL2A_20240915T034529_N0511_R104_T47QNC_20240915T065143`, sensing
   2024-09-15 03:45:29 UTC, used with the SAFE SHA-256 recorded in the
   acquisition manifest. The 2024-09-05 scene
   `S2B_MSIL2A_20240905T034539_N0511_R104_T47QNC_20240905T080012` is the dry
   context for permanent water.
3. **Date tolerance.** The optical scene precedes the SAR scene by 19 h 31 min.
   This is accepted for this single event only. Cells where the reference shows
   water but the SAR candidate does not are also reported in a separate
   `possible_recession` stratum.
4. **Independence.** Labels are drawn from Sentinel-2 bands only. SAR imagery,
   SAR candidate outputs and GFM stay hidden from Reviewers A and B until both
   have locked their labels.
5. **Classes.** The `flood_label_v1` codes apply:
   - 0 dry land;
   - 1 temporary flood;
   - 2 permanent or pre-existing water, meaning water also present on the
     5 September scene;
   - 3 uncertain water change;
   - 4 unobservable;
   - 255 unreviewed.
6. **Unobservable rule.** Code 4 applies to SCL no data (0), cloud shadow (3),
   medium or high cloud (8, 9), thin cirrus (10) and a 20 m buffer around them,
   plus any cell a reviewer marks as not interpretable.
7. **Interpretation.** Use true colour and B11/B8A/B4 false colour.
   Spectral indices (MNDWI, NDWI) and the SCL water class are aids only;
   turbid floodwater is often classed as bare ground.
8. **Grid.** EPSG:32647 at 10 m, snapped to the T47QNC origin. Before labelling,
   check the SAR RTC grid origin against it.
9. **Coverage.** Only codes 0 and 1 inside AOI-01 are scored. Report the
   evaluated fraction.
10. **Permitted purpose.** Bounded single-event observation evaluation for Mae
    Sai. Not model training and not transfer to other events.
11. **Rejection path.** If the authority finds 19.5 h unfit for this flash-flood
    setting, the decision is `rejected`. No accumulated or differently dated map
    is substituted.
