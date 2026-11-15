"""Mock agent for testing AgentGuard without an LLM API.

Returns deterministic canned solutions so the pipeline can be tested
end-to-end without network access or API keys.
"""

from __future__ import annotations

from typing import Any

from agentguard.agent.base import Agent, AgentSolution

MOCK_SQL = """-- Mock solution for {task_id}
SELECT l.name AS location_name,
       l.country,
       TO_CHAR(dw.date, 'YYYY-MM') AS month,
       ROUND(AVG(dw.avg_temp_c)::numeric, 1) AS avg_temp_c,
       MIN(dw.min_temp_c) AS min_temp_c,
       MAX(dw.max_temp_c) AS max_temp_c,
       COUNT(*) AS days_recorded
FROM daily_weather dw
JOIN locations l ON dw.location_id = l.location_id
GROUP BY l.name, l.country, TO_CHAR(dw.date, 'YYYY-MM')
ORDER BY l.name, month;"""


class MockAgent(Agent):
    """Deterministic mock agent that returns a canned solution.

    Useful for testing the benchmark pipeline without LLM API access.
    """

    @property
    def name(self) -> str:
        """Human-readable name of the agent."""
        return "mock"

    def solve_task(self, task: dict[str, Any]) -> AgentSolution:
        """Return a canned solution for the task.

        Args:
            task: Task definition dictionary loaded from YAML.

        Returns:
            AgentSolution with deterministic mock content.
        """
        task_id = str(task.get("id", "unknown"))
        return AgentSolution(
            task_id=task_id,
            raw_response=f"## Reasoning\nMock response for {task_id}",
            sql_queries=[MOCK_SQL.format(task_id=task_id)],
            reasoning=f"Mock response for {task_id}",
            metadata={"model": "mock"},
            attempts=1,
        )
