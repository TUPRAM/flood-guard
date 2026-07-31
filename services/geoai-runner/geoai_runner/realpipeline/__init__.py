"""FloodGuard GeoAI model pipeline.

This subpackage contains the runnable GeoAI/ML model tier for FloodGuard,
mapped to *Introduction to GeoAI* (Wu, 2026). Each component is a real,
executable implementation (real algorithms, real raster I/O, real PyTorch
training) rather than a stub.

Honesty boundary (consistent with ``AGENTS.md`` and the project no-fabrication
rule): in this environment there is no GPU, no internet to fetch pretrained
weights or open datasets, and licensed Thai flood imagery is gated. The demo
therefore runs every model on a *coherent synthetic Mae Sai-like scene* built
by :mod:`geoai_runner.realpipeline.synth`. The pipeline validates that each
architecture executes end to end and produces georeferenced artifacts. Swapping
in real Sentinel-1/Sentinel-2/THEOS-2 tiles and pretrained encoders is a data
step, not a code change -- the same functions accept real GeoTIFF paths.

Nothing here is an official flood warning. Every artifact carries a
``data_mode`` and ``assumptions`` field stating that the input pixels are
synthetic in this demo build.
"""

from __future__ import annotations

DATA_MODE_SYNTHETIC = "synthetic_demo_scene"
DATA_MODE_REAL = "real_licensed_inputs"

SYNTHETIC_ASSUMPTION = (
    "Pipeline-validation run on a synthetic Mae Sai-like scene. Real algorithms "
    "and real raster I/O; input pixels are procedurally generated because "
    "licensed Thai imagery is gated and there is no network access to open "
    "datasets or pretrained weights in this build. Not an official flood warning."
)

__all__ = [
    "DATA_MODE_SYNTHETIC",
    "DATA_MODE_REAL",
    "SYNTHETIC_ASSUMPTION",
]
