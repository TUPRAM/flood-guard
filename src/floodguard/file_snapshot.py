"""Comparable path/descriptor metadata for immutable-file verification."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def path_snapshot(path: Path) -> os.stat_result:
    """Bind a regular path to descriptor metadata without dropping change time.

    On Windows CPython, stat and fstat can expose different st_ctime semantics.
    Comparing two descriptor snapshots preserves the change-time guard. Device,
    inode, size, mtime and birth time still bind the opened handle to the path.
    Nonregular paths are returned to the caller for its normal rejection.
    """
    before = os.stat(path, follow_symlinks=False)
    if os.name != "nt" or not stat.S_ISREG(before.st_mode):
        return before
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    descriptor = os.open(path, flags)
    try:
        value = os.fstat(descriptor)
        after = os.stat(path, follow_symlinks=False)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_birthtime_ns")
        if (
            not stat.S_ISREG(value.st_mode)
            or not stat.S_ISREG(after.st_mode)
            or any(
                getattr(before, key, None) != getattr(value, key, None)
                or getattr(value, key, None) != getattr(after, key, None)
                for key in fields
            )
        ):
            raise OSError("File path changed while capturing descriptor metadata")
        return value
    finally:
        os.close(descriptor)
