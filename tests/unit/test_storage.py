"""Unit tests for storage database helpers (no real database needed)."""

from __future__ import annotations

import pytest

from agentguard.storage.database import DatabaseError, _assert_readonly


class TestAssertReadonly:
    def test_select_allowed(self) -> None:
        _assert_readonly("SELECT * FROM daily_weather")
        _assert_readonly("  select 1;  ")
        _assert_readonly("WITH cte AS (SELECT 1) SELECT * FROM cte")

    def test_write_statement_rejected(self) -> None:
        for sql in (
            "INSERT INTO t VALUES (1)",
            "UPDATE t SET x = 1",
            "DELETE FROM t",
            "DROP TABLE t",
            "TRUNCATE TABLE t",
            "ALTER TABLE t ADD COLUMN x INT",
            "CREATE TABLE t (x INT)",
        ):
            with pytest.raises(DatabaseError):
                _assert_readonly(sql)

    def test_injected_statement_rejected(self) -> None:
        with pytest.raises(DatabaseError, match="Forbidden"):
            _assert_readonly("SELECT 1; DROP TABLE daily_weather")

    def test_empty_rejected(self) -> None:
        with pytest.raises(DatabaseError):
            _assert_readonly("")

    def test_explain_allowed(self) -> None:
        _assert_readonly("EXPLAIN SELECT 1")
