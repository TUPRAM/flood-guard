"""Diagnosis figure of plan task A1: the Sentinel-1 passes over Mae Sai in September 2024, and the gap between them.

README
======

Reads
    The committed catalogue snapshot ``outputs/cdse_mae_sai_2024_metadata.csv``: the rows the Copernicus
    Data Space catalogue returned on 8 July 2026 for Sentinel-1 IW GRDH dual-polarisation products that
    cover one point in Mae Sai (99.88 E, 20.43 N) between 1 and 25 September 2024. Metadata only: no image.

Computes
    The distinct passes in the snapshot (a pass has one row for each product made from it), their times in
    UTC and in Thailand, the track of each from its orbit number, the gaps between neighbouring passes, and
    the passes that fall strictly between 6 September 11:31 UTC and 15 September 23:16 UTC. Plan row A1
    states the figure as "no pass between 6 Sep 11:31 and 15 Sep 23:16 UTC". For context it sets two
    keyframes of the Mae Sai replay beside the passes and counts the hours between them; those keyframes
    are illustrative scenario values, written in the script as ``docs/demo/replay_numbers.md`` states them.

Does not show
    * When the flood rose or fell. The pass times say when the radar looked, not what the water did.
    * That no other satellite looked in the gap. The snapshot holds Sentinel-1 only.
    * Today's catalogue. The snapshot was not taken again: this lane makes no network request. A product
      of another mode or type would not be in it.

Writes
    ``outputs/a1_diagnosis/sentinel1_pass_gap.json``, the run receipt
    ``outputs/planning_v1/a1_diagnosis_sentinel1_pass_gap.json`` and its register entry.

Run
    ``python scripts/diagnostics/sentinel1_pass_gap.py``
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import csv
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from floodguard import abstention_diagnosis as diagnosis  # noqa: E402
from floodguard import diagnosis_run  # noqa: E402

SNAPSHOT = Path("outputs") / "cdse_mae_sai_2024_metadata.csv"
SNAPSHOT_LOG = Path("docs") / "live_metadata_snapshot_review_log.md"
INTERVAL_AFTER = "2024-09-06T11:31:06Z"
INTERVAL_BEFORE = "2024-09-15T23:16:01Z"
REPLAY_NUMBERS = Path("docs") / "demo" / "replay_numbers.md"
REPLAY_KEYFRAMES = {
    "onset_keyframe": {"utc": "2024-09-10T11:15:00Z", "in_thailand": "10 Sep 18:15 ICT", "key": "stage.onset_knot"},
    "modelled_peak_keyframe": {"utc": "2024-09-12T05:00:00Z", "in_thailand": "12 Sep 12:00 ICT", "key": "stage.peak"},
}
"""Two keyframes of the Mae Sai replay, as ``docs/demo/replay_numbers.md`` states them. They are illustrative
scenario keyframes shaped to the event chronology; no gauge record exists for September 2024."""
_ORBIT = re.compile(r"^S1A_IW_GRDH_1SDV_\d{8}T\d{6}_\d{8}T\d{6}_(\d{6})_")

SPEC = diagnosis_run.FigureSpec(
    figure_id="sentinel1_pass_gap",
    title="Sentinel-1 passes over Mae Sai in September 2024 and the gap between 6 and 15 September",
    script="scripts/diagnostics/sentinel1_pass_gap.py",
    plan_statement="S1 metadata (no pass between 6 Sep 11:31 and 15 Sep 23:16 UTC)",
    computes="The distinct Sentinel-1 passes in the committed catalogue snapshot for Mae Sai, the gaps between them and the "
             "passes between 6 September 11:31 UTC and 15 September 23:16 UTC. Metadata only.",
    does_not_show=(
        "When the flood rose or fell: the pass times say when the radar looked, not what the water did.",
        "That no other satellite looked in the gap: the snapshot holds Sentinel-1 only.",
        "Today's catalogue: the snapshot was not taken again, and a product of another mode or type would not be in it.",
    ),
)


def relative_orbit_s1a(product_name: str) -> int:
    """Return the relative orbit (track) of a Sentinel-1A product from the absolute orbit in its name.

    For Sentinel-1A the relative orbit is ``(absolute orbit - 73) mod 175 + 1``.

    Raises:
        ValueError: when the name is not that of a Sentinel-1A IW GRDH dual-polarisation product.
    """

    match = _ORBIT.match(product_name)
    if match is None:
        raise ValueError(f"not a Sentinel-1A IW GRDH product name: {product_name}")
    return (int(match.group(1)) - 73) % 175 + 1


def make_compute(root: Path, external: Path | None) -> Callable[[], diagnosis_run.FigureResult]:
    """Return the function that computes the figures of this script."""

    def compute() -> diagnosis_run.FigureResult:
        path = root / SNAPSHOT
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        gap = diagnosis.pass_gap((row["acquisition_date"] for row in rows), after=INTERVAL_AFTER, before=INTERVAL_BEFORE)
        tracks: dict[str, int] = {}
        products: dict[str, int] = {}
        for row in rows:
            stamp = diagnosis.parse_utc(row["acquisition_date"]).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            tracks[stamp] = relative_orbit_s1a(row["product_name"])
            products[stamp] = products.get(stamp, 0) + 1
        for entry in gap["passes"]:
            entry["relative_orbit"] = tracks[entry["start_utc"]]
            entry["catalogue_rows"] = products[entry["start_utc"]]
        by_track: dict[str, list[str]] = {}
        for entry in gap["passes"]:
            by_track.setdefault(str(entry["relative_orbit"]), []).append(entry["start_utc"])
        after, before = diagnosis.parse_utc(INTERVAL_AFTER), diagnosis.parse_utc(INTERVAL_BEFORE)
        keyframes: dict[str, dict] = {}
        for name, keyframe in REPLAY_KEYFRAMES.items():
            moment = diagnosis.parse_utc(keyframe["utc"])
            keyframes[name] = {
                **keyframe,
                "inside_the_gap": after < moment < before,
                "hours_after_the_pass_of_6_september": round((moment - after).total_seconds() / 3600.0, 2),
                "hours_before_the_pass_of_15_september_utc": round((before - moment).total_seconds() / 3600.0, 2),
                "days_before_the_pass_of_15_september_utc": round((before - moment).total_seconds() / 86400.0, 2),
            }
        figures = {
            "catalogue_rows": len(rows),
            "platforms_in_the_snapshot": sorted({row["mission_platform_prefix"] for row in rows}),
            **gap,
            "passes_by_relative_orbit": by_track,
            "no_pass_strictly_inside_the_interval": not gap["passes_strictly_inside_the_interval"],
            "replay_keyframes_for_context": {
                "what": "Two keyframes of the Mae Sai replay, set beside the passes. The replay's stage is an illustrative "
                        "keyframe curve shaped to the event chronology (lane SCN, tier T1); no gauge record exists for "
                        "September 2024. They are not observations of when the water rose or peaked.",
                "stated_in": REPLAY_NUMBERS.as_posix(),
                **keyframes,
            },
        }
        queries = sorted({row["source_url"] for row in rows})
        return diagnosis_run.FigureResult(
            figures=figures,
            inputs={"catalogue_snapshot": diagnosis_run.file_record(path, root, external, rows=len(rows))},
            parameters={"interval": {"after_utc": INTERVAL_AFTER, "before_utc": INTERVAL_BEFORE, "open_interval": True},
                        "snapshot_date": {"date": "2026-07-08", "stated_in": SNAPSHOT_LOG.as_posix(),
                                          "note": "The log says the snapshot was taken with scripts/query_cdse_metadata.py and that "
                                                  "no product was downloaded. The log is a growing document, so it is named and "
                                                  "not bound by SHA-256."},
                        "query_profile": sorted({row["query_profile"] for row in rows}),
                        "catalogue_query_as_recorded": queries,
                        "relative_orbit_rule": "Sentinel-1A: (absolute orbit - 73) mod 175 + 1",
                        "replay_keyframes": {name: keyframe["utc"] for name, keyframe in REPLAY_KEYFRAMES.items()}},
            source_timestamp="2024-09-01/2024-09-25 (acquisitions); catalogue snapshot of 2026-07-08",
            confidence_basis="Catalogue metadata as the Copernicus Data Space returned it on 8 July 2026. The snapshot was not "
                             "taken again and was not compared with another catalogue.",
            assumptions=[
                "Rows with one acquisition start time are one pass: the catalogue lists the original product and its "
                "cloud-optimised copy.",
                "The query asked for IW GRDH dual-polarisation products that cover the point 99.88 E, 20.43 N, with a start "
                "time from 1 to 25 September 2024.",
                "Thailand time is UTC+7.",
            ],
            limits=[
                "The pass times say when the radar looked. They do not say when the water rose or fell.",
                "The snapshot is one catalogue, one point and one product type. A pass that produced no IW GRDH "
                "dual-polarisation product over that point is not in it.",
                "The catalogue was not queried again in this run.",
            ],
            plan_figure={
                "stated_in_the_plan": "no pass between 6 Sep 11:31 and 15 Sep 23:16 UTC",
                "plan_value": {"after_utc": "2024-09-06T11:31", "before_utc": "2024-09-15T23:16", "passes_between": 0},
                "measured": {"after_utc": gap["interval"]["after_utc"][:16], "before_utc": gap["interval"]["before_utc"][:16],
                             "passes_between": len(gap["passes_strictly_inside_the_interval"]),
                             "both_ends_are_passes": gap["interval_starts_at_a_pass"] and gap["interval_ends_at_a_pass"]},
                "reproduced": (not gap["passes_strictly_inside_the_interval"]) and gap["interval_starts_at_a_pass"]
                              and gap["interval_ends_at_a_pass"],
                "note": "Reproduced from the committed snapshot of the catalogue, not from a new query.",
            },
            attributions=["Copernicus Data Space Ecosystem catalogue metadata; Copernicus Sentinel-1 products of 2024"],
            not_computed=["any figure from an image", "the time of the flood peak", "FPPS", "A-E class", "flood candidate"],
        )

    return compute


def main(argv: Sequence[str] | None = None) -> int:
    """Run the script from the command line."""

    return diagnosis_run.command_line(SPEC, make_compute, root=ROOT, description=__doc__, needs_external_data=False, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
