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

## Follow-ups

1. **Email C.** A person sends it to UNOSAT to confirm the CC BY-SA version for 4009.
2. **Protocol hash.** Hash protocol v1a into `RECEIPTS.jsonl` on the `codex/thai-event-selection` lineage. That happens there, not on the replay branch.
3. **Open items.** Supply the original wording of D5, D8, D10 and D14–D16, or record them as withdrawn.

## Rachmania's confirmation

_(optional: date and initials)_
