# Demo Story

## One-Minute Pitch

Flood maps answer one question: where is the water? During a disaster, local governments need a harder answer: who is cut off, and where should they act first?

FloodGuard Thailand is a decision-support layer that builds on flood products and adds the missing operational intelligence: road-disruption probability, evacuation access loss, Evacuation Equity Gap, shelter capacity versus reachable demand, and a transparent subdistrict priority score with recommended actions and confidence.

## Golden Vertical Slice

Input:

- sample flood probability
- sample roads
- sample shelters
- sample hospitals or clinics
- sample population and vulnerability
- sample subdistrict boundaries

Pipeline:

```text
flood probability
  -> road disruption
  -> access loss
  -> equity gap
  -> priority score
  -> action class
  -> one-page brief
```

Output:

- `priority_subdistricts.geojson`
- `road_risk.geojson`
- `action_brief_subdistrict_x.md`
- `validation_summary.md`

## Demo Rule

A non-technical reviewer should be able to identify the highest-priority subdistrict, the reason it is high priority, the confidence class, and the recommended action in under one minute.

## Replay Beat (60-90 s)

Flood maps answer where the water was. The Mae Sai replay of September 2024 answers what the flood did to people who needed to leave: hour by hour, which roads went under, who lost a shelter within walking distance, and how the shelters used in 2024 compare with a ranked plan. Every figure carries its lane: model (T1 scenario, low confidence), observed, calibration, reported, or scenario envelope. The replay is a historical reconstruction, not real-time, and it gives no priority score and no action class; those come from the planning overlay.

Path:

```text
onset, 10 Sep 22:00 (first-flooded view)
  -> peak, 12 Sep 12:00: walking access and the two shelter sets
  -> 15 Sep: Sentinel-2 and VIIRS observed beside the model
  -> the checks and the 2024 season envelope (product 4009, a scenario)
  -> download the tables
  -> the same page in Thai
```

Links, lines and on-screen labels:

- `docs/demo_walkthrough.md`, section "Mae Sai Replay Beat (60-90 s)"
- figures to quote: `docs/demo/replay_numbers.md`
- venue fallback video: `docs/demo/mae-sai-replay-demo.mp4`
- offline laptop: `docs/demo/offline_dry_run_checklist.md`

Replay rule: after the beat, a judge should be able to say which figures are model output and which are observed, and that the replay itself ranks no subdistrict.
