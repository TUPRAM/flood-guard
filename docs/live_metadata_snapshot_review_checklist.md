# Live Metadata Snapshot Review Checklist

Use this checklist before committing any `outputs/cdse_*_metadata.csv` file. The CDSE query workflow is metadata-only, but live snapshots still need review because row sets can change over time.

## Required Review

- [ ] The dry-run URL was inspected first with `--dry-run`.
- [ ] The exact command used to create the CSV is recorded in the commit or PR notes.
- [ ] The query profile is one of `mae_sai_2024` or `hat_yai_2025`.
- [ ] The CSV is located under `outputs/` and matches `outputs/cdse_<profile>_metadata.csv`.
- [ ] The file contains metadata rows only; no Sentinel-1 product assets were downloaded.
- [ ] The columns match the CDSE metadata contract: `acquisition_date`, `product_name`, `cdse_product_id`, `online_status`, `mission_platform_prefix`, `product_storage_type`, `candidate_role`, `query_profile`, `source_url`, and `blocker_note`.
- [ ] The row count is recorded and looks plausible for the profile window.
- [ ] At least two product IDs were spot-checked against the printed OData URL or CDSE catalogue response.
- [ ] `source_url` is present so the query can be reproduced.
- [ ] `blocker_note` still states that download was not performed and licensing/geometry blockers remain unresolved where applicable.
- [ ] No credentials, cookies, private tokens, or local absolute data paths appear in the CSV.
- [ ] The snapshot has a clear reason to be committed, such as freezing candidate products for judging or review.

## Commit Note Template

```text
CDSE metadata snapshot review:
- Profile:
- Command:
- Dry-run URL inspected: yes/no
- Output file:
- Row count:
- Product IDs spot-checked:
- Download performed: no
- Reason for committing:
```

## Non-Goals

- Do not download `.SAFE`, `.tif`, `.jp2`, `.zip`, NetCDF, GRIB, or other product assets through this workflow.
- Do not treat metadata rows as validation masks.
- Do not begin model training from metadata alone.

