"""Unit tests for the benchmark task loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentguard.benchmark.tasks import (
    TaskNotFoundError,
    TaskValidationError,
    load_all_tasks,
    load_task,
    load_task_file,
)

VALID_TASK = """\
id: task_test
name: Test Task
difficulty: easy
description: |
  A test task description.
context: |
  Some context.
schema_hint: |
  Tables: locations
task: |
  Do the thing.
hints:
  - hint one
tags:
  - sql
"""


@pytest.fixture
def tasks_dir(tmp_path: Path) -> Path:
    """Create a temp tasks directory with sample tasks."""
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "task_001.yaml").write_text(VALID_TASK, encoding="utf-8")
    (tasks_dir / "task_002.yaml").write_text(
        "id: task_002\nname: Second Task\ndescription: d\ntask: t\n",
        encoding="utf-8",
    )
    return tasks_dir


class TestLoadTaskFile:
    def test_loads_valid_task(self, tasks_dir: Path) -> None:
        task = load_task_file(tasks_dir / "task_001.yaml")
        assert task.id == "task_test"
        assert task.name == "Test Task"
        assert task.difficulty == "easy"
        assert task.hints == ["hint one"]
        assert task.tags == ["sql"]

    def test_missing_required_field_raises(self, tasks_dir: Path) -> None:
        bad = tasks_dir / "task_bad.yaml"
        bad.write_text("id: task_bad\nname: Incomplete\n", encoding="utf-8")
        with pytest.raises(TaskValidationError, match="missing required fields"):
            load_task_file(bad)

    def test_invalid_yaml_raises(self, tasks_dir: Path) -> None:
        bad = tasks_dir / "task_bad2.yaml"
        bad.write_text("id: [unclosed\n", encoding="utf-8")
        with pytest.raises(TaskValidationError, match="Invalid YAML"):
            load_task_file(bad)

    def test_non_mapping_raises(self, tasks_dir: Path) -> None:
        bad = tasks_dir / "task_bad3.yaml"
        bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(TaskValidationError, match="must be a mapping"):
            load_task_file(bad)


class TestLoadTask:
    def test_loads_by_id(self, tasks_dir: Path) -> None:
        task = load_task("task_001", tasks_dir)
        assert task.id == "task_test"

    def test_missing_task_raises(self, tasks_dir: Path) -> None:
        with pytest.raises(TaskNotFoundError):
            load_task("task_999", tasks_dir)


class TestLoadAllTasks:
    def test_loads_all_sorted(self, tasks_dir: Path) -> None:
        tasks = load_all_tasks(tasks_dir)
        assert len(tasks) == 2
        assert tasks[0].file_path is not None
        assert tasks[0].file_path.name == "task_001.yaml"

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        assert load_all_tasks(tmp_path / "nonexistent") == []

    def test_invalid_files_skipped(self, tasks_dir: Path) -> None:
        (tasks_dir / "task_broken.yaml").write_text("name: no-id\n", encoding="utf-8")
        tasks = load_all_tasks(tasks_dir)
        assert len(tasks) == 2
