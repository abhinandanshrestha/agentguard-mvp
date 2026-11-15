"""Tests for configuration management."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentguard.config import Settings, get_settings


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self, clean_env: None) -> None:  # noqa: ARG002
        """Test that defaults are applied when no env vars set."""
        settings = Settings(_env_file=None)

        assert settings.environment == "development"
        assert "postgresql" in settings.database_url
        assert settings.max_agent_attempts == 3
        assert settings.log_level == "INFO"

    def test_environment_override(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch  # noqa: ARG002
    ) -> None:
        """Test environment variable overrides."""
        monkeypatch.setenv("AGENTGUARD_ENVIRONMENT", "test")
        monkeypatch.setenv("AGENTGUARD_MAX_AGENT_ATTEMPTS", "5")
        monkeypatch.setenv("AGENTGUARD_LOG_LEVEL", "debug")

        settings = Settings(_env_file=None)

        assert settings.environment == "test"
        assert settings.max_agent_attempts == 5
        assert settings.log_level == "DEBUG"  # Should be normalized

    def test_log_level_normalization(self, clean_env: None) -> None:  # noqa: ARG002
        """Test that log level is normalized to uppercase."""
        settings = Settings(_env_file=None, log_level="warning")
        assert settings.log_level == "WARNING"

    def test_invalid_log_level(self, clean_env: None) -> None:  # noqa: ARG002
        """Test that invalid log level raises error."""
        with pytest.raises(ValueError, match="log_level must be one of"):
            Settings(_env_file=None, log_level="invalid")

    def test_max_attempts_bounds(self, clean_env: None) -> None:  # noqa: ARG002
        """Test max_agent_attempts bounds validation."""
        # Valid values
        settings = Settings(_env_file=None, max_agent_attempts=1)
        assert settings.max_agent_attempts == 1

        settings = Settings(_env_file=None, max_agent_attempts=10)
        assert settings.max_agent_attempts == 10

        # Invalid: too low
        with pytest.raises(ValueError):
            Settings(_env_file=None, max_agent_attempts=0)

        # Invalid: too high
        with pytest.raises(ValueError):
            Settings(_env_file=None, max_agent_attempts=11)

    def test_database_url_validation(self, clean_env: None) -> None:  # noqa: ARG002
        """Test database URL validation."""
        # Valid SQLite
        settings = Settings(_env_file=None, database_url="sqlite:///./test.db")
        assert "sqlite" in settings.database_url

        # Valid PostgreSQL format
        settings = Settings(
            _env_file=None, database_url="postgresql://user:pass@localhost/db"
        )
        assert "postgresql" in settings.database_url

    def test_safe_database_url_masks_password(self, clean_env: None) -> None:  # noqa: ARG002
        """Test that safe_database_url masks passwords."""
        settings = Settings(
            _env_file=None, database_url="postgresql://user:secret123@localhost/db"
        )

        safe_url = settings.safe_database_url
        assert "secret123" not in safe_url
        assert "***" in safe_url
        assert "user" in safe_url

    def test_safe_database_url_no_password(self, clean_env: None) -> None:  # noqa: ARG002
        """Test safe_database_url with no password."""
        settings = Settings(_env_file=None, database_url="sqlite:///./test.db")

        safe_url = settings.safe_database_url
        assert safe_url == "sqlite:///./test.db"

    def test_path_settings(self, clean_env: None) -> None:  # noqa: ARG002
        """Test that path settings are Path objects."""
        settings = Settings(_env_file=None)

        assert isinstance(settings.benchmark_dir, Path)
        assert isinstance(settings.policies_path, Path)
        assert isinstance(settings.results_dir, Path)


class TestGetSettings:
    """Tests for get_settings function."""

    def test_returns_settings_instance(self, clean_env: None) -> None:  # noqa: ARG002
        """Test that get_settings returns a Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_caching(self, clean_env: None) -> None:  # noqa: ARG002
        """Test that get_settings returns cached instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_cache_clear(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch  # noqa: ARG002
    ) -> None:
        """Test that cache can be cleared."""
        settings1 = get_settings()

        get_settings.cache_clear()
        monkeypatch.setenv("AGENTGUARD_ENVIRONMENT", "test")

        settings2 = get_settings()
        assert settings1 is not settings2


class TestEnvExample:
    """Tests that .env.example is valid."""

    def test_env_example_parseable(self, project_root: Path) -> None:
        """Test that .env.example can be parsed."""
        env_example = project_root / ".env.example"
        assert env_example.exists(), ".env.example file should exist"

        # Parse the file
        env_vars: dict[str, str] = {}
        with env_example.open() as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, _, value = stripped.partition("=")
                    env_vars[key.strip()] = value.strip()

        # Check required variables are present
        assert "AGENTGUARD_ENVIRONMENT" in env_vars
        assert "AGENTGUARD_DATABASE_URL" in env_vars
        assert "AGENTGUARD_MAX_AGENT_ATTEMPTS" in env_vars
        assert "AGENTGUARD_LOG_LEVEL" in env_vars
