# Decision log D1–D16 (restructuring plan v2)

- Status: **Signed** for the decisions marked *Adopted* below. D5, D8, D10 and D14–D16 are still open.
- Signed: 2026-09-30 by Putu (Pram) and Rachmania.
- How it was recorded: Putu approved the 2026-09-28 draft in a Claude Code session on behalf of both signers. Claude wrote this record from that approval. Rachmania has not signed this file directly; add a confirmation line below if the team wants a direct record.
- Source: the draft decision log of 2026-09-28, built from *FloodGuard restructuring plan v2* (§8.1 task G4) and the pre-Monday prep notes. The team rule is "agents draft, humans sign".

| # | Decision | Outcome | Effect on the Mae Sai replay (`/studio/cases/mae-sai-2024/`) |
|---|---|---|---|
| D1 | POLICY_V2 applies to planning outputs only. MVP-01 is a disclosed deviation. Mueang Chiang Rai is a scope extension. | **Adopted** | Access and shelter figures stay labelled "T1 scenario (model)". `accepted_*` fields stay null. |
| D2 | Rights record for UNOSAT/GISTDA product 4009 under CC BY-SA 4.0, with attribution, ShareAlike and a change notice. | **Adopted, signed by both** | Publishing the 4009 comparison is now allowed. Any derived 4009 layer ships under CC BY-SA 4.0, carries attribution and states what was changed (clip, reprojection, rasterisation). HDX gives no licence version, so email C still asks UNOSAT to confirm it. If UNOSAT names a different version, update this record and the attribution. |
| D3 | A strict ±3-day date rule. The Aug–Oct accumulated 4009 layer is scenario-only (SCN-ENV). The 22 Oct layer is its own observed case (D3b). | **Adopted** | 4009 appears as a season envelope, never as an observation for a replay day. |
| D4 | Freeze score scaling. The flood anchor is 0.20; the team discloses that it was chosen after seeing the data, and 0.10 and 0.30 run as sensitivity checks. Exposure is share-based. Vulnerability uses national P10/P90 anchors. Permanent water comes from WorldCover. | **Adopted, with the disclosure** | None directly. Any FPPS shown later uses these anchors. |
| D5 | Not defined in the plan files. | **Open** | — |
| D6 | Whether class rules v2 (proposal §5.2 triggers) bind before v1a. | **Adopted:** v1 class rules stay binding, and v2 is reported as a predeclared secondary axis. | Any A–E class shown uses the v1 rules. v2 can appear only when labelled "secondary". |
| D7 | Case list. MUST: O1, O2, SE1, SE2 and SE2-dist. SHOULD: SE2-blind. Conditional: O4. Stretch: Hat Yai. | **Adopted** | The replay is the narrative surface for O1 and SE1. It is not a new case. |
| D8 | Not defined in the plan files. | **Open** | — |
| D8b | Participation sweeps (5, 10 and 25%) stay scenario-labelled and pitch-level only. | **Adopted (default)** | None. |
| D9 | Present from the Preview URL. | **Adopted** | Present the replay from the branch preview until PR #34 is merged and production is rebuilt. |
| D10 | Not defined in the plan files. | **Open** | — |
| D11 | Scope freeze. Stop work on Ayutthaya, the lower basin, Chaiyaphum, Phayao and extra GEOID work. | **Adopted** | Replay work stays inside Mae Sai district, plus Mueang Chiang Rai only for SE2. |
| D12 | Google Earth Engine for the UN-SPIDER extra dates (6 and 18 Sep), only if someone already has an account. | **Adopted, conditional** | Without GEE, the fallback is the 18 Sep Sentinel-1 pass on the same track as 6 Sep. It is one CDSE download of about 1.3 GB, which needs the owner's approval first. |
| D13 | Endpoint-only coincident joins in `grade_join.py` are logged. The finals contract is unchanged. | **Adopted (default)** | None. |
| D14 | Not defined in the plan files. | **Open** | — |
| D15 | Not defined in the plan files. | **Open** | — |
| D16 | Not defined in the plan files. | **Open** | — |

