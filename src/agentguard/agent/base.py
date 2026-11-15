"""Agent base abstraction.

Defines the Agent interface and AgentSolution result type. The agent
receives benchmark tasks and produces a solution (SQL queries, scripts,
and notes). The agent never evaluates or scores its own output.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentSolution:
    """The output produced by an agent for a benchmark task.

    Attributes:
        task_id: ID of the task being solved.
        raw_response: Full raw LLM response text.
        sql_queries: SQL queries extracted from the response.
        files: Mapping of filename to file content produced by the agent.
        reasoning: Chain-of-thought / explanation text from the agent.
        metadata: Additional provider-specific metadata.
        attempts: Number of LLM calls used to produce this solution.
    """

    task_id: str
    raw_response: str = ""
    sql_queries: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    reasoning: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0

    @property
    def is_empty(self) -> bool:
        """Check whether the solution contains any usable output."""
        return not (self.sql_queries or self.files or self.raw_response)


class Agent(ABC):
    """Abstract base class for AI agents that solve benchmark tasks.

    Implementations receive a task definition and must return an
    AgentSolution. Implementations must not evaluate or score
    themselves; evaluation is handled by the independent evaluator.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the agent/provider."""

    @abstractmethod
    def solve_task(self, task: dict[str, Any]) -> AgentSolution:
        """Solve a benchmark task.

        Args:
            task: Task definition dictionary loaded from YAML containing
                at least 'id', 'name', 'description', 'task', and
                'schema_hint' keys.

        Returns:
            AgentSolution: The solution produced by the agent.
        """
