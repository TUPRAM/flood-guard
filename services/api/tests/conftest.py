from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from floodguard_api.app import create_app
from floodguard_api.repository import ArtifactRepository


@pytest.fixture
def repository() -> ArtifactRepository:
    return ArtifactRepository()


@pytest.fixture
def client(repository: ArtifactRepository) -> Iterator[TestClient]:
    with TestClient(create_app(repository)) as test_client:
        yield test_client
