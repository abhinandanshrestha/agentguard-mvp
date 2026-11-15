"""Command-line interface for AgentGuard.

Provides commands for managing benchmarks, running experiments,
and analyzing results.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from agentguard import __version__
from agentguard.agent.factory import AgentNotConfiguredError, create_agent
from agentguard.agent.llm_client import LLMError
from agentguard.benchmark.tasks import (
    TaskNotFoundError,
    TaskValidationError,
    load_all_tasks,
    load_task,
)
from agentguard.config import Settings, get_settings
from agentguard.evaluator import HeuristicEvaluator, load_run_artifact, save_evaluation
from agentguard.storage import Database, DatabaseError


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all subcommands.

    Returns:
        ArgumentParser: Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="agentguard",
        description="AgentGuard: Evaluating and Governing AI Agents in Data Engineering Workflows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  agentguard info                    Show configuration info
  agentguard benchmark list          List available benchmark tasks
  agentguard benchmark run task_001  Run task_001 with the LLM agent
  agentguard benchmark run task_001 --agent mock   Run with MockAgent
  agentguard benchmark show task_001 Show task details
  agentguard experiment run          Run a full experiment
  agentguard results summary         Show experiment results summary

For more information, see: https://github.com/agentguard/agentguard
""",
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"agentguard {__version__}",
    )

    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        metavar="<command>",
    )

    # Info command
    info_parser = subparsers.add_parser(
        "info",
        help="Show configuration and environment info",
        description="Display current configuration, Python version, and environment details.",
    )
    info_parser.set_defaults(func=cmd_info)

    # Benchmark commands
    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="Manage benchmark tasks",
        description="List, inspect, and run benchmark tasks.",
    )
    benchmark_subparsers = benchmark_parser.add_subparsers(
        title="benchmark commands",
        dest="benchmark_command",
        metavar="<subcommand>",
    )

    benchmark_list = benchmark_subparsers.add_parser(
        "list",
        help="List available benchmark tasks",
    )
    benchmark_list.set_defaults(func=cmd_benchmark_list)

    benchmark_run = benchmark_subparsers.add_parser(
        "run",
        help="Run a benchmark task with an agent",
    )
    benchmark_run.add_argument(
        "task_id",
        nargs="?",
        default=None,
        help="Task ID to run (e.g., task_001)",
    )
    benchmark_run.add_argument(
        "--agent",
        choices=["llm", "mock"],
        default=None,
        help="Agent to use (default: from AGENTGUARD_LLM_PROVIDER)",
    )
    benchmark_run.add_argument(
        "--save",
        action="store_true",
        default=True,
        help="Save the solution to the results directory (default: True)",
    )
    benchmark_run.add_argument(
        "--no-evaluate",
        action="store_true",
        help="Skip automatic evaluation after solving",
    )
    benchmark_run.set_defaults(func=cmd_benchmark_run)

    benchmark_show = benchmark_subparsers.add_parser(
        "show",
        help="Show details of a benchmark task",
    )
    benchmark_show.add_argument(
        "task_id",
        help="Task ID to show (e.g., task_001)",
    )
    benchmark_show.set_defaults(func=cmd_benchmark_show)

    # Evaluate command
    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="Evaluate a saved agent solution",
        description="Run the five-dimension evaluation on a saved run artifact.",
    )
    evaluate_parser.add_argument(
        "--run",
        help="Path to a run artifact JSON (default: latest in results/runs)",
    )
    evaluate_parser.set_defaults(func=cmd_evaluate)

    # DB commands
    db_parser = subparsers.add_parser(
        "db",
        help="Database operations",
        description="Create the benchmark schema and load fetched data.",
    )
    db_subparsers = db_parser.add_subparsers(
        title="db commands",
        dest="db_command",
        metavar="<subcommand>",
    )

    db_load = db_subparsers.add_parser(
        "load",
        help="Recreate schema and load CSV data into PostgreSQL",
        description=(
            "Drops all existing benchmark tables/views, recreates the schema "
            "from scratch, and loads the CSV data fresh."
        ),
    )
    db_load.add_argument(
        "--data-dir",
        default=None,
        help="Directory with CSV files (default: benchmark/weather_platform/data)",
    )
    db_load.add_argument(
        "--no-recreate",
        action="store_true",
        help="Do not drop existing objects; apply schema.sql as-is (IF NOT EXISTS)",
    )
    db_load.set_defaults(func=cmd_db_load)

    db_verify = db_subparsers.add_parser(
        "verify",
        help="Check table row counts and data quality",
    )
    db_verify.set_defaults(func=cmd_db_verify)

    # Experiment commands
    experiment_parser = subparsers.add_parser(
        "experiment",
        help="Manage experiments",
        description="Run and manage research experiments.",
    )
    experiment_subparsers = experiment_parser.add_subparsers(
        title="experiment commands",
        dest="experiment_command",
        metavar="<subcommand>",
    )

    experiment_run = experiment_subparsers.add_parser(
        "run",
        help="Run an experiment",
    )
    experiment_run.add_argument(
        "--config",
        help="Path to experiment config YAML",
    )
    experiment_run.set_defaults(func=cmd_experiment_run)

    # Results commands
    results_parser = subparsers.add_parser(
        "results",
        help="Analyze experiment results",
        description="View and analyze experiment results.",
    )
    results_subparsers = results_parser.add_subparsers(
        title="results commands",
        dest="results_command",
        metavar="<subcommand>",
    )

    results_summary = results_subparsers.add_parser(
        "summary",
        help="Show results summary",
    )
    results_summary.set_defaults(func=cmd_results_summary)

    return parser


