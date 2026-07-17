"""Build a path-redacted FloodGuard proposal evidence manifest.

The builder does not execute test commands. It consumes JUnit XML created by
the reviewed commands in the manifest, recalculates every artifact checksum,
and validates the result against the shared JSON Schema before writing it.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Iterable, Mapping
import xml.etree.ElementTree as ET

from jsonschema import Draft202012Validator, FormatChecker


PRIVATE_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\|file://|/(?:Users|home|root|tmp|var|private)/)",
    re.IGNORECASE,
)
COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")


class EvidenceBuildError(ValueError):
    """Raised when proposal evidence is incomplete, unsafe, or inconsistent."""


def file_sha256(path: Path) -> str:
    """Return a lowercase SHA-256 for a regular file."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_junit_receipt(path: Path) -> dict[str, int | str]:
    """Reduce one JUnit XML document to the public suite receipt fields."""

    if not path.is_file():
        raise EvidenceBuildError(f"JUnit receipt does not exist: {path}")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise EvidenceBuildError(f"JUnit receipt is not valid XML: {path}") from exc

    nodes = _counting_nodes(root)
    tests = sum(_nonnegative_xml_int(node, "tests") for node in nodes)
    failures = sum(_nonnegative_xml_int(node, "failures") for node in nodes)
    errors = sum(_nonnegative_xml_int(node, "errors") for node in nodes)
    skipped = sum(_nonnegative_xml_int(node, "skipped") for node in nodes)
    if failures + errors + skipped > tests:
        raise EvidenceBuildError("JUnit counts are internally inconsistent.")
    passed = tests - failures - errors - skipped
    if failures or errors:
        result = "failed"
    elif tests:
        result = "passed"
    else:
        result = "not_run"
    return {"result": result, "passed": passed, "skipped": skipped}


def build_manifest(
    template: Mapping[str, Any],
    *,
    repository_root: Path,
    junit_by_suite: Mapping[str, Path],
    git_commit: str,
    generated_at: str,
    require_all_passed: bool = False,
) -> dict[str, Any]:
    """Re-hash artifacts and merge JUnit counts into a manifest template."""

    root = repository_root.resolve()
    if not root.is_dir():
        raise EvidenceBuildError("Repository root must be an existing directory.")
    normalized_commit = git_commit.strip().lower()
    if not COMMIT_RE.fullmatch(normalized_commit):
        raise EvidenceBuildError("git_commit must contain 7-40 lowercase hex characters.")
    _parse_timestamp(generated_at)

    payload = deepcopy(dict(template))
    payload["generated_at"] = generated_at
    payload["git_commit"] = normalized_commit

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise EvidenceBuildError("Manifest template must list at least one artifact.")
    seen_paths: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            raise EvidenceBuildError("Artifact entries must be objects.")
        relative = item.get("relative_path")
        if not isinstance(relative, str):
            raise EvidenceBuildError("Artifact relative_path must be a string.")
        if relative in seen_paths:
            raise EvidenceBuildError(f"Duplicate artifact path: {relative}")
        artifact_path = resolve_public_artifact(root, relative)
        item["sha256"] = file_sha256(artifact_path)
        seen_paths.add(relative)

    _sync_geoai_proof(payload, repository_root=root)

    suites = payload.get("test_suites")
    if not isinstance(suites, list) or not suites:
        raise EvidenceBuildError("Manifest template must list at least one test suite.")
    seen_suites: set[str] = set()
    for suite in suites:
        if not isinstance(suite, dict) or not isinstance(suite.get("name"), str):
            raise EvidenceBuildError("Test-suite entries require a string name.")
        name = suite["name"]
        if name in seen_suites:
            raise EvidenceBuildError(f"Duplicate test-suite name: {name}")
        seen_suites.add(name)
        if name in junit_by_suite:
            suite.update(parse_junit_receipt(junit_by_suite[name]))

    unknown_receipts = sorted(set(junit_by_suite) - seen_suites)
    if unknown_receipts:
        raise EvidenceBuildError(
            "JUnit receipts name suites absent from the template: "
            + ", ".join(unknown_receipts)
        )
    if require_all_passed:
        incomplete = [suite["name"] for suite in suites if suite.get("result") != "passed"]
        if incomplete:
            raise EvidenceBuildError(
                "Required proposal test suites are not all passed: " + ", ".join(incomplete)
            )
    return payload


