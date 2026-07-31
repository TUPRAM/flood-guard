# Bounded agency pilot architecture

Status: implementation-ready control plane; non-operational by default
Control version: `agency-pilot-v1`

## Purpose and boundary

The agency pilot is a bounded evaluation environment for authenticated agency
staff. It does not turn FloodGuard into an official warning system, a guaranteed
real-time detector, or a live evacuation navigator. The committed fixture, a
cached snapshot, and every candidate dataset remain `non_operational`.

`agency_operational` is a derived server-side state. It is available only when
all of the following are true:

1. the current dataset is `official_input`;
2. a signed acceptance receipt is installed from an external workspace;
3. the receipt signature and payload checksum validate against a configured
   key ID;
4. the receipt is unexpired and bound to the current study area, data version,
   artifact-manifest checksum, and field-validation receipt, and the API hashes
   both current mounted evidence files and compares those actual byte digests to
   the signed values in constant time;
5. all mandatory Thai/English acceptance criteria are present;
6. the audit chain remains valid.

The Next.js interface may display a user's role or pilot readiness, but it is
never an authorization boundary. FastAPI authenticates and authorizes every
protected request again.

## Roles and server capabilities

| Role | Intended scope | Server capabilities |
|---|---|---|
| `public_viewer` | Read a bounded identity summary | session only |
| `command_viewer` | Observe deployment and data state | session, monitoring |
| `analyst` | Inspect and validate acceptance evidence | monitoring, receipt verification, operational assessment |
| `data_steward` | Plan governed artifact retention | analyst capabilities, retention dry run |
| `pilot_admin` | Perform explicitly authorized pilot administration | receipt signing, audit read, retention execute, all lower capabilities |

Roles do not inherit through client-side assumptions. The API maps each role to
an explicit capability set. A credential may contain multiple unique roles;
the server uses the union of their grants.

The artifact API also applies those capabilities conditionally at the dataset
boundary. Fixture and candidate demonstrations preserve anonymous access and
the offline fallback remains unchanged. When the repository status is
`official_input`, decision areas, layers, layer data, and briefs require
`monitoring:read` (`command_viewer` or higher); scenario execution, model-run
evidence, and data-readiness evidence require `assessment:run` (`analyst` or
higher). Sanitized process health, repository status, and study-area discovery
remain anonymous bootstrap endpoints and do not expose protected decision,
scenario, or model artifacts.

## Identity and key custody

Pilot credentials use the compact `fgp1` envelope and contain a subject, unique
token ID, role list, issue time, expiry, and key ID. FloodGuard exposes no token
issuance endpoint. An external identity adapter issues credentials, and FastAPI
verifies the keyed HMAC in constant time on every request. A credential lifetime
may not exceed one hour; a correctly signed longer-lived credential is rejected.

Key bytes are injected by the deployment secret manager. The repository,
contracts, logs, responses, and browser bundle contain only key IDs. Key
material is never written to the audit log or signed receipt.

HMAC is used here as a bounded pilot mechanism because it is available in the
Python standard library. A multi-agency deployment should replace the keyring
adapter with an externally managed asymmetric signing service while preserving
the same receipt payload and key-ID contract.

## Signed acceptance manifest

The API signs only `official_input` acceptance requests. It rejects fixture and
candidate requests before signing. The immutable payload binds:

- acceptance ID and issuer subject;
- study area and data version;
- artifact-manifest SHA-256;
- source timestamp;
- all mandatory acceptance-criterion IDs;
- `field-validation-v1` receipt SHA-256;
- issue and expiry times;
- requested state `agency_operational`.

Acceptance receipts may be valid for at most 30 days. The mounted accepted
field-validation receipt must also be inside its maximum 30-day review window.
Before signing, the API checks that both mounted evidence files are stable,
regular, non-symlink files; hashes their actual bytes; validates the strict
field receipt; and confirms that both files name the same study area and data
version and source timestamp as the request. The artifact manifest is the
strict `floodguard.served-responses.v1` contract. Every promotable response is
listed by the SHA-256 of its canonical response bytes, source timestamp, data
version, and a non-empty set of underlying artifact IDs and SHA-256 values.
An operational response with changed bytes, source time, version, or absent
manifest membership is rejected even when its acceptance receipt is valid.

The signature envelope includes `algorithm`, `key_id`, `payload_sha256`, and the
keyed authentication value. Payload, checksum, key, or signature substitution
causes verification to fail closed.

## Tamper-evident audit trail

Protected administrative actions append JSON Lines entries to an external audit
file. A separately mounted HMAC-authenticated anchor records the exact entry
count, final event hash, and full-ledger SHA-256. Both an empty ledger and its
signed genesis anchor must be explicitly provisioned before startup; the API
never silently recreates either file. Missing, empty-after-history, rolled-back,
or valid-prefix-truncated ledgers therefore fail closed across restart.
The genesis also contains a random, signed `audit_instance_id` that is preserved
on every anchor update. Retention evidence binds the live ledger and anchor to
role-specific hashes of this immutable ID, so normal audit appends do not
require re-signing the retention catalog.

