"""Tests for command-line interface."""

from __future__ import annotations

import pytest

from agentguard import __version__
from agentguard.cli import build_parser, main
from agentguard.config import Settings


class TestCLIParser:
    """Tests for CLI argument parser."""

    def test_parser_creation(self) -> None:
        """Test parser can be created."""
        parser = build_parser()
        assert parser is not None
        assert parser.prog == "agentguard"

    def test_version_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test --version flag."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert __version__ in captured.out

    def test_help_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test --help flag."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "AgentGuard" in captured.out
        assert "benchmark" in captured.out

    def test_no_args_shows_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test that no arguments shows help."""
        exit_code = main([])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "AgentGuard" in captured.out


class TestInfoCommand:
    """Tests for info command."""

    def test_info_command(
        self,
        capsys: pytest.CaptureFixture[str],
        test_settings: Settings,  # noqa: ARG002
    ) -> None:
        """Test info command shows configuration."""
        exit_code = main(["info"])

        assert exit_code == 0
        captured = capsys.readouterr()

        # Should show version
        assert __version__ in captured.out
        # Should show Python info
        assert "Python" in captured.out
        # Should show configuration
        assert "Configuration" in captured.out
        assert "Environment" in captured.out


class TestBenchmarkCommands:
    """Tests for benchmark commands."""

    def test_benchmark_list_no_tasks(
        self,
        capsys: pytest.CaptureFixture[str],
        test_settings: Settings,  # noqa: ARG002
    ) -> None:
        """Test benchmark list with no tasks."""
        main(["benchmark", "list"])

        # Should return error (no tasks directory)
        captured = capsys.readouterr()
        assert "not found" in captured.out or "No benchmark" in captured.out

    def test_benchmark_run_no_task_id(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test benchmark run requires task_id."""
        exit_code = main(["benchmark", "run"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "task_id is required" in captured.out


class TestExperimentCommands:
    """Tests for experiment commands."""

    def test_experiment_run(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test experiment run command."""
        exit_code = main(["experiment", "run"])

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Running experiment" in captured.out


class TestResultsCommands:
    """Tests for results commands."""

    def test_results_summary(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test results summary command."""
        exit_code = main(["results", "summary"])

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Results summary" in captured.out
