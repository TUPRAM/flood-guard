"""Repository-relative service configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RepositoryPaths:
    """Resolve only small, committed artifacts from a repository root."""

    root: Path

    @classmethod
    def discover(cls) -> RepositoryPaths:
        return cls(root=Path(__file__).resolve().parents[4])

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def fixtures(self) -> Path:
        return self.root / "tests" / "fixtures"

    @property
    def contracts(self) -> Path:
        return self.root / "packages" / "contracts"
