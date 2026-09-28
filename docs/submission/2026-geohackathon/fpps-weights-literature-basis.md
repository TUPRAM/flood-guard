# FPPS Weights: Literature Basis, Benchmarks and Robustness

FloodGuard Thailand · Flood Preparedness Priority Score (FPPS) · submission note for reviewers

```text
FPPS = 0.30 flood likelihood + 0.25 exposure + 0.20 access gap
     + 0.15 road criticality + 0.10 vulnerability/context      (each component 0-100)
```

Code: `src/floodguard/scoring.py` (engine), `src/floodguard/sensitivity.py` (weight scenarios),
`apps/web/src/lib/fpps.ts` (web port, parity-tested against the Python engine through
`tests/fixtures/fpps_parity_cases.json`), `apps/web/src/lib/replay-fpps.ts` (Mae Sai replay components).

---

## 1. Summary for reviewers

1. **No single paper prescribes 0.30 / 0.25 / 0.20 / 0.15 / 0.10.** The weights are expert-set
   defaults (`AGENTS.md`, `docs/model_contract.md`). The OECD/JRC composite-indicator handbook accepts
   expert weighting, provided the weights are stated openly and their effect is tested. FPPS does both.
2. **The numbers are close to published benchmarks.** The closest is an AHP-derived flood-risk index
   (Wang et al. 2025): hazard **30.05%**, exposure **23.69%**, vulnerability **26.52%**, coping capacity
   **19.74%**. FPPS's first three weights (0.30, 0.25, 0.20) sit within 1.3 percentage points of the
   corresponding values.
3. **Two weights deliberately depart from the benchmarks**, for stated reasons:
   road criticality is higher (0.15 vs about 0.05) and vulnerability is lower (0.10 vs about 0.16-0.33).
   See section 3.
4. **The ranking does not depend on the exact weights.** For the Mae Sai flood peak, all eight
   subdistricts keep the same rank under six weightings, including equal weights (section 5).

---

## 2. From literature to the five weights: the reasoning chain

| Step | Question | What the literature says | Decision for FPPS |
|---|---|---|---|
| 1 | What makes up flood risk? | Risk comes from hazard interacting with exposure and vulnerability (IPCC 2014). INFORM adds lack of coping capacity as a third dimension (JRC 2017). | Five components: hazard (flood likelihood), exposure, coping capacity (split into access gap and road criticality), vulnerability. |
| 2 | How do published indices weight these dimensions? | INFORM: equal thirds (hazard & exposure, vulnerability, lack of coping capacity), geometric mean. WorldRiskIndex: exposure × vulnerability, vulnerability = equal thirds of susceptibility, lack of coping and lack of adaptive capacity. Wang et al. (2025), AHP: 30.05 / 23.69 / 26.52 / 19.74%. | Equal weighting is the common baseline; AHP puts hazard highest, at about 30%. |
| 3 | Should hazard get the most weight? | Wang et al. (2025) AHP gives hazard the largest weight. Al Kuisi et al. (2024) weight the hazard map above vulnerability "as the severity of the hazard is the primary determinant of flood risk". | Flood likelihood 0.30, the largest weight. |
| 4 | How to set weights for our mission and data? | OECD/JRC (2008): weights must reflect the index's purpose and data quality. Coles et al. (2017), Yu et al. (2020) and Ermagun et al. (2024) show access loss is what turns exposure into harm. Rufat et al. (2015): vulnerability needs demographic, socioeconomic and health data. | Keep hazard, exposure and access close to the benchmarks; raise roads (the Mae Sai isolation mechanism); lower vulnerability (our proxy has no demographic data). |
| 5 | Are the results robust to the choice? | Saisana et al. (2005) and Tate (2012): test rank stability under alternative weights. | Six weighting scenarios: the Mae Sai peak ranking is unchanged (section 5). |

---

## 3. Weight-by-weight evidence table

Benchmark shares are percentages of the whole index. Where a benchmark gives a sub-indicator weight, the
share of the whole index is computed as dimension weight × sub-indicator weight
(for example 19.74% × 27.17% = 5.36%).

