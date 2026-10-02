"""Load, validate and gate on a FloodGuard rights record.

A rights record states which licence, attribution and change notice apply to one
external product, which owner decisions it transcribes and whether the project
owners have confirmed it. The first record is
``docs/proposal_execution/rights_basis_4009_v1.json`` (UNOSAT/GISTDA product
4009).

Nothing here is legal advice. The gate is deliberately strict: a derived layer
may be published only when the record validates *and* its
``owner_confirmation.status`` is ``"confirmed"``.

The gate recognises a product 4009 derivative in two ways, and both are by
convention rather than by content: a public folder or file whose name carries
the product (``unosat4009``, ``UNOSAT_4009``, ``unosat-4009`` ...), and a replay
manifest entry that cites the product and names a file or is marked as shown.
A derived file under another name that no manifest entry ties to the product
is not detected.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import hashlib
import json
from pathlib import Path
import re
from typing import Any

RIGHTS_BASIS_4009_PATH = Path("docs/proposal_execution/rights_basis_4009_v1.json")
"""Repository-relative path of the product 4009 rights record."""

RIGHTS_BASIS_4009_SCHEMA = "floodguard.rights_basis_4009.v1"
PUBLIC_DERIVATIVE_FOLDER = "unosat4009"
"""Folder name reserved for product 4009 derivatives under ``apps/web/public``."""

PRODUCT_4009_NAME = re.compile(r"unosat[-_ ]?4009", re.IGNORECASE)
"""A folder or file name that marks a product 4009 derivative, whatever its case or separator."""

PRODUCT_4009_CITATION = re.compile(r"(?:unosat|product)[-_ /A-Za-z]{0,20}?4009(?![0-9])", re.IGNORECASE)
"""Text that cites the product in a manifest: "unosat-4009", "UNOSAT/GISTDA product 4009", "unosat4009/envelope.png"."""

CONFIRMATION_STATUSES: tuple[str, ...] = ("pending", "confirmed")
RECORD_STATUS_BY_CONFIRMATION: dict[str, str] = {"pending": "draft_pending_owner_confirmation", "confirmed": "confirmed"}
"""The ``record_status`` each owner-confirmation status requires."""

_REQUIRED_TEXT_FIELDS: tuple[str, ...] = (
    "schema",
    "record_id",
    "source",
    "source_timestamp",
    "required_attribution_text",
    "share_alike",
    "confidence",
    "confidence_reason",
    "licence_notice_file",
)
_REQUIRED_OBJECT_FIELDS: tuple[str, ...] = (
    "product",
    "hdx",
    "archive",
    "licence",
    "provider_reply",
    "change_notice",
    "signed_decision",
    "owner_confirmation",
)
_REQUIRED_LIST_FIELDS: tuple[str, ...] = ("use_in_this_track", "limitations", "assumptions", "decision_refs")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/|\\\\)")


class RightsBasisError(ValueError):
    """Raised when a rights record is missing, malformed or incomplete."""


class RightsNotConfirmedError(RightsBasisError):
    """Raised when a rights record is valid but the owners have not confirmed it."""


def load_rights_basis(path: Path | str) -> dict[str, Any]:
    """Read a rights record from ``path`` and validate it.

    Raises :class:`RightsBasisError` when the file is absent, is not a JSON
    object or fails :func:`validate_rights_basis`.
    """
    record_path = Path(path)
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RightsBasisError(f"rights record not found: {record_path.name}") from exc
    except json.JSONDecodeError as exc:
        raise RightsBasisError(f"rights record is not valid JSON: {record_path.name}") from exc
    if not isinstance(record, dict):
        raise RightsBasisError("rights record must be a JSON object")
    validate_rights_basis(record)
    return record


def validate_rights_basis(record: Mapping[str, Any]) -> None:
    """Check that ``record`` carries every field a product 4009 derivative cites.

    The check covers the licence, attribution, change notice, archive identity,
    limits, decision references, the signers of the decision it transcribes and
    the owner-confirmation block. It never decides whether publishing is
    allowed; :func:`require_owner_confirmation` does that.
    """
    for name in _REQUIRED_TEXT_FIELDS:
        _text(record.get(name), name)
    for name in _REQUIRED_OBJECT_FIELDS:
        if not isinstance(record.get(name), Mapping):
            raise RightsBasisError(f"{name} must be an object")
    for name in _REQUIRED_LIST_FIELDS:
        _non_empty_list(record.get(name), name)
    if record["schema"] != RIGHTS_BASIS_4009_SCHEMA:
        raise RightsBasisError(f"unsupported rights record schema: {record['schema']}")
    if record["confidence"] not in ("high", "medium", "low"):
        raise RightsBasisError("confidence must be high, medium or low")

    licence = record["licence"]
    for name in ("name", "url", "legal_code_url", "version_basis"):
        _text(licence.get(name), f"licence.{name}")
    _non_empty_list(licence.get("notes"), "licence.notes")

    archive = record["archive"]
    _text(archive.get("file_name"), "archive.file_name")
    relative_path = _text(archive.get("relative_path"), "archive.relative_path")
    if _ABSOLUTE_PATH.match(relative_path) or ".." in Path(relative_path).parts:
        raise RightsBasisError("archive.relative_path must stay inside the external data root")
    if not isinstance(archive.get("sha256"), str) or not _SHA256.match(archive["sha256"]):
        raise RightsBasisError("archive.sha256 must be 64 lowercase hexadecimal characters")
    if not _is_positive_int(archive.get("bytes")):
        raise RightsBasisError("archive.bytes must be a positive integer")

    _text(record["hdx"].get("dataset_id"), "hdx.dataset_id")
    _text(record["product"].get("unosat_product_id"), "product.unosat_product_id")

    change_notice = record["change_notice"]
    _text(change_notice.get("template"), "change_notice.template")
    steps = _non_empty_list(change_notice.get("steps"), "change_notice.steps")
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            raise RightsBasisError(f"change_notice.steps[{index}] must be an object")
        _text(step.get("id"), f"change_notice.steps[{index}].id")
        _text(step.get("text"), f"change_notice.steps[{index}].text")

    reply = record["provider_reply"]
    _text(reply.get("quote"), "provider_reply.quote")
    _text(reply.get("relayed_by"), "provider_reply.relayed_by")
    _iso_date(reply.get("relayed_on"), "provider_reply.relayed_on")

    for index, item in enumerate(record["limitations"]):
        _text(item, f"limitations[{index}]")
    for index, ref in enumerate(record["decision_refs"]):
        if not isinstance(ref, Mapping):
            raise RightsBasisError(f"decision_refs[{index}] must be an object")
        _text(ref.get("id"), f"decision_refs[{index}].id")

    signed = record["signed_decision"]
    _text(signed.get("decision"), "signed_decision.decision")
    _iso_date(signed.get("signed_on"), "signed_decision.signed_on")
    signers = _names(signed.get("signers"), "signed_decision.signers")
    if len(signers) < 2:
        raise RightsBasisError("signed_decision.signers must list both signers")

    confirmation = record["owner_confirmation"]
    status = confirmation.get("status")
    if status not in CONFIRMATION_STATUSES:
        raise RightsBasisError(f"owner_confirmation.status must be one of {', '.join(CONFIRMATION_STATUSES)}")
    confirmed_by = _names(confirmation.get("confirmed_by"), "owner_confirmation.confirmed_by", allow_empty=True)
    confirmed_on = confirmation.get("confirmed_on")
    if record.get("record_status") != RECORD_STATUS_BY_CONFIRMATION[status]:
        raise RightsBasisError(f"record_status must be {RECORD_STATUS_BY_CONFIRMATION[status]} while the owner confirmation is {status}")
    if status == "pending":
        if confirmed_by or confirmed_on is not None:
            raise RightsBasisError("a pending owner confirmation must not name confirmers or a date")
        if record.get("signed_by_human") is not False or record.get("human_rights_clearance") is not False:
            raise RightsBasisError("a pending record must keep signed_by_human and human_rights_clearance false")
    else:
        missing = [name for name in signers if name not in confirmed_by]
        if missing:
            raise RightsBasisError(f"owner confirmation is missing: {', '.join(missing)}")
        _iso_date(confirmed_on, "owner_confirmation.confirmed_on")
        if record.get("signed_by_human") is not True or record.get("human_rights_clearance") is not True:
            raise RightsBasisError("a confirmed record must set signed_by_human and human_rights_clearance true")

    if record.get("official_warning") is not False:
        raise RightsBasisError("official_warning must be false")
    if record.get("operational_status") != "non_operational":
        raise RightsBasisError("operational_status must be non_operational")
    if record.get("can_feed_decision_layer") is not False:
        raise RightsBasisError("can_feed_decision_layer must be false")


def owner_confirmed(record: Mapping[str, Any]) -> bool:
    """Return ``True`` only when the owners have confirmed ``record``."""
    confirmation = record.get("owner_confirmation")
    return isinstance(confirmation, Mapping) and confirmation.get("status") == "confirmed"


def require_owner_confirmation(record: Mapping[str, Any]) -> None:
    """Raise unless ``record`` is valid and ``owner_confirmation.status`` is ``"confirmed"``.

    Call this before writing any file derived from the product into public
    files. A missing or malformed confirmation block counts as not confirmed.
    """
    if not owner_confirmed(record):
        confirmation = record.get("owner_confirmation")
        status = confirmation.get("status") if isinstance(confirmation, Mapping) else None
        raise RightsNotConfirmedError(
            f"rights record {record.get('record_id', '(no id)')} is not confirmed by the owners "
            f"(owner_confirmation.status is {status!r}); derived layers must stay out of public files"
        )
    validate_rights_basis(record)


def file_sha256(path: Path | str) -> str:
    """Return the SHA-256 of the file at ``path`` as lowercase hexadecimal."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(record: Mapping[str, Any], external_root: Path | str) -> Path:
    """Check the archive under ``external_root`` against the record's size and SHA-256.

    Returns the archive path. Raises :class:`RightsBasisError` when the file is
    absent or its size or hash differs from the record.
    """
    archive = record["archive"]
    path = Path(external_root) / archive["relative_path"]
    if not path.is_file():
        raise RightsBasisError(f"archive not found under the external data root: {archive['relative_path']}")
    size = path.stat().st_size
    if size != archive["bytes"]:
        raise RightsBasisError(f"archive size differs from the record: {size} != {archive['bytes']}")
    digest = file_sha256(path)
    if digest != archive["sha256"]:
        raise RightsBasisError(f"archive SHA-256 differs from the record: {digest}")
    return path


