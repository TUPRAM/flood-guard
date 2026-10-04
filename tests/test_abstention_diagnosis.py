"""The arithmetic of the abstention diagnosis (plan task A1), on invented numbers only.

No file of the external data workspace is read here. The committed runs are checked in
``tests/test_a1_diagnosis_outputs.py``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import shutil

import numpy as np
import pytest

from floodguard import abstention_diagnosis as diagnosis
from floodguard import diagnosis_run

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"


# --- Between-class variance fraction ---------------------------------------------------------------------


def test_one_normal_population_gives_two_over_pi_and_stays_below_the_gate() -> None:
    assert diagnosis.GAUSSIAN_BVF_THEORY == pytest.approx(2 / math.pi)
    assert round(diagnosis.GAUSSIAN_BVF_THEORY, 3) == 0.637  # The figure plan row A1 states.
    assert diagnosis.m2_gate() == 0.72
    assert diagnosis.GAUSSIAN_BVF_THEORY < diagnosis.m2_gate()


def test_the_theory_value_is_what_a_large_sample_gives() -> None:
    values = np.random.default_rng(7).normal(3.0, 2.5, 2_000_000)
    low, high = values[values < values.mean()], values[values >= values.mean()]
    between = low.size / values.size * high.size / values.size * (high.mean() - low.mean()) ** 2
    assert between / values.var() == pytest.approx(diagnosis.GAUSSIAN_BVF_THEORY, abs=2e-3)


def test_clipping_at_the_kernels_percentiles_raises_the_fraction_a_little() -> None:
    clipped = diagnosis.clipped_gaussian_bvf(0.01, 0.99)
    assert diagnosis.GAUSSIAN_BVF_THEORY < clipped < diagnosis.m2_gate()
    assert clipped == pytest.approx(0.6491, abs=1e-4)
    # A clip far in the tails changes nothing.
    assert diagnosis.clipped_gaussian_bvf(1e-9, 1 - 1e-9) == pytest.approx(diagnosis.GAUSSIAN_BVF_THEORY, abs=1e-6)
    with pytest.raises(diagnosis.DiagnosisError):
        diagnosis.clipped_gaussian_bvf(0.02, 0.99)


def test_the_frozen_kernel_declines_every_window_of_pure_noise() -> None:
    rows = diagnosis.simulate_unimodal((4096, 16384), repeats=20, seed=3)
    assert [row["samples_per_window"] for row in rows] == [4096, 16384]
    for row in rows:
        assert row["windows_passing_the_gate"] == 0
        assert row["reason_counts"] == {diagnosis.UNIMODAL_REASON: 20}
        assert row["between_variance_fraction_max"] < diagnosis.m2_gate()
        assert row["between_variance_fraction_mean"] == pytest.approx(diagnosis.clipped_gaussian_bvf(), abs=0.01)
    # The same seed gives the same figures, and the result does not depend on the spread of the noise.
    assert diagnosis.simulate_unimodal((4096, 16384), repeats=20, seed=3) == rows
    wide = diagnosis.simulate_unimodal((4096,), repeats=20, seed=3, sigma_db=5.0)
    assert wide[0]["between_variance_fraction_mean"] == pytest.approx(rows[0]["between_variance_fraction_mean"], abs=1e-6)
    with pytest.raises(diagnosis.DiagnosisError):
        diagnosis.simulate_unimodal((100,), repeats=5, seed=1)


def test_two_populations_pass_the_gate_only_when_they_lie_far_apart() -> None:
    rows = diagnosis.separation_needed((0.5, 0.1), [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0], size=16384, repeats=3, seed=11)
    half, tenth = rows
    assert half["fraction_with_no_separation"] < diagnosis.m2_gate()
    assert half["first_separation_passing_the_gate"] == 3.0  # Passes between 2 and 3 standard deviations.
    assert tenth["first_separation_passing_the_gate"] == 6.0  # A small second population needs far more.
    assert tenth["first_separation_passing_the_gate"] > half["first_separation_passing_the_gate"]
    none = diagnosis.separation_needed((0.1,), [0.0, 1.0], size=16384, repeats=2, seed=11)[0]
    assert none["first_separation_passing_the_gate"] is None and none["first_separation_every_window_accepted"] is None
    rng = np.random.default_rng(1)
    for weight, separation in ((0.0, 1.0), (1.0, 1.0), (0.5, -1.0)):
        with pytest.raises(diagnosis.DiagnosisError):
            diagnosis.mixture_fraction(weight, separation, size=8192, repeats=1, rng=rng)


def test_window_fractions_are_summarised_against_the_gate() -> None:
    summary = diagnosis.summarise_fractions([0.60, 0.65, 0.70, 0.72, 0.80], gate=0.72, marks=(0.70,))
    assert summary == {"windows": 5, "windows_at_or_above_the_gate": 2, "gate": 0.72, "between_variance_fraction_min": 0.6,
                       "between_variance_fraction_median": 0.7, "between_variance_fraction_max": 0.8, "windows_at_or_above_0.70": 3}
    with pytest.raises(diagnosis.DiagnosisError):
        diagnosis.summarise_fractions([], gate=0.72)


# --- Rank statistic --------------------------------------------------------------------------------------


def test_rank_auc_is_the_share_of_pairs_ordered_the_right_way() -> None:
    # Three cells inside (scores 3, 2, 2) and two outside (2, 1): 6 pairs; wins 4, ties 2 -> (4 + 1) / 6.
    result = diagnosis.rank_auc([3.0, 2.0, 2.0, 2.0, 1.0], [True, True, True, False, False])
    assert result == {"auc": round(5 / 6, 6), "cells_inside_the_layer": 3, "cells_outside_the_layer": 2, "cells_left_out_for_no_value": 0}
    assert diagnosis.rank_auc([1, 2, 3, 4], [False, False, True, True])["auc"] == 1.0
    assert diagnosis.rank_auc([4, 3, 2, 1], [False, False, True, True])["auc"] == 0.0
    assert diagnosis.rank_auc([5, 5, 5, 5], [False, True, False, True])["auc"] == 0.5
    with_gap = diagnosis.rank_auc([1, np.nan, 3, 4], [False, True, True, True])
    assert with_gap["cells_left_out_for_no_value"] == 1 and with_gap["cells_inside_the_layer"] == 2


def test_rank_auc_matches_a_pair_count_and_scikit_learn() -> None:
    rng = np.random.default_rng(5)
    score = np.round(rng.normal(size=400), 1)  # Rounded, so that there are many ties.
    inside = rng.random(400) < 0.3
    score[inside] += 0.4
    wins = sum((a > b) + 0.5 * (a == b) for a in score[inside] for b in score[~inside])
    expected = wins / (inside.sum() * (~inside).sum())
    assert diagnosis.rank_auc(score, inside)["auc"] == pytest.approx(expected, abs=1e-6)
    metrics = pytest.importorskip("sklearn.metrics")
    assert diagnosis.rank_auc(score, inside)["auc"] == pytest.approx(metrics.roc_auc_score(inside, score), abs=1e-6)
    # Turning the feature round turns the statistic round.
    assert diagnosis.rank_auc(-score, inside)["auc"] == pytest.approx(1 - expected, abs=1e-6)


def test_rank_auc_refuses_one_sided_or_misshapen_input() -> None:
    with pytest.raises(diagnosis.DiagnosisError):
        diagnosis.rank_auc([1, 2, 3], [True, True, True])
    with pytest.raises(diagnosis.DiagnosisError):
        diagnosis.rank_auc([1, 2, 3], [True, False])
    with pytest.raises(diagnosis.DiagnosisError):
        diagnosis.rank_auc([np.nan, 2, 3], [True, False, False])


def test_separation_against_a_layer_reads_the_domain_only() -> None:
    feature = np.array([[9.0, 9.0, 1.0, 2.0], [3.0, 4.0, np.nan, 0.0]])
    inside = np.array([[True, False, False, False], [True, True, True, False]])
    domain = np.array([[False, False, True, True], [True, True, True, True]])
    result = diagnosis.separation_against_layer({"f": feature}, inside, domain)["f"]
    # In the domain: inside 3 and 4, outside 1, 2 and 0; the cell with no value is left out.
    assert result["auc"] == 1.0 and result["cells_inside_the_layer"] == 2 and result["cells_outside_the_layer"] == 3
    assert result["cells_left_out_for_no_value"] == 1
    assert result["median_inside_the_layer"] == 3.5 and result["median_outside_the_layer"] == 1.0
    with pytest.raises(diagnosis.DiagnosisError):
        diagnosis.separation_against_layer({"f": feature[:, :2]}, inside, domain)


# --- Grids -----------------------------------------------------------------------------------------------


def test_boxcar_mean_ignores_cells_with_no_value_and_cuts_the_window_at_the_edge() -> None:
    values = np.arange(25.0).reshape(5, 5)
    smooth = diagnosis.boxcar_mean(values, 3)
    assert smooth[2, 2] == pytest.approx(values[1:4, 1:4].mean())
    assert smooth[0, 2] == pytest.approx(values[:2, 1:4].mean())  # At the edge the window is cut: six of nine cells.
    assert np.isnan(smooth[0, 0])  # A corner window holds four of nine cells: half the window or less, so no value.
    holed = values.copy()
    holed[2, 2] = np.nan
    assert diagnosis.boxcar_mean(holed, 3)[2, 2] == pytest.approx((values[1:4, 1:4].sum() - 12.0) / 8)
    mostly_empty = np.full((5, 5), np.nan)
    mostly_empty[2, 2] = 1.0
    assert np.isnan(diagnosis.boxcar_mean(mostly_empty, 3)).all()
    assert np.array_equal(diagnosis.boxcar_mean(values, 1), values)
    with pytest.raises(diagnosis.DiagnosisError):
        diagnosis.boxcar_mean(values, 4)


def test_boxcar_edge_rule_needs_more_than_half_the_full_window() -> None:
    values = np.ones((5, 5))
    smooth = diagnosis.boxcar_mean(values, 5)
    # A corner window holds 9 of 25 cells: no value. An edge-centre window holds 15 of 25: a value.
    assert np.isnan(smooth[0, 0]) and smooth[0, 2] == 1.0 and smooth[2, 2] == 1.0


def test_block_mean_and_darkening() -> None:
    values = np.array([[1.0, 3.0, np.nan, np.nan], [5.0, 7.0, np.nan, 4.0]])
    assert np.array_equal(diagnosis.block_mean(values, 2), np.array([[4.0, 4.0]]))
    assert np.isnan(diagnosis.block_mean(np.full((2, 2), np.nan), 2)).all()
    with pytest.raises(diagnosis.DiagnosisError):
        diagnosis.block_mean(np.ones((3, 4)), 2)
    darkening = diagnosis.darkening_db(np.array([0.1, 0.1, 0.1, np.nan, 0.0]), np.array([0.01, 0.1, 1.0, 0.1, 0.1]))
    assert darkening[:3] == pytest.approx([10.0, 0.0, -10.0])  # Positive where the later image is darker.
    assert np.isnan(darkening[3:]).all()


def test_slope_of_a_plane() -> None:
    rows, cols = np.mgrid[0:6, 0:6]
    plane = cols * 20.0 * math.tan(math.radians(10.0))  # Rises 10 degrees towards the east.
    assert diagnosis.slope_degrees(plane, 20.0) == pytest.approx(np.full((6, 6), 10.0))
    assert diagnosis.slope_degrees(np.full((4, 4), 300.0), 20.0) == pytest.approx(np.zeros((4, 4)))
    with pytest.raises(diagnosis.DiagnosisError):
        diagnosis.slope_degrees(np.ones((1, 5)), 20.0)


# --- Passes ----------------------------------------------------------------------------------------------


def test_pass_gap_counts_distinct_passes_and_reads_the_interval_as_open() -> None:
    rows = ["2024-09-03T23:16:00.776136Z", "2024-09-03T23:16:00.776136Z", "2024-09-06T11:31:06.757356Z",
            "2024-09-15T23:16:01.675690Z", "2024-09-18T11:31:07.397843Z"]
    gap = diagnosis.pass_gap(rows, after="2024-09-06T11:31:06Z", before="2024-09-15T23:16:01Z")
    assert gap["pass_count"] == 4
    assert gap["passes"][2] == {"start_utc": "2024-09-15T23:16:01Z", "start_in_thailand": "2024-09-16 06:16 ICT"}
    assert gap["passes_strictly_inside_the_interval"] == []
    assert gap["interval_starts_at_a_pass"] and gap["interval_ends_at_a_pass"]
    assert gap["longest_gap"] == {"from_utc": "2024-09-06T11:31:06Z", "to_utc": "2024-09-15T23:16:01Z", "hours": 227.749, "days": 9.49}
    # A pass inside the interval is found; an interval that does not start at a pass says so.
    inside = diagnosis.pass_gap([*rows, "2024-09-11T23:20:00Z"], after="2024-09-06T12:00:00Z", before="2024-09-15T23:16:01Z")
    assert inside["passes_strictly_inside_the_interval"] == ["2024-09-11T23:20:00Z"] and not inside["interval_starts_at_a_pass"]
    with pytest.raises(diagnosis.DiagnosisError):
        diagnosis.pass_gap(rows, after="2024-09-15T23:16:01Z", before="2024-09-06T11:31:06Z")
    with pytest.raises(diagnosis.DiagnosisError):
        diagnosis.pass_gap(["2024-09-03 23:16"], after="2024-09-01T00:00:00Z", before="2024-09-02T00:00:00Z")


def test_share_outside() -> None:
    assert diagnosis.share_outside(15.0, 3.0) == {"share_inside": 0.2, "share_outside": 0.8}
    for total, part in ((0.0, 0.0), (10.0, -1.0), (10.0, 11.0)):
        with pytest.raises(diagnosis.DiagnosisError):
            diagnosis.share_outside(total, part)


# --- Receipts --------------------------------------------------------------------------------------------


SPEC = diagnosis_run.FigureSpec(
    figure_id="invented_figure",
    title="An invented figure",
    script="scripts/invented.py",
    plan_statement="nothing: a test",
    computes="An invented number.",
    does_not_show=("Anything real.",),
    label=diagnosis_run.ENVELOPE_LABEL,
)


@pytest.fixture()
def checkout(tmp_path: Path) -> Path:
    """A small repository root with both protocol files in force and an invented script."""

    docs = tmp_path / "docs" / "proposal_execution"
    docs.mkdir(parents=True)
    for name in ("planning_protocol_v1a.json", "planning_protocol_v1b.json", "RECEIPTS.jsonl"):
        shutil.copyfile(DOCS / name, docs / name)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "invented.py").write_text("# invented\n", encoding="ascii")
    return tmp_path


def _result(value: float) -> diagnosis_run.FigureResult:
    return diagnosis_run.FigureResult(
        figures={"value": value},
        inputs={"an_input": {"path": "scripts/invented.py", "sha256": "0" * 64}},
        parameters={"seed": 1},
        source_timestamp="invented",
        confidence_basis="Invented for a test.",
        assumptions=["Nothing here is real."],
        limits=["It says nothing."],
        plan_figure={"plan_value": 1.0, "measured": value, "reproduced": value == 1.0},
        open_points=diagnosis_run.open_points("A1-OP1"),
        not_computed=["FPPS"],
    )


def test_a_run_writes_figures_a_receipt_and_one_register_entry(checkout: Path) -> None:
    clock = iter(["2026-10-05T10:00:00Z", "2026-10-05T10:00:05Z"])
    summary = diagnosis_run.run(SPEC, lambda: _result(1.0), root=checkout, now=lambda: next(clock))
    figures_path, receipt_path, register_path = (checkout / SPEC.figures_path, checkout / SPEC.receipt_path, checkout / SPEC.register_path)
    assert SPEC.receipt_path.as_posix() == "outputs/planning_v1/a1_diagnosis_invented_figure.json"
    assert SPEC.figures_path.as_posix() == "outputs/a1_diagnosis/invented_figure.json"
    for path in (figures_path, receipt_path, register_path):
        raw = path.read_bytes()
        assert raw.endswith(b"\n") and b"\r" not in raw and raw.decode("ascii")
    receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    figures = json.loads(figures_path.read_text(encoding="ascii"))
    assert json.loads(register_path.read_text(encoding="ascii")) == {
        "path": SPEC.receipt_path.as_posix(), "sha256": diagnosis_run.sha256_file(receipt_path)}
    assert receipt["outputs"]["figures"] == {"path": SPEC.figures_path.as_posix(), "sha256": diagnosis_run.sha256_file(figures_path),
                                             "bytes": figures_path.stat().st_size}
    assert summary["receipt_sha256"] == diagnosis_run.sha256_file(receipt_path) and summary["run_kind"] == "first_run"
    # What every planning output carries (AGENTS.md; tests/test_planning_v1_outputs.py).
    protocols = {f"planning_protocol_{name}": diagnosis_run.sha256_file(DOCS / f"planning_protocol_{name}.json") for name in ("v1a", "v1b")}
    for document in (receipt, figures):
        assert document["generated_at_utc"] == "2026-10-05T10:00:05Z" and document["source_timestamp"] == "invented"
        assert document["confidence_class"] == "low" and document["confidence_basis"] and document["assumptions"]
        assert document["official_warning"] is False and document["operational_status"] == "non_operational"
        assert document["protocol_sha256"] == protocols
    assert receipt["status"] == "run_receipt" and receipt["supersedes"] is None and receipt["run_history"]["earlier_runs"] == []
    assert receipt["timestamps"] == {"run_started_at_utc": "2026-10-05T10:00:00Z", "run_finished_at_utc": "2026-10-05T10:00:05Z"}
    assert receipt["script"] == {"path": "scripts/invented.py", "sha256": diagnosis_run.sha256_file(checkout / "scripts" / "invented.py")}
    assert figures["status"] == "diagnosis_figures" and figures["figures"] == {"value": 1.0}
    assert figures["measured_against"] == "vs a season envelope, not an event map"
    assert figures["does_not_show"] == ["Anything real."] and figures["open_points"][0]["id"] == "A1-OP1"


def test_a_second_run_needs_replace_and_a_reason_and_names_the_first(checkout: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    diagnosis_run.run(SPEC, lambda: _result(1.0), root=checkout, now=lambda: "2026-10-05T10:00:00Z")
    first_receipt = diagnosis_run.sha256_file(checkout / SPEC.receipt_path)
    first_figures = diagnosis_run.sha256_file(checkout / SPEC.figures_path)
    calls: list[int] = []

    def never() -> diagnosis_run.FigureResult:
        calls.append(1)
        return _result(2.0)

    for arguments in ({}, {"replace": True}, {"replace": True, "reason": "  "}, {"reason": "why"}):
        with pytest.raises(diagnosis_run.DiagnosisRunError, match="--replace and --reason"):
            diagnosis_run.run(SPEC, never, root=checkout, **arguments)
    assert calls == [] and diagnosis_run.sha256_file(checkout / SPEC.receipt_path) == first_receipt  # Nothing was computed or written.

    external = tmp_path_factory.mktemp("external_data")
    diagnosis_run.run(SPEC, lambda: _result(2.0), root=checkout, external=external, replace=True, reason="a corrected input",
                      now=lambda: "2026-10-05T11:00:00Z")
    receipt = json.loads((checkout / SPEC.receipt_path).read_text(encoding="ascii"))
    assert receipt["run_kind"] == "superseding_run"
    assert receipt["supersedes"]["receipt_sha256"] == first_receipt and receipt["supersedes"]["figures_sha256"] == first_figures
    assert receipt["supersedes"]["reason"] == "a corrected input" and receipt["supersedes"]["figures_same"] is False
    assert receipt["run_history"]["earlier_runs"] == [{
        "generated_at_utc": "2026-10-05T10:00:00Z", "receipt_sha256": first_receipt, "figures_sha256": first_figures,
        "run_kind": "first_run", "superseded_because": "a corrected input"}]
    # The superseded pair is kept outside Git, and the register entry follows the new receipt.
    kept = sorted(path.name for path in (external / diagnosis_run.SUPERSEDED_RELATIVE_PATH).rglob("*.json"))
    assert kept == ["a1_diagnosis_invented_figure.json", "invented_figure.json"]
    assert all(label.startswith("<external_data_workspace>/") for label in receipt["supersedes"]["copies_kept"])
    assert json.loads((checkout / SPEC.register_path).read_text(encoding="ascii"))["sha256"] == diagnosis_run.sha256_file(checkout / SPEC.receipt_path)

    # A third run carries both earlier runs, and says so when the figures did not move.
    diagnosis_run.run(SPEC, lambda: _result(2.0), root=checkout, replace=True, reason="wording", now=lambda: "2026-10-05T12:00:00Z")
    third = json.loads((checkout / SPEC.receipt_path).read_text(encoding="ascii"))
    assert [run["generated_at_utc"] for run in third["run_history"]["earlier_runs"]] == ["2026-10-05T10:00:00Z", "2026-10-05T11:00:00Z"]
    assert third["supersedes"]["figures_same"] is True and third["supersedes"]["copies_kept"] == []


def test_replace_with_nothing_to_replace_is_refused(checkout: Path) -> None:
    with pytest.raises(diagnosis_run.DiagnosisRunError, match="no run to supersede"):
        diagnosis_run.run(SPEC, lambda: _result(1.0), root=checkout, replace=True, reason="why")
    assert not (checkout / SPEC.receipt_path).exists()


def test_a_run_is_refused_when_a_protocol_is_not_in_force(checkout: Path) -> None:
    from floodguard.normalisation import NormalisationError

    protocol = checkout / "docs" / "proposal_execution" / "planning_protocol_v1b.json"
    protocol.write_bytes(protocol.read_bytes() + b" ")
    calls: list[int] = []
    with pytest.raises(NormalisationError):
        diagnosis_run.run(SPEC, lambda: calls.append(1) or _result(1.0), root=checkout)
    assert calls == [] and not (checkout / "outputs").exists()


def test_verify_computes_again_and_writes_nothing(checkout: Path) -> None:
    with pytest.raises(diagnosis_run.DiagnosisRunError, match="no run to verify"):
        diagnosis_run.verify(SPEC, lambda: _result(1.0), root=checkout)
    diagnosis_run.run(SPEC, lambda: _result(1.0), root=checkout, now=lambda: "2026-10-05T10:00:00Z")
    before = {path: path.read_bytes() for path in (checkout / "outputs").rglob("*.json")}
    assert diagnosis_run.verify(SPEC, lambda: _result(1.0), root=checkout)["verified"] is True
    changed = diagnosis_run.verify(SPEC, lambda: _result(1.5), root=checkout)
    assert changed["verified"] is False and changed["figures_same"] is False and changed["inputs_same"] is True
    assert {path: path.read_bytes() for path in (checkout / "outputs").rglob("*.json")} == before
    # An edited figures file is noticed.
    (checkout / SPEC.figures_path).write_bytes((checkout / SPEC.figures_path).read_bytes() + b"\n")
    assert diagnosis_run.verify(SPEC, lambda: _result(1.0), root=checkout)["figures_file_is_the_one_the_receipt_binds"] is False


def test_the_command_line_runs_refuses_and_verifies(checkout: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def make(root: Path, external: Path | None):
        return lambda: _result(1.0)

    arguments = {"root": checkout, "description": "invented", "needs_external_data": False}
    assert diagnosis_run.command_line(SPEC, make, argv=[], **arguments) == 0
    assert diagnosis_run.command_line(SPEC, make, argv=[], **arguments) == 2  # A second run without --replace.
    assert "--replace and --reason" in capsys.readouterr().err
    assert diagnosis_run.command_line(SPEC, make, argv=["--verify"], **arguments) == 0
    assert diagnosis_run.command_line(SPEC, lambda root, external: (lambda: _result(3.0)), argv=["--verify"], **arguments) == 1
    assert diagnosis_run.command_line(SPEC, make, argv=["--replace", "--reason", "again"], **arguments) == 0
    with pytest.raises(SystemExit):
        diagnosis_run.command_line(SPEC, make, argv=[], root=checkout, description="invented", needs_external_data=True)


def test_paths_are_named_without_a_machine_path(tmp_path: Path) -> None:
    root, external = tmp_path / "repo", tmp_path / "data"
    (root / "a").mkdir(parents=True)
    (external / "b").mkdir(parents=True)
    (root / "a" / "x.txt").write_text("x", encoding="ascii")
    (external / "b" / "y.txt").write_text("y", encoding="ascii")
    assert diagnosis_run.path_label(root / "a" / "x.txt", root, external) == "a/x.txt"
    assert diagnosis_run.path_label(external / "b" / "y.txt", root, external) == "<external_data_workspace>/b/y.txt"
    assert diagnosis_run.path_label(tmp_path / "elsewhere.txt", root, external) == "elsewhere.txt"
    record = diagnosis_run.file_record(external / "b" / "y.txt", root, external, layer="l")
    assert record == {"path": "<external_data_workspace>/b/y.txt", "sha256": diagnosis_run.sha256_bytes(b"y"), "bytes": 1, "layer": "l"}
    assert diagnosis_run.external_root(None, {}) is None
    assert diagnosis_run.external_root(None, {diagnosis_run.EXTERNAL_DATA_VARIABLE: str(external)}) == external
    assert diagnosis_run.external_root(root, {diagnosis_run.EXTERNAL_DATA_VARIABLE: str(external)}) == root


def test_open_points_are_stated_as_open() -> None:
    assert sorted(diagnosis_run.OPEN_POINTS) == [f"A1-OP{number}" for number in range(1, 10)]
    for identifier, point in diagnosis_run.OPEN_POINTS.items():
        assert set(point) == {"point", "signed_files_say", "what_was_done"} and all(value.strip() for value in point.values()), identifier
    assert diagnosis_run.open_points("A1-OP2")[0]["id"] == "A1-OP2"
    assert diagnosis_run.ENVELOPE_LABEL == "vs a season envelope, not an event map"  # The label of plan row A1, word for word.