| FPPS weight | Nearest published benchmarks | How we reach our value | Where the evidence stops |
|---|---|---|---|
| **0.30 Flood likelihood (hazard)** | Wang et al. 2025 (AHP): **hazard 30.05%**, the largest of four dimensions. INFORM: hazard & exposure **1/3** (JRC 2017). Al Kuisi et al. 2024: hazard map weighted **above** vulnerability. Kittipongvises et al. 2020 (Ayutthaya, Thailand) and Kazakis et al. 2015: AHP-weighted flood hazard indices. | 0.30 matches Wang's AHP hazard weight to within 0.05 percentage points, sits just under INFORM's one-third, and is the largest FPPS weight, as in Al Kuisi et al. | Wang's hazard is rainstorm and soil-erosion hazard on China's Loess Plateau, not a riverine flood in Thailand. The match supports the magnitude, not an exact equivalence. |
| **0.25 Exposure (people in water)** | Wang et al. 2025: **exposure 23.69%** (physical: vegetation cover, relief, impervious surface). Their population density is 40.15% of vulnerability = **10.65%** of the index. WorldRiskIndex: exposure (share of population exposed) is one of **two multiplied factors** (Welle & Birkmann 2015; WRI 2021 notes). | 0.25 is within 1.3 points of Wang's exposure weight and second only to hazard. FPPS measures exposure as residents in water (WorldPop; Stevens et al. 2015), which is closer to the WorldRiskIndex definition. | Definitions differ: Wang's exposure is landscape, not people. Our 0.25 therefore also covers the population share that Wang places under vulnerability. |
| **0.20 Access gap (walking access to a dry shelter)** | Wang et al. 2025: **coping capacity 19.74%**, of which emergency shelter 34.88% (**6.89%** of the index), medical institutions 37.94%, road network density 27.17%. INFORM: lack of coping capacity **1/3**. WorldRiskIndex: lack of coping capacity **1/3** of vulnerability. Ermagun et al. 2024 add shelter access to a flood-risk index. Coles et al. 2017; Yu et al. 2020: flooded networks cut emergency access. | 0.20 is within 0.3 points of Wang's whole coping-capacity weight. FPPS gives shelter access the whole coping-capacity weight because evacuation access is the project's mission. | Wang's coping capacity also includes medical institutions; ours covers shelter access only. Ermagun et al. use clustering, not numeric weights. |
| **0.15 Road criticality (impassable roads)** | Wang et al. 2025: road network density = **5.36%** of the index. Pregnolato et al. 2017: roads impassable at **0.3 m** (our threshold). Yu et al. 2020: road flooding reduces emergency-response coverage. | 0.15 is **deliberately above** the ~5% benchmark. In Mae Sai the trunk and primary roads (Mae Sai bypass, Phahonyothin Road) are modelled cut for up to about 110 hours, which is the main way villages become isolated. Action class B (Keep Routes Open) depends on this component. | This is the weight with the least direct literature support. It is a local judgement; the road-heavy scenario (0.30) leaves the peak ranking unchanged. |
| **0.10 Vulnerability/context** | INFORM: vulnerability **1/3**. WorldRiskIndex: vulnerability is one of **two multiplied factors**. Wang et al. 2025: vulnerability **26.52%**; without population density (counted in our exposure), **15.87%**. Tingsanchali & Promping 2022 (Nan, Thailand): vulnerability = **0.33** population + **0.67** household (AHP). Cutter et al. 2003; Rufat et al. 2015: demographic, socioeconomic and health drivers. | 0.10 is **deliberately below** the 16-33% benchmarks. Our proxy is terrain and remoteness only (slope ≥ 8°, or ≥ 750 m from a drivable road), with no age, disability, income or health data, so it gets the least weight. Population is already counted in exposure, so it is not counted twice. | Lower than every benchmark. When demographic vulnerability data is available, this weight should rise toward the literature range. The vulnerability-heavy scenario (0.25) leaves the peak ranking unchanged. |

### Side by side: FPPS and the closest AHP benchmark

