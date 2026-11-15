"""LLM-powered agent provider.

Uses any OpenAI-compatible LLM API to solve benchmark tasks. The agent
receives the task definition, prompts the LLM with a structured data
engineering prompt, and extracts SQL queries and files from the response.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agentguard.agent.base import Agent, AgentSolution
from agentguard.agent.llm_client import LLMClient

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an expert data engineer working on a PostgreSQL \
weather data platform. You will be given a data engineering task with a \
database schema description.

Respond in this exact structure:

1. A brief reasoning section starting with "## Reasoning" (max 10 lines)
2. Your SQL queries in ```sql code blocks — every query MUST be in a \
complete ```sql fenced block
3. Any file contents in code blocks with the filename on the line before, \
in the format "FILE: <filename>"

Rules:
- Write production-quality SQL compatible with PostgreSQL 13+
- Use ONLY the tables and columns listed in the "Database Schema" section of
  the task; if a table is not listed there, it does not exist in the database
- Handle NULLs, duplicates, and data quality issues as specified in the task
- Do not invent tables or columns not present in the schema
- Keep queries efficient and readable
- Prioritize completeness of the SQL over lengthy explanations"""


class LLMAgent(Agent):
    """Agent that solves tasks using an OpenAI-compatible LLM API.

    Attributes:
        client: The LLM client to use.
        system_prompt: System prompt for the LLM.
    """

    def __init__(self, client: LLMClient, system_prompt: str | None = None):
        self.client = client
        self.system_prompt = system_prompt or SYSTEM_PROMPT

    @property
    def name(self) -> str:
        """Human-readable name of the agent."""
        return f"llm:{self.client.model}"

    def solve_task(self, task: dict[str, Any]) -> AgentSolution:
        """Solve a benchmark task using the LLM.

        Args:
            task: Task definition dictionary loaded from YAML.

        Returns:
            AgentSolution with extracted SQL queries, files, and reasoning.
        """
        task_id = str(task.get("id", "unknown"))
        user_prompt = self._build_user_prompt(task)

        logger.info("Agent '%s' solving task %s", self.name, task_id)

        raw_response = self.client.chat(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        solution = self._parse_response(task_id, raw_response)
        solution.attempts = 1

        logger.info(
            "Task %s solved: %d SQL queries, %d files",
            task_id,
            len(solution.sql_queries),
            len(solution.files),
        )
        return solution

    def _build_user_prompt(self, task: dict[str, Any]) -> str:
        """Build the user prompt from the task definition.

        Args:
            task: Task definition dictionary loaded from YAML.

        Returns:
            Formatted user prompt string.
        """
        sections = [
            f"# Task: {task.get('name', 'Unnamed task')}",
            "",
            "## Description",
            task.get("description", "").strip(),
            "",
            "## Context",
            task.get("context", "").strip(),
            "",
            "## Database Schema",
            task.get("schema_hint", "").strip(),
            "",
            "## Your Task",
            task.get("task", "").strip(),
        ]

        difficulty = task.get("difficulty")
        if difficulty:
            sections.insert(1, f"(Difficulty: {difficulty})")

        return "\n".join(sections)

    def _parse_response(self, task_id: str, raw_response: str) -> AgentSolution:
        """Parse the LLM response into an AgentSolution.

        Extracts:
        - SQL queries from ```sql code blocks
        - Files declared with "FILE: <name>" followed by a code block
        - Reasoning text from a "## Reasoning" section

        Args:
            task_id: ID of the task.
            raw_response: Raw LLM response text.

        Returns:
            Parsed AgentSolution.
        """
        solution = AgentSolution(task_id=task_id, raw_response=raw_response)

        # Extract reasoning section
        reasoning_match = re.search(
            r"##\s*Reasoning\s*\n(.*?)(?=\n##\s|\nFILE:|\Z)",
            raw_response,
            re.DOTALL | re.IGNORECASE,
        )
        if reasoning_match:
            solution.reasoning = reasoning_match.group(1).strip()

        # Extract SQL from ```sql code blocks
        sql_blocks = re.findall(
            r"```sql\s*\n(.*?)```",
            raw_response,
            re.DOTALL | re.IGNORECASE,
        )

        # Recover a truncated unterminated block (e.g. max_tokens cutoff):
        # take everything after the last opening ```sql fence with no
        # closing fence anywhere after it.
        open_positions = [
            m.end()
            for m in re.finditer(r"```sql\s*\n", raw_response, re.IGNORECASE)
        ]
        if open_positions:
            last_open = open_positions[-1]
            if "```" not in raw_response[last_open:]:
                tail = raw_response[last_open:].strip()
                if tail and tail not in [b.strip() for b in sql_blocks]:
                    sql_blocks.append(tail)
                    logger.warning(
                        "Response appears truncated; recovered unterminated "
                        "SQL block (%d chars)",
                        len(tail),
                    )

        solution.sql_queries = [block.strip() for block in sql_blocks if block.strip()]

        # Extract files: "FILE: <name>" followed by the next code block
        file_pattern = re.compile(
            r"FILE:\s*(?P<name>[\w./-]+)\s*\n+```\w*\s*\n(?P<content>.*?)```",
            re.DOTALL,
        )
        for match in file_pattern.finditer(raw_response):
            solution.files[match.group("name")] = match.group("content").strip()

        solution.metadata = {
            "model": self.client.model,
            "base_url": self.client.base_url,
        }

        return solution