def cmd_info(_args: argparse.Namespace) -> int:
    """Show configuration and environment info."""
    settings = get_settings()

    print(f"AgentGuard v{__version__}")
    print()
    print("Python:")
    print(f"  Version:    {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print(f"  Supported:  {'Yes' if sys.version_info[:2] == (3, 10) else 'No (requires 3.10.x)'}")
    print()
    print("Configuration:")
    print(f"  Environment:    {settings.environment}")
    print(f"  Database:       {settings.safe_database_url}")
    print(f"  Max Attempts:   {settings.max_agent_attempts}")
    print(f"  Log Level:      {settings.log_level}")
    print()
    print("LLM:")
    print(f"  Provider:     {settings.llm_provider}")
    print(f"  Base URL:     {settings.llm_base_url}")
    print(f"  Model:        {settings.llm_model}")
    print(f"  API Key:      {settings.safe_llm_api_key}")
    print(f"  Temperature:  {settings.llm_temperature}")
    print(f"  Max Tokens:   {settings.llm_max_tokens}")
    print(f"  Configured:   {'Yes' if settings.llm_configured else 'No'}")
    print()
    print("Paths:")
    print(f"  Benchmark:  {settings.benchmark_dir}")
    print(f"    Exists:   {settings.benchmark_dir.exists()}")
    print(f"  Policies:   {settings.policies_path}")
    print(f"    Exists:   {settings.policies_path.exists()}")
    print(f"  Results:    {settings.results_dir}")
    print(f"    Exists:   {settings.results_dir.exists()}")

    return 0


def cmd_benchmark_list(_args: argparse.Namespace) -> int:
    """List available benchmark tasks."""
    settings = get_settings()
    tasks_dir = settings.benchmark_dir / "tasks"

    if not tasks_dir.exists():
        print(f"Error: Benchmark tasks directory not found: {tasks_dir}")
        print("Run 'python scripts/generate_data.py' to initialize the benchmark.")
        return 1

    tasks = load_all_tasks(tasks_dir)
    if not tasks:
        print("No benchmark tasks found.")
        return 0

    print(f"Available benchmark tasks ({len(tasks)}):")
    print()
    print(f"  {'ID':<12} {'Difficulty':<10} Name")
    print(f"  {'-' * 12} {'-' * 10} {'-' * 40}")
    for task in tasks:
        print(f"  {task.id:<12} {task.difficulty:<10} {task.name}")

    return 0


def cmd_benchmark_show(args: argparse.Namespace) -> int:
    """Show details of a benchmark task."""
    settings = get_settings()
    tasks_dir = settings.benchmark_dir / "tasks"

    try:
        task = load_task(args.task_id, tasks_dir)
    except (TaskNotFoundError, TaskValidationError) as e:
        print(f"Error: {e}")
        return 1

    print(f"Task:      {task.id}")
    print(f"Name:      {task.name}")
    print(f"Difficulty: {task.difficulty}")
    print(f"File:      {task.file_path}")
    print()
    print("Description:")
    print(f"  {task.description.strip()}")
    print()
    print("Tags:")
    print(f"  {', '.join(task.tags)}")

    return 0


def _save_solution(solution: Any, settings: Any) -> Path:
    """Save an agent solution to the results directory.

    Args:
        solution: AgentSolution to save.
        settings: AgentGuard settings.

    Returns:
        Path to the saved solution file.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = settings.results_dir / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)

    out_path = run_dir / f"{solution.task_id}_{timestamp}.json"
    payload = {
        "task_id": solution.task_id,
        "agent": solution.metadata.get("model", "unknown"),
        "created_at": datetime.now().isoformat(),
        "sql_queries": solution.sql_queries,
        "files": solution.files,
        "reasoning": solution.reasoning,
        "raw_response": solution.raw_response,
        "attempts": solution.attempts,
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return out_path


def _print_solution_overview(solution: Any) -> None:
    """Print the reasoning, SQL queries, and files produced by the agent."""
    print("Reasoning:")
    if solution.reasoning:
        for line in solution.reasoning.splitlines()[:20]:
            print(f"  {line}")
    print()
    print(f"SQL queries found: {len(solution.sql_queries)}")
    for i, query in enumerate(solution.sql_queries, 1):
        print(f"  --- Query {i} ---")
        for line in query.splitlines():
            print(f"  {line}")
    print()
    if solution.files:
        print(f"Files produced: {len(solution.files)}")
        for name in solution.files:
            print(f"  - {name}")
        print()


def cmd_benchmark_run(args: argparse.Namespace) -> int:
    """Run a benchmark task with an agent."""
    if not args.task_id:
        print("Error: task_id is required")
        print("Usage: agentguard benchmark run <task_id>")
        return 1

    settings = get_settings()
    tasks_dir = settings.benchmark_dir / "tasks"

    try:
        task = load_task(args.task_id, tasks_dir)
    except (TaskNotFoundError, TaskValidationError) as e:
        print(f"Error: {e}")
        return 1

    # Determine agent type (--agent mock forces MockAgent; --agent llm uses
    # whatever LLM provider is configured in settings)
    if args.agent == "mock":
        settings_dict = settings.model_dump()
        settings_dict["llm_provider"] = "mock"
        settings = Settings(**settings_dict)

    try:
        agent = create_agent(settings)
    except AgentNotConfiguredError as e:
        print(f"Error: {e}")
        return 1

    print("=" * 60)
    print("AgentGuard - Benchmark Task Run")
    print("=" * 60)
    print()
    print(f"Task:          {task.id} - {task.name}")
    print(f"Difficulty:    {task.difficulty}")
    print(f"Agent:         {agent.name}")
    print()

    try:
        solution = agent.solve_task(task.to_dict())
    except LLMError as e:
        print(f"Error: LLM call failed: {e}")
        return 1

    if solution.is_empty:
        print("Error: Agent returned an empty solution")
        return 1

    _print_solution_overview(solution)

    out_path = _save_solution(solution, settings)
    print(f"Solution saved to: {out_path}")

    # Record the run in the benchmark_runs metadata table (best effort)
    database = _get_database(settings)
    if database is not None:
        _record_run_in_database(
            database,
            solution.task_id,
            solution.metadata.get("model", agent.name),
            solution.sql_queries,
            out_path,
        )

    # Auto-evaluate unless disabled
    if not args.no_evaluate:
        result = _evaluate_solution(
            {
                "task_id": solution.task_id,
                "agent": solution.metadata.get("model", agent.name),
                "sql_queries": solution.sql_queries,
                "files": solution.files,
            },
            settings,
            database,
            run_artifact=out_path,
        )
        _print_evaluation(result)

    return 0


def _get_database(settings: Any) -> Any:
    """Create a Database connection, returning None with a warning on failure."""
    try:
        return Database.from_settings(settings)
    except DatabaseError as e:
        print(f"Warning: database not available - {e}")
        return None


def _print_evaluation(result: Any) -> None:
    """Print an evaluation result as a formatted table."""
    print()
    print("-" * 60)
    print("Evaluation Results")
    print("-" * 60)
    labels = [
        ("correctness", "Correctness"),
        ("data_quality", "Data Quality"),
        ("security", "Security"),
        ("technical_debt", "Technical Debt"),
        ("governance", "Governance"),
    ]
    for key, label in labels:
        if key in result.scores:
            print(f"  {label:<16} {result.scores[key]:>8.2f}")
        else:
            print(f"  {label:<16} {'n/a':>8}")

    print()
    print(f"  TOTAL SCORE      {result.total:>8.2f}")
    print(f"  SQL executed:    {result.evaluated_sql}")

    if result.evaluated_sql and result.query_results:
        print()
        print("  Query outputs:")
        for i, query_result in enumerate(result.query_results, 1):
            if query_result.get("status") == "ok":
                row_count = int(query_result.get("row_count", 0))
                print(f"    Query {i}: {row_count} row(s)")
                for row in query_result.get("rows", [])[:5]:
                    print(f"      {row}")
                remaining = row_count - len(query_result.get("rows", []))
                if remaining > 0:
                    print(f"      ... {remaining} more row(s) (see saved evaluation)")
            else:
                print(f"    Query {i}: execution error (see saved evaluation)")

    if result.findings:
        print()
        print("  Findings:")
        for finding in result.findings:
            print(f"    - {finding}")


def _record_run_in_database(
    database: Any,
    task_id: str,
    agent_name: str,
    sql_queries: list[str],
    run_artifact: Path,
) -> None:
    """Record a benchmark run in the benchmark_runs metadata table (best effort)."""
    try:
        database.ensure_runs_table()
        database.record_run(
            task_id=task_id,
            agent=agent_name,
            sql_queries=sql_queries,
            run_artifact=str(run_artifact),
        )
        print("Run recorded in benchmark_runs table.")
    except Exception as e:
        print(f"Warning: could not record run in database: {e}")


def _evaluate_solution(
    solution: dict[str, Any],
    settings: Any,
    database: Any = None,
    run_artifact: Path | None = None,
) -> Any:
    """Evaluate a solution dict and persist the result.

    Args:
        solution: Solution dict (task_id, agent, sql_queries, files).
        settings: AgentGuard settings.
        database: Optional Database instance for execution-based scoring.
        run_artifact: Optional path of the source run artifact; when
            provided the evaluation is attached to the benchmark_runs row.

    Returns:
        EvaluationResult.
    """
    executor = database.execute_readonly_query if database else None
    evaluator = HeuristicEvaluator(execute_query=executor)
    result = evaluator.evaluate(solution)
    path = save_evaluation(result, settings.results_dir)
    print(f"Evaluation saved to: {path}")

    if database is not None and run_artifact is not None:
        try:
            database.ensure_runs_table()
            database.record_evaluation(
                run_artifact=str(run_artifact),
                evaluation_artifact=str(path),
                scores=result.scores,
                total=result.total,
                findings=result.findings,
                query_results=result.query_results,
                evaluated_at=result.evaluated_at,
            )
            print("Evaluation recorded in benchmark_runs table.")
        except Exception as e:
            print(f"Warning: could not record evaluation in database: {e}")

    return result


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Evaluate a saved agent solution."""
    settings = get_settings()
    runs_dir = settings.results_dir / "runs"

    if args.run:
        run_path = Path(args.run)
    else:
        candidates = sorted(runs_dir.glob("*.json")) if runs_dir.exists() else []
        if not candidates:
            print("Error: no run artifacts found in results/runs/")
            print("Run a task first: agentguard benchmark run task_001")
            return 1
        run_path = candidates[-1]

    try:
        solution = load_run_artifact(run_path)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    print(f"Evaluating run artifact: {run_path}")
    database = _get_database(settings)
    if database is not None:
        # Upsert the run row so artifacts predating run-logging are covered
        _record_run_in_database(
            database,
            str(solution.get("task_id", "unknown")),
            str(solution.get("agent", "unknown")),
            list(solution.get("sql_queries") or []),
            run_path,
        )
    result = _evaluate_solution(solution, settings, database, run_artifact=run_path)
    _print_evaluation(result)
    return 0


def cmd_db_load(args: argparse.Namespace) -> int:
    """Create schema and load CSV data into PostgreSQL."""
    settings = get_settings()
    data_dir = (
        Path(args.data_dir)
        if args.data_dir
        else settings.benchmark_dir / "weather_platform" / "data"
    )
    schema_path = settings.benchmark_dir / "weather_platform" / "sql" / "schema.sql"

    if not data_dir.exists():
        print(f"Error: data directory not found: {data_dir}")
        print("Fetch data first: uv run python scripts/generate_data.py --size small")
        return 1

    print("=" * 60)
    print("AgentGuard - Database Load (Full Recreate)")
    print("=" * 60)
    print()
    print(f"Database:  {settings.safe_database_url}")
    print(f"Data dir:  {data_dir}")
    print()

    database = _get_database(settings)
    if database is None:
        print()
        print("Error: cannot proceed without a database connection.")
        return 1

    try:
        if args.no_recreate:
            print(f"Applying schema (no drop): {schema_path}")
            database.create_schema(schema_path)
            print("  Schema applied (existing objects kept).")
        else:
            print("Dropping existing benchmark tables and views...")
            database.drop_all()
            print("  All benchmark objects dropped.")
            print()
            print(f"Recreating schema: {schema_path}")
            database.create_schema(schema_path)
            print("  Schema recreated from scratch.")
        print()

        print("Loading CSV data...")
        counts = database.load_csvs(data_dir, truncate=True)
        print()
        for table, count in counts.items():
            print(f"  {table:<20} {count:>8,} rows")
    except Exception as e:
        print(f"Error: {e}")
        return 1

    print()
    print("Database load complete.")
    return 0


def cmd_db_verify(_args: argparse.Namespace) -> int:
    """Check table row counts and data quality."""
    settings = get_settings()

    database = _get_database(settings)
    if database is None:
        return 1

    try:
        counts = database.table_counts()
        print("Table row counts:")
        for table, count in counts.items():
            print(f"  {table:<20} {count:>8,}")
        print()

        quality = database.quality_summary()
        if quality:
            print("Data quality summary:")
            for table, metrics in quality.items():
                print(f"  {table}:")
                for key, value in metrics.items():
                    if key != "table_name":
                        print(f"    {key:<24} {value}")
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


def cmd_experiment_run(_args: argparse.Namespace) -> int:
    """Run an experiment."""
    print("Running experiment...")
    print("Note: Full implementation pending")
    return 0


def cmd_results_summary(_args: argparse.Namespace) -> int:
    """Show results summary."""
    print("Results summary...")
    print("Note: Full implementation pending")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Main entry point for the CLI.

    Args:
        argv: Command-line arguments. Uses sys.argv if None.

    Returns:
        int: Exit code (0 for success, non-zero for errors).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if hasattr(args, "func"):
        return args.func(args)

    # Handle subcommand groups without specific command
    if args.command == "benchmark" and args.benchmark_command is None:
        parser.parse_args(["benchmark", "--help"])
    elif args.command == "db" and args.db_command is None:
        parser.parse_args(["db", "--help"])
    elif args.command == "experiment" and args.experiment_command is None:
        parser.parse_args(["experiment", "--help"])
    elif args.command == "results" and args.results_command is None:
        parser.parse_args(["results", "--help"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
