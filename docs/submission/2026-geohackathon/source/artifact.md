# Proposal source-template fidelity contract

This directory retains the supplied polished proposal source unchanged. The
editable DOCX and its matching PDF are the visual authority for the final
submission; the Markdown proposal is the text-diffable content authority.

## Retained source artifacts

| Artifact | Repository-relative path | SHA-256 | Verified structure |
|---|---|---|---|
| Editable proposal source | `docs/submission/2026-geohackathon/source/FloodGuard_GeoHackathon_2026_Proposal.docx` | `6615334437814db7bc303004481db68b5ad2c7d97fff320746c1ffae4d5984e6` | 1 section, 166 body paragraphs, 13 tables |
| Supplied visual reference | `docs/submission/2026-geohackathon/source/FloodGuard_GeoHackathon_2026_Proposal.pdf` | `fe56037edae41fce08d47d60ac9526d4a881de06028ac398d0abbf7d7ac709d7` | 12 A4 pages |

The source files must never be overwritten in place. A final editor must copy
the DOCX, apply reviewed content changes to that copy, and render the resulting
release candidate to a new PDF.

## Page and style specification

- Paper: portrait A4, 8.27 by 11.69 inches.
- Margins: 0.67 inches left/right, 0.65 inches top, 0.62 inches bottom.
- Body: Aptos, 9 pt, ink `#1C2B39`, 5 pt paragraph spacing.
- Title: Aptos Display, 28 pt, bold, navy `#0B2447`.
- Level-one heading: Aptos Display, 18 pt, bold, navy `#0B2447`, kept with
  the following paragraph.
- Level-two heading: Aptos Display, 13 pt, bold, teal `#159A8C`, kept with the
  following paragraph.
- Code: Cascadia Mono, 7.5 pt, ink `#1C2B39`.
- Small note: Aptos, 8 pt, slate `#64748B`.
- Header: right-aligned `FLOODGUARD THAILAND | GEOHACKATHON 2026`, Aptos
  7.5 pt bold, teal `#159A8C`, above a fine blue-grey rule.
- Footer: page number aligned to the lower-right corner.
- Tables: navy header cells with bold white text; fine blue-grey borders;
  restrained pale alternate rows; rows kept intact where possible.
- Callouts: pale teal background with a teal left rule.
- Figures: centered at readable width with a small muted caption below.

These values were read from the retained DOCX and cross-checked against a
render of every page in the supplied PDF. Pages 1–12 were visually inspected
for hierarchy, table treatment, figure placement, header/footer continuity,
and clipping.

## Required content substitutions

The supplied source contains draft owner placeholders and older evidence
language. A release copy must replace, never conceal, each of the following:

1. Team name, institution, primary contact, and all three member records from
   owner-reviewed `submission-metadata.json`.
2. Generic or stale implementation claims with the current evidence in
   `proposal.md`, `model-card.md`, and `validation-summary.md`.
3. Any statement that implies completed GeoAI training with the precise proof
   status: tile export, model construction, inference, explicit class-1
   probability extraction, validation, and report-only aggregation. Training
   remains a wrapper/model-construction proof unless a bounded real invocation
   has its own current receipt.
4. Any real-data performance metric with `not yet measured on qualified real
   data` until every acquisition, license, reference-mask, calibration,
   checksum, and spatial-holdout gate passes.
5. Mae Sai wording with candidate/planning language. Hat Yai remains a future
   transfer/stress-test location, not completed validation.
6. Test counts, commit, proposal tag, demo URL, and portal constraints with
   values from the final clean release run and owner review.

## Final-fidelity gates

A source-derived final PDF is allowed only when all of these conditions hold:

- the original DOCX and PDF checksums above still match;
- the release DOCX is derived from a copy of the retained DOCX;
- the strict submission checker passes on the same pinned commit;
- all 12 source-informed layout patterns remain coherent in the release copy;
- the release PDF has been rendered page-by-page and visually inspected;
- no placeholder, private path, secret, unsupported live claim, or fabricated
  performance result appears;
- the release PDF, DOCX, and text mirror agree on team identity, evidence
  status, demo link, commit, and limitations.

## Current release-rendering boundary

Microsoft Word is available on the development machine, while LibreOffice is
not installed. The supplied PDF was used as the visual reference for this
source-template distillation and all 12 pages were inspected. A newly edited
release DOCX has intentionally not been created or approved because owner team
metadata, the final demo URL, portal constraints, final test receipts, pinned
commit, and proposal tag are still unavailable. Once those release inputs are
complete, Microsoft Word can render the source-derived release copy for the
required page-by-page comparison.

The HTML renderer in `tools/build_submission.py` is a preliminary, visibly
watermarked layout preview only. It cannot produce the final submission PDF.
