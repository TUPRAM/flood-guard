# THEOS-2 Usage Terms Log

This log records the project-level use status for local THEOS-2 and other hackathon-provided sample data. It does not store source imagery, private emails, or full local paths.

## Current Status

| Source | Reported permission date | Permission source | Local analysis | Derived outputs | Public demo screenshots | Redistribution of source imagery | Checksums recorded | Processing decision | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| THEOS-2 hackathon sample imagery | 2026-07-03 | project owner reported hackathon-provided data can be used freely | allowed_by_user_report | allowed_by_user_report | allowed_by_user_report | keep_original_imagery_outside_git | not_recorded | checksum_required_before_reproducible_pixel_outputs | Use for optical context, land-cover/exposure support, and future optical experiments; not a flood reference mask. |
| Other hackathon-provided local data | 2026-07-03 | project owner reported provided data can be used freely | allowed_by_user_report | allowed_by_user_report | allowed_by_user_report | keep_original_data_outside_git | not_recorded | inventory_required_before_processing | Add rows after each dataset is inventoried with file names, paths outside Git, and checksums. |

## Operating Rule

THEOS-2 can now move beyond metadata-only planning, but selected source files must be checksum-tracked before generated pixel-processing outputs are treated as reproducible artifacts. Source imagery remains outside Git. Any generated screenshots, thumbnails, map tiles, or features must be labeled non-operational and must not imply official warning status.

## Immediate Use Cases

1. Generate small optical preview thumbnails for selected samples.
2. Add optional optical context to the static dashboard.
3. Build land-cover/exposure interpretation fixtures from selected samples.
4. Prototype optical water-index or visible-water heuristics on hackathon samples.
5. Keep real flood validation and ML labels blocked until UNOSAT/UNITAR or GISTDA reference-mask terms are confirmed.
