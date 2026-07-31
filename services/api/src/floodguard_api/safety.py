"""Fail-closed checks for values crossing the public API boundary."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_WINDOWS_ABSOLUTE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]")
_PRIVATE_POSIX_PREFIX = re.compile(
    r"(?<![A-Za-z0-9_.-])/(?:Users|home|root|tmp|var|opt|mnt|srv)(?:/|$)",
    re.IGNORECASE,
)


class PrivatePathError(ValueError):
    """Raised when a public payload contains a private absolute path."""


def assert_public_payload(value: Any) -> None:
    """Reject private absolute paths recursively without rejecting API URLs."""

    if isinstance(value, BaseModel):
        assert_public_payload(value.model_dump(mode="json"))
        return
    if isinstance(value, Path):
        raise PrivatePathError("filesystem Path objects cannot cross the API boundary")
    if isinstance(value, str):
        if _looks_like_private_absolute_path(value):
            raise PrivatePathError("public response contains a private absolute path")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            assert_public_payload(key)
            assert_public_payload(child)
        return
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        for child in value:
            assert_public_payload(child)


def _looks_like_private_absolute_path(value: str) -> bool:
    candidate = value.strip()
    return bool(
        _WINDOWS_ABSOLUTE.search(candidate)
        or "\\\\" in candidate
        or "file://" in candidate.lower()
        or _PRIVATE_POSIX_PREFIX.search(candidate)
    )