| Dimension | Wang et al. 2025 (AHP) | FPPS | Difference |
|---|---|---|---|
| Hazard / flood likelihood | 30.05% | 30% | -0.05 |
| Exposure | 23.69% | 25% | +1.31 |
| Coping capacity / access gap | 19.74% | 20% | +0.26 |
| of which roads | 5.36% | 15% (separate component) | +9.64 |
| Vulnerability | 26.52% | 10% | -16.52 |
| Total | 100% (roads inside coping capacity) | 100% | |

Roads sit inside coping capacity in Wang et al. but are a separate component in FPPS, so their weights do
not add to the same total row for row.

---

## 4. Other parameters and their sources

| Parameter | Value in FloodGuard | Source |
|---|---|---|
| Road impassable depth | 0.3 m | Pregnolato et al. 2017: vehicle speed falls to zero at about 300 mm. |
| Shelter floor space | 3.5 m² per person | Sphere Handbook 2018, minimum covered living space (warm climate). |
| Flood water model | HAND terrain model | Nobre et al. 2011. |
| Population | WorldPop 100 m | Stevens et al. 2015. |
| Action-class thresholds (A: exposure ≥ 70 and access ≥ 70, …) | Expert defaults | `docs/model_contract.md`: "intentionally simple for the MVP and should be sensitivity-tested later". |
| Component scale anchors (e.g. 25% of area flooded scores 100) | Expert defaults, versioned `replay_fpps_anchor_v1` | Fixed anchors instead of min-max scaling, as required by `docs/model_contract.md` §2b. |

---

## 5. Robustness: the Mae Sai ranking under alternative weights

Scenarios from `src/floodguard/sensitivity.py` (each raises one weight; weights are then normalised to
sum to 1), plus equal weights. Inputs: the Mae Sai replay at the flood peak (12 Sep 2024 12:00 ICT,
assumed stage 3.5 m), shelters reported in use in Sep 2024.

| Scenario | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| Default | Mae Sai 89.3 | Si Mueang Chum 86.0 | Ban Dai 81.1 | Ko Chang 76.4 | Pong Pha 66.1 | Pong Ngam 53.9 | Huai Khrai 34.1 | Wiang Phang Kham 31.3 |
| Access-heavy (0.35) | Mae Sai 90.2 | Si Mueang Chum 87.7 | Ban Dai 83.6 | Ko Chang 79.5 | Pong Pha 70.5 | Pong Ngam 59.6 | Huai Khrai 42.7 | Wiang Phang Kham 40.2 |
| Exposure-heavy (0.40) | Mae Sai 90.7 | Si Mueang Chum 85.8 | Ban Dai 78.6 | Ko Chang 72.3 | Pong Pha 62.9 | Pong Ngam 49.5 | Huai Khrai 30.5 | Wiang Phang Kham 27.4 |
| Road-heavy (0.30) | Mae Sai 90.7 | Si Mueang Chum 87.8 | Ban Dai 83.6 | Ko Chang 79.5 | Pong Pha 61.5 | Pong Ngam 53.6 | Huai Khrai 30.2 | Wiang Phang Kham 29.6 |
| Vulnerability-heavy (0.25) | Mae Sai 77.8 | Si Mueang Chum 74.8 | Ban Dai 71.5 | Ko Chang 66.6 | Pong Pha 61.9 | Pong Ngam 55.3 | Huai Khrai 39.7 | Wiang Phang Kham 36.1 |
| Equal (0.20 each, as in INFORM/WRI) | Mae Sai 79.5 | Si Mueang Chum 76.8 | Ban Dai 73.8 | Ko Chang 69.3 | Pong Pha 59.7 | Pong Ngam 56.8 | Huai Khrai 40.3 | Wiang Phang Kham 38.4 |

**Results**

- **At the peak, every subdistrict keeps the same rank in all six scenarios** (rank range 0). By the
  Saisana et al. (2005) criterion, the peak ranking does not depend on the weights, including the equal
  weighting used by INFORM and the WorldRiskIndex.
- **The implied action classes of the top six never change:** Mae Sai and Si Mueang Chum A, Ban Dai and
  Ko Chang B, Pong Pha and Pong Ngam D. Only Huai Khrai and Wiang Phang Kham move between E and D, because
  their scores are near the 35-point cut-off.
