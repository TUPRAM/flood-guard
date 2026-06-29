# Validation Plan

## Technical Validation

1. Reference-mask validation: compare flood extent against available GISTDA, UNOSAT, International Charter, Copernicus EMS/CEMS, or manual reference layers.
2. Temporal holdout: tune on one event and test on another.
3. Spatial holdout: evaluate transfer across mountainous urban, lowland riverine, and dense urban drainage contexts.
4. Manual review: inspect urban layover, rice paddies, permanent water, steep terrain, and shadow areas.
5. Policy validation: compare top-ranked subdistricts with field knowledge from district, municipal, or DDPM stakeholders.

## MVP Unit Validation

The first code milestone validates:

- missing required columns raise clear errors
- FPPS formula is deterministic
- boundary component values remain in the 0-100 range
- A-E action classes follow the documented rule order
- sample fixture can generate a reviewable output CSV

## Metrics Roadmap

- Flood extent: IoU, F1/Dice, precision, recall, area error, false-alarm rate.
- Flood probability: Brier score, calibration curve, reliability class.
- Road disruption: segment-level precision/recall where closures exist; top-k expert review otherwise.
- Access loss: share of population losing 15/30/60-minute access; travel-time increase.
- Equity gap: difference and ratio of access loss between vulnerability groups.
- Priority score: top-k agreement with historical impact data or expert validation; sensitivity to weights.
