"""Agent abstraction layer.

This module provides a provider-independent interface for AI coding agents.
The agent receives tasks and produces solutions (SQL queries, scripts, files)
via an OpenAI-compatible LLM API. The agent never evaluates or scores its
own output.
"""

from __future__ import annotations

from agentguard.agent.anthropic_client import AnthropicClient, AnthropicError
from agentguard.agent.base import Agent, AgentSolution
from agentguard.agent.factory import AgentNotConfiguredError, create_agent
from agentguard.agent.llm_client import LLMClient, LLMError
from agentguard.agent.mock_agent import MockAgent
from agentguard.agent.providers.openai_compatible import LLMAgent

__all__ = [
    "Agent",
    "AgentNotConfiguredError",
    "AgentSolution",
    "AnthropicClient",
    "AnthropicError",
    "LLMAgent",
    "LLMClient",
    "LLMError",
    "MockAgent",
    "create_agent",
]