- **At the flood's onset (stage 0.5 m) the top two are stable** in every scenario. Middle ranks move by up
  to two places (Ban Dai 3-4, Wiang Phang Kham 3-5, Pong Pha 4-6). Early in an event, when scores are
  close, weights matter more, and this should be reported with any early ranking.

---

## 6. Limitations and next step

- **Replay confidence is LOW.** The water is a terrain-model reconstruction with assumed river levels, so
  every action class is E; the "score implies" class is shown for planning checks only.
- **Benchmarks come from other regions.** Wang et al. (2025) is a Chinese regional study; the Thai studies
  (Kittipongvises et al. 2020; Tingsanchali & Promping 2022) weight hazard and vulnerability
  sub-indicators, not the five FPPS components.
- **Recommended next step: derive Mae Sai weights with local stakeholders.** Run an AHP pairwise
  comparison (Saaty 1990) with the Mae Sai district office, DDPM and local responders, as Tingsanchali &
  Promping (2022) did in Nan. Report the AHP weights and ranking next to the defaults.

---

## 7. References

**Method: composite indicators and weighting**

1. OECD & European Commission JRC (2008). *Handbook on Constructing Composite Indicators: Methodology
   and User Guide.* OECD Publishing, Paris.
   <https://www.oecd.org/content/dam/oecd/en/publications/reports/2008/08/handbook-on-constructing-composite-indicators-methodology-and-user-guide_g1gh9301/9789264043466-en.pdf>
2. Saisana, M., Saltelli, A. & Tarantola, S. (2005). Uncertainty and sensitivity analysis techniques as
   tools for the quality assessment of composite indicators. *Journal of the Royal Statistical Society
   A*, 168(2), 307-323. https://doi.org/10.1111/j.1467-985X.2005.00350.x
3. Tate, E. (2012). Social vulnerability indices: a comparative assessment using uncertainty and
   sensitivity analysis. *Natural Hazards*, 63, 325-347. https://doi.org/10.1007/s11069-012-0152-2
4. Saaty, T. L. (1990). How to make a decision: the analytic hierarchy process. *European Journal of
   Operational Research*, 48(1), 9-26. https://doi.org/10.1016/0377-2217(90)90057-I

**Risk frameworks and indices with published weights**

5. IPCC (2014). *Climate Change 2014: Impacts, Adaptation, and Vulnerability. Working Group II
   contribution to AR5, Summary for Policymakers*, Figure SPM.1.
   <https://www.preventionweb.net/publication/ipcc-fifth-assessment-report-climate-change-2014-impacts-adaptation-and-vulnerability>
6. European Commission JRC (2017). *INFORM Index for Risk Management: Concept and Methodology, Version
   2017.* Risk = (Hazard & Exposure)^1/3 × Vulnerability^1/3 × (Lack of coping capacity)^1/3.
   <https://drmkc.jrc.ec.europa.eu/inform-index/INFORM-Risk/Methodology>
7. Welle, T. & Birkmann, J. (2015). The World Risk Index – an approach to assess risk and vulnerability
   on a global scale. *Journal of Extreme Events*, 2(1), 1550003.
   https://doi.org/10.1142/S2345737615500037
8. Bündnis Entwicklung Hilft & IFHV (2021). *Methodological Notes of the WorldRiskIndex, Version 2021.*
   WorldRiskIndex = Exposure × Vulnerability; Vulnerability = [Susceptibility + (1 − Coping capacity) +
   (1 − Adaptive capacity)] / 3.
   <https://weltrisikobericht.de/wp-content/uploads/2021/09/Methodological_notes_WorldRiskIndex2021.pdf>
9. Wang, M., Zhu, H., Yao, J., Hu, L., Kang, H. & Qian, A. (2025). Assessing large-scale flood risks:
   a multi-source data approach. *Sustainability*, 17(11), 5133. https://doi.org/10.3390/su17115133
   (Table 4: AHP weights hazard 30.05%, exposure 23.69%, vulnerability 26.52%, coping capacity 19.74%.)
10. Al Kuisi, M., Al Azzam, N., Hyarat, T. & Farhan, I. (2024). Flood hazard and risk assessment of
    flash floods for Petra catchment area using hydrological and analytical hierarchy (AHP) modeling.
    *Water*, 16(16), 2283. https://doi.org/10.3390/w16162283
