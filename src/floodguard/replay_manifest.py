"""Evidence envelope checks for a case-replay manifest (``timeline.json``).

A replay manifest mixes three kinds of content: a model reconstruction, dated
observations shown beside it, and reported facts. AGENTS.md asks every output
for a source timestamp, a confidence and its assumptions; the replay adds an
*evidence block* per part of the manifest, so a reader can tell which lane a
figure belongs to and what it is dated.

This module holds the rules that do not depend on any one study:

* :func:`normalise_timestamp` and :func:`newest_timestamp` for ``generated_at``,
  which is never read from the machine clock (a clock value would make a
  byte-for-byte rebuild impossible);
* :func:`uncovered_blocks`, which finds manifest content no evidence block
  describes;
* :func:`evidence_problems`, the invariants a replay manifest must keep: no
  score, no action class, not an official warning, non-operational, input
  hashes present, every block with a lane and a source timestamp;
* :func:`schema_problems`, validation against the JSON schema in
  ``packages/contracts/schemas/case-replay-timeline.schema.json``.

Nothing here computes a Flood Preparedness Priority Score or an action class.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timezone
import re
from typing import Any

LANES: Mapping[str, str] = {
    "SCN": "Scenario (model): computed on the reconstructed water with stated assumptions; not an observation.",
    "OBS": "Observed: a dated measurement or image, used as provided and shown beside the model.",
    "CAL": "Calibration: an external figure used to tune the model, or known while it was tuned; agreement with it is not independent evidence.",
    "SCN-ENV": "Scenario envelope: a season-long extent used as a scenario, never as an observation for a replay day.",
    "REP": "Reported: public reporting compiled by the team; not an official register.",
    "CTX": "Context: static reference data (terrain, boundaries) with its own date.",
    "REF": "Reference: a cited source this revision has not ingested.",
}
"""Evidence lanes a replay block can sit in. ``SCN`` blocks carry the tier "T1 scenario (model)"."""

SCENARIO_TIER = "T1 scenario (model)"

BLOCK_FIELDS: tuple[str, ...] = ("id", "covers", "lane", "evidence_tier", "temporal_relation", "source_timestamp")
"""Fields every evidence block must carry."""

ENVELOPE_KEYS: frozenset[str] = frozenset({
    "study_id", "revision", "schema_version", "schema_id", "generated_by", "generated_at", "generated_at_basis", "generated_at_note",
    "git_commit", "git_commit_reason", "git_commit_lookup", "data_version", "dataset_mode", "data_mode", "operational_status",
    "official_warning", "real_time", "can_feed_decision_layer", "accepted_fpps", "accepted_action_class", "protocol_sha256",
    "protocol_sha256_reason", "permitted_use", "reason_blocked", "confidence", "confidence_class", "confidence_reason",
    "confidence_basis", "source_name", "event_time", "source_timestamp", "source_timestamp_note", "timezone", "area", "bounds",
    "lanes", "evidence_blocks", "exploratory_knowledge", "publication_eligibility", "input_sha256", "sources", "assumptions",
    "limitations", "gauge_note",
})
"""Top-level keys that describe the manifest as a whole. Every other top-level key is content and needs an evidence block."""

REQUIRED_KEYS: tuple[str, ...] = (
    "study_id", "revision", "schema_version", "generated_by", "generated_at", "generated_at_basis", "git_commit", "git_commit_reason",
    "data_version", "dataset_mode", "data_mode", "operational_status", "official_warning", "real_time", "can_feed_decision_layer",
    "accepted_fpps", "accepted_action_class", "protocol_sha256", "protocol_sha256_reason", "permitted_use", "reason_blocked",
    "confidence", "confidence_class", "confidence_reason", "confidence_basis", "source_name", "event_time", "source_timestamp",
    "source_timestamp_note", "timezone", "lanes", "evidence_blocks", "exploratory_knowledge", "publication_eligibility",
    "input_sha256", "sources", "assumptions", "limitations",
)
"""Evidence keys a replay manifest must carry (``accepted_*``, ``git_commit`` and ``protocol_sha256`` may be null, but must be present)."""

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COVER = re.compile(r"^(?P<key>[A-Za-z0-9_]+)(?:\[(?P<item>[^\]]+)\]|\.(?P<child>[A-Za-z0-9_.]+))?$")


class ReplayManifestError(ValueError):
    """Raised when a replay manifest breaks its evidence contract."""


def normalise_timestamp(value: str) -> str:
    """Return ``value`` as an ISO 8601 date-time with seconds and an explicit UTC offset.

    A bare date means midnight UTC. A date-time without an offset is refused: the reader could not tell which
    clock it is on.
    """
    text = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            moment = datetime.combine(date.fromisoformat(text), time(0, 0), tzinfo=timezone.utc)
        else:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayManifestError(f"not an ISO 8601 timestamp: {value!r}") from exc
    if moment.tzinfo is None:
        raise ReplayManifestError(f"a timestamp needs a UTC offset (for example +07:00 or Z): {value!r}")
    stamp = moment.replace(microsecond=0).isoformat()
    return stamp[:-6] + "Z" if stamp.endswith("+00:00") else stamp


def newest_timestamp(values: Iterable[str]) -> str:
    """Return the latest of ``values`` (ISO 8601 dates or date-times), normalised and compared as instants."""
    stamps = [normalise_timestamp(value) for value in values]
    if not stamps:
        raise ReplayManifestError("at least one timestamp is required")
    return max(stamps, key=lambda stamp: datetime.fromisoformat(stamp.replace("Z", "+00:00")))


def _covered(blocks: Iterable[Mapping[str, Any]]) -> tuple[set[str], set[tuple[str, str]], set[str]]:
    whole: set[str] = set()
    items: set[tuple[str, str]] = set()
    partial: set[str] = set()
    for block in blocks:
        for path in block.get("covers", ()):
            match = _COVER.match(path) if isinstance(path, str) else None
            if not match:
                raise ReplayManifestError(f"evidence block {block.get('id')!r} has a malformed covers path: {path!r}")
            if match["item"] is not None:
                items.add((match["key"], match["item"]))
            elif match["child"] is not None:
                partial.add(match["key"])
            else:
                whole.add(match["key"])
    return whole, items, partial


def uncovered_blocks(manifest: Mapping[str, Any]) -> list[str]:
    """Return the manifest content that no evidence block covers (empty when everything has a lane).

    A block covers ``"key"`` (the whole value), ``"key.child"`` (part of an object) or ``"key[id]"`` (one item of a
    list whose items carry an ``id``). A list of identified items is covered only when every item is.
    """
    whole, items, partial = _covered(manifest.get("evidence_blocks", ()))
    missing: list[str] = []
    for key, value in manifest.items():
        if key in ENVELOPE_KEYS or key in whole:
            continue
        identified = isinstance(value, list) and value and all(isinstance(item, Mapping) and "id" in item for item in value)
        if identified:
            missing.extend(f"{key}[{item['id']}]" for item in value if (key, str(item["id"])) not in items)
        elif key not in partial:
            missing.append(key)
    known = set(manifest)
    for key in sorted(whole | partial | {key for key, _ in items}):
        if key not in known:
            missing.append(f"{key} (named by an evidence block but absent)")
    for key, item in sorted(items):
        value = manifest.get(key)
        if isinstance(value, list) and not any(isinstance(row, Mapping) and str(row.get("id")) == item for row in value):
            missing.append(f"{key}[{item}] (named by an evidence block but absent)")
    return missing


def evidence_problems(manifest: Mapping[str, Any]) -> list[str]:
    """Return every way ``manifest`` breaks the replay's evidence contract (empty when it holds).

    The contract: every required key is present; no accepted score or action class; not an official warning and
    not real-time; non-operational; cannot feed the decision layer; ``confidence_class`` mirrors ``confidence``;
    ``data_mode`` mirrors ``dataset_mode``; input hashes are listed; and every piece of content sits in an evidence
    block that names its lane, tier, temporal relation and source timestamp.
    """
    problems = [f"missing key: {key}" for key in REQUIRED_KEYS if key not in manifest]
    for key in ("accepted_fpps", "accepted_action_class"):
        if manifest.get(key) is not None:
            problems.append(f"{key} must be null: the replay computes no score and no action class")
    if manifest.get("protocol_sha256") is not None:
        problems.append("protocol_sha256 must be null: the replay is not a protocol case")
    for key in ("official_warning", "real_time", "can_feed_decision_layer"):
        if manifest.get(key) is not False:
            problems.append(f"{key} must be false")
    if manifest.get("operational_status") != "non_operational":
        problems.append("operational_status must be non_operational")
    if manifest.get("confidence_class") != manifest.get("confidence"):
        problems.append("confidence_class must mirror confidence")
    if manifest.get("data_mode") != manifest.get("dataset_mode"):
        problems.append("data_mode must mirror dataset_mode")
    try:
        if "generated_at" in manifest and normalise_timestamp(str(manifest["generated_at"])) != manifest["generated_at"]:
            problems.append("generated_at must be a normalised ISO 8601 date-time with a UTC offset")
    except ReplayManifestError as exc:
        problems.append(f"generated_at: {exc}")
    inputs = manifest.get("input_sha256")
    if not isinstance(inputs, list) or not inputs:
        problems.append("input_sha256 must list at least one input")
    else:
        for row in inputs:
            if not isinstance(row, Mapping) or not _SHA256.match(str(row.get("sha256", ""))) or not row.get("path"):
                problems.append(f"input_sha256 entry needs a path and a SHA-256: {row!r}")
            elif str(row["path"]).startswith("/") or re.match(r"^[A-Za-z]:", str(row["path"])) or ".." in str(row["path"]).split("/"):
                problems.append(f"input_sha256 path must be relative to its root: {row['path']!r}")
    blocks = manifest.get("evidence_blocks")
    if not isinstance(blocks, list) or not blocks:
        problems.append("evidence_blocks must list at least one block")
        return problems
    lanes = manifest.get("lanes", {})
    seen: set[str] = set()
    for block in blocks:
        name = block.get("id") if isinstance(block, Mapping) else None
        if not isinstance(block, Mapping) or not name:
            problems.append(f"evidence block without an id: {block!r}")
            continue
        if name in seen:
            problems.append(f"evidence block id repeats: {name}")
        seen.add(name)
        for field in BLOCK_FIELDS:
            if not block.get(field):
                problems.append(f"evidence block {name} lacks {field}")
        lane = block.get("lane")
        if lane and lane not in LANES:
            problems.append(f"evidence block {name} has an unknown lane: {lane}")
        if lane and lane not in lanes:
            problems.append(f"evidence block {name} uses lane {lane}, which the manifest's lanes table does not define")
        if lane == "SCN" and block.get("evidence_tier") != SCENARIO_TIER:
            problems.append(f"evidence block {name} is a scenario and must carry the tier {SCENARIO_TIER!r}")
    try:
        problems.extend(f"no evidence block covers {path}" for path in uncovered_blocks(manifest))
    except ReplayManifestError as exc:
        problems.append(str(exc))
    return problems


def schema_problems(manifest: Mapping[str, Any], schema: Mapping[str, Any]) -> list[str]:
    """Return JSON-schema violations of ``manifest`` against ``schema`` as ``"path: message"`` lines, sorted."""
    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return sorted(f"{'/'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}" for error in validator.iter_errors(manifest))