def public_derivative_files(public_root: Path | str, name_pattern: re.Pattern[str] = PRODUCT_4009_NAME) -> list[Path]:
    """List every file under ``public_root`` whose own name or a folder above it matches ``name_pattern`` (sorted).

    The match ignores case and the separator, so ``unosat4009/``, ``UNOSAT_4009/`` and ``unosat-4009-envelope.png``
    are all found. A derivative saved under an unrelated name is not: see :func:`unconfirmed_product_citations`.
    """
    root = Path(public_root)
    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*")
                  if path.is_file() and any(name_pattern.search(part) for part in path.relative_to(root).parts))


def unconfirmed_product_citations(manifest: Mapping[str, Any], citation: re.Pattern[str] = PRODUCT_4009_CITATION) -> list[str]:
    """Return every way a replay manifest publishes the product while its rights record is unconfirmed.

    An entry (an object at any depth) cites the product when its key, one of its own text values or one of its own
    lists of text matches ``citation``. Such an entry must not name a file (``href``) and, where it carries
    ``shown``, that must be ``false``; an evidence block or a ``publication_eligibility`` input that cites the
    product must carry ``shown: false``. Call this only while :func:`owner_confirmed` is false.
    """
    problems: list[str] = []

    def cites(key: str, node: Mapping[str, Any]) -> bool:
        if citation.search(key):
            return True
        for value in node.values():
            if isinstance(value, str) and citation.search(value):
                return True
            if isinstance(value, list) and any(isinstance(item, str) and citation.search(item) for item in value):
                return True
        return False

    def visit(value: Any, path: str, key: str, must_state_shown: bool) -> None:
        if isinstance(value, Mapping):
            if cites(key, value):
                if "href" in value:
                    problems.append(f"{path} cites product 4009 and names a file ({value['href']}) while the rights record is unconfirmed")
                if ("shown" in value or must_state_shown) and value.get("shown") is not False:
                    problems.append(f"{path} cites product 4009 and must carry shown: false while the rights record is unconfirmed")
            for child_key, child in value.items():
                visit(child, f"{path}.{child_key}", str(child_key), False)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                label = item.get("id", index) if isinstance(item, Mapping) else index
                visit(item, f"{path}[{label}]", "", must_state_shown)

    for top_key, top_value in manifest.items():
        if top_key == "evidence_blocks":
            visit(top_value, top_key, top_key, True)
        elif top_key == "publication_eligibility" and isinstance(top_value, Mapping):
            for child_key, child in top_value.items():
                visit(child, f"{top_key}.{child_key}", str(child_key), child_key == "inputs")
        else:
            visit(top_value, top_key, str(top_key), False)
    return problems


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RightsBasisError(f"{name} must be a non-empty string")
    return value


def _non_empty_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise RightsBasisError(f"{name} must be a non-empty list")
    return value


def _names(value: Any, name: str, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise RightsBasisError(f"{name} must be a list of names")
    names: Iterable[Any] = value
    for item in names:
        _text(item, name)
    if len(set(value)) != len(value):
        raise RightsBasisError(f"{name} must not repeat a name")
    return list(value)


def _iso_date(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        raise RightsBasisError(f"{name} must be a date written as YYYY-MM-DD")
    return value


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
