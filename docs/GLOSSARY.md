# AgentGuard Terminology Guide

This document explains all the key terms and concepts you need to understand the
AgentGuard project. Read this before diving into the code.

---

## Table of Contents

1. [AI / LLM Concepts](#1-ai--llm-concepts)
2. [Agent Concepts](#2-agent-concepts)
3. [Benchmark Concepts](#3-benchmark-concepts)
4. [Evaluation Concepts](#4-evaluation-concepts)
5. [Data Engineering Concepts](#5-data-engineering-concepts)
6. [Database Concepts](#6-database-concepts)
7. [API Concepts](#7-api-concepts)
8. [Python / Tooling Concepts](#8-python--tooling-concepts)
9. [AgentGuard-Specific Terms](#9-agentguard-specific-terms)

---

## 1. AI / LLM Concepts

### LLM (Large Language Model)
An AI model trained on massive amounts of text that can generate human-like
responses. Examples: GPT-4o, Claude, Gemini, DeepSeek, Llama.

In AgentGuard: The LLM is the "brain" of the agent being tested. You give it a
data engineering task, it writes SQL/code, and AgentGuard evaluates the result.

### API Key
A secret token that authenticates your requests to an API service
(e.g., `sk-proj-abc123...`). Like a password for programs.

In AgentGuard: You need two API keys — `WEATHERAPI_KEY` (fetches weather data)
and `AGENTGUARD_LLM_API_KEY` (powers the agent). Both live in `.env`.

### API Endpoint / Base URL
The web address where an API can be reached
(e.g., `https://api.openai.com/v1`).

In AgentGuard: `AGENTGUARD_LLM_BASE_URL` points to any OpenAI-compatible API.
Change it to use OpenRouter, DeepSeek, Groq, or a local Ollama instance.

### OpenAI-Compatible API
An API that follows the same request/response format as OpenAI's chat
completions endpoint (`POST /v1/chat/completions`). Many providers
(OpenRouter, DeepSeek, Groq, Ollama, LM Studio) adopt this format.

In AgentGuard: Our `LLMClient` speaks this format, so **any** of these
providers works without code changes — just swap the base URL, model, and key.

### Chat Completions
The standard LLM API pattern: you send a list of messages (conversation
history), the model returns a new message.

```
Request:  [{role: "system", ...}, {role: "user", ...}]
Response: {choices: [{message: {role: "assistant", content: "..."}}]}
```

### Messages / Roles
The parts of a chat completion request:

| Role | Purpose |
|------|---------|
| `system` | Sets the model's behavior/persona ("You are a data engineer...") |
| `user` | The actual question or task from the user |
| `assistant` | The model's previous responses (for conversation history) |

In AgentGuard: `SYSTEM_PROMPT` in `agent/providers/openai_compatible.py` sets
the persona; the task YAML content becomes the user message.

### System Prompt
The `system` message that instructs the LLM how to behave throughout the
conversation. It's invisible to the end user but shapes all responses.

In AgentGuard: Defines the agent as a data engineer, specifies the exact
response format (reasoning + ```sql blocks + FILE: declarations).

### Token
The basic unit of text that LLMs process — roughly 4 characters or ¾ of a
word in English. "temperature" and "max_tokens" are measured in tokens.

- **max_tokens**: The maximum length of the LLM's response. Too low = response
  gets cut off mid-query.
- Context window: The maximum total tokens (input + output) a model can
  process at once.

### Temperature
A number (0.0–2.0) controlling randomness of LLM output:

| Value | Behavior | Use Case |
|-------|----------|----------|
| 0.0 | Deterministic — same prompt, same output | Reproducible benchmarks |
| 0.2–0.5 | Focused, mostly consistent | **AgentGuard default (0.2)** |
| 1.0+ | Creative, varied | Creative writing |

In AgentGuard: Lower temperature = more reproducible benchmark runs, which is
important for research comparing agents.

### Hallucination
When an LLM confidently generates false information — e.g., inventing a table
or column that doesn't exist in your schema.

In AgentGuard: The system prompt explicitly forbids inventing tables/columns,
and the evaluator checks whether generated SQL only references real schema
objects.

### Rate Limiting
API providers restrict how many requests you can make per minute/hour/month
(e.g., HTTP 429 "Too Many Requests").

In AgentGuard: The weather fetcher sleeps 0.5s between API calls;
`LLMClient` retries with exponential backoff on 429/5xx errors.

---

## 2. Agent Concepts

### Agent
An AI system that can perceive a task, plan, and take actions (write code,
run queries) to accomplish it. An LLM alone is not an agent — an agent is
LLM + tools + a task loop.

In AgentGuard: The agent receives a benchmark task and produces a solution.
It **never evaluates itself** — that's the evaluator's job (separation of
powers).

### Agent Solution
The output an agent produces for a task: SQL queries, files (scripts,
migrations), and reasoning text. Stored as `AgentSolution` in
`agent/base.py`.

### Tool (Agent Tool)
A capability given to an agent, e.g.:
- `read_file` — read repository files
- `write_file` — create/modify files
- `run_sql` — execute a SQL query against the database
- `run_tests` — execute the test suite

In AgentGuard (future work): Tasks like the ETL pipeline (task_004) will need
the agent to actually run code. Today the agent only *produces* text output.

### MockAgent
A fake agent that returns a fixed, deterministic solution without calling
any LLM. Used to test the pipeline end-to-end for free.

```bash
agentguard benchmark run task_001 --agent mock
```

### Provider
The company/service behind an LLM API (OpenAI, Anthropic, DeepSeek...).
AgentGuard abstracts this away: any OpenAI-compatible endpoint works.

---

## 3. Benchmark Concepts

### Benchmark
A standardized set of tasks + evaluation criteria used to measure and compare
system performance. Like an exam for AI agents.

In AgentGuard: 10 tasks in `benchmark/tasks/task_001.yaml` … `task_010.yaml`
covering SQL analytics, data quality, ETL, security, and governance.

### Benchmark Task
A single unit of work given to an agent, defined declaratively in YAML
(NOT hardcoded in Python). Each task has:

```yaml
id: task_001           # unique identifier
name: Monthly Temperature Analysis
difficulty: easy       # easy | medium | hard
description: |         # what the task is about
context: |             # background story for the agent
schema_hint: |         # what tables/columns exist
task: |                # the actual instructions
evaluation:            # how the solution will be scored
hints:                 # optional hints
tags:                  # categorization
```

### Why YAML (declarative) tasks?
- Add/modify tasks without touching Python code
- Tasks are data, not logic — easy to version, review, and share
- The same task file works for any agent

### Ground Truth / Reference Solution
The "correct answer" for a task, used by the evaluator to compare against
the agent's output. **Not yet implemented** — a key piece of future work.

### Data Quality Issues (Injected)
Deliberately introduced defects in the benchmark data to test whether agents
handle dirty data:

| Issue | Rate | Example |
|-------|------|---------|
| Duplicates | ~2% | Same (location_id, date) appearing twice |
| Nulls | ~3% | Missing temperature readings |
| Invalid values | ~1% | Humidity = 150% (impossible) |

Real-world data is messy; these test whether the agent notices and handles it
or ignores it (a quality-vs-correctness signal).

---

## 4. Evaluation Concepts

### Evaluator
The independent component that scores agent solutions. It runs *after* the
agent finishes and has no communication with the agent during solving.

**Core design principle:** The agent never sees its own score during the
first attempt — preventing it from optimizing for the metric instead of the
task.

### Evaluation Dimensions
AgentGuard scores solutions on five dimensions:

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| Correctness | 35% | Does the SQL/code actually work and give right answers? |
| Data Quality | 20% | Does it handle duplicates, nulls, invalid values? |
| Security | 20% | No SQL injection, no hardcoded credentials |
| Technical Debt | 15% | Code complexity, maintainability, test coverage |
| Governance | 10% | PII handling, policy compliance, auditability |

> These weights are **heuristic starting points**, not empirically validated.

### Scoring / Rubric
The rules used to assign scores. Each task YAML defines criteria per
dimension. Example from task_001:

```yaml
evaluation:
  correctness:
    weight: 0.4
    criteria:
      - Correct aggregation logic (AVG, MIN, MAX)
      - Proper date truncation to month
```

### Static Analysis
Analyzing code without executing it (parsing, pattern matching). Used for
security checks like detecting `f"SELECT * FROM {user_input}"` (SQL
injection risk) or `password = "hardcoded"`.

### Regression
When something that used to work breaks after a change. Test suites exist
to catch regressions — task_007 asks the agent to write those tests.

### Reproducibility
Getting the same result when an experiment is repeated. Critical for
research credibility. Supported by: fixed random seeds, low temperature,
deterministic tasks, and saved run artifacts.

---

## 5. Data Engineering Concepts

### Data Engineering
The discipline of building systems that collect, store, transform, and serve
data reliably. Distinct from data science (analysis/modeling).

### ETL (Extract, Transform, Load)
The classic data pipeline pattern:

1. **Extract** — pull data from a source (CSV files, APIs)
2. **Transform** — clean, validate, reshape the data
3. **Load** — write it into the target system (database)

In AgentGuard: task_004 asks the agent to build a weather-data ETL pipeline
from CSV files into PostgreSQL.

### Upsert
INSERT + UPDATE in one operation: insert if new, update if the record
already exists. In PostgreSQL: `INSERT ... ON CONFLICT (key) DO UPDATE ...`

### Idempotency
Running an operation multiple times has the same effect as running it once.
Critical for pipelines that may be re-run after failures.

### Incremental Load
Loading only new/changed data since the last run (vs. a full load that
processes everything each time).

### Referential Integrity
The guarantee that every foreign key points to an existing record — e.g.,
every `daily_weather.location_id` exists in the `locations` table. An
"orphan record" violates this.

---

## 6. Database Concepts

### PostgreSQL
The open-source relational database AgentGuard uses. Chosen for rich SQL
features (window functions, CTEs, materialized views) that real data
engineering relies on.

### Primary Key
Column(s) that uniquely identify each row in a table (e.g., `location_id`).

### Foreign Key
A column referencing another table's primary key, enforcing referential
integrity (`daily_weather.location_id` → `locations.location_id`).

### Constraint
A rule the database enforces on data, e.g.:

```sql
CHECK (avg_humidity >= 0 AND avg_humidity <= 100)   -- valid range
UNIQUE (location_id, date)                           -- no duplicates
NOT NULL                                             -- required value
```

In AgentGuard: task_010 asks the agent to add CHECK constraints to prevent
invalid data at the database level (defense in depth).

### Index
A lookup structure that speeds up queries (like a book's index). Indexing
`daily_weather(date)` makes date-range filters fast. Task_006 is about
choosing the right indexes.

### View
A saved query that behaves like a table:

```sql
CREATE VIEW v_monthly_averages AS SELECT ... GROUP BY ...;
SELECT * FROM v_monthly_averages;   -- use it like a table
```

### Window Function
SQL functions that compute across related rows without collapsing them:
`ROW_NUMBER() OVER (PARTITION BY location_id ORDER BY date)`.
Essential for deduplication (task_003) and ranking.

### CTE (Common Table Expression)
A named temporary result within a query: `WITH dedup AS (SELECT ...) SELECT
* FROM dedup`. Makes complex queries readable.

### EXPLAIN ANALYZE
PostgreSQL command that shows *how* a query executes (scan types, join
methods, actual timing) — the primary tool for query optimization (task_006).

### Schema Migration
A versioned, reversible change to the database structure (add a table,
column, index). Task_005 asks for migration scripts with rollback support.
Migrations are numbered (`V001__add_air_quality_table.sql`) and tracked in a
history table so every database can be brought to the same version.

---

## 7. API Concepts

### REST API
An HTTP interface exposing resources via URLs and methods
(GET/POST/PUT/DELETE). AgentGuard will expose a FastAPI REST API for
programmatic access to experiments and results.

### HTTP Status Codes

| Code | Meaning | AgentGuard Context |
|------|---------|-------------------|
| 200 | OK | Successful API call |
| 401 | Unauthorized | Wrong/missing API key |
| 404 | Not Found | Unknown task ID or endpoint |
| 429 | Too Many Requests | Rate limited → retry with backoff |
| 500 | Server Error | Provider problem → retry |

### Retry with Exponential Backoff
On transient failures (429/5xx), wait progressively longer between retries:
1s → 2s → 4s. Implemented in `LLMClient.chat()`.

### Timeout
Maximum time to wait for an API response before giving up
(`AGENTGUARD_LLM_TIMEOUT=120` seconds).

### Secrets Management
Practices for keeping credentials safe:
- Never hardcode keys in source code
- Keep secrets in `.env` (git-ignored), never committed
- Mask keys in logs (`sk-a...z` instead of the full key)
- Task_008 challenges the agent to implement this properly

---

## 8. Python / Tooling Concepts

### uv
A fast Python package manager. AgentGuard uses it for all dependency
operations:

```bash
uv sync          # install dependencies from pyproject.toml/uv.lock
uv run pytest    # run a command inside the project venv
uv add requests  # add a dependency
```

### Virtual Environment (.venv)
An isolated Python environment per project so dependencies don't conflict
between projects. `uv sync` creates `.venv/` automatically.

### pyproject.toml
The standard Python project configuration file: metadata, dependencies,
tool configs (ruff, pytest), and the `[project.scripts]` entry that creates
the `agentguard` command.

### src/ Layout
Package code lives under `src/agentguard/` rather than a top-level
`agentguard/` folder. Prevents accidentally importing from the source tree
instead of the installed package.

### Ruff
An extremely fast Python linter + formatter. Checks style, bugs, and
security:

```bash
uv run ruff check .    # lint
uv run ruff format .   # format
```

Rule codes seen in per-file-ignores: `S311` (random not for crypto),
`PLR0913` (too many args), `F401` (unused import), `E501` (line length).

### Pytest
The Python test framework AgentGuard uses:

```bash
uv run pytest            # run all tests
uv run pytest -v         # verbose
uv run pytest tests/unit # only unit tests
```

- **Unit test** — tests one piece in isolation (no DB, no network)
- **Integration test** — tests components together (with DB/API)
- **Fixture** — reusable test setup data (`@pytest.fixture`)
- **Mock** — fake object replacing a real dependency (e.g., fake LLM API)
- **Parametrize** — run the same test with many inputs

### LRU Cache
"Least Recently Used" caching. `@lru_cache` on `get_settings()` means the
settings object is created once and reused (environment variables aren't
re-read on every call).

### Type Hints
Annotations like `def solve_task(self, task: dict[str, Any]) -> AgentSolution:`
document expected types and enable tooling (mypy). `str | None` means
"string or None" (Python 3.10 union syntax).

---

## 9. AgentGuard-Specific Terms

### AgentGuard
The overall framework: benchmark tasks + agents + independent evaluator +
results storage, for researching how AI agents behave on data engineering
work.

### Research Questions (RQ1–RQ5)
The scientific questions AgentGuard is designed to answer:

| RQ | Question |
|----|----------|
| RQ1 | How often are agent solutions functionally correct but governance-unsafe? |
| RQ2 | What failure modes occur most frequently? |
| RQ3 | What's the relationship between agent productivity and technical debt? |
| RQ4 | Can evaluator-generated feedback reduce governance violations? |
| RQ5 | How do different agents/models compare? |

### Separation of Agent and Evaluator
Architectural principle: the component *solving* tasks (agent) is separate
from the component *judging* solutions (evaluator). The agent never scores
itself, preventing conflicts of interest.

### Feedback Loop
The planned cycle: agent solves → evaluator scores → feedback generator
explains violations → agent revises → evaluator re-scores. Controlled by
`AGENTGUARD_MAX_AGENT_ATTEMPTS`.

### Weather Platform
The benchmark environment: PostgreSQL schema (`locations`, `daily_weather`,
`hourly_weather`, views) + real historical data fetched from WeatherAPI.com
for 10 cities.

### Manifest
A metadata file (`manifest.json`) describing generated/fetched data: row
counts, column names, checksums. Used to verify data integrity across runs.

### Run Artifact
The saved output of one benchmark run (JSON in `results/runs/`): task ID,
agent model, SQL queries, files, reasoning, timestamp. This is what the
evaluator consumes and what makes experiments auditable.

### Evaluation Artifact
The saved score of one evaluation (JSON in `results/evaluations/`): per-
dimension scores, weighted total, findings, and whether SQL was executed.
Produced automatically after each `benchmark run` (or via
`agentguard evaluate`).

### Heuristic Evaluator
The current MVP evaluator: scores solutions via pattern analysis (regex
checks for NULL handling, injection patterns, SELECT *) plus real query
execution against PostgreSQL for correctness. Fast and dependency-free,
but not a substitute for ground-truth comparison (planned).

### Experiment
A full research run: one or more tasks × one or more agents × N repetitions,
producing comparable score data. Configured via YAML in
`experiments/configs/`.

---

## Quick Reference: Where Everything Lives

| Term | Code Location |
|------|--------------|
| Agent interface | `src/agentguard/agent/base.py` |
| Anthropic client | `src/agentguard/agent/anthropic_client.py` |
| LLM client (OpenAI-compatible) | `src/agentguard/agent/llm_client.py` |
| LLM agent | `src/agentguard/agent/providers/openai_compatible.py` |
| MockAgent | `src/agentguard/agent/mock_agent.py` |
| Agent factory | `src/agentguard/agent/factory.py` |
| Task loader | `src/agentguard/benchmark/tasks.py` |
| Task YAMLs | `benchmark/tasks/task_*.yaml` |
| DB schema | `benchmark/weather_platform/sql/schema.sql` |
| Weather fetcher | `src/agentguard/benchmark/weather_fetcher.py` |
| Config (LLM + DB + WeatherAPI) | `src/agentguard/config.py` |
| Database loader | `src/agentguard/storage/database.py` |
| Evaluator | `src/agentguard/evaluator/evaluator.py` |
| CLI | `src/agentguard/cli.py` |
| Run artifacts | `results/runs/*.json` |
| Evaluation artifacts | `results/evaluations/*.json` |

---

*Last updated: November 2024*
