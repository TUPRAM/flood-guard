"""Explain the frozen M2 abstention without accessing reference label values."""

from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

if __name__ == "__main__":
    from floodguard.label_factory.sar_abstention_diagnostic import main

    raise SystemExit(main())
