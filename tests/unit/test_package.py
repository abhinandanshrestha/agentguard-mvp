"""Tests for package structure and imports."""

from __future__ import annotations

import sys

import agentguard
import agentguard.agent
import agentguard.agent.providers
import agentguard.api
import agentguard.benchmark
import agentguard.evaluator
import agentguard.experiments
import agentguard.feedback
import agentguard.storage
from agentguard import __version__


def test_python_version() -> None:
    """Verify Python version is 3.10.x as required."""
    assert sys.version_info[:2] == (3, 10), (
        f"Python 3.10.x required, got {sys.version_info.major}.{sys.version_info.minor}"
    )


def test_package_import() -> None:
    """Verify main package can be imported."""
    assert agentguard is not None


def test_package_version() -> None:
    """Verify package has a version string."""
    assert isinstance(__version__, str)
    assert len(__version__) > 0
    # Should be semantic version format
    parts = __version__.split(".")
    assert len(parts) >= 2


def test_subpackage_imports() -> None:
    """Verify all subpackages can be imported."""
    # All should import without error (imported at top of module)
    assert agentguard.agent is not None
    assert agentguard.benchmark is not None
    assert agentguard.evaluator is not None
    assert agentguard.feedback is not None
    assert agentguard.experiments is not None
    assert agentguard.storage is not None
    assert agentguard.api is not None
    assert agentguard.agent.providers is not None
