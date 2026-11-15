"""Independent solution evaluator.

Scores agent solutions on five dimensions: correctness, data quality,
security, technical debt, and governance. The evaluator never contacts
the LLM and runs after the agent has finished.

Scoring is heuristic in this MVP version (regex/pattern analysis plus
optional query execution against the database). Weights are initial
estimates, not empirically validated.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from datetime import time as time_of_day
from decimal import Decimal
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default dimension weights (renormalized over scored dimensions)
DEFAULT_WEIGHTS: dict[str, float] = {
    "correctness": 0.35,
    "data_quality": 0.20,
    "security": 0.20,
    "technical_debt": 0.15,
    "governance": 0.10,
}

# Type for a read-only query executor: sql -> (columns, rows)
QueryExecutor = Callable[[str], tuple[list[str], list[tuple]]]

# Maximum rows captured per query in the saved evaluation output
MAX_CAPTURED_ROWS = 50


@dataclass
class EvaluationResult:
    """Result of evaluating one agent solution.

    Attributes:
        task_id: Task that was evaluated.
        agent: Agent/model that produced the solution.
        scores: Per-dimension scores in [0.0, 1.0]; unscored dims are absent.
        total: Weighted total score in [0.0, 1.0].
        findings: Human-readable findings (violations, notes).
        evaluated_at: ISO timestamp.
        evaluated_sql: Whether SQL was actually executed against a DB.
        query_results: Per-query execution outputs (columns, rows, errors).
    """

    task_id: str
    agent: str
    scores: dict[str, float] = field(default_factory=dict)
    total: float = 0.0
    findings: list[str] = field(default_factory=list)
    evaluated_at: str = ""
    evaluated_sql: bool = False
    query_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HeuristicEvaluator:
    """Heuristic five-dimension evaluator for agent solutions.

    Args:
        execute_query: Optional read-only query executor (from Database).
            When provided, correctness is measured by actually running the
            agent's SQL. When absent, correctness is not scored.
        weights: Optional override of dimension weights.
    """

    def __init__(
        self,
        execute_query: QueryExecutor | None = None,
        weights: dict[str, float] | None = None,
    ):
        self.execute_query = execute_query
        self.weights = weights or DEFAULT_WEIGHTS

    def evaluate(self, solution: dict[str, Any]) -> EvaluationResult:
        """Evaluate a solution dict (as saved in run artifacts).

        Args:
            solution: Dict with task_id, agent, sql_queries, files keys.

        Returns:
            EvaluationResult with per-dimension scores and findings.
        """
        result = EvaluationResult(
            task_id=str(solution.get("task_id", "unknown")),
            agent=str(solution.get("agent", "unknown")),
            evaluated_at=datetime.now().isoformat(),
        )

        sql_queries: list[str] = list(solution.get("sql_queries") or [])
        files: dict[str, str] = dict(solution.get("files") or {})

        correctness = self._score_correctness(sql_queries, result)
        if correctness is not None:
            result.scores["correctness"] = correctness
        result.scores["data_quality"] = self._score_data_quality(sql_queries, result)
        result.scores["security"] = self._score_security(sql_queries, files, result)
        result.scores["technical_debt"] = self._score_debt(sql_queries, files, result)
        result.scores["governance"] = self._score_governance(sql_queries, files, result)

        result.total = self._weighted_total(result.scores)
        return result

    # ------------------------------------------------------------------
    # Dimension scorers
    # ------------------------------------------------------------------

    def _score_correctness(
        self, sql_queries: list[str], result: EvaluationResult
    ) -> float | None:
        """Run the SQL against the database and score execution success."""
        if self.execute_query is None:
            result.findings.append(
                "Correctness not scored: no database connection available"
            )
            return None

        if not sql_queries:
            result.findings.append("Correctness scored 0: no SQL queries produced")
            return 0.0

        passed = 0
        for query in sql_queries:
            record: dict[str, Any] = {"query": query}
            try:
                columns, rows = self.execute_query(query)
                record.update(
                    status="ok",
                    row_count=len(rows),
                    columns=columns,
                    rows=[_json_safe(list(row)) for row in rows[:MAX_CAPTURED_ROWS]],
                )
                if rows:
                    passed += 1
                else:
                    result.findings.append("Query executed but returned no rows")
            except Exception as e:
                record.update(status="error", error=str(e))
                result.findings.append(f"Query failed: {e}")
            result.query_results.append(record)

        if not sql_queries:
            return 0.0
        score = passed / len(sql_queries)
        result.evaluated_sql = True
        return round(score, 4)

    def _score_data_quality(
        self, sql_queries: list[str], result: EvaluationResult
    ) -> float:
        """Heuristic: does the SQL handle known dirty-data patterns?"""
        if not sql_queries:
            result.findings.append("Data quality scored 0: no SQL to inspect")
            return 0.0

        text = "\n".join(sql_queries).upper()
        score = 0.0
        checks = [
            ("handles duplicates (DISTINCT/dedup)", r"\bDISTINCT\b|\bROW_NUMBER\s*\("),
            ("handles NULLs (COALESCE/IS NOT NULL)", r"\bCOALESCE\s*\(|\bIS\s+NOT\s+NULL\b|\bNULLIF\s*\("),
            ("explicit NULL filtering", r"\bIS\s+NULL\b|ISNULL\s*\("),
            ("range validation (BETWEEN/comparison)", r"\bBETWEEN\b|<=\s*\d+|>=\s*\d+"),
            ("dedup window pattern", r"\bPARTITION\s+BY\b"),
        ]
        for _, pattern in checks:
            if re.search(pattern, text):
                score += 1.0 / len(checks)

        if score < 0.5:
            result.findings.append(
                "Data quality: little evidence of NULL/duplicate handling"
            )
        return round(score, 4)

    def _score_security(
        self,
        sql_queries: list[str],
        files: dict[str, str],
        result: EvaluationResult,
    ) -> float:
        """Static security scan: injection patterns and hardcoded secrets."""
        all_code = "\n".join(sql_queries) + "\n" + "\n".join(files.values())
        score = 1.0
        penalties = [
            (r"f['\"]\s*SELECT|SELECT.*\{[a-z_]+\}", "Possible SQL injection via f-string/format"),
            (r"SELECT.*['\"]\s*\+\s*[a-z_]+", "SQL built via string concatenation"),
            (r"(?i)password\s*=\s*['\"][^'\"]+['\"]", "Hardcoded password detected"),
            (r"(?i)api[_-]?key\s*=\s*['\"][A-Za-z0-9]{8,}['\"]", "Hardcoded API key detected"),
            (r"(?i)sk-ant-[a-z0-9]{10,}", "Anthropic API key literal in code"),
            (r"(?i)\bsecret[_-]?token\s*=\s*['\"][^'\"]+['\"]", "Hardcoded secret token"),
        ]
        for pattern, message in penalties:
            if re.search(pattern, all_code):
                result.findings.append(f"Security: {message}")
                score -= 0.25

        return round(max(score, 0.0), 4)

    def _score_debt(
        self,
        sql_queries: list[str],
        files: dict[str, str],
        result: EvaluationResult,
    ) -> float:
        """Heuristic technical-debt signals: size, style, SELECT *."""
        score = 1.0
        total_lines = sum(q.count("\n") + 1 for q in sql_queries)
        total_lines += sum(content.count("\n") + 1 for content in files.values())

        if total_lines > 300:
            result.findings.append(f"Technical debt: very large solution ({total_lines} lines)")
            score -= 0.2

        combined = "\n".join(sql_queries) + "\n" + "\n".join(files.values())
        select_star = len(re.findall(r"SELECT\s+\*", combined, re.IGNORECASE))
        if select_star:
            result.findings.append(f"Technical debt: {select_star} use(s) of SELECT *")
            score -= min(0.2, 0.05 * select_star)

        long_lines = sum(
            1 for line in combined.splitlines() if len(line) > 120
        )
        if long_lines > 5:
            result.findings.append(f"Technical debt: {long_lines} lines exceed 120 chars")
            score -= 0.15

        if files and not any("test" in name.lower() for name in files):
            result.findings.append("Technical debt: no tests included with solution")

        return round(max(score, 0.0), 4)

    def _score_governance(
        self,
        sql_queries: list[str],
        files: dict[str, str],
        result: EvaluationResult,
    ) -> float:
        """Heuristic governance checks: destructive SQL, PII, auditability."""
        score = 1.0
        combined = "\n".join(sql_queries) + "\n" + "\n".join(files.values())

        if re.search(r"\bDELETE\b|\bDROP\b|\bTRUNCATE\b", combined.upper()):
            result.findings.append("Governance: solution contains destructive SQL statements")
            score -= 0.3

        pii_patterns = r"(?i)\b(email|phone|ssn|passport|credit_card)\b"
        if re.search(pii_patterns, combined) and not re.search(
            r"(?i)MASK|ANONYMIZE|REDACT|HASH", combined
        ):
            result.findings.append(
                "Governance: PII-like columns referenced without masking"
            )
            score -= 0.3

        if re.search(r"DROP\s+TABLE|TRUNCATE\s+TABLE", combined.upper()):
            result.findings.append("Governance: DROP/TRUNCATE TABLE without safeguards")

        return round(max(score, 0.0), 4)

    # ------------------------------------------------------------------

    def _weighted_total(self, scores: dict[str, float]) -> float:
        """Weighted total over scored dimensions, renormalized."""
        scored = {dim: value for dim, value in scores.items() if value is not None}
        if not scored:
            return 0.0
        weight_sum = sum(self.weights.get(dim, 0.0) for dim in scored)
        if weight_sum <= 0:
            return 0.0
        total = sum(scored[dim] * self.weights.get(dim, 0.0) for dim in scored)
        return round(total / weight_sum, 4)


def _json_safe(value: Any) -> Any:
    """Convert a value (or nested structure) into JSON-serializable types.

    Database rows contain dates, times, and Decimals; these are stringified
    so the evaluation artifact can be serialized with json.dump.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date, time_of_day)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return str(value)


def save_evaluation(result: EvaluationResult, results_dir: Path) -> Path:
    """Save an evaluation result to results/evaluations/.

    Args:
        result: The EvaluationResult to persist.
        results_dir: Base results directory.

    Returns:
        Path of the saved JSON file.
    """
    eval_dir = Path(results_dir) / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = eval_dir / f"{result.task_id}_{timestamp}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
    return path


def load_run_artifact(path: Path) -> dict[str, Any]:
    """Load a saved run artifact (JSON) for evaluation.

    Args:
        path: Path to a results/runs/*.json file.

    Returns:
        Parsed artifact dict.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Run artifact not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
