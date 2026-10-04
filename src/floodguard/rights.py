"""Rights registry: which rights record covers an input, and what that record allows (plan row G6).

Restructuring plan v2 tracks rights per input (section 0 item 6; guardrail G31; row G6): each input has a
rights level of ``local``, ``pitch`` or ``public``, an output's level is the minimum across its lineage
(protocol v1a, guardrail ``GR6_publication_eligibility``), and only a public output may be written under
``apps/web/public/``. Rights are not an input to confidence (protocol v1a, ``confidence_rule_v1``).

This module is a thin registry over the rights records that already exist in the repository. It adds no
rights of its own and it is not legal advice:

* :data:`REGISTERED_RECORDS` names each record and the input it covers;
* :meth:`RightsRegistry.require_use` refuses any use of an input that has no registered record, or whose
  record is missing, malformed or not confirmed by the owners (signed by a human);
* :meth:`RightsRegistry.require_public_write` refuses a public write unless the record itself names what is
  written as in scope for publication;
* :func:`minimum_level` gives the level of an output from the levels of its lineage.

The product 4009 record is read and checked by :mod:`floodguard.rights_basis`, unchanged. Its
``product.layer_in_scope`` names the accumulated layer only, and decision R6 allows publication "as a season
envelope only". Every other layer of the same archive (the layer of 22 October 2024, the analysis extent) is
therefore held at ``local``: it may be read and processed outside Git, and nothing derived from it may be
written under ``apps/web/public/`` until the owners extend the record. The registry never assigns ``pitch``:
no record says what a pitch-level use is.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from floodguard import rights_basis

LOCAL_LEVEL = "local"
PITCH_LEVEL = "pitch"
PUBLIC_LEVEL = "public"
RIGHTS_LEVELS: tuple[str, ...] = (LOCAL_LEVEL, PITCH_LEVEL, PUBLIC_LEVEL)
"""The three levels of protocol v1a guardrail GR6, from the most to the least restricted."""

PRODUCT_4009 = "unosat_4009"
"""Registry key of UNOSAT/GISTDA product 4009 (archive ``FL20240912THA_GDB.zip``)."""

SENTINEL2_AUTOMATED_TRACK = "copernicus_sentinel2_l2a_automated_track"
"""Registry key of the Sentinel-2 record of the automated optical track (a legal-notice record, not signed)."""

PUBLIC_WEB_ROOT = Path("apps/web/public")
"""The only place a public output is written (protocol v1a, guardrail GR6)."""


class RightsRefusedError(rights_basis.RightsBasisError):
    """Raised when the registry refuses a use or a public write of an input."""


@dataclass(frozen=True)
class RegisteredRecord:
    """One rights record of the repository and the input it covers."""

    input_id: str
    record_path: str
    covers: str


REGISTERED_RECORDS: tuple[RegisteredRecord, ...] = (
    RegisteredRecord(
        PRODUCT_4009,
        rights_basis.RIGHTS_BASIS_4009_PATH.as_posix(),
        "UNOSAT/GISTDA product 4009 (event code FL20240912THA), every layer of the archive FL20240912THA_GDB.zip",
    ),
    RegisteredRecord(
        SENTINEL2_AUTOMATED_TRACK,
        "docs/proposal_execution/automated_track/rights_basis_v1.json",
        "Copernicus Sentinel-2 Level-2A scenes of the automated optical reference track",
    ),
)
"""The rights records that exist in the repository. An input that is not listed here has no record."""


@dataclass(frozen=True)
class RightsGrant:
    """What a confirmed rights record allows for one input (and one layer of it)."""

    input_id: str
    layer: str | None
    record_id: str
    record_path: str
    record_sha256: str
    record_schema: str
    confirmed_by: tuple[str, ...]
    confirmed_on: str | None
    licence: Mapping[str, str]
    attribution: str
    share_alike: str | None
    rights_level: str
    rights_level_basis: str

    def as_record(self) -> dict[str, Any]:
        """Return the grant as plain JSON values, for an input record or a receipt."""

        return {
            "input_id": self.input_id,
            "layer": self.layer,
            "record_id": self.record_id,
            "record_path": self.record_path,
            "record_sha256": self.record_sha256,
            "record_schema": self.record_schema,
            "record_status": "confirmed",
            "confirmed_by": list(self.confirmed_by),
            "confirmed_on": self.confirmed_on,
            "licence": dict(self.licence),
            "attribution": self.attribution,
            "share_alike": self.share_alike,
            "rights_level": self.rights_level,
            "rights_level_basis": self.rights_level_basis,
            "not_legal_advice": True,
        }


def minimum_level(levels: Iterable[str]) -> str:
    """Return the rights level of an output: the minimum across the levels of its lineage (guardrail GR6).

    Raises:
        RightsRefusedError: for an empty lineage or a value that is not one of :data:`RIGHTS_LEVELS`.
    """

    found = list(levels)
    if not found:
        raise RightsRefusedError("an output with no lineage has no rights level")
    unknown = sorted({level for level in found if level not in RIGHTS_LEVELS})
    if unknown:
        raise RightsRefusedError(f"unknown rights level: {', '.join(map(str, unknown))}")
    return min(found, key=RIGHTS_LEVELS.index)


class RightsRegistry:
    """Look up the rights record of an input and refuse what it does not allow.

    Args:
        root: The repository root the record paths are relative to.
        records: The registered records; default :data:`REGISTERED_RECORDS`.
    """

    def __init__(self, root: Path | str, records: Sequence[RegisteredRecord] = REGISTERED_RECORDS) -> None:
        self.root = Path(root)
        identifiers = [entry.input_id for entry in records]
        if len(set(identifiers)) != len(identifiers):
            raise RightsRefusedError("an input is registered twice")
        self._records = {entry.input_id: entry for entry in records}

    def input_ids(self) -> tuple[str, ...]:
        """Return the inputs that have a registered record, sorted."""

        return tuple(sorted(self._records))

    def entry(self, input_id: str) -> RegisteredRecord:
        """Return the registry entry of an input.

        Raises:
            RightsRefusedError: when no rights record is registered for the input.
        """

        if input_id not in self._records:
            raise RightsRefusedError(
                f"no rights record is registered for input {input_id!r}: it may not be used until the owners "
                "sign one and it is added to floodguard.rights.REGISTERED_RECORDS"
            )
        return self._records[input_id]

    def read_record(self, input_id: str) -> tuple[dict[str, Any], str]:
        """Read the rights record of an input and return it with the SHA-256 of its bytes.

        Raises:
            RightsRefusedError: when no record is registered, or the file is absent or not a JSON object.
        """

        entry = self.entry(input_id)
        path = self.root / entry.record_path
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise RightsRefusedError(f"the rights record of {input_id!r} is not in the repository: {entry.record_path}") from error
        except json.JSONDecodeError as error:
            raise RightsRefusedError(f"the rights record of {input_id!r} is not valid JSON: {entry.record_path}") from error
        if not isinstance(record, dict):
            raise RightsRefusedError(f"the rights record of {input_id!r} must be a JSON object")
        return record, rights_basis.file_sha256(path)

    def require_use(self, input_id: str, *, layer: str | None = None) -> RightsGrant:
        """Return what the confirmed rights record of an input allows, or refuse the use.

        Args:
            input_id: The registry key of the input.
            layer: The layer of the input that is read, where the input has layers.

        Raises:
            RightsRefusedError: when the input has no registered record, or the record is missing,
                malformed or not confirmed by the owners.
        """

        record, sha256 = self.read_record(input_id)
        entry = self.entry(input_id)
        if record.get("schema") == rights_basis.RIGHTS_BASIS_4009_SCHEMA:
            return _grant_4009(input_id, layer, record, entry.record_path, sha256)
        return _grant_generic(input_id, layer, record, entry.record_path, sha256)

    def require_public_write(self, input_id: str, *, layer: str | None = None) -> RightsGrant:
        """Return the grant for a write under ``apps/web/public/``, or refuse the write.

        A public write needs everything a use needs, and a record that itself names what is written as in
        scope for publication (rights level ``public``).

        Raises:
            RightsRefusedError: when the use is refused or the rights level is not ``public``.
        """

        grant = self.require_use(input_id, layer=layer)
        if grant.rights_level != PUBLIC_LEVEL:
            raise RightsRefusedError(
                f"input {input_id!r}{'' if layer is None else f' layer {layer!r}'} is at rights level "
                f"{grant.rights_level!r}, so nothing derived from it may be written under "
                f"{PUBLIC_WEB_ROOT.as_posix()}/: {grant.rights_level_basis}"
            )
        return grant

    def verify_source(self, grant: RightsGrant, external_root: Path | str) -> Path:
        """Check that the source file on disk is the one the rights record names, and return its path.

        Only the product 4009 record names an archive by size and SHA-256.

        Raises:
            RightsRefusedError: when the record names no archive, or the file is absent or differs.
        """

        record, sha256 = self.read_record(grant.input_id)
        if sha256 != grant.record_sha256:
            raise RightsRefusedError(f"the rights record of {grant.input_id!r} changed after the grant was read")
        if not isinstance(record.get("archive"), Mapping):
            raise RightsRefusedError(f"the rights record of {grant.input_id!r} names no source archive to verify")
        try:
            return rights_basis.verify_archive(record, external_root)
        except rights_basis.RightsBasisError as error:
            raise RightsRefusedError(str(error)) from error


def _grant_4009(input_id: str, layer: str | None, record: Mapping[str, Any], path: str, sha256: str) -> RightsGrant:
    """Build the grant of the product 4009 record, checked by :mod:`floodguard.rights_basis`."""

    try:
        rights_basis.require_owner_confirmation(record)
    except rights_basis.RightsBasisError as error:
        raise RightsRefusedError(f"input {input_id!r} may not be used: {error}") from error
    in_scope = record["product"].get("layer_in_scope")
    licence = record["licence"]
    if layer is not None and layer == in_scope:
        level = PUBLIC_LEVEL
        basis = (
            f"The confirmed record {record['record_id']} names this layer as its layer in scope. Layers derived "
            f"from it may be published under {licence['name']} with the credit and a change notice, as a "
            "season envelope only (decisions D2, D3 and R6)."
        )
    else:
        level = LOCAL_LEVEL
        basis = (
            f"The confirmed record {record['record_id']} covers the product and its archive under "
            f"{licence['name']} (decision D2), but it names only {in_scope} as its layer in scope, and decision "
            "R6 allows publication as a season envelope only. This layer is read and processed outside Git; "
            "nothing derived from it is written into public web files until the owners extend the record."
        )
    confirmation = record["owner_confirmation"]
    return RightsGrant(
        input_id=input_id,
        layer=layer,
        record_id=str(record["record_id"]),
        record_path=path,
        record_sha256=sha256,
        record_schema=str(record["schema"]),
        confirmed_by=tuple(confirmation["confirmed_by"]),
        confirmed_on=confirmation["confirmed_on"],
        licence={key: str(licence[key]) for key in ("name", "full_name", "spdx_id", "url", "legal_code_url") if key in licence},
        attribution=str(record["required_attribution_text"]),
        share_alike=str(record["share_alike"]),
        rights_level=level,
        rights_level_basis=basis,
    )


def _grant_generic(input_id: str, layer: str | None, record: Mapping[str, Any], path: str, sha256: str) -> RightsGrant:
    """Build the grant of a record of another schema: it must say that a human signed and cleared it.

    Both records of the repository carry ``signed_by_human`` and ``human_rights_clearance``. A record of a
    schema this module does not know counts as confirmed only when both are true, and it gives the ``local``
    level: no such record states what may be published.
    """

    if record.get("signed_by_human") is not True or record.get("human_rights_clearance") is not True:
        kind = record.get("rights_basis_kind", "(no kind)")
        raise RightsRefusedError(
            f"input {input_id!r} may not be used: its rights record ({kind}) is not signed by a human "
            "(signed_by_human and human_rights_clearance must both be true)"
        )
    attribution = record.get("required_attribution_text")
    if not isinstance(attribution, str) or not attribution.strip():
        raise RightsRefusedError(f"the rights record of {input_id!r} gives no required_attribution_text")
    if record.get("official_warning") is not False or record.get("can_feed_decision_layer") is not False:
        raise RightsRefusedError(f"the rights record of {input_id!r} must be non-operational and not an official warning")
    licence = record.get("licence")
    if isinstance(licence, Mapping) and isinstance(licence.get("name"), str) and licence["name"].strip():
        licence_record = {key: str(value) for key, value in licence.items() if isinstance(value, str)}
    elif isinstance(record.get("legal_notice_title"), str) and record["legal_notice_title"].strip():
        licence_record = {"name": record["legal_notice_title"], "url": str(record.get("legal_notice_url", ""))}
    else:
        raise RightsRefusedError(f"the rights record of {input_id!r} names no licence and no legal notice")
    confirmation = record.get("owner_confirmation") if isinstance(record.get("owner_confirmation"), Mapping) else {}
    return RightsGrant(
        input_id=input_id,
        layer=layer,
        record_id=str(record.get("record_id") or Path(path).stem),
        record_path=path,
        record_sha256=sha256,
        record_schema=str(record.get("schema", "")),
        confirmed_by=tuple(str(name) for name in confirmation.get("confirmed_by", ())),
        confirmed_on=confirmation.get("confirmed_on"),
        licence=licence_record,
        attribution=attribution,
        share_alike=record.get("share_alike") if isinstance(record.get("share_alike"), str) else None,
        rights_level=LOCAL_LEVEL,
        rights_level_basis=(
            "The record is signed by a human and states no publication scope, so the input is read and "
            "processed outside Git and nothing derived from it is written into public web files."
        ),
    )
