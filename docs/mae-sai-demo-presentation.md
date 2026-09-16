# Mae Sai historical planning demonstration

This branch presents one historical planning rehearsal at
`/command/mae-sai-demo/`. It uses the existing Python access/equity engine and
checksum-bound candidate inputs. No API server or external map service is
required for the comparison or decision record.

## Five-minute presentation

1. Open **Planning → Present the Mae Sai historical case**. Explain that this
   is a September 2024 case with low confidence, not current conditions or an
   independently validated reconstruction. Observation, source-processing,
   context-data and package-generation dates have different meanings.
2. Inspect the input identity and the selected area's normal-access shortfall
   separately from people losing access under the candidate disruption.
3. Select **Mae Sai** and **Close one candidate connection**. The registered
   hypothetical closure changes its modelled 30-minute access loss from 74
   to 172, an increase of 98. The full graph changes from 11,114 to 11,212.
   These are estimates under assumptions, not confirmed affected residents.
4. Select **Ko Chang** and **Add a candidate service location**. The existing
   engine changes its modelled loss measure from 5,794 to 4,877, a difference
   of -917. It adds a destination to both normal and disrupted networks;
   this is not a claim of 917 people rescued or confirmed shelter capacity.
   Explain that site suitability, permission, function and access need review.
5. Write a planning decision, reasoning, verification need, follow-up team and
   reviewer role. Save it as a draft or reviewed **for this exercise**. Reload
   to show local persistence, then export the saved snapshot as Markdown or
   JSON. A later save preserves the earlier snapshot.

The saved record retains the selected area and scenario, case revision,
package digest and time. JSON includes the full source package. Markdown
includes the chosen comparison, source inventory, assumptions and limitations.
Changing the active comparison does not rewrite an earlier saved decision.

## What to say about readiness

- FPPS and A–E remain the original priority context; scenarios do not recalculate
  them. Low confidence may produce Class E while verification remains important.
- The flood observation is from 2024; population and infrastructure context
  have different dates. A current context graph does not prove event-time roads.
- The scenario graph's population and access values are labelled separately
  from the previously published ADM3 priority summaries.
- A reviewed exercise record is self-described and device-local. It is not
  authenticated agency acceptance, a staff assignment, a server receipt, or a
  tamper-proof audit trail. Use role/team descriptions without personal data.
- Local reference validation, actual road/facility verification, and an
  exercise completed by an operating partner are still outstanding.
- A shared staffed intake/review workflow is a later pilot deliverable. Public
  reports also remain on the reporting device and are never automatically
  treated as flood observations or road closures.

## Reproduce and run

From this branch's repository root:

```powershell
pnpm install --frozen-lockfile
uv sync --project services/api --locked --group dev
uv run --project services/api python scripts/build_mae_sai_planning_demo.py --check
pnpm build:web
uv run python -m http.server 3127 --bind 127.0.0.1 --directory apps/web/out
```

Open `http://127.0.0.1:3127/command/mae-sai-demo/`.

The generator's check recomputes the results and compares the package with
the committed version. Change an analytical input only through a new reviewed
case revision; a newly generated package has a distinct identity and its own
device-local review history.

## Verification commands

```powershell
pnpm lint
pnpm typecheck
pnpm test:contracts
pnpm test:web
pnpm --filter @floodguard/web verify:profiles
pnpm test:offline
pnpm test:csp
pnpm --filter @floodguard/web test:mae-sai-demo
uv run --project services/api pytest services/api/tests
uv run pytest
uv run --project services/geoai-runner pytest services/geoai-runner/tests -m "not geoai_smoke"
```

Browser verification exercises scenario changes, preservation of area/scenario
identity in saved records and exports, reload persistence, failed storage,
English/Thai controls, and responsive layouts. Passing software checks does
not establish the scientific or operating-partner acceptance listed above.
