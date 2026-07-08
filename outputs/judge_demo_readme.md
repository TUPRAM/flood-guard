# FloodGuard Judge Demo Readme

This demo is a fixture-backed decision-layer prototype. It is non-operational, not an official warning, not a real-time sensor, and not a validated flood-detection product.

## What The Fixture Demo Proves

FloodGuard can turn a flood-probability input into local decision outputs:

- subdistrict Flood Preparedness Priority Score (FPPS)
- A-E action class
- road-disruption probability
- normal versus disrupted access loss
- Evacuation Equity Gap
- scenario comparison for temporary shelter and road closure cases
- action briefs that translate scores into local response priorities
- dashboard-ready GeoJSON with provenance, confidence, and assumptions

The important point is that FloodGuard is more than a flood map. The prototype converts flood information into access, equity, road-risk, scenario, and action-priority evidence that a local team can review.

## What It Does Not Prove

The current dashboard does not prove real flood-detection accuracy. It does not validate against a legal Mae Sai reference mask. It does not claim that SAR, DEM, or THEOS-2 context previews are flood labels, reference masks, or official observations.

Real Mae Sai validation remains blocked until:

- provider responses confirm reference-mask terms
- geometry access is confirmed
- local analysis is allowed
- derived metrics are allowed
- screenshots/demo reuse is allowed
- redistribution or reference-only status is known
- citation requirements are locked
- local files are tracked outside Git with SHA-256 checksums

Real-data ML remains blocked until those gates pass and a real non-ML SAR baseline is validated first.

## How The Demo Connects

1. `sample_priority_scores.csv` scores synthetic subdistricts with FPPS.
2. `sample_road_risk.csv` estimates which road segments are likely disrupted.
3. `sample_access_loss.csv` compares normal access with disrupted access.
4. `sample_equity_gap.csv` measures whether vulnerable people lose access at a higher rate.
5. Scenario outputs compare baseline conditions against a temporary shelter intervention and a road-closure stress case.
6. `priority_subdistricts.geojson` merges the score, scenario deltas, confidence, assumptions, and geometry for the dashboard.
7. `dashboard.html` embeds all data statically so the judge demo can run without a backend.

## Recommended Judge Path

Start with `FG-TB-001 / River Market`. It is the highest actionable A-class target in the fixture set and has a compact action brief.

Then show `FG-TB-002 / Bridge Junction`. Toggle the temporary shelter scenario to show a 30-minute access-loss improvement, then toggle the road closure scenario to show a stress-case worsening.

Use the Context Assets panel only as situational context:

- Sentinel-1 SAR quicklooks: context only; timing unresolved; not flood detection.
- DEM terrain preview: terrain context only; not flood observation or flood label.
- THEOS-2 optical thumbnails: optical context only; not flood validation.

End with Data Readiness. The honest blocker is that real validation cannot start until provider/legal and file-level gates are clear.

## Files To Open

- `outputs/dashboard.html`
- `outputs/data_dictionary.md`
- `docs/demo_walkthrough.md`
- `docs/dashboard_demo_qa_checklist.md`
- `outputs/mae_sai_validation_summary.md`

## Safety Boundary

FloodGuard is a preparedness and rapid post-event prioritization prototype. It supports review and planning; it does not replace GISTDA, DDPM, TMD, RID, ONWR, local authorities, or field verification.
