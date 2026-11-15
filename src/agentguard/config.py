"""Configuration management for AgentGuard.

Settings are loaded from environment variables and .env files.
All settings have sensible defaults that allow the system to run
without external API keys using the MockAgent.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import make_url


def _find_project_root() -> Path:
    """Find the project root by looking for pyproject.toml."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return current


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes:
        environment: Runtime environment (development, test, ci).
        database_url: SQLAlchemy database connection string.
        max_agent_attempts: Maximum revision attempts per task (1-10).
        log_level: Logging verbosity level.
        benchmark_dir: Path to benchmark tasks and data.
        policies_path: Path to governance policies YAML.
        results_dir: Path for storing experiment results.
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENTGUARD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
    )

    # Core settings
    environment: Literal["development", "test", "ci"] = "development"
    database_url: str = Field(
        default="postgresql://agentguard:agentguard@localhost:5432/agentguard",
        description="PostgreSQL database connection string",
    )
    max_agent_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum agent revision attempts per task",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # LLM settings
    llm_provider: Literal["anthropic", "openai_compatible", "mock"] = Field(
        default="anthropic",
        description="LLM provider type (anthropic, openai_compatible, or mock)",
    )
    llm_api_key: str = Field(
        default="",
        description="LLM API key (Anthropic sk-ant-... or OpenAI-compatible)",
    )
    llm_base_url: str = Field(
        default="https://api.anthropic.com",
        description="LLM API base URL (Anthropic or OpenAI-compatible endpoint)",
    )
    llm_model: str = Field(
        default="claude-sonnet-4-5",
        description="Model name for chat completions",
    )
    llm_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for the LLM",
    )
    llm_max_tokens: int = Field(
        default=8192,
        ge=1,
        description="Maximum tokens in LLM response",
    )
    llm_timeout: int = Field(
        default=120,
        ge=1,
        description="Request timeout in seconds for LLM calls",
    )

    # Path settings (relative to project root by default)
    benchmark_dir: Path = Field(
        default_factory=lambda: _find_project_root() / "benchmark",
        description="Path to benchmark tasks and weather platform",
    )
    policies_path: Path = Field(
        default_factory=lambda: _find_project_root() / "policies" / "default_policies.yaml",
        description="Path to governance policies YAML file",
    )
    results_dir: Path = Field(
        default_factory=lambda: _find_project_root() / "results",
        description="Directory for storing experiment results",
    )

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, v: str) -> str:
        """Normalize and validate log level."""
        normalized = v.upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}, got {v!r}")
        return normalized

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format."""
        try:
            make_url(v)
        except Exception as e:
            raise ValueError(f"Invalid database URL format: {e}") from e
        return v

    @field_validator("llm_base_url")
    @classmethod
    def validate_llm_base_url(cls, v: str) -> str:
        """Validate LLM base URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("llm_base_url must start with http:// or https://")
        return v.rstrip("/")

    @property
    def llm_configured(self) -> bool:
        """Check if the LLM API is ready to use."""
        if self.llm_provider == "mock":
            return True
        return bool(self.llm_api_key)

    @property
    def safe_llm_api_key(self) -> str:
        """Return masked LLM API key for logging."""
        if not self.llm_api_key:
            return "<not set>"
        if len(self.llm_api_key) <= 8:
            return "***"
        return f"{self.llm_api_key[:4]}...{self.llm_api_key[-4:]}"

    @property
    def safe_database_url(self) -> str:
        """Return database URL with password masked for logging."""
        url = make_url(self.database_url)
        if url.password:
            return str(url.set(password="***"))  # noqa: S106
        return str(url)

    def configure_logging(self) -> None:
        """Configure logging based on settings."""
        logging.basicConfig(
            level=getattr(logging, self.log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


class WeatherAPISettings(BaseSettings):
    """WeatherAPI configuration settings.

    These settings are loaded from environment variables without
    the AGENTGUARD_ prefix for the API key.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    weatherapi_key: str = Field(
        default="",
        description="WeatherAPI.com API key for fetching weather data",
    )

    @property
    def is_configured(self) -> bool:
        """Check if the API key is configured."""
        return bool(self.weatherapi_key) and self.weatherapi_key != "your_api_key_here"

    @property
    def safe_api_key(self) -> str:
        """Return masked API key for logging."""
        if not self.weatherapi_key:
            return "<not set>"
        if len(self.weatherapi_key) <= 8:
            return "***"
        return f"{self.weatherapi_key[:4]}...{self.weatherapi_key[-4:]}"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Settings: Validated settings loaded from environment.

    Note:
        Call `get_settings.cache_clear()` to reload settings.
    """
    return Settings()


@lru_cache
def get_weather_settings() -> WeatherAPISettings:
    """Get cached WeatherAPI settings instance."""
    return WeatherAPISettings()
