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
  describes, including a new child of an object that is covered child by child;
* :func:`score_or_class_keys`, which finds a score or action-class field at any
  depth of the manifest;
* :func:`evidence_problems`, the invariants a replay manifest must keep: no
  score, no action class, not an official warning, non-operational, input
  hashes present, every block with a lane and a source timestamp;
* :func:`shelter_plan_problems`, the rules of the shelter plan's sub-blocks: the
  capacity-aware plan, the what-if levels and the local check each need their
  own evidence block in the right lane, the capacity figures must add up, and
  no participation share or listed capacity may appear;
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

SCENARIO_FIELDS_KEY = "scenario_fields"
"""Optional block field: paths inside the covered content that hold T1 scenario (model) values placed beside it for
comparison (for example ``viirs_daily.days[].model_flood_km2_clear``). They are not in the block's own lane."""

ACCEPTED_NULL_KEYS: frozenset[str] = frozenset({"accepted_fpps", "accepted_action_class"})
"""The only score and action-class keys a replay manifest may hold: top level, both null."""

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

SHELTER_SUBBLOCK_LANES: Mapping[str, str] = {"capacitated": "SCN", "robustness": "SCN", "reported": "REP", "verification": "REP"}
"""Parts of ``shelters`` that need an evidence block of their own, and the lane it must sit in. ``shelters`` as a
whole is a scenario; reported use and a local check are reported facts and must not inherit that lane, and the
capacity-aware plan and the what-if levels carry their own temporal relation and source timestamp."""

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SWEEP_OR_LISTED_KEY = re.compile(r"participation|listed[_-]?capacit|ddpm", re.IGNORECASE)
_SCORE_OR_CLASS_KEY = re.compile(r"fpps|action[_-]?class|priority[_-]?score", re.IGNORECASE)
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


def _covered(blocks: Iterable[Mapping[str, Any]]) -> tuple[set[str], set[tuple[str, str]], dict[str, set[str]]]:
    whole: set[str] = set()
    items: set[tuple[str, str]] = set()
    partial: dict[str, set[str]] = {}
    for block in blocks:
        for path in block.get("covers", ()):
            match = _COVER.match(path) if isinstance(path, str) else None
            if not match:
                raise ReplayManifestError(f"evidence block {block.get('id')!r} has a malformed covers path: {path!r}")
            if match["item"] is not None:
                items.add((match["key"], match["item"]))
            elif match["child"] is not None:
                partial.setdefault(match["key"], set()).add(match["child"].split(".")[0])
            else:
                whole.add(match["key"])
    return whole, items, partial


def uncovered_blocks(manifest: Mapping[str, Any]) -> list[str]:
    """Return the manifest content that no evidence block covers (empty when everything has a lane).

    A block covers ``"key"`` (the whole value), ``"key.child"`` (one child of an object) or ``"key[id]"`` (one item
    of a list whose items carry an ``id``). A list of identified items is covered only when every item is, and an
    object that is covered child by child only when every one of its children is named: a child added later has
    no lane until a block names it.
    """
    whole, items, partial = _covered(manifest.get("evidence_blocks", ()))
    missing: list[str] = []
    for key, value in manifest.items():
        if key in ENVELOPE_KEYS or key in whole:
            continue
        identified = isinstance(value, list) and value and all(isinstance(item, Mapping) and "id" in item for item in value)
        if identified:
            missing.extend(f"{key}[{item['id']}]" for item in value if (key, str(item["id"])) not in items)
        elif key in partial and isinstance(value, Mapping):
            missing.extend(f"{key}.{child}" for child in value if child not in partial[key])
        else:
            missing.append(key)
    known = set(manifest)
    for key in sorted(whole | set(partial) | {key for key, _ in items}):
        if key not in known:
            missing.append(f"{key} (named by an evidence block but absent)")
    for key, children in sorted(partial.items()):
        value = manifest.get(key)
        if isinstance(value, Mapping):
            missing.extend(f"{key}.{child} (named by an evidence block but absent)" for child in sorted(children) if child not in value)
    for key, item in sorted(items):
        value = manifest.get(key)
        if isinstance(value, list) and not any(isinstance(row, Mapping) and str(row.get("id")) == item for row in value):
            missing.append(f"{key}[{item}] (named by an evidence block but absent)")
    return missing


