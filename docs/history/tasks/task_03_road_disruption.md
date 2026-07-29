# Task 03 - Road-Disruption Probability

## Goal

Estimate likely disrupted road segments from simple, explainable features.

## Initial Inputs

- road segment id
- road class
- flood probability
- surrounding inundation proxy
- bridge flag if available

## Initial Output

- `road_disruption_probability_0_1`
- `confidence_class`
- `top_risk_reason`

## Acceptance

Unit tests cover road class weighting, bridge adjustment, flood-probability boundaries, and missing columns.
