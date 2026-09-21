# FloodGuard current demonstration walkthrough

Start the Mae Sai finals presentation at
`/studio/brief/?aoi=aoi-01_mae_sai_core&event=mae_sai_2024`.
Use [the finals guide and claim register](mae_sai_finals_guide.md) for the current
three-minute script, source boundaries and readiness checklist.

1. Start from a prepared public-place pin. Name the service, mode, geographic
   scope, observation question and source years.
2. Compare the baseline path with an explicit road-link closure or destination
   removal. Show the two paths, nearest eligible destinations, times, distances
   and assumed connectors. These are not observed before/after flood conditions.
3. Distinguish modelled residential population, route coverage and unavailable
   observed flood impact. Do not call these residents flood victims.
4. Compare one declared intervention with its matching baseline. Explain both
   threshold changes and travel-time effects, including an honest zero result.
5. Show which assumptions alter the conclusion and which facility/route fact
   still needs review.
6. Open `/studio/library/` for source, rights and quality detail; return to the
   concise brief for the decision story.

The research archive in `/studio/` and the older `/command/` workspace do not
provide accepted event FPPS/action classes. Their retained scores are report-only
comparators. Do not combine them with current brief numbers. The release handoff
identifies the tested preview, package hashes and local reproduction commands.

## Archived synthetic-dashboard walkthrough

Everything below describes the older static fixture-backed dashboard at
`outputs/dashboard.html`. These numerical examples remain for software
rehearsal; they are not the current Mae Sai case or a finals-ready evidence claim.
This is not an official warning, real flood validation, or real-data ML output.

## Setup

Regenerate the dashboard:

```powershell
uv run python scripts/generate_sample_priority.py
uv run python scripts/generate_sample_decision_outputs.py
uv run python scripts/smoke_dashboard.py
```

Serve locally:

```powershell
uv run python -m http.server 8000 -d outputs
```

Open:

```text
http://localhost:8000/dashboard.html
```

### Archived 3-5 Minute Judge Path (synthetic example)

1. Start on `FG-TB-001 / River Market`.
   - Point to FPPS `81.60`, action class `A`, confidence `high`, baseline 30-minute access loss, and equity gap.
   - Say: FloodGuard ranks local action priorities from flood, exposure, access, equity, and road-risk evidence. It is not just showing where water might be.

2. Explain the map.
   - Polygons are synthetic subdistrict priorities.
   - Road segments are synthetic road-risk outputs.
   - The map is fixture-backed and non-operational.

3. Open or point to the `Action Brief` panel.
   - Show the top reason and recommended local actions.
   - Mention that A/B/C briefs are generated for actionable subdistricts.

4. Switch to `FG-TB-002 / Bridge Junction`.
   - This is the best scenario demo row because the intervention and stress-test deltas are visible.

5. Toggle `temporary shelter delta`.
   - Explain that the temporary shelter reduces 30-minute access loss by `30` people in the fixture.
   - The dashboard shows the intervention effect without claiming it is a real deployment plan.

6. Toggle `road closure delta`.
   - Explain the stress case: closing the selected road increases people losing 30-minute access by `50` in the fixture.
   - This is why road-risk and access-loss are part of the decision layer.

7. Switch to `Mae Sai weak-reference candidate`.
   - At regional zoom, point out that only priority road candidates and ADM3 facility clusters are shown.
   - Select `TH570903 / Ko Chang`; the map zooms to selected-area detail, dims surrounding ADM3 units, and reveals typed candidate facilities and detailed roads.

8. Open `Sentinel-1 evidence`, then enter `Judge mode`.
   - Show the pre/post acquisition pair, selected-unit SAR change, flood-probability summaries, source quality, and compact provenance.
   - State that this is weak-reference candidate evidence, not official validation or field validation.
   - Use the English/Thai (`EN / TH`) toggle once to show bilingual readiness, then return to the presentation language.

### Archived 10 Minute Expanded Path (synthetic example)

1. Start with the status chips:
   - `Fixture demo`
   - `Non-operational`
   - `Real validation blocked`

2. Explain the FPPS inputs:
   - flood likelihood
   - exposure
   - access gap
   - road criticality
   - vulnerability/context

3. Show `FG-TB-001 / River Market`.
   - It is class A because high exposure and access loss require life-safety action.

4. Show `FG-TB-002 / Bridge Junction`.
   - It is class B because routes and access are the key decision issue.

5. Show `FG-TB-003 / Clinic Basin`.
   - It is class C because essential services are the policy focus.

6. Use action-class filters.
   - Temporarily hide `D` and `E` to focus on actionable A/B/C areas.

7. Use scenario mode:
   - `baseline`
   - `temporary shelter delta`
   - `road closure delta`
   - For `FG-TB-002`, say the temporary shelter improves 30-minute access by `30` people and the road-closure stress case worsens it by `50` people.

8. Use export buttons:
   - `Download current brief`
   - `Download filtered GeoJSON`

9. Switch to the Mae Sai weak-reference dataset and inspect a selected ADM3 unit.
   - Regional zoom intentionally suppresses low-priority road detail and clusters facilities.
   - Selected-area detail reveals all candidate roads and separate hospital, clinic, other healthcare, school, shelter, emergency-service, and community symbols where available.
   - The Sentinel-1 drawer reports derived ADM3 statistics from the real pre/post pair; it does not claim official validation.

10. Close in `Judge mode`:
   - Secondary controls and long reports are hidden, but the weak-reference warning, source quality, SAR evidence, and provenance remain visible.
   - THEOS-2, SAR quicklooks, and DEM previews remain context only.
   - Official validation remains blocked; current Mae Sai metrics are against a manually digitized weak-reference candidate and are not field validated.

## Exact Phrases To Use

- "This is a fixture-backed decision demo."
- "This is non-operational and not an official warning."
- "The context assets are not flood labels or reference masks."
- "The current real-data candidate is evaluated against a manual weak reference, not an official or field-validated mask."
- "The differentiator is turning flood information into access, equity, road risk, scenario effects, and local action briefs."

## Avoid Saying

- "Real-time detection"
- "Official warning"
- "Validated flood extent"
- "THEOS-2 confirms flooding"
- "Sentinel-1 quicklook proves flood water"
- "ML is ready"
