# FloodGuard Thailand - Engineering Brief

## One-Line Objective

Build a reproducible GeoAI decision-support prototype that converts flood extent or probability into subdistrict-level action priorities for flood preparedness and response in Thailand.

## MVP Study Areas

1. Chiang Rai / Mae Sai 2024 - validation tile.
2. Hat Yai / Songkhla 2025 - story and stress-test tile.
3. Lower Chao Phraya / Greater Bangkok - scale target.

## MVP Outputs

1. Flood probability or binary flood extent.
2. Population and facility exposure by subdistrict.
3. Road-disruption probability by road segment.
4. Normal versus flood-disrupted access to shelters, hospitals, clinics, and main roads.
5. Evacuation Equity Gap.
6. Shelter capacity versus reachable demand.
7. Flood Preparedness Priority Score.
8. A-E action class.
9. One-page action brief for a selected high-priority subdistrict.

## Non-Goals

- Do not build a full official emergency warning system.
- Do not claim guaranteed real-time flood detection.
- Do not depend on unavailable private government datasets for the MVP.
- Do not make the ML model more complex than the validation data can support.

## Product Principle

Flood extent is the input. The product is the local decision layer: who is exposed, who loses access, whether loss is unequal, which roads matter, which shelters are overwhelmed, and where officials should act first.
