"""Agent factory.

Creates the appropriate Agent implementation based on configuration.
"""

from __future__ import annotations

from typing import Any

from agentguard.agent.anthropic_client import AnthropicClient
from agentguard.agent.base import Agent
from agentguard.agent.llm_client import LLMClient
from agentguard.agent.mock_agent import MockAgent
from agentguard.agent.providers.openai_compatible import LLMAgent


class AgentNotConfiguredError(Exception):
    """Raised when the agent cannot be created due to missing configuration."""


def create_agent(settings: Any) -> Agent:
    """Create an agent based on settings.

    Args:
        settings: AgentGuard Settings instance.

    Returns:
        Configured Agent instance.

    Raises:
        AgentNotConfiguredError: If the provider requires an API key but
            none is configured, or the provider is unknown.
    """
    if settings.llm_provider == "mock":
        return MockAgent()

    if not settings.llm_api_key:
        raise AgentNotConfiguredError(
            "LLM API key not configured. "
            "Set AGENTGUARD_LLM_API_KEY in your .env file, "
            "or set AGENTGUARD_LLM_PROVIDER=mock to use the MockAgent."
        )

    if settings.llm_provider == "anthropic":
        client = AnthropicClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
        )
        return LLMAgent(client)

    if settings.llm_provider == "openai_compatible":
        client = LLMClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
        )
        return LLMAgent(client)

    raise AgentNotConfiguredError(f"Unknown LLM provider: {settings.llm_provider}")
