# FloodGuard Demo Walkthrough

This walkthrough is for the static fixture-backed dashboard at `outputs/dashboard.html`. It is not an official warning, not real flood validation, and not real-data ML output.

## Setup

Regenerate the dashboard:

```powershell
cd "C:\Users\iputu\Documents\Flood Guard"
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

## 3-5 Minute Judge Path

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

7. Open `Context Assets`.
   - Sentinel-1 quicklooks are SAR context only.
   - DEM is terrain context only.
   - THEOS-2 is optical context only.
   - None of these are legal flood labels in the current dashboard.

8. Open `Data Readiness`.
   - End with the blocker: real Mae Sai validation waits for provider/legal clearance, local paths, SHA-256 checksums, and a locked pre/post Sentinel-1 pair.

## 10 Minute Expanded Path

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

9. Scroll to the validation/report section.
   - Explain that fixture SAR metrics prove wiring only.
   - Real IoU, F1/Dice, precision, recall, and area error remain blocked until a legal reference mask exists.

10. Close with readiness:
   - UNOSAT/UNITAR and GISTDA requests are logged as sent and waiting for response.
   - THEOS-2, SAR quicklooks, and DEM previews support context only.
   - The next real-data step is legal/file manifest clearance, not ML.

## Exact Phrases To Use

- "This is a fixture-backed decision demo."
- "This is non-operational and not an official warning."
- "The context assets are not flood labels or reference masks."
- "Real-data ML starts only after legal reference masks and the non-ML baseline are ready."
- "The differentiator is turning flood information into access, equity, road risk, scenario effects, and local action briefs."

## Avoid Saying

- "Real-time detection"
- "Official warning"
- "Validated flood extent"
- "THEOS-2 confirms flooding"
- "Sentinel-1 quicklook proves flood water"
- "ML is ready"
