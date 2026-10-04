"""Diagnosis figure of plan task A1: what one bell-shaped population gives the 0.72 histogram gate.

README
======

Reads
    No satellite data and no flood map. It loads the frozen M2 Otsu kernel
    (``floodguard.label_factory.sentinel1_processing``) and draws random numbers with a fixed seed.

Computes
    The between-class variance fraction (the share of a histogram's variance that an Otsu split explains)

    * in theory, for a normal population split at its mean: 2/pi;
    * in theory, for the same population clipped at its 1st and 99th percentiles, as the kernel clips it;
    * through the kernel itself, for simulated windows of pure normal noise of three sizes;
    * through the kernel, for windows that hold a second population: the smallest distance between the two
      populations, in standard deviations, at which the kernel accepts the window.

    Plan row A1 states the first figure as "a unimodal Gaussian gives 0.637 < 0.72".

Does not show
    * Anything about Mae Sai, or about any image: it is arithmetic and simulation.
    * That a window which failed the gate held no flood. It shows that the gate cannot be passed by one
      population, whatever it is, and how far apart two populations must lie to pass it.
    * That real change values are normal. Speckle is not, and a real window is a mixture of land covers.

Writes
    ``outputs/a1_diagnosis/bvf_unimodal_gaussian.json`` (the figures),
    ``outputs/planning_v1/a1_diagnosis_bvf_unimodal_gaussian.json`` (the run receipt) and its register entry.

Run
    ``python scripts/diagnostics/bvf_unimodal_gaussian.py`` (a second run needs ``--replace --reason``;
    ``--verify`` computes the figures again and compares them).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from floodguard import abstention_diagnosis as diagnosis  # noqa: E402
from floodguard import diagnosis_run  # noqa: E402

KERNEL_MODULE = "src/floodguard/label_factory/sentinel1_processing.py"
SEED = 20240916
SAMPLE_SIZES = (4096, 16384, 65536)
REPEATS = 200
MIXTURE_SHARES = (0.5, 0.3, 0.2, 0.1)
MIXTURE_SEPARATIONS = tuple(round(step * 0.1, 1) for step in range(0, 61))
MIXTURE_REPEATS = 10
MIXTURE_SIZE = 65536

SPEC = diagnosis_run.FigureSpec(
    figure_id="bvf_unimodal_gaussian",
    title="Between-class variance fraction of one bell-shaped population against the 0.72 gate",
    script="scripts/diagnostics/bvf_unimodal_gaussian.py",
    plan_statement="BVF theory/simulation (a unimodal Gaussian gives 0.637 < 0.72)",
    computes="The between-class variance fraction of a normal population in theory and through the frozen M2 Otsu kernel, "
             "and the separation two populations need before the kernel accepts a window. No image is read.",
    does_not_show=(
        "Anything about Mae Sai or about any image: it is arithmetic and simulation.",
        "That a window which failed the gate held no flood.",
        "That real change values are normal: speckle is not, and a real window is a mixture of land covers.",
    ),
)


def make_compute(root: Path, external: Path | None) -> Callable[[], diagnosis_run.FigureResult]:
    """Return the function that computes the figures of this script."""

    def compute() -> diagnosis_run.FigureResult:
        gate = diagnosis.m2_gate()
        theory = diagnosis.GAUSSIAN_BVF_THEORY
        clipped = diagnosis.clipped_gaussian_bvf(0.01, 0.99)
        simulated = diagnosis.simulate_unimodal(SAMPLE_SIZES, repeats=REPEATS, seed=SEED)
        needed = diagnosis.separation_needed(MIXTURE_SHARES, MIXTURE_SEPARATIONS, size=MIXTURE_SIZE, repeats=MIXTURE_REPEATS, seed=SEED + 1)
        largest = max(row["between_variance_fraction_max"] for row in simulated)
        figures = {
            "gate": gate,
            "theory_normal_population_split_at_its_mean": round(theory, 6),
            "theory_formula": "(E|x|)^2 / var(x) = 2/pi",
            "theory_same_population_clipped_at_1st_and_99th_percentile": round(clipped, 6),
            "below_the_gate": {"theory": theory < gate, "theory_clipped": clipped < gate, "every_simulated_window": largest < gate},
            "shortfall_against_the_gate": {"theory": round(gate - theory, 6), "theory_clipped": round(gate - clipped, 6)},
            "simulated_windows_of_pure_noise_through_the_m2_kernel": simulated,
            "largest_fraction_of_any_simulated_window": largest,
            "two_populations_through_the_m2_kernel": needed,
            "two_populations_note": "Both populations are normal with one standard deviation. The separation is the distance "
                                    "between their means in standard deviations. The first column of each row is the share of "
                                    "the window in the second population.",
        }
        return diagnosis_run.FigureResult(
            figures=figures,
            inputs={"m2_otsu_kernel": diagnosis_run.file_record(root / KERNEL_MODULE, root, external,
                                                                function="_otsu_threshold with AdaptiveOtsuConfig()")},
            parameters={
                "seed": SEED, "sample_sizes": list(SAMPLE_SIZES), "windows_per_size": REPEATS,
                "kernel": {"histogram_bins": 64, "clip_quantiles": [0.01, 0.99], "min_between_variance_fraction": gate},
                "two_populations": {"shares_of_the_second_population": list(MIXTURE_SHARES),
                                    "separations_tried": [MIXTURE_SEPARATIONS[0], MIXTURE_SEPARATIONS[-1]],
                                    "separation_step": 0.1, "windows_per_case": MIXTURE_REPEATS, "samples_per_window": MIXTURE_SIZE,
                                    "seed": SEED + 1},
            },
            source_timestamp="not applicable: theory and simulation, no observation",
            confidence_basis="Arithmetic and a seeded simulation through the unchanged M2 kernel. It reads no image and no flood "
                             "map, and it was not checked against anything outside the repository.",
            assumptions=[
                "A window with no flood class is modelled as one normal population. Real backscatter change is not normal, "
                "and a real window mixes land covers.",
                "The kernel is the frozen M2 kernel, unchanged: it clips the samples at their 1st and 99th percentiles, builds "
                "a 64-bin histogram and divides the between-class variance at the Otsu split by the variance of the clipped samples.",
                "The simulation is seeded, so a second run gives the same figures.",
            ],
            limits=[
                "The figure says what one population gives the gate. It does not say what the windows at Mae Sai held.",
                "The two-population table uses equal standard deviations. A flood class that is narrower or wider than the "
                "land around it needs a different separation.",
                "The kernel has two more tests (class share and mean separation); a window can pass the gate and still be declined.",
            ],
            plan_figure={
                "stated_in_the_plan": "a unimodal Gaussian gives 0.637 < 0.72",
                "plan_value": 0.637,
                "measured": round(theory, 3),
                "reproduced": round(theory, 3) == 0.637,
                "note": "The plan's figure is the theory value 2/pi. The kernel clips the samples before it measures the "
                        "variance, so through the kernel one population gives a little more; see "
                        "theory_same_population_clipped_at_1st_and_99th_percentile and the simulated windows. Both stay below 0.72.",
            },
            not_computed=["any figure from an image", "FPPS", "A-E class", "flood candidate"],
        )

    return compute


def main(argv: Sequence[str] | None = None) -> int:
    """Run the script from the command line."""

    return diagnosis_run.command_line(SPEC, make_compute, root=ROOT, description=__doc__, needs_external_data=False, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
