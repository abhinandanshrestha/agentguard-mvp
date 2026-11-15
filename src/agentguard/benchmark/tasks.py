"""Benchmark task loading.

Loads and validates benchmark task definitions from YAML files in the
benchmark/tasks directory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class TaskNotFoundError(Exception):
    """Raised when a requested task does not exist."""


class TaskValidationError(Exception):
    """Raised when a task file is missing required fields."""


# Required top-level keys in a task YAML file
_REQUIRED_FIELDS = ("id", "name", "description", "task")


@dataclass
class BenchmarkTask:
    """A benchmark task loaded from a YAML file.

    Attributes:
        id: Unique task identifier (e.g., task_001).
        name: Human-readable task name.
        description: Task description.
        context: Background context for the agent.
        schema_hint: Database schema description.
        task: The actual task instructions.
        difficulty: Task difficulty level (easy/medium/hard).
        evaluation: Evaluation criteria and weights.
        hints: Optional hints for the agent.
        tags: Task tags.
        file_path: Path to the source YAML file.
        raw: The full parsed YAML dictionary.
    """

    id: str
    name: str
    description: str
    context: str
    schema_hint: str
    task: str
    difficulty: str = "medium"
    evaluation: dict[str, Any] = field(default_factory=dict)
    hints: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    file_path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict (used by agents)."""
        return dict(self.raw)


def load_task(task_id: str, tasks_dir: Path) -> BenchmarkTask:
    """Load a single benchmark task by ID.

    Args:
        task_id: Task identifier (e.g., 'task_001').
        tasks_dir: Directory containing task YAML files.

    Returns:
        The loaded BenchmarkTask.

    Raises:
        TaskNotFoundError: If the task file does not exist.
        TaskValidationError: If the task file is missing required fields.
    """
    file_path = tasks_dir / f"{task_id}.yaml"
    if not file_path.exists():
        raise TaskNotFoundError(f"Task file not found: {file_path}")

    return load_task_file(file_path)


def load_task_file(file_path: Path) -> BenchmarkTask:
    """Load a benchmark task from a YAML file.

    Args:
        file_path: Path to the task YAML file.

    Returns:
        The loaded BenchmarkTask.

    Raises:
        TaskValidationError: If the file is invalid or missing fields.
    """
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise TaskValidationError(f"Invalid YAML in {file_path}: {e}") from e

    if not isinstance(data, dict):
        raise TaskValidationError(f"Task file must be a mapping: {file_path}")

    missing = [key for key in _REQUIRED_FIELDS if not data.get(key)]
    if missing:
        raise TaskValidationError(
            f"Task {file_path.name} is missing required fields: {', '.join(missing)}"
        )

    return BenchmarkTask(
        id=str(data["id"]),
        name=str(data["name"]),
        description=str(data.get("description", "")),
        context=str(data.get("context", "")),
        schema_hint=str(data.get("schema_hint", "")),
        task=str(data.get("task", "")),
        difficulty=str(data.get("difficulty", "medium")),
        evaluation=data.get("evaluation", {}) or {},
        hints=list(data.get("hints", []) or []),
        tags=list(data.get("tags", []) or []),
        file_path=file_path,
        raw=data,
    )


def load_all_tasks(tasks_dir: Path) -> list[BenchmarkTask]:
    """Load all benchmark tasks from a directory.

    Args:
        tasks_dir: Directory containing task YAML files.

    Returns:
        List of BenchmarkTask objects sorted by ID. Invalid task files
        are skipped with a warning.
    """
    if not tasks_dir.exists():
        return []

    tasks: list[BenchmarkTask] = []
    for file_path in sorted(tasks_dir.glob("task_*.yaml")):
        try:
            tasks.append(load_task_file(file_path))
        except TaskValidationError as e:
            logger.warning("Skipping invalid task file: %s", e)

    return tasks