def score_or_class_keys(value: Any, path: str = "$") -> list[str]:
    """Return the path of every key, at any depth, that names a priority score or an action class.

    The replay computes neither. The two top-level ``accepted_*`` fields are the only such keys a manifest may
    hold (and :func:`evidence_problems` requires them to be null); a nested ``accepted_fpps`` is reported too.
    """
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            here = f"{path}.{key}"
            if _SCORE_OR_CLASS_KEY.search(str(key)) and not (path == "$" and key in ACCEPTED_NULL_KEYS):
                found.append(here)
            found.extend(score_or_class_keys(item, here))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(score_or_class_keys(item, f"{path}[{index}]"))
    return found


def evidence_problems(manifest: Mapping[str, Any]) -> list[str]:
    """Return every way ``manifest`` breaks the replay's evidence contract (empty when it holds).

    The contract: every required key is present; no accepted score or action class; not an official warning and
    not real-time; non-operational; cannot feed the decision layer; ``confidence_class`` mirrors ``confidence``;
    ``data_mode`` mirrors ``dataset_mode``; input hashes are listed; no other score or action-class field exists at
    any depth; and every piece of content sits in an evidence block that names its lane, tier, temporal relation
    and source timestamp.
    """
    problems = [f"missing key: {key}" for key in REQUIRED_KEYS if key not in manifest]
    for key in ("accepted_fpps", "accepted_action_class"):
        if manifest.get(key) is not None:
            problems.append(f"{key} must be null: the replay computes no score and no action class")
    problems.extend(f"{path} is a score or action-class field: the replay computes no score and no action class"
                    for path in score_or_class_keys(manifest))
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
        if SCENARIO_FIELDS_KEY in block:
            fields = block[SCENARIO_FIELDS_KEY]
            roots = {re.split(r"[.\[]", str(path))[0] for path in block.get("covers", ())}
            if not isinstance(fields, list) or not fields or not all(isinstance(field, str) and field for field in fields):
                problems.append(f"evidence block {name}: {SCENARIO_FIELDS_KEY} must list at least one field path")
            elif any(re.split(r"[.\[]", field)[0] not in roots for field in fields):
                problems.append(f"evidence block {name}: every {SCENARIO_FIELDS_KEY} path must lie inside the content the block covers")
            elif lane == "SCN":
                problems.append(f"evidence block {name} is already a scenario; {SCENARIO_FIELDS_KEY} marks model values inside another lane")
    try:
        problems.extend(f"no evidence block covers {path}" for path in uncovered_blocks(manifest))
    except ReplayManifestError as exc:
        problems.append(str(exc))
    return problems


def sweep_or_listed_capacity_keys(value: Any, path: str = "$") -> list[str]:
    """Return the path of every key, at any depth, that names a participation share or a listed capacity.

    The replay publishes no participation sweep (decision D8b) and no capacity listed in a shelter register (the
    DDPM list): its capacities are footprint estimates, or figures a local checker reported by role.
    """
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            here = f"{path}.{key}"
            if _SWEEP_OR_LISTED_KEY.search(str(key)):
                found.append(here)
            found.extend(sweep_or_listed_capacity_keys(item, here))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(sweep_or_listed_capacity_keys(item, f"{path}[{index}]"))
    return found


