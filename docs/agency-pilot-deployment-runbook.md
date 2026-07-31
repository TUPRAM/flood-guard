# Agency pilot deployment runbook

This runbook configures a bounded pilot. It does not authorize production or
official warning use. Keep the fixture/offline bundle enabled for judging and
recovery, and keep its status `non_operational`.

## 1. Prepare external services

Provision, outside the repository:

- an identity provider or credential adapter;
- a secret manager containing at least one 32-byte pilot HMAC key;
- a durable append-only audit destination;
- an independently protected audit-integrity anchor destination;
- a pilot artifact workspace with backup and access controls;
- a deployment monitor that polls health, monitoring, and data status
  independently.

Do not place keys, tokens, credentials, raw imagery, model weights, audit logs,
or acceptance receipts in Git or the browser bundle.

## 2. Configure environment variables

The service recognizes these names:

| Variable | Source | Purpose |
|---|---|---|
| `FLOODGUARD_PILOT_KEYS_JSON` | secret manager | JSON mapping of key IDs to base64-encoded key bytes |
| `FLOODGUARD_PILOT_ACTIVE_KEY_ID` | deployment config | key ID used for new credentials, receipts, and audit entries |
| `FLOODGUARD_PILOT_AUDIT_LOG` | mounted external workspace | append-only JSONL audit destination |
| `FLOODGUARD_PILOT_AUDIT_ANCHOR` | separate protected mount | HMAC anchor for exact ledger count, tail hash, and full-file digest |
| `FLOODGUARD_PILOT_ARTIFACT_ROOT` | mounted external workspace | root for retention-controlled artifacts |
| `FLOODGUARD_PILOT_RETENTION_CATALOG` | protected release evidence | current HMAC-signed retention inventory and legal-hold state |
| `FLOODGUARD_PILOT_ACCEPTANCE_RECEIPT` | mounted external workspace | optional signed acceptance receipt installed after approval |
| `FLOODGUARD_PILOT_CURRENT_ARTIFACT_MANIFEST` | mounted release evidence | current immutable artifact-manifest file, hashed by the API |
| `FLOODGUARD_PILOT_CURRENT_FIELD_VALIDATION_RECEIPT` | mounted release evidence | current field-validation receipt file, hashed by the API |
| `FLOODGUARD_PILOT_AUDIT_WRITER_MODE` | deployment config | must be `single_process` for the JSONL ledger |

Use secret references and mounted workspace aliases in deployment manifests.
Do not substitute literal key bytes or operator-specific paths into checked-in
configuration.

The bundled JSONL audit ledger is single-writer only. Run exactly one API worker
and set `FLOODGUARD_PILOT_AUDIT_WRITER_MODE=single_process`. The service rejects
a declared multi-worker configuration. Use a transactional append store with
atomic sequence allocation before scaling horizontally; a shared JSONL volume
is not a safe multi-writer design.

Before normal startup, create the empty ledger and signed genesis anchor once:

```text
uv run --project services/api python services/api/scripts/provision_audit_ledger.py \
  --ledger <external-ledger-path> --anchor <separate-anchor-path>
```

The command reads the configured HMAC keyring, refuses existing paths, writes
both files, fsyncs them, and verifies the genesis. Normal API startup never
creates or repairs them. Missing either file is an invalid audit state, including
on first boot. Protect the anchor independently (prefer immutable/WORM or a
remote integrity store); coordinated rollback of both local files by the same
privileged actor cannot be detected by a local comparison alone.

Pre-create the artifact root and `.retention-quarantine` as real non-symlink
directories on the same device. Restrict both to the API retention identity.
Generate the signed retention catalog outside request handling. It must expire
no more than 30 days after generation and include the mandatory acceptance,
audit, served-manifest, and field-validation evidence IDs. Requests contain IDs
only; never accept operator-supplied creation times, categories, paths, hashes,
or legal-hold booleans.

Generate catalog entries from the mounted objects, not placeholder files. The
audit-ledger and audit-anchor entries must name those exact configured files and
carry the role-specific binding hashes derived from their signed
`audit_instance_id`. The served manifest and field receipt entries must name the
exact configured files and carry their actual byte SHA-256 values. At bootstrap,
the acceptance entry contains the documented `not-installed` sentinel. Before
installing an accepted receipt, replace that sentinel with the exact receipt
file, update both receipt hashes, and re-sign the catalog. An identical copy at
a different path is intentionally rejected. Bootstrap readiness stable-reads
the catalog target and requires its exact bytes to equal both the sentinel and
the signed hashes; creating an arbitrary file at the expected path is not
sufficient. Manifest and field-validation checks likewise reuse one
descriptor-bound byte snapshot for retention validation, evidence parsing, and
acceptance or promotion decisions.

