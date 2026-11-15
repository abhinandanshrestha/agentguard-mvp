"""Benchmark task management.

This module handles loading, validating, and managing benchmark tasks.
Tasks are defined in YAML files and describe realistic data engineering
challenges for AI agents to solve.
"""

from __future__ import annotations

from agentguard.benchmark.tasks import (
    BenchmarkTask,
    TaskNotFoundError,
    TaskValidationError,
    load_all_tasks,
    load_task,
    load_task_file,
)

__all__ = [
    "BenchmarkTask",
    "TaskNotFoundError",
    "TaskValidationError",
    "load_all_tasks",
    "load_task",
    "load_task_file",
]
