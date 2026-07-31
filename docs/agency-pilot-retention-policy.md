# Agency pilot artifact retention policy

Policy version: `agency-pilot-retention-v1`

The policy covers files in the configured external pilot artifact root only. It
does not cover the source repository, committed fixture bundle, raw source-data
archive, or an agency's independent records system.

| Category | Minimum retention | Automatic deletion eligible |
|---|---:|---|
| `acceptance_receipt` | Indefinite | No |
| `audit_log` | Indefinite | No |
| `source_manifest` | 730 days | After window and review |
| `derived_candidate` | 90 days | After window and review |
| `temporary` | 7 days | After window and review |

Legal hold overrides every expiration. Future-dated artifacts, symbolic links,
directories, missing artifacts, absolute paths, path traversal, and paths
outside the configured root are blocked or reported without deletion.

The caller submits artifact IDs only. A stable HMAC-signed server catalog owns
the path, category, creation time, legal-hold state, and expected SHA-256. The
catalog must be generated no later than evaluation time, reviewed within a
maximum 30-day window, and contain unique non-empty evidence entries for:

- the pilot acceptance receipt or explicit pre-install sentinel;
- the configured pilot audit ledger;
- the configured pilot audit anchor;
- the current served-response artifact manifest;
- the current field-validation receipt.

An absent, expired, future-dated, malformed, non-standard JSON, tampered, empty,
or incomplete catalog makes retention unconfigured. This prevents a request
from backdating an artifact or clearing a later legal hold.

Mandatory entries are evidence bindings, not labels. Ledger and anchor entries
must resolve to those exact live files and bind their roles to the immutable,
signed `audit_instance_id`; their changing append-state bytes do not require a
new catalog signature. Manifest and field-receipt entries must resolve to the
exact configured files and match their current content hashes. The retention
check and evidence parser consume the same descriptor-bound byte snapshot; they
do not reopen a path after validating it. Agency promotion also requires the
acceptance entry to resolve to the exact installed receipt file and match its
bytes. Before a receipt exists, only the explicit `not-installed` sentinel is
valid for acceptance signing: the catalog target is stable-read and its exact
target bytes must equal the sentinel and both signed catalog hashes. Dummy
files, identical copies at other paths, and substituted content or binding
hashes fail closed.

Each category also has a server-defined namespace: `acceptance/`, `audit/`,
`source-manifests/`, `derived-candidates/`, or `temporary/`. A caller cannot
relabel a protected acceptance or audit path as temporary; a category/path
mismatch is rejected before evaluation.

## Dry run

A data steward may submit a dry run. It returns each artifact's proposed
disposition and reason but never changes a file. Dry runs are audited.

## Execute

Execution requires:

1. an authenticated `pilot_admin` credential;
2. the exact approval phrase `EXECUTE PILOT RETENTION`;
3. a valid audit chain;
4. normalized relative paths under the configured external root;
5. a current signed catalog entry whose byte digest matches the target;
6. a regular file outside legal hold and beyond its retention window.

The API evaluates the same versioned policy for dry run and execution. It does
not accept user-supplied retention-day values, paths, categories, timestamps,
hashes, or legal-hold flags. Each completed execution appends the policy
version, signed catalog digest, safe artifact IDs, and deletion count to the
audit chain.

Deletion is two-stage: atomically move the selected name into a private
same-device `.retention-quarantine`, then recheck source object identity,
directory identities, and SHA-256 before unlink. A detected swap remains
quarantined and is reported `blocked`, not deleted. The root and quarantine
must be existing non-symlink directories and the quarantine must be restricted
to the retention identity.

On Windows, Python does not expose kernel-atomic directory-descriptor unlink.
Quarantine plus rehash closes tested target and parent substitutions, but a
same-privilege process that can mutate the private quarantine between final
verification and unlink is outside this bounded control. Restrictive ACLs, one
retention writer, monitoring of `.pending` files, and suspension on workspace
compromise are mandatory.

Backups, litigation holds, incident evidence, agency-records schedules, and
secure erasure remain the deployment owner's responsibility and may only extend
retention beyond this minimum policy.
