# Form 1: Sentinel-2 reference imagery, per-purpose rights record

**Status: UNSIGNED.** Pre-filled from `GATE_RESEARCH_DOSSIER.md` Step 1.

## Source

| Field | Value |
| --- | --- |
| Product | `S2B_MSIL2A_20240915T034529_N0511_R104_T47QNC_20240915T065143.SAFE` |
| CDSE product id | `f1a638d2-3b8f-4f9a-a862-1b651d6662c3` |
| SAFE ZIP SHA-256 | `<from outputs/cdse_mae_sai_sentinel2_reference_acquisition_manifest.csv after download>` |
| SAFE ZIP bytes | `<same manifest>` |
| Licence | Legal notice on the use of Copernicus Sentinel Data and Service Information (Reg. (EU) 377/2014; Delegated Reg. (EU) 1159/2013, Art. 7) |

## Purposes

Mark each purpose **Yes** or **No**. The "Licence basis" column is research
input; your mark is the decision.

| Purpose | Licence basis | Condition | Decision (Yes / No) |
| --- | --- | --- | --- |
| Reprojection, clipping, rasterization on the 10 m EPSG:32647 grid | (d) adaptation, modification | — | |
| Human annotation and reviewer calibration | (d) | — | |
| Model training and probability calibration | (d) | — | |
| Final evaluation and derived metrics | (d) | — | |
| Blinded reviewer display | (a), (d) | — | |
| Hosted Preview display of derivatives | (b), (c), (d) | "Contains modified Copernicus Sentinel data 2024" | |
| Downloadable derivatives | (b), (d) | same attribution | |
| Downstream decision input | not a rights question | still needs Steps 2 and 6 | |

## Signature

| Field | Value |
| --- | --- |
| Name | |
| Organisation / role | |
| Decision UTC (`YYYY-MM-DDTHH:MM:SSZ`) | |
| Evidence (signed PDF, email or message export) SHA-256 | |

Signing records permission only. It does not certify that the scene is a
fit reference; that is the Reference Authority's Step 2 decision.