def _whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def capacity_plan_problems(plan: Any, path: str = "shelters.capacitated") -> list[str]:
    """Why the figures of a capacity-aware plan do not add up (empty when they do).

    For each row of ``plan`` and ``coverage_plan`` and for each bound: a site's load never exceeds its capacity,
    the running total ``served`` grows by exactly that load, and ``overflow = demand_people - served``. The lower
    bound never counts more capacity, or serves more residents, than the upper bound. ``all_eligible`` follows the
    same rules for its totals.
    """
    if not isinstance(plan, Mapping):
        return [f"{path} is not an object"]
    demand = plan.get("demand_people")
    if not _whole(demand):
        return [f"{path}.demand_people must be a whole number of residents"]
    problems: list[str] = []

    def bounds(row: Any, where: str, keys: tuple[str, ...]) -> dict[str, Mapping[str, Any]] | None:
        found = {name: row.get(name) if isinstance(row, Mapping) else None for name in ("lower", "upper")}
        for name, bound in found.items():
            if not isinstance(bound, Mapping) or not all(_whole(bound.get(key)) for key in keys):
                problems.append(f"{where}.{name} must give {', '.join(keys)} in whole residents")
                return None
        return found  # type: ignore[return-value]

    for name in ("plan", "coverage_plan"):
        rows = plan.get(name)
        if not isinstance(rows, list):
            problems.append(f"{path}.{name} must be a list")
            continue
        served_so_far = {"lower": 0, "upper": 0}
        for index, row in enumerate(rows):
            where = f"{path}.{name}[{index}]"
            found = bounds(row, where, ("capacity", "load", "served", "overflow"))
            if found is None:
                break
            for bound_name, bound in found.items():
                if bound["load"] > bound["capacity"]:
                    problems.append(f"{where}.{bound_name}: load {bound['load']} is above capacity {bound['capacity']}")
                if bound["served"] != served_so_far[bound_name] + bound["load"]:
                    problems.append(f"{where}.{bound_name}: served must grow by the site's load")
                if bound["overflow"] != demand - bound["served"]:
                    problems.append(f"{where}.{bound_name}: overflow must equal demand_people - served")
                served_so_far[bound_name] = bound["served"]
            if found["lower"]["capacity"] > found["upper"]["capacity"]:
                problems.append(f"{where}: the lower bound counts more capacity than the upper bound")
            if found["lower"]["served"] > found["upper"]["served"]:
                problems.append(f"{where}: the lower bound serves more residents than the upper bound")
    totals = plan.get("all_eligible")
    found = bounds(totals, f"{path}.all_eligible", ("capacity", "served", "overflow"))
    if found is not None:
        for bound_name, bound in found.items():
            if bound["served"] > bound["capacity"]:
                problems.append(f"{path}.all_eligible.{bound_name}: served {bound['served']} is above capacity {bound['capacity']}")
            if bound["overflow"] != demand - bound["served"]:
                problems.append(f"{path}.all_eligible.{bound_name}: overflow must equal demand_people - served")
        if found["lower"]["capacity"] > found["upper"]["capacity"] or found["lower"]["served"] > found["upper"]["served"]:
            problems.append(f"{path}.all_eligible: the lower bound exceeds the upper bound")
    return problems


def shelter_plan_problems(manifest: Mapping[str, Any]) -> list[str]:
    """Return every way the shelter plan's sub-blocks break the evidence contract (empty when they hold).

    ``shelters`` is covered as a whole by one scenario block, so :func:`uncovered_blocks` cannot tell whether the
    capacity-aware plan, the what-if levels, the reported sites and the local check have a block of their own. This
    function requires one for each part that is present (:data:`SHELTER_SUBBLOCK_LANES`), in its lane: a local check
    filed as a scenario or as an observation is refused. It also checks the capacity figures
    (:func:`capacity_plan_problems`), that a conducted local check carries its confidence, its reason, its
    assumptions and its source timestamp, and that no participation share or listed capacity is published.
    """
    shelters = manifest.get("shelters")
    if not isinstance(shelters, Mapping):
        return []
    lanes: dict[str, list[Any]] = {}
    for block in manifest.get("evidence_blocks") or ():
        if isinstance(block, Mapping):
            for path in block.get("covers") or ():
                lanes.setdefault(str(path), []).append(block.get("lane"))
    problems: list[str] = []
    for child, lane in SHELTER_SUBBLOCK_LANES.items():
        if child not in shelters:
            continue
        found = lanes.get(f"shelters.{child}")
        if not found:
            problems.append(f"no evidence block names shelters.{child}: it needs its own block in lane {lane}")
        elif any(item != lane for item in found):
            problems.append(f"shelters.{child} must sit in lane {lane}, not {', '.join(sorted({str(item) for item in found if item != lane}))}")
    if "capacitated" in shelters:
        problems.extend(capacity_plan_problems(shelters["capacitated"]))
    check = shelters.get("verification")
    if isinstance(check, Mapping) and check.get("status") == "conducted":
        for key in ("confidence", "confidence_reason", "assumptions", "source_timestamp"):
            if not check.get(key):
                problems.append(f"shelters.verification is a conducted check and lacks {key}")
    problems.extend(f"{path} names a participation share or a listed capacity: the replay publishes neither"
                    for path in sweep_or_listed_capacity_keys(manifest))
    return problems


def schema_problems(manifest: Mapping[str, Any], schema: Mapping[str, Any]) -> list[str]:
    """Return JSON-schema violations of ``manifest`` against ``schema`` as ``"path: message"`` lines, sorted."""
    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return sorted(f"{'/'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}" for error in validator.iter_errors(manifest))