## Owner decisions after signing (2026-09-30)

Putu gave these in the same Claude Code session, after reading the roadmap drafted from this log.

| # | Decision | Effect |
|---|---|---|
| R1 | UNOSAT 3991 is **calibration-informed**, not independent. The 70 km² figure was known while the replay's stage keyframes were tuned. | In r3, `timeline.json` gives `unosat-3991` the role `calibration_informed_magnitude_check`. The page lists it under "Size checks (calibration-informed, not independent)". No check on the replay is labelled independent now. |
| R2 | PR #35 (`codex/policy-mentoring`, the bilingual policy page) is **brought into the replay branch and improved**, not held. | The improvements must keep to D4 (score anchors), D6 (v1 class rules binding) and D7 (the replay is not a scored case). Any priority score shown carries its tier, its method source and its anchors. |
| R3 | **Merge PR #34 into master**, so production carries the replay. | This replaces D9's "present from the Preview URL" once production is rebuilt from master. |
| R4 | **Email C was sent to UNOSAT.** UNOSAT replied "we approve the use" (relayed by Putu, 1 Oct 2026). | D2 no longer waits on the email. The reply names no licence version and no credit wording, so 4009 derivatives ship under CC BY-SA 4.0 as signed in D2, with the credit "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009". The original message is not in the repo; file it as `docs/provider_response_logging_guide.md` describes. |
| R5 | **Go-ahead of 1 Oct 2026** (Putu). Merge PR #36. Draft protocol v1a and v1b for signature. Draft the 4009 rights record. Start the replay roadmap. Review the open dependency updates. | PR #36 is merged (92d7451). The protocol drafts are not in force until both owners sign them and the hashes are in `RECEIPTS.jsonl`. No 4009 layer reaches master until the owners confirm the rights record. |

## Follow-ups

1. **Email C.** Sent; UNOSAT replied "we approve the use" (R4). File the original message.
2. **Protocol hash.** Hash protocol v1a into `RECEIPTS.jsonl` on the `codex/thai-event-selection` lineage. That happens there, not on the replay branch.
3. **Open items.** Supply the original wording of D5, D8, D10 and D14–D16, or record them as withdrawn.
4. **Rights record for 4009 (R5).** Drafted on 1 Oct 2026 as `docs/proposal_execution/rights_basis_4009_v1.json`, with a licence notice beside it. Its `owner_confirmation.status` is `pending`: both owners still have to read and confirm it. Until they do, a test keeps every 4009-derived file out of `apps/web/public`.
5. **Replay revision r4 (roadmap P2-1).** Baked on 1 Oct 2026; it replaces r3 in the tree. The manifest keeps R1's label for UNOSAT 3991 and adds a disclosure of what was used or known during tuning: GISTDA's 10 Sep figure and the 16 Sep Sentinel-1 pass were used to set keyframes, so the Sentinel-1 size comparison is labelled calibration-informed too; the VIIRS and product 4009 comparisons were computed after the keyframes were final. It carries no FPPS and no action class (`accepted_*` null, D7) and lists product 4009 as not shown. Putu still has to review the fields and approve the revision.
6. **Shelter comparison and equity null rule (roadmap P2-4, open question 6).** Built on 1 Oct 2026 with the display order the owners accepted: for each shelter set, residents with a shelter within reach before the flood, residents keeping access at the replay hour, residents newly lost out of that set's own baseline, and the modelled access cut-off hour; both ways of counting (all residents, and residents whose homes flood) are always shown and no figure ranks the sets. The Evacuation Equity Gap gives no ratio, with a reason, when a group has fewer than 50 residents or when nobody has lost access. The equity rates still divide by all residents counted in each group, as before; the card also shows how many of each group had a shelter within reach before the flood, because with that denominator the direction of the gap changes for the plan (320 of 373 proxy-vulnerable residents against 13,109 of 24,537 others at the peak). Putu still has to review the rule wording and say which denominator the ratio should use.

## Rachmania's confirmation

_(optional: date and initials)_
