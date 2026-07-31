"""The candidate lane must not reach FPPS without a receipt (D-02).

`from floodguard.scoring import score_subdistricts` just works, produces
plausible numbers, and leaves no trace. That is precisely why the bypass
existed for as long as it did: nothing objected, and the resulting FPPS values
and A-E action classes were published to the Command surface indistinguishable
from governed ones.

Routing through `floodguard.candidate_zonal_receipt` is behaviour-preserving --
`test_scoring_characterization.py` pins the published Mae Sai figures, and
`tests/test_candidate_zonal_receipt.py` asserts the routed frame equals the
direct one. So the only thing standing between a future edit and a silent
regression is this check.

Deliberately source-level rather than import-level: it must fail on the *edit*,
in the dependency-light environment, without importing the pipeline or needing
the geoai extra.
"""

from __future__ import annotations

import ast
from pathlib import Path

REALPIPELINE = Path(__file__).resolve().parents[1] / "geoai_runner" / "realpipeline"

#: Reaching these directly skips the receipt.
GATED = {"score_subdistricts"}
GATED_MODULE = "floodguard.scoring"


def _offending_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offences: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == GATED_MODULE:
            names = {alias.name for alias in node.names} & GATED
            if names:
                offences.append(
                    f"{path.name}:{node.lineno}: from {GATED_MODULE} import {sorted(names)}"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == GATED_MODULE:
                    offences.append(f"{path.name}:{node.lineno}: import {GATED_MODULE}")
    return offences


def test_realpipeline_reaches_fpps_only_through_the_receipt() -> None:
    offences: list[str] = []
    for path in sorted(REALPIPELINE.rglob("*.py")):
        offences.extend(_offending_imports(path))

    assert not offences, (
        "The GeoAI pipeline imports the scoring engine directly, bypassing the "
        "report-only receipt. Candidate evidence would reach an A-E action "
        "class with nothing recording that it is candidate tier:\n  "
        + "\n  ".join(offences)
        + "\n\nUse floodguard.candidate_zonal_receipt.score_candidate_areas instead."
    )


def test_the_receipt_module_is_actually_used() -> None:
    """Guard against the check passing because scoring was dropped entirely."""

    run_real = REALPIPELINE / "run_real.py"
    source = run_real.read_text(encoding="utf-8")
    assert "score_candidate_areas" in source, (
        "run_real.py no longer routes through score_candidate_areas; the "
        "previous test would now pass vacuously."
    )
