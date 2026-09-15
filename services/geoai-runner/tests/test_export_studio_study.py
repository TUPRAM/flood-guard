"""Network-free tests for public export identity and disclosure boundaries."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_SPEC = spec_from_file_location(
    "export_studio_study", Path(__file__).parents[1] / "scripts/export_studio_study.py"
)
assert _SPEC and _SPEC.loader
export = module_from_spec(_SPEC)
_SPEC.loader.exec_module(export)


def test_public_path_conversion_retains_relative_lineage(tmp_path):
    value = {"checkpoint": str(tmp_path / "outputs/model.pth"),
             "source": "https://registry.opendata.aws/c2smsfloods/", "iou": 0.45}
    result = export.public_safe(value, tmp_path)
    assert result == {**value, "checkpoint": "outputs/model.pth"}
    assert value["checkpoint"] != result["checkpoint"]


@pytest.mark.parametrize("value", [
    "C:/OtherPrivateWorkspace/model.pth", "file:///tmp/private", "//server/private",
    "https://example.com/data?sig=secret", "https://user:password@example.com/file",
])
def test_private_paths_and_authenticated_urls_fail_closed(value, tmp_path):
    with pytest.raises(ValueError):
        export.public_safe({"nested": [value]}, tmp_path)


def test_source_hash_and_length_both_bind_download(tmp_path):
    body = b'{"metric":0.3}'
    (tmp_path / "report.json").write_bytes(body)
    exporter = export.Exporter(tmp_path)
    expected = {"bytes": len(body), "sha256": export.digest(body)}
    assert exporter.read("report.json", expected) == {"metric": 0.3}
    (tmp_path / "report.json").write_bytes(b'{"metric":0.4}')
    with pytest.raises(ValueError, match="receipt mismatch"):
        exporter.read("report.json", expected)
    with pytest.raises(ValueError, match="inside the experiment root"):
        exporter.read("../report.json")


def test_exported_hash_is_distinct_from_original_serialization(tmp_path):
    (tmp_path / "report.json").write_text('{ "metric": 0.3 }', encoding="utf-8")
    exporter = export.Exporter(tmp_path)
    value, asset = exporter.download("report.json", "report.json")
    assert value["metric"] == 0.3
    assert asset["source_sha256"] != asset["sha256"]
    assert export.digest(exporter.files["downloads/report.json"]) == asset["sha256"]


def test_identical_release_is_idempotent_and_conflict_does_not_write(tmp_path):
    files = {"manifest.json": b"{}\n", "models/detail.json": b'{"iou":0.4}\n'}
    export.write_release(files, tmp_path)
    before = {name: (tmp_path / name).stat().st_mtime_ns for name in files}
    export.write_release(files, tmp_path)
    assert before == {name: (tmp_path / name).stat().st_mtime_ns for name in files}
    with pytest.raises(ValueError, match="Immutable revision"):
        export.write_release({"new.json": b"{}", "manifest.json": b"different"}, tmp_path)
    assert not (tmp_path / "new.json").exists()
    assert (tmp_path / "manifest.json").read_bytes() == b"{}\n"
    with pytest.raises(ValueError, match="escapes"):
        export.write_release({"../outside.json": b"{}"}, tmp_path)


def test_partition_projection_requires_complete_frozen_role_counts():
    chips = []
    event_roles = {}
    envelopes = {}
    for role, count, groups in zip(export.ROLE_PURPOSE, [443, 130, 98, 118, 111], [9, 2, 2, 2, 3], strict=True):
        for group in range(groups):
            event = f"{role}-{group}"
            event_roles[event] = role
            envelopes[event] = [1, 2, 3, 4]
            n = count // groups + (group < count % groups)
            chips.extend({"event_id": event, "scene_id": event,
                          "source_timestamp": "2020-01-01T00:00:00Z"} for _ in range(n))
    partition = {"event_roles": event_roles, "event_envelopes": envelopes}
    events, roles = export.make_events({"chips": chips}, partition)
    assert len(events) == 18
    assert [role["n_chips"] for role in roles] == [443, 130, 98, 118, 111]
    assert all(event["centroid_lon_lat"] == [2, 3] for event in events)
    partition["event_roles"]["train-0"] = "test"
    with pytest.raises(ValueError, match="role membership changed"):
        export.make_events({"chips": chips}, partition)


def test_display_index_is_bound_without_rewriting_its_bytes(tmp_path):
    value = {"study_id": export.STUDY, "revision": export.REVISION, "schema_version": 1,
             "metadata": {"official_warning": False, "can_feed_decision_layer": False,
                          "aggregation_status": "report_only"}}
    body = export.encoded(value)
    (tmp_path / "visual-index.json").write_bytes(body)
    exporter = export.Exporter(tmp_path)
    asset = exporter.existing_asset(tmp_path, "visual-index.json", "Visual index")
    assert asset["sha256"] == export.digest(body)
    assert "visual-index.json" not in exporter.files
    value["metadata"]["can_feed_decision_layer"] = True
    (tmp_path / "visual-index.json").write_bytes(export.encoded(value))
    with pytest.raises(ValueError, match="report-only"):
        exporter.existing_asset(tmp_path, "visual-index.json", "Visual index")
