# AGENTS.md - FloodGuard Thailand

## Project Mission

FloodGuard Thailand converts flood extent or flood probability into local decision intelligence:

- exposed population and facilities
- likely disrupted road segments
- evacuation access loss
- Evacuation Equity Gap
- shelter capacity versus reachable demand
- subdistrict Flood Preparedness Priority Score
- A-E recommended action class

The project is a preparedness and rapid post-event prioritization tool. Do not describe it as a guaranteed real-time emergency sensor or official warning system.

## Technical Principles

1. Prefer simple, testable geospatial modules over large untested notebooks.
2. Keep flood detection, road disruption, access analysis, equity analysis, and scoring as separate modules.
3. Every output must include source timestamp, confidence, and assumptions where relevant.
4. Do not hard-code local file paths, secrets, API keys, or private data.
5. Use open, reproducible fixtures for tests.
6. Use type hints and docstrings for public functions.
7. Add tests for scoring, equity ratios, and access-loss logic.
8. Keep notebooks exploratory; production logic belongs in `src/floodguard/`.

## Method Constraints

Default Flood Preparedness Priority Score:

```text
FPPS = 0.30 Flood likelihood
     + 0.25 Exposure
     + 0.20 Access gap
     + 0.15 Road criticality
     + 0.10 Vulnerability/context
```

Each component should be normalized to 0-100.

Action classes:

- A: Protect Lives Now
- B: Keep Routes Open
- C: Protect Essential Services
- D: Build Resilience
- E: Monitor and Verify

## Review Guidelines

Flag as high priority:

- missing tests for scoring or equity logic
- outputs without confidence or timestamp fields
- claims of real-time detection
- code that mixes raw data, processed data, and outputs without clear separation
- code that cannot run on the provided sample fixtures