Each entry contains a sequence number, the previous event hash, the new event
hash, and a keyed authentication code. Append opens one regular non-symlink
descriptor, verifies the exact pre-append bytes against the anchor, writes and
re-parses the complete post-append chain through that same descriptor, then
updates the external anchor. A path identity change before or during append is
an error and no successful security action is returned.

Authorization headers, tokens, secrets, signatures, key material, and private
absolute paths are redacted before persistence. An invalid chain changes pilot
readiness to `degraded` and blocks further audited mutation.

Every always-protected pilot authorization and every `official_input`
artifact authorization appends an action-specific `allowed` or `denied`
outcome. The record contains only the static action, required capability,
dataset mode, sanitized reason, and authenticated subject/roles. It does not
persist the request URL, query, body, bearer value, receipt signature, or local
path. Missing or invalid credentials are recorded as an anonymous request when
the ledger is configured. An authenticated protected operation is rejected if
the ledger is not configured, so a successful official-input read cannot bypass
the audit requirement. Anonymous fixture/candidate reads and the intentionally
public bootstrap endpoints are not audited.

The JSONL ledger's lock is process-local. This implementation supports exactly
one audit-writer API process. Deployment configuration with more than one
declared worker is rejected. Before multi-worker or multi-instance use, replace
`AuditLedger` with a transactional append store that provides atomic sequence
allocation and compare-and-append semantics; never share this JSONL file across
multiple writers.

The ledger and anchor must be held on independently protected storage. A
same-privilege actor that can coordinate rollback of both files may still evade
local comparison; production-grade use requires an immutable/WORM or remote
anchor with independent credentials. This bounded JSONL implementation does
not claim to defeat an administrator who controls both mounted stores.

## Retention and monitoring

Retention applies only to an existing, non-symlink external directory root, a
pre-created private `.retention-quarantine` directory on the same device, and a
stable HMAC-signed server catalog. Catalogs expire within 30 days and must cover
acceptance, audit, served-manifest, and field-validation evidence. Requests name
catalog artifact IDs only; the signed catalog supplies path, category,
creation time, legal-hold state, and expected SHA-256.

Fixed IDs and categories are insufficient. Readiness additionally requires the
catalog's audit entries to resolve to the exact configured ledger and anchor
files and match their signed audit-instance bindings. Served-manifest and field-
validation entries must resolve to the exact configured files and match their
current byte hashes. One descriptor-bound snapshot supplies the exact manifest
and field-receipt bytes for both retention validation and evidence parsing, so
the control never validates one object and later signs or promotes a substituted
path. Before acceptance signing, the acceptance catalog target is stable-read
and its exact bytes must equal the documented `not-installed` sentinel as well
as both catalog hashes, avoiding a bootstrap cycle without trusting mere path
existence. Agency promotion additionally requires the entry to resolve to the
exact installed receipt file and match its current bytes. An identical copy at
a different path, a dummy file, or a substituted binding hash does not satisfy
readiness.

Execution moves an eligible file into the private quarantine, verifies object
identity, bytes, and directory identities again, then removes it. A detected
swap is reported as blocked and the quarantined file is preserved. Python on
Windows does not expose a kernel-atomic directory-descriptor unlink primitive;
the bounded pilot therefore also requires restrictive workspace ACLs and a
single retention writer. A same-privilege process able to mutate the private
quarantine between final verification and unlink remains outside this local
control's guarantee.

Monitoring reports separately:

- service/control health;
- deployment configuration;
- identity configuration;
- audit-chain integrity;
- retention configuration;
- acceptance-receipt state;
- data freshness and source timestamp;
- derived operational status.

A stale or unavailable dataset does not falsely make the API process unhealthy,
and a healthy process does not imply fresh or accepted data.
Monitoring passes the exact current status response through the same manifest-
membership check used by readiness. Study-area and data-version metadata alone
cannot produce an `agency_operational` monitoring result.

## API surface

- `GET /api/v1/pilot/readiness` — public for fixture/candidate state; command
  viewer or higher for `official_input`, always sanitized and without identity
  data;
- `GET /api/v1/pilot/session` — any authenticated pilot role;
- `GET /api/v1/pilot/monitoring` — command viewer or higher;
- `POST /api/v1/pilot/acceptance-receipts` — pilot admin;
- `POST /api/v1/pilot/acceptance-receipts/verify` — analyst or higher;
- `POST /api/v1/pilot/operational-assessments` — analyst or higher;
- `GET /api/v1/pilot/audit-log` — pilot admin;
- `POST /api/v1/pilot/retention` — steward dry run or admin execute.

## Fail-closed conditions

Missing, malformed, future-dated, expired, tampered, or unknown-key credentials
are rejected. Missing or mismatched acceptance evidence produces
`non_operational` or `planning_only`. Offline cached state is downgraded to
`non_operational`, even if its last online receipt was accepted, because the
browser cannot revalidate server-side key, expiry, or audit state.

If the deployment has not supplied regular, non-symlink current artifact-
manifest and field-validation receipt files, response-level promotion is
rejected even when a previously signed receipt is installed. Digest-only
environment claims are not accepted for agency-operation promotion.