## 3. Start in non-operational mode

1. Start the API without an acceptance receipt.
2. Confirm `GET /api/v1/health` reports only process health.
3. Confirm `GET /api/v1/status` reports the real dataset state.
4. Confirm `GET /api/v1/pilot/readiness` reports either
   `pilot_ready_non_operational` or `pilot_not_configured` and
   `agency_operational_allowed=false`.
5. Verify `/public`, `/command`, and `/studio` still load from the offline bundle
   when the API is unavailable.

Do not continue if fixture or candidate data reports `agency_operational`.

## 4. Exercise role enforcement

For each role, use a test credential valid for no more than one hour and verify
the matrix in `agency-pilot-architecture.md`. Confirm missing, expired,
overlong, malformed, and tampered credentials receive `401`, and role
violations receive `403`.

Record only token IDs and safe subjects in the test evidence. Never paste bearer
credentials into tickets, screenshots, or logs.

## 5. Validate external persistence

1. Perform a retention dry run with a data-steward credential.
2. Confirm no file changed.
3. Attempt execution as a data steward and confirm denial.
4. Execute against disposable expired artifacts as a pilot admin using the exact
   approval phrase.
5. Confirm only listed, expired, regular files under the external root changed.
6. Simulate a target/parent substitution and confirm deletion is blocked while
   the moved object remains in quarantine for investigation.
7. Read the audit log as a pilot admin and verify `chain_valid=true` and that
   ledger count/tail/full-file digest match the external anchor.

Never run retention against the source repository, committed fixture directory,
or raw source-data archive.

## 6. Complete acceptance

1. Complete the bilingual checklist in
   `agency-pilot-acceptance-criteria.md`.
2. Complete `agency-pilot-field-validation-protocol.md` and generate an immutable
   field-validation receipt.
3. Build the strict served-response artifact manifest. For every response that
   may be promoted, record its canonical response SHA-256, exact source
   timestamp, data version, and non-empty underlying artifact ID/SHA-256 set.
   Hash the final manifest and validation receipt.
4. Submit the official-input acceptance request as a pilot admin.
5. Independently verify the returned signed receipt as an analyst.
6. Store the receipt in the external pilot workspace.
7. Install its external reference and restart or reload the API through the
   deployment controller.
8. Confirm the receipt matches the current study area and data version.
9. Confirm the API hashes both mounted current evidence files and that those
   actual byte digests exactly match the signed artifact-manifest and field-
   validation receipt digests.
10. Confirm both mounted files name the same study area, data version, and
    source timestamp; confirm the exact current status/decision response digest
    is a member of the served-response manifest; confirm the
    field receipt is still inside its maximum 30-day review window, and the
    acceptance receipt expiry is no more than 30 days after issuance.

An accepted receipt for one data version never authorizes another version.

## 7. Monitor

Monitor at least:

- `/api/v1/health` for process reachability;
- `/api/v1/status` for freshness and artifact availability;
- `/api/v1/pilot/monitoring` for identity, audit, retention, acceptance, and
  derived operational state; verify its accepted state is derived from the exact
  current `/api/v1/status` payload digest, not only study area/version fields;
- denial rates and audit-chain validity;
- acceptance and credential expiry windows;
- artifact-workspace capacity.
- retention-catalog review expiry and non-empty mandatory evidence coverage;
- private quarantine contents (any retained `.pending` object is an incident).

Alerting must preserve the difference between a healthy service, fresh data,
and accepted evidence.

## 8. Rotate keys

1. Add a new key ID to the external keyring.
2. Make it active for new signatures.
3. Retain the previous key until every unexpired credential, receipt, and audit
   entry signed by it has passed the approved retention period.
4. Verify old and new entries during the overlap.
5. Remove the old key only after a documented custody review.

Never reuse a key ID for different bytes.

## 9. Roll back or suspend

Remove the installed acceptance-receipt reference and restart the API if:

- the audit chain is invalid;
- a key or credential may be compromised;
- source provenance or licensing changes;
- field validation is withdrawn;
- monitoring cannot distinguish freshness;
- an accepted artifact is replaced or reprocessed.

After suspension, verify `agency_operational_allowed=false`; retain the audit and
acceptance evidence under legal-hold policy and continue only in planning mode.

On Windows, Python cannot make final name-based unlink atomic against a process
with the same filesystem privileges. Quarantine, identity checks, and rehashing
make substitutions fail closed in the bounded pilot, but restrictive ACLs and a
single retention writer remain mandatory. Treat any same-privilege workspace
compromise as a suspension condition.
