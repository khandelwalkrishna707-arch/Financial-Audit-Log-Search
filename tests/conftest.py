"""Shared pytest fixtures."""

from pathlib import Path

import pytest

from audit_search.storage.database import connect

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def conn():
    """A fresh in-memory SQLite database with the schema created. Gone after each test."""
    connection = connect(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
