"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest

from agentguard.config import Settings, get_settings


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Provide a clean environment without AgentGuard variables."""
    # Remove all AGENTGUARD_ prefixed environment variables
    for key in list(os.environ.keys()):
        if key.startswith("AGENTGUARD_"):
            monkeypatch.delenv(key, raising=False)

    # Clear settings cache
    get_settings.cache_clear()

    yield

    # Clear cache again after test
    get_settings.cache_clear()


@pytest.fixture
def test_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Settings, None, None]:
    """Provide settings configured for testing.

    Note: Uses a PostgreSQL URL format for consistency with production,
    but does not require an actual PostgreSQL connection for unit tests.
    """
    # Set up test environment
    monkeypatch.setenv("AGENTGUARD_ENVIRONMENT", "test")
    monkeypatch.setenv(
        "AGENTGUARD_DATABASE_URL",
        "postgresql://test:test@localhost:5432/agentguard_test",
    )
    monkeypatch.setenv("AGENTGUARD_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("AGENTGUARD_BENCHMARK_DIR", str(tmp_path / "benchmark"))
    monkeypatch.setenv("AGENTGUARD_RESULTS_DIR", str(tmp_path / "results"))

    # Create directories
    (tmp_path / "benchmark").mkdir()
    (tmp_path / "results").mkdir()

    # Clear cache and get fresh settings
    get_settings.cache_clear()

    yield get_settings()

    get_settings.cache_clear()
