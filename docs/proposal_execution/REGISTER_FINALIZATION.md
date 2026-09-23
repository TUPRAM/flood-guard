# Finalizing source-bound execution registers

Current state: **PARTIAL**. The 40 requirement rows and 50 acceptance rows contain evidence paths and honest PASS/PARTIAL/BLOCKED/NOT RUN decisions, but their `last_verified_sha` cells remain blank. The baseline commit `14df822e8161cef4edd253f371a89c09d0e5fac9` identifies the reviewed starting point and must **not** be copied into rows for new work. Fill only rows actually checked against a frozen new source commit after the final case packages, catalog, briefs, profiles and tests stabilize.

## Source identity rule

1. Freeze the working code, package exports and documentation in a focused branch commit. Record `git rev-parse HEAD`, `git rev-parse 'HEAD^{tree}'`, branch, `git status --porcelain=v1`, PR head/base and all input/output manifest hashes **outside Git** before any later documentation update. Preserve the ordinary checkout and unrelated dirt.
2. Run the current repository CI commands, public export/profile and browser checks **at that exact commit**. A test from the reviewed baseline or a pre-integration working tree is not a pass for the frozen source. If the source or generated public catalog changes, rerun the affected checks and use the new SHA.
3. `last_verified_sha` means *the exact commit whose source/output was verified for that individual R or AC row*. Populate a row only when its named output receipt, test and applicable review decision exist at that SHA. A BLOCKED scientific/human gate can still have technical tooling evidence, but the row stays BLOCKED and the SHA never implies acceptance. Leave `NOT RUN` rows and human-only gates blank unless a real relevant check later occurs.
4. Do not batch-fill all 90 rows. Make an explicit reviewed ID list with the corresponding test/output receipt for each row. Reopen every referenced file and verify hashes before writing an ID. If a row names an old case-package hash, regenerate it or retain that row PARTIAL with a clear comparator label.
5. Append a machine-readable release receipt **after** the commit and Preview exist. It should name the exact source SHA/tree, PR head/base, deployment URL/READY identity, profile, catalog/brief/offline hashes, commands and exit codes, dated public accessibility checks, rights/export result, limitations and human evidence. Keep the release receipt in the configured external project-support root and link its path/hash from the handoff. An append-only `RECEIPTS.jsonl` checkpoint may also point to it without replacing earlier milestones.

## Avoid a self-referential SHA

A Git commit cannot practically contain its own hash inside a tracked CSV. If a later **documentation-only** commit writes the verified code commit SHA into `last_verified_sha`, that field truthfully binds the prior tested source. The documentation commit receives a different SHA/tree and needs its own exact-source CI/Preview verification before it is described as the delivered release. Record that final deployed SHA/tree in the external post-commit receipt and final handoff. Do not set `last_verified_sha` to the documentation commit by guessing its future hash, and do not borrow the prior Preview's READY result for the new commit.

## Row-level release gates

- AC39: only PASS after the final exact source/tree root, API, runner, frontend, evidence verification, profile/CSP and meaningful browser checks are recorded; advisory dependency audit findings stay explicit.
- AC40: only PASS after the exact competition build produces a hashed ZIP, manifest replay passes and the supplied local server opens the offline case/brief routes. The second-machine check belongs to AC41 and remains NOT RUN until real rehearsal.
- AC41: only PASS when a real nontechnical comprehension response **and** another-machine offline run are recorded. Until then NOT RUN with instructions.
- AC42: only PASS for a READY competition Preview whose source SHA is confirmed and whose actual link is anonymously accessible. Production remains unchanged.
- AC43: compare the ten-minute pitch, current bilingual briefs, report, Preview and offline artifact against one frozen release. The user supplied no organizer file submission instruction, so none is made.
- AC49: only PASS when the R/AC rows, milestone status, exact resume instructions and post-commit release receipt identify the delivered source truthfully. If `last_verified_sha` cells remain blank or final release identity is missing, keep PARTIAL.
- AC50: verify no production promotion, agency message, private export, fabricated reviewer/approval, operational status or raw/restricted publication at the final Preview. Technical boundary PASS does not grant scientific acceptance.

The independent Reference Authority, Reviewer A/B, Adjudicator C, five-event custody and separate downstream decision authority remain real human/scientific gates. They cannot be closed by a successful software release or a populated `last_verified_sha` cell.
