# Sentinel-1 Local Provenance

Status: timing unresolved; processing remains blocked.

This note records metadata-only evidence for the local hackathon-provided Sentinel-1 file. It does not process pixels, download imagery, or authorize the real SAR baseline.

## Selected File Evidence

| File | Candidate role | Timing status | Provenance status | Processing allowed | Blocker |
| --- | --- | --- | --- | --- | --- |
| Sentinel1_Thailand-0000000000-0000000000-002.tif | unresolved | timing_unresolved | unresolved_placeholder_filename | False | Sentinel-1 product provenance unresolved; acquisition timing unresolved; candidate role is not pre/post baseline ready; resolved product id unavailable; reference mask not confirmed |

## What Was Checked

- TIFF tags were inspected without reading raster pixels.
- Local Drive ZIP member names were inspected without extraction.
- Optional CDSE metadata snapshots were checked when present.
- Provider/hackathon notes were treated as usage notes, not acquisition timing.

## Findings

### Sentinel1_Thailand-0000000000-0000000000-002.tif

- Filename evidence: local Sentinel1_Thailand tile name uses placeholder numeric offsets, not acquisition timestamps
- TIFF tag evidence: AREA_OR_POINT=Area; IMAGE_STRUCTURE:COMPRESSION=LZW; IMAGE_STRUCTURE:INTERLEAVE=PIXEL; band_1_description=VV; band_2_description=VH
- ZIP evidence: 5 Sentinel-1 ZIP member(s) found in drive-download-20260705T102948Z-3-001.zip; no exact selected-file match; tiled companion names: Sentinel1_Thailand-0000000000-0000023296.tif, Sentinel1_Thailand-0000023296-0000000000.tif, Sentinel1_Thailand-0000023296-0000023296.tif, Sentinel1_Thailand-0000046592-0000000000.tif, Sentinel1_Thailand-0000046592-0000023296.tif; no Sentinel-1 sidecar metadata files found
- CDSE evidence: no CDSE metadata snapshot supplied
- Provider/hackathon note: hackathon usage note found: project owner reported free use; no acquisition date or Sentinel-1 product id found

## Decision

The standalone local Sentinel-1 TIFF is useful as a checksum-backed SAR context candidate, but it cannot be called pre-event, post-event, or event-window yet. The acquisition date is not recoverable from the current filename, TIFF tags, ZIP member names, or committed metadata snapshots.

It must not be used as the real Mae Sai flood baseline until provenance, event timing, and reference-mask status are resolved.

## Next Step

Proceed to Task 43 - DEM Readiness Lane while Sentinel-1 provenance remains blocked, or acquire a provider note/source package manifest that maps the local TIFF to a real Sentinel-1 acquisition.