def _sync_geoai_proof(payload: dict[str, Any], *, repository_root: Path) -> None:
    """Derive shared GeoAI proof fields from its checksum-valid public receipt."""

    artifacts = payload["artifacts"]
    proof_artifacts = [item for item in artifacts if item.get("kind") == "geoai_proof_receipt"]
    if not proof_artifacts:
        return
    if len(proof_artifacts) != 1:
        raise EvidenceBuildError("Manifest must contain exactly one GeoAI proof receipt.")
    proof_path = resolve_public_artifact(
        repository_root,
        proof_artifacts[0]["relative_path"],
    )
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceBuildError("GeoAI proof receipt is not valid JSON.") from exc
    if not isinstance(proof, dict):
        raise EvidenceBuildError("GeoAI proof receipt must be a JSON object.")
    claimed_receipt = proof.pop("receipt_payload_sha256", None)
    if not isinstance(claimed_receipt, str) or claimed_receipt != _canonical_sha256(proof):
        raise EvidenceBuildError("GeoAI proof receipt self-checksum is invalid.")

    expected_calls = [
        "geoai.utils.training.export_geotiff_tiles",
        "geoai.inference.predict_geotiff",
    ]
    if (
        proof.get("floodguard_commit") != payload.get("git_commit")
        or proof.get("proof_scope") != "synthetic_integration_only"
        or proof.get("dataset_mode") != "candidate"
        or proof.get("operational_status") != "non_operational"
        or proof.get("official_warning") is not False
        or proof.get("can_feed_decision_layer") is not False
        or proof.get("execution_mode") != "real_geoai_smoke"
        or proof.get("training_execution") != "model_construction_only"
        or proof.get("actual_geoai_calls") != expected_calls
        or proof.get("claim_boundary")
        != "Synthetic integration proof; not evidence of real flood-detection accuracy."
        or not isinstance(proof.get("reason_blocked"), str)
        or not proof["reason_blocked"].strip()
    ):
        raise EvidenceBuildError("GeoAI proof receipt is not commit-bound and fail-closed.")

    feature_stack = proof.get("feature_stack")
    probability = proof.get("probability")
    validation = proof.get("validation_checks")
    aggregation = proof.get("aggregation")
    if not all(isinstance(value, dict) for value in (feature_stack, probability, validation, aggregation)):
        raise EvidenceBuildError("GeoAI proof receipt is missing required evidence sections.")
    if not validation or any(value is not True for value in validation.values()):
        raise EvidenceBuildError(
            "GeoAI proof validation is not fail-closed because not all checks passed."
        )
    validation_status = "passed"
    aggregation_status = aggregation.get("status")
    if (
        aggregation_status != "report_only"
        or aggregation.get("eligible_for_decision_layer") is not False
        or aggregation.get("eligible_for_fpps") is not False
        or probability.get("class_index") != 1
        or probability.get("band_name") != "flood_probability_0_1"
        or probability.get("dtype") != "float32"
        or aggregation.get("sample_pixel_count") != probability.get("valid_pixel_count")
    ):
        raise EvidenceBuildError("GeoAI proof aggregation is not fail-closed.")

    thumbnail = proof.get("thumbnail")
    thumbnail_artifacts = [
        item for item in artifacts if item.get("kind") == "geoai_probability_thumbnail"
    ]
    if not isinstance(thumbnail, dict) or len(thumbnail_artifacts) != 1:
        raise EvidenceBuildError("GeoAI proof requires exactly one probability thumbnail.")
    if thumbnail.get("sha256") != thumbnail_artifacts[0].get("sha256"):
        raise EvidenceBuildError("GeoAI proof thumbnail checksum does not match the manifest.")

    payload["geoai_proof"] = {
        "geoai_version": proof.get("geoai_version"),
        "feature_stack_id": feature_stack.get("feature_stack_id"),
        "preprocessing_id": feature_stack.get("preprocessing_id"),
        "input_manifest_sha256": feature_stack.get("input_manifest_sha256"),
        "output_probability_sha256": probability.get("sha256"),
        "validation_status": validation_status,
        "aggregation_status": aggregation_status,
        "processing_allowed": proof.get("processing_allowed"),
        "can_feed_decision_layer": proof.get("can_feed_decision_layer"),
        "reason_blocked": proof.get("reason_blocked"),
    }