11. Kazakis, N., Kougias, I. & Patsialis, T. (2015). Assessment of flood hazard areas at a regional
    scale using an index-based approach and Analytical Hierarchy Process: application in Rhodope–Evros
    region, Greece. *Science of the Total Environment*, 538, 555-563.
    https://doi.org/10.1016/j.scitotenv.2015.08.055

**Thailand**

12. Kittipongvises, S., Phetrak, A., Rattanapun, P., Brundiers, K., Buizer, J. L. & Melnick, R. (2020).
    AHP-GIS analysis for flood hazard assessment of the communities nearby the world heritage site on
    Ayutthaya Island, Thailand. *International Journal of Disaster Risk Reduction*, 48, 101612.
    https://doi.org/10.1016/j.ijdrr.2020.101612
13. Tingsanchali, T. & Promping, T. (2022). Comprehensive assessment of flood hazard, vulnerability, and
    flood risk at the household level in a municipality area: a case study of Nan Province, Thailand.
    *Water*, 14(2), 161. https://doi.org/10.3390/w14020161
    (Flood risk = hazard × vulnerability; AHP hazard weights: duration 0.63, depth 0.26, velocity 0.11;
    vulnerability: population 0.33, household 0.67.)

**Components**

14. Nobre, A. D. et al. (2011). Height Above the Nearest Drainage – a hydrologically relevant new
    terrain model. *Journal of Hydrology*, 404, 13-29. https://doi.org/10.1016/j.jhydrol.2011.03.051
15. Stevens, F. R., Gaughan, A. E., Linard, C. & Tatem, A. J. (2015). Disaggregating census data for
    population mapping using random forests with remotely-sensed and ancillary data. *PLoS ONE*, 10(2),
    e0107042. https://doi.org/10.1371/journal.pone.0107042
16. Coles, D., Yu, D., Wilby, R. L., Green, D. & Herring, Z. (2017). Beyond 'flood hotspots': modelling
    emergency service accessibility during flooding in York, UK. *Journal of Hydrology*, 546, 419-436.
    https://doi.org/10.1016/j.jhydrol.2016.12.013
17. Yu, D., Yin, J., Wilby, R. L. et al. (2020). Disruption of emergency response to vulnerable
    populations during floods. *Nature Sustainability*, 3, 728-736.
    https://doi.org/10.1038/s41893-020-0516-7
18. Ermagun, A., Smith, V. & Janatabadi, F. (2024). High urban flood risk and no shelter access
    disproportionally impacts vulnerable communities in the USA. *Communications Earth & Environment*,
    5, 2. https://doi.org/10.1038/s43247-023-01165-x
19. Pregnolato, M., Ford, A., Wilkinson, S. M. & Dawson, R. J. (2017). The impact of flooding on road
    transport: a depth-disruption function. *Transportation Research Part D*, 55, 67-81.
    https://doi.org/10.1016/j.trd.2017.06.020
20. Cutter, S. L., Boruff, B. J. & Shirley, W. L. (2003). Social vulnerability to environmental hazards.
    *Social Science Quarterly*, 84(2), 242-261. https://doi.org/10.1111/1540-6237.8402002
21. Rufat, S., Tate, E., Burton, C. G. & Maroof, A. S. (2015). Social vulnerability to floods: review of
    case studies and implications for measurement. *International Journal of Disaster Risk Reduction*,
    14, 470-486. https://doi.org/10.1016/j.ijdrr.2015.09.013
22. Sphere Association (2018). *The Sphere Handbook: Humanitarian Charter and Minimum Standards in
    Humanitarian Response*, 4th ed. Geneva. <https://spherestandards.org/handbook-2018/>

*Verification note: every DOI, and each benchmark number quoted in sections 2-3, was checked against the
publisher page or official methodology document in September 2026. Wang et al. (2025) Table 4,
Tingsanchali & Promping (2022) and Al Kuisi et al. (2024) were read in full text; INFORM and the
WorldRiskIndex formulas were read from their official methodology pages.*
