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
