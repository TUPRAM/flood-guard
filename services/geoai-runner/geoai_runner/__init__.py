"""Isolated GeoAI integration; importing this package never imports GeoAI."""

from .contract import GeoAIRunContract, InputManifestRow, PreprocessingContract
from .manifest import build_public_model_run

__all__ = [
    "GeoAIRunContract",
    "InputManifestRow",
    "PreprocessingContract",
    "build_public_model_run",
]
__version__ = "0.1.0"
