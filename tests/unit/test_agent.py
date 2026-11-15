"""Unit tests for the agent abstraction, LLM client, and factory."""

from __future__ import annotations

from typing import Any

import pytest

from agentguard.agent import (
    Agent,
    AgentNotConfiguredError,
    AgentSolution,
    AnthropicClient,
    LLMAgent,
    MockAgent,
    create_agent,
)
from agentguard.agent.anthropic_client import AnthropicError
from agentguard.agent.llm_client import LLMClient, LLMError

TASK: dict[str, Any] = {
    "id": "task_001",
    "name": "Test Task",
    "difficulty": "easy",
    "description": "A test task.",
    "context": "Some context.",
    "schema_hint": "Tables: locations, daily_weather",
    "task": "Write a query.",
}


class TestAgentSolution:
    def test_empty_solution(self) -> None:
        solution = AgentSolution(task_id="t")
        assert solution.is_empty

    def test_non_empty_solution(self) -> None:
        solution = AgentSolution(task_id="t", sql_queries=["SELECT 1"])
        assert not solution.is_empty


class TestMockAgent:
    def test_solve_task_returns_solution(self) -> None:
        agent = MockAgent()
        solution = agent.solve_task(TASK)
        assert solution.task_id == "task_001"
        assert solution.sql_queries
        assert "task_001" in solution.sql_queries[0]
        assert not solution.is_empty

    def test_agent_name(self) -> None:
        assert MockAgent().name == "mock"


class TestLLMAgentParsing:
    def make_agent(self) -> LLMAgent:
        return LLMAgent(LLMClient(api_key="test-key"))

    def test_extracts_sql_queries(self) -> None:
        agent = self.make_agent()
        response = (
            "## Reasoning\nI analyzed the schema.\n\n"
            "```sql\nSELECT 1;\n```\n\n```sql\nSELECT 2;\n```"
        )
        solution = agent._parse_response("task_001", response)
        assert solution.sql_queries == ["SELECT 1;", "SELECT 2;"]
        assert "analyzed" in solution.reasoning

    def test_extracts_files(self) -> None:
        agent = self.make_agent()
        response = (
            "FILE: etl.py\n```python\nprint('hello')\n```\n"
            "FILE: query.sql\n```sql\nSELECT 1;\n```"
        )
        solution = agent._parse_response("task_001", response)
        assert solution.files["etl.py"] == "print('hello')"
        assert solution.files["query.sql"] == "SELECT 1;"

    def test_builds_user_prompt(self) -> None:
        agent = self.make_agent()
        prompt = agent._build_user_prompt(TASK)
        assert "Test Task" in prompt
        assert "Tables: locations" in prompt
        assert "Write a query." in prompt

    def test_agent_name_includes_model(self) -> None:
        agent = self.make_agent()
        assert agent.name == "llm:gpt-4o-mini"

    def test_recovers_truncated_sql_block(self) -> None:
        agent = self.make_agent()
        response = (
            "## Reasoning\nTruncated by max_tokens.\n\n"
            "```sql\nSELECT 1;\n```\n\n```sql\nSELECT location_id FROM loca"
        )
        solution = agent._parse_response("task_001", response)
        assert len(solution.sql_queries) == 2
        assert solution.sql_queries[1] == "SELECT location_id FROM loca"

    def test_no_duplicate_on_complete_blocks(self) -> None:
        agent = self.make_agent()
        response = "```sql\nSELECT 1;\n```"
        solution = agent._parse_response("task_001", response)
        assert solution.sql_queries == ["SELECT 1;"]


class TestLLMClient:
    def test_extract_message(self) -> None:
        client = LLMClient(api_key="k")
        data = {"choices": [{"message": {"content": "hello"}}]}
        assert client._extract_message(data) == "hello"

    def test_extract_message_no_choices(self) -> None:
        client = LLMClient(api_key="k")
        with pytest.raises(LLMError, match="no choices"):
            client._extract_message({"choices": []})

    def test_extract_message_empty_content(self) -> None:
        client = LLMClient(api_key="k")
        with pytest.raises(LLMError, match="empty content"):
            client._extract_message({"choices": [{"message": {}}]})


class TestAnthropicClient:
    def test_extract_message(self) -> None:
        client = AnthropicClient(api_key="k")
        data = {"content": [{"type": "text", "text": "hello"}]}
        assert client._extract_message(data) == "hello"

    def test_extract_message_multiple_blocks(self) -> None:
        client = AnthropicClient(api_key="k")
        data = {
            "content": [
                {"type": "text", "text": "part1 "},
                {"type": "tool_use", "id": "x"},
                {"type": "text", "text": "part2"},
            ]
        }
        assert client._extract_message(data) == "part1 part2"

    def test_extract_message_no_content(self) -> None:
        client = AnthropicClient(api_key="k")
        with pytest.raises(AnthropicError, match="no content"):
            client._extract_message({"content": []})

    def test_extract_message_empty_text(self) -> None:
        client = AnthropicClient(api_key="k")
        with pytest.raises(AnthropicError, match="empty text"):
            client._extract_message({"content": [{"type": "text", "text": ""}]})

    def test_works_with_llm_agent(self) -> None:
        agent = LLMAgent(AnthropicClient(api_key="k", model="claude-sonnet-4-5"))
        assert agent.name == "llm:claude-sonnet-4-5"


class TestCreateAgentFactory:
    def test_mock_provider(self) -> None:
        class FakeSettings:
            llm_provider = "mock"

        assert isinstance(create_agent(FakeSettings()), MockAgent)

    def test_missing_api_key_raises(self) -> None:
        class FakeSettings:
            llm_provider = "anthropic"
            llm_api_key = ""

        with pytest.raises(AgentNotConfiguredError, match="API key not configured"):
            create_agent(FakeSettings())

    def test_anthropic_provider(self) -> None:
        class FakeSettings:
            llm_provider = "anthropic"
            llm_api_key = "sk-ant-test"
            llm_base_url = "https://api.anthropic.com"
            llm_model = "claude-sonnet-4-5"
            llm_temperature = 0.1
            llm_max_tokens = 100
            llm_timeout = 30

        agent = create_agent(FakeSettings())
        assert isinstance(agent, LLMAgent)
        assert isinstance(agent, Agent)
        assert isinstance(agent.client, AnthropicClient)
        assert agent.client.model == "claude-sonnet-4-5"
        assert agent.client.base_url == "https://api.anthropic.com"

    def test_unknown_provider_raises(self) -> None:
        class FakeSettings:
            llm_provider = "unknown_provider"
            llm_api_key = "key"

        with pytest.raises(AgentNotConfiguredError, match="Unknown LLM provider"):
            create_agent(FakeSettings())

    def test_llm_provider(self) -> None:
        class FakeSettings:
            llm_provider = "openai_compatible"
            llm_api_key = "sk-test"
            llm_base_url = "https://api.example.com/v1"
            llm_model = "test-model"
            llm_temperature = 0.1
            llm_max_tokens = 100
            llm_timeout = 30

        agent = create_agent(FakeSettings())
        assert isinstance(agent, LLMAgent)
        assert isinstance(agent, Agent)
        assert agent.client.model == "test-model"
        assert agent.client.base_url == "https://api.example.com/v1"
