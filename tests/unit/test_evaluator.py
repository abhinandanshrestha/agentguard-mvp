"""Unit tests for the heuristic evaluator."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from agentguard.evaluator import (
    DEFAULT_WEIGHTS,
    EvaluationResult,
    HeuristicEvaluator,
    load_run_artifact,
    save_evaluation,
)

SOLUTION_GOOD: dict[str, Any] = {
    "task_id": "task_001",
    "agent": "test-agent",
    "sql_queries": [
        """
        SELECT DISTINCT l.name,
               COALESCE(dw.avg_temp_c, 0) AS avg_temp
        FROM daily_weather dw
        JOIN locations l ON dw.location_id = l.location_id
        WHERE dw.avg_humidity BETWEEN 0 AND 100
        """
    ],
    "files": {},
}

SOLUTION_BAD_SQL_INJECTION: dict[str, Any] = {
    "task_id": "task_001",
    "agent": "test-agent",
    "sql_queries": [],
    "files": {
        "script.py": "query = f\"SELECT * FROM users WHERE name = '{name}'\"",
    },
}

SOLUTION_WITH_SECRETS: dict[str, Any] = {
    "task_id": "task_001",
    "agent": "test-agent",
    "sql_queries": ["SELECT 1"],
    "files": {"config.py": "password = 'supersecret123'"},
}


class TestCorrectnessScoring:
    def test_with_executor_success(self) -> None:
        def fake_executor(sql: str) -> tuple[list[str], list[tuple]]:
            return ["name"], [("Kathmandu",)]

        evaluator = HeuristicEvaluator(execute_query=fake_executor)
        result = evaluator.evaluate(SOLUTION_GOOD)
        assert result.scores["correctness"] == 1.0
        assert result.evaluated_sql is True

    def test_with_executor_query_fails(self) -> None:
        def fake_executor(_sql: str) -> tuple[list[str], list[tuple]]:
            raise RuntimeError("syntax error")

        evaluator = HeuristicEvaluator(execute_query=fake_executor)
        result = evaluator.evaluate(SOLUTION_GOOD)
        assert result.scores["correctness"] == 0.0
        assert any("Query failed" in f for f in result.findings)

    def test_with_executor_empty_rows(self) -> None:
        def fake_executor(_sql: str) -> tuple[list[str], list[tuple]]:
            return ["name"], []

        evaluator = HeuristicEvaluator(execute_query=fake_executor)
        result = evaluator.evaluate(SOLUTION_GOOD)
        assert result.scores["correctness"] == 0.0

    def test_without_executor_not_scored(self) -> None:
        evaluator = HeuristicEvaluator()
        result = evaluator.evaluate(SOLUTION_GOOD)
        assert "correctness" not in result.scores
        assert any("not scored" in f for f in result.findings)

    def test_query_output_captured(self) -> None:
        def fake_executor(_sql: str) -> tuple[list[str], list[tuple]]:
            return ["name", "date", "temp"], [
                ("Kathmandu", date(2026, 11, 8), Decimal("15.4")),
                ("New York", date(2026, 11, 9), Decimal("12.4")),
            ]

        evaluator = HeuristicEvaluator(execute_query=fake_executor)
        result = evaluator.evaluate(SOLUTION_GOOD)

        assert len(result.query_results) == 1
        captured = result.query_results[0]
        assert captured["status"] == "ok"
        assert captured["row_count"] == 2
        assert captured["columns"] == ["name", "date", "temp"]
        assert captured["rows"] == [
            ["Kathmandu", "2026-11-08", "15.4"],
            ["New York", "2026-11-09", "12.4"],
        ]

    def test_query_error_captured(self) -> None:
        def fake_executor(_sql: str) -> tuple[list[str], list[tuple]]:
            raise RuntimeError("syntax error")

        evaluator = HeuristicEvaluator(execute_query=fake_executor)
        result = evaluator.evaluate(SOLUTION_GOOD)

        assert len(result.query_results) == 1
        captured = result.query_results[0]
        assert captured["status"] == "error"
        assert "syntax error" in captured["error"]
        assert "query" in captured

    def test_rows_truncated_to_cap(self) -> None:
        def fake_executor(_sql: str) -> tuple[list[str], list[tuple]]:
            return ["n"], [(i,) for i in range(100)]

        evaluator = HeuristicEvaluator(execute_query=fake_executor)
        result = evaluator.evaluate(SOLUTION_GOOD)

        captured = result.query_results[0]
        assert captured["row_count"] == 100
        assert len(captured["rows"]) == 50

    def test_query_results_json_serializable(self) -> None:
        def fake_executor(_sql: str) -> tuple[list[str], list[tuple]]:
            return ["d"], [(date(2026, 11, 8),)]

        evaluator = HeuristicEvaluator(execute_query=fake_executor)
        result = evaluator.evaluate(SOLUTION_GOOD)
        json.dumps(result.to_dict())  # must not raise


class TestDataQualityScoring:
    def test_good_patterns_scored(self) -> None:
        evaluator = HeuristicEvaluator()
        result = evaluator.evaluate(SOLUTION_GOOD)
        assert result.scores["data_quality"] >= 0.6

    def test_no_sql_scored_zero(self) -> None:
        evaluator = HeuristicEvaluator()
        result = evaluator.evaluate({"task_id": "t", "sql_queries": [], "files": {}})
        assert result.scores["data_quality"] == 0.0


class TestSecurityScoring:
    def test_clean_solution_full_score(self) -> None:
        evaluator = HeuristicEvaluator()
        result = evaluator.evaluate(SOLUTION_GOOD)
        assert result.scores["security"] == 1.0

    def test_sql_injection_detected(self) -> None:
        evaluator = HeuristicEvaluator()
        result = evaluator.evaluate(SOLUTION_BAD_SQL_INJECTION)
        assert result.scores["security"] < 1.0
        assert any("injection" in f.lower() for f in result.findings)

    def test_hardcoded_password_detected(self) -> None:
        evaluator = HeuristicEvaluator()
        result = evaluator.evaluate(SOLUTION_WITH_SECRETS)
        assert result.scores["security"] < 1.0
        assert any("password" in f.lower() for f in result.findings)


class TestDebtScoring:
    def test_select_star_penalized(self) -> None:
        evaluator = HeuristicEvaluator()
        result = evaluator.evaluate(
            {"task_id": "t", "sql_queries": ["SELECT * FROM t"], "files": {}}
        )
        assert result.scores["technical_debt"] < 1.0
        assert any("SELECT *" in f for f in result.findings)

    def test_clean_sql_full_score(self) -> None:
        evaluator = HeuristicEvaluator()
        result = evaluator.evaluate(
            {"task_id": "t", "sql_queries": ["SELECT id FROM t"], "files": {}}
        )
        assert result.scores["technical_debt"] == 1.0


class TestGovernanceScoring:
    def test_destructive_sql_penalized(self) -> None:
        evaluator = HeuristicEvaluator()
        result = evaluator.evaluate(
            {"task_id": "t", "sql_queries": ["DROP TABLE daily_weather;"], "files": {}}
        )
        assert result.scores["governance"] < 1.0
        assert any("destructive" in f.lower() for f in result.findings)

    def test_clean_solution_full_score(self) -> None:
        evaluator = HeuristicEvaluator()
        result = evaluator.evaluate(SOLUTION_GOOD)
        assert result.scores["governance"] == 1.0


class TestWeightedTotal:
    def test_total_renormalized_when_dim_missing(self) -> None:
        evaluator = HeuristicEvaluator()
        result = evaluator.evaluate(SOLUTION_GOOD)
        # correctness is not scored (no executor) -> total uses 4 dims
        expected_weight_sum = sum(
            DEFAULT_WEIGHTS[d] for d in result.scores if result.scores[d] is not None
        )
        assert expected_weight_sum == pytest.approx(0.65)
        assert 0.0 <= result.total <= 1.0

    def test_result_type(self) -> None:
        evaluator = HeuristicEvaluator()
        result = evaluator.evaluate(SOLUTION_GOOD)
        assert isinstance(result, EvaluationResult)
        assert result.task_id == "task_001"


class TestPersistence:
    def test_save_and_load_roundtrip(self, tmp_path: Any) -> None:
        evaluator = HeuristicEvaluator()
        result = evaluator.evaluate(SOLUTION_GOOD)
        path = save_evaluation(result, tmp_path)
        assert path.exists()
        assert path.parent.name == "evaluations"

    def test_load_run_artifact_missing(self, tmp_path: Any) -> None:
        with pytest.raises(FileNotFoundError):
            load_run_artifact(tmp_path / "nonexistent.json")

    def test_load_run_artifact(self, tmp_path: Any) -> None:
        artifact = tmp_path / "run.json"
        artifact.write_text(json.dumps(SOLUTION_GOOD), encoding="utf-8")
        data = load_run_artifact(artifact)
        assert data["task_id"] == "task_001"
