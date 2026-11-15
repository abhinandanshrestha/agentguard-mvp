# AgentGuard Makefile
# Note: On Windows without make, use the 'uv run' commands directly.

.PHONY: help install sync test lint format typecheck clean data baseline api

help:
	@echo "AgentGuard Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install    Install dependencies with uv"
	@echo "  make sync       Sync dependencies (alias for install)"
	@echo ""
	@echo "Quality:"
	@echo "  make test       Run tests with pytest"
	@echo "  make lint       Run ruff linter"
	@echo "  make format     Format code with ruff"
	@echo "  make typecheck  Run mypy type checker"
	@echo ""
	@echo "Run:"
	@echo "  make data       Generate benchmark data"
	@echo "  make baseline   Run baseline experiment"
	@echo "  make api        Start FastAPI server"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean      Remove generated files"

install:
	uv sync

sync: install

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

clean:
	python -c "import shutil; import pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
	python -c "import shutil; import pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.mypy_cache', '.ruff_cache', 'htmlcov', '.coverage']]"

data:
	uv run python scripts/generate_data.py

baseline:
	uv run python scripts/run_baseline.py

api:
	uv run uvicorn agentguard.api.main:app --reload