def resolve_public_artifact(repository_root: Path, relative_path: str) -> Path:
    """Resolve a repository-relative artifact without accepting path escape."""

    if PRIVATE_PATH_RE.search(relative_path) or "\\" in relative_path:
        raise EvidenceBuildError("Artifact paths must be public POSIX-style relative paths.")
    pure = PurePosixPath(relative_path)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise EvidenceBuildError("Artifact paths must stay within the repository.")
    candidate = (repository_root / Path(*pure.parts)).resolve()
    try:
        candidate.relative_to(repository_root)
    except ValueError as exc:
        raise EvidenceBuildError("Artifact path escapes the repository.") from exc
    if not candidate.is_file():
        raise EvidenceBuildError(f"Artifact is not a regular file: {relative_path}")
    return candidate


def validate_manifest(payload: Mapping[str, Any], schema_path: Path) -> None:
    """Validate a built proposal evidence manifest against the shared schema."""

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        details = "; ".join(
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: "
            f"{error.message}"
            for error in errors
        )
        raise EvidenceBuildError(f"Built manifest failed schema validation: {details}")


def write_manifest(payload: Mapping[str, Any], output_path: Path) -> None:
    """Atomically write canonical, human-readable evidence JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(output_path)


def _counting_nodes(root: ET.Element) -> list[ET.Element]:
    tag = root.tag.rsplit("}", 1)[-1]
    if tag == "testsuite":
        return [root]
    if tag != "testsuites":
        raise EvidenceBuildError("JUnit root element must be testsuite or testsuites.")
    if root.get("tests") is not None:
        return [root]
    direct = [child for child in root if child.tag.rsplit("}", 1)[-1] == "testsuite"]
    if not direct:
        raise EvidenceBuildError("JUnit testsuites document contains no suite counts.")
    return direct


def _nonnegative_xml_int(node: ET.Element, name: str) -> int:
    raw = node.get(name, "0")
    try:
        value = int(raw)
    except ValueError as exc:
        raise EvidenceBuildError(f"JUnit {name} count must be an integer.") from exc
    if value < 0:
        raise EvidenceBuildError(f"JUnit {name} count must be non-negative.")
    return value


def _parse_timestamp(value: str) -> None:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EvidenceBuildError("generated_at must be an RFC 3339 timestamp.") from exc
    if "T" not in value or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceBuildError("generated_at must include a time and UTC offset.")


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _git_commit(repository_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip().lower()


def _junit_mapping(values: Iterable[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        name, separator, path = value.partition("=")
        if not separator or not name.strip() or not path.strip():
            raise EvidenceBuildError("--junit values must use SUITE=PATH.")
        if name in result:
            raise EvidenceBuildError(f"Duplicate --junit suite: {name}")
        result[name] = Path(path)
    return result


def main(argv: list[str] | None = None) -> int:
    """Build a validated proposal evidence manifest from a reviewed template."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--git-commit")
    parser.add_argument("--generated-at")
    parser.add_argument("--junit", action="append", default=[], metavar="SUITE=PATH")
    parser.add_argument("--require-all-passed", action="store_true")
    args = parser.parse_args(argv)

    repository_root = args.repository_root.resolve()
    schema = args.schema or (
        repository_root / "packages/contracts/schemas/proposal-evidence.schema.json"
    )
    generated_at = args.generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    template = json.loads(args.template.read_text(encoding="utf-8"))
    manifest = build_manifest(
        template,
        repository_root=repository_root,
        junit_by_suite=_junit_mapping(args.junit),
        git_commit=args.git_commit or _git_commit(repository_root),
        generated_at=generated_at,
        require_all_passed=args.require_all_passed,
    )
    validate_manifest(manifest, schema)
    serialized = json.dumps(manifest, ensure_ascii=False, allow_nan=False)
    if PRIVATE_PATH_RE.search(serialized):
        raise EvidenceBuildError("Built manifest contains a private absolute path.")
    write_manifest(manifest, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
