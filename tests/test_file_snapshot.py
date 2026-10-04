"""Cross-platform metadata guards must accept unchanged files and reject changes."""

import os

import pytest

from floodguard.controlled_experiment import (
    ControlledExperimentError,
    _assert_unchanged_snapshot,
    _read_stable_bytes,
)
from floodguard.file_snapshot import path_snapshot
from floodguard.model_promotion import _read_stable_bytes as promotion_read


def test_rewritten_file_has_comparable_descriptor_metadata(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_bytes(b"initial")
    path.write_bytes(b"replacement")
    snapshot = path_snapshot(path)
    with path.open("rb") as stream:
        descriptor = os.fstat(stream.fileno())
    assert snapshot.st_ctime_ns == descriptor.st_ctime_ns
    assert _read_stable_bytes(path, "receipt") == b"replacement"
    assert promotion_read(path, "receipt") == b"replacement"


def test_post_read_content_change_is_rejected(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_bytes(b"original")
    before = path_snapshot(path)
    path.write_bytes(b"modified and longer")
    with pytest.raises(ControlledExperimentError, match="path no longer"):
        _assert_unchanged_snapshot(path, before, before, "receipt")


def test_post_read_replacement_with_same_size_and_mtime_is_rejected(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_bytes(b"original")
    before = path_snapshot(path)
    replacement = tmp_path / "new.json"
    replacement.write_bytes(b"changed!")
    os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
    os.replace(replacement, path)
    with pytest.raises(ControlledExperimentError):
        _assert_unchanged_snapshot(path, before, before, "receipt")
