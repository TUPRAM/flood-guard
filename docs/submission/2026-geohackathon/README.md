# FloodGuard GeoHackathon 2026 submission package

This directory is the reviewable source of truth for the proposal-stage
submission. It is intentionally fail-closed: the release build must not
produce a final PDF while owner-supplied identity, contact, portal, demo, or
final-verification evidence is missing.

## Current release state

- Dataset mode: `fixture_demo` and `candidate` evidence only.
- Operational status: `non_operational`.
- Official warning: `false`.
- Demonstration story: Mae Sai 2024 candidate/planning demo.
- Future transfer story: Hat Yai / Songkhla; no completed Hat Yai validation is
  claimed.
- Real three-model experiment: blocked by the signed acquisition-authority,
  qualified-reference, reviewer-calibration, spatial-holdout, and model-evidence
  gates recorded in
  `docs/validation/controlled_three_model_experiment_gate_status.md`.
- Final proposal PDF: blocked until `submission-metadata.json` and
  `evidence/test-results.json` pass strict validation.

## Package map

- `proposal.md` - authoritative, text-diffable proposal body.
- `application-form-answers.md` - concise portal-ready narrative answers.
- `submission-metadata.json` - the only source for missing team, contact,
  portal, repository-release, and demo-link fields.
- `claim-to-evidence.md` - permitted proposal claims and their evidence.
- `model-card.md` - synthetic GeoAI integration-proof model card.
- `validation-summary.md` - current validation evidence and blocked metrics.
- `bilingual-action-brief-reference.md` - safe English/Thai brief reference.
- `architecture-and-api-inventory.md` - implementation and API inventory.
- `offline-demo-instructions.md` - static and offline judging instructions.
- `../../visual-qa/proposal-stage/` - the six required responsive captures
  produced from the offline static export.
- `source/FloodGuard_GeoHackathon_2026_Proposal.docx` - retained polished
  editable source and visual design authority.
- `source/FloodGuard_GeoHackathon_2026_Proposal.pdf` - retained 12-page visual
  reference matching the editable source.
- `source/artifact.md` - measured page/style contract and final-fidelity gates.
- `evidence/proposal-evidence.json` - proposal-facing evidence manifest.
- `evidence/test-results.json` - passed tested-source verification receipt;
  overall submission release remains separately blocked on owner inputs.
- `tools/build_submission.py` - metadata validation, placeholder scan,
  preliminary draft preview, and evidence checksum validation.

## Strict release build

From the repository root:

```powershell
uv run python docs/submission/2026-geohackathon/tools/build_submission.py --check
```

`--check` is expected to fail until the owner fills every blocking field and
the final source-derived DOCX, PDF, and page-inspection receipt are checksummed
in the evidence manifest. A strict check does not render the final PDF. The
final editable document must be created from a copy of the retained polished
DOCX and rendered with Microsoft Word or LibreOffice after the source-fidelity
gates in `source/artifact.md` pass. The post-tag check also requires a clean
worktree.

For layout review before team metadata is available, build an explicitly
watermarked draft into a temporary directory:

```powershell
uv run python docs/submission/2026-geohackathon/tools/build_submission.py `
  --draft --pdf --output-dir .tmp/submission-preview
```

Draft mode never claims submission readiness and never creates the final PDF
filename. Its HTML/PDF is a preliminary layout proof, not a replacement for
the supplied polished DOCX.

## Release checklist

1. Fill `submission-metadata.json` with real owner-supplied values.
2. Commit the tested application source and record that full hash as
   `submission.repository_commit`; every test and GeoAI receipt must name that
   same tested source commit.
3. Rerun every final verification command on that clean commit and record exact
   results in `evidence/test-results.json`.
4. Regenerate and review all required route screenshots.
5. Copy the retained DOCX and apply the reviewed proposal text to the release
   copy without changing the retained source file.
6. Render the source-derived release DOCX to PDF, render every PDF page to PNG,
   and visually inspect every page.
7. Add the final DOCX, PDF, and inspection receipt to the evidence template,
   regenerate their checksums, and run `--check --pre-tag`.
8. Verify the deployed demo and offline ZIP from a clean browser with the API
   unavailable and external networking disabled.
9. Commit the proposal/evidence package, create `proposal-2026-submission-v1`
   on that packaging commit, then run `--check` again. The post-tag pass is the
   only check that declares the package release-ready.

The tested source commit may be the parent of the packaging commit. It must
exist locally and be an ancestor of the packaging commit; this avoids the
impossible requirement for a tracked receipt to contain the hash of the commit
that contains the receipt itself.

FloodGuard remains a preparedness and rapid post-event prioritization tool. It
is not an official warning system, guaranteed real-time detector, or live
evacuation navigator.
