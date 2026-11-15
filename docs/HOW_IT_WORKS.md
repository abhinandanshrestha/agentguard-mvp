# How AgentGuard Works

Diagrams and explanations of the complete flow: what AgentGuard does today,
what it's designed to do, how results are produced, and how to view them.

---

## Table of Contents

1. [Big Picture Architecture](#1-big-picture-architecture)
2. [Phase 1: Data Preparation (Implemented)](#2-phase-1-data-preparation-implemented)
3. [Phase 2: Task Solving — Current Flow (Implemented)](#3-phase-2-task-solving--current-flow-implemented)
4. [Phase 2b: Task Solving — Planned Agentic Flow](#4-phase-2b-task-solving--planned-agentic-flow)
5. [Phase 3: Evaluation (Implemented - Heuristic)](#5-phase-3-evaluation-implemented---heuristic)
6. [Results: Where They Live and How to View Them](#6-results-where-they-live-and-how-to-view-them)
7. [What's Implemented vs Planned](#7-whats-implemented-vs-planned)

---

## 1. Big Picture Architecture

AgentGuard has three independent stages. The agent never scores itself, and
the evaluator never talks to the LLM while the agent is solving.

```
                        ┌─────────────────────────────┐
                        │   STAGE 1: DATA SETUP       │
                        │   (WeatherAPI → DB)         │
                        └──────────────┬──────────────┘
                                       │
                        ┌──────────────▼──────────────┐
                        │   STAGE 2: AGENT SOLVING    │
                        │   (LLM writes SQL/code)     │
                        └──────────────┬──────────────┘
                                       │  AgentSolution (JSON)
                        ┌──────────────▼──────────────┐
                        │   STAGE 3: EVALUATION       │
                        │   (scores 5 dimensions)     │
                        └──────────────┬──────────────┘
                                       │
                        ┌──────────────▼──────────────┐
                        │   RESULTS / RESEARCH DATA   │
                        └─────────────────────────────┘
```

**Key design rule:** the agent and evaluator are strictly separated.

```
   ┌──────────┐  writes   ┌────────────┐  scores   ┌───────────┐
   │  AGENT   │──────────►│ SOLUTION   │──────────►│ EVALUATOR │
   │ (LLM)    │           │ (artifact) │           │ (code)    │
   └──────────┘           └────────────┘           └───────────┘
        ▲                                                   │
        │            never talk directly                    │
        └─────────────────── X ─────────────────────────────┘
```

---

## 2. Phase 1: Data Preparation (Implemented)

Real weather data is fetched from WeatherAPI.com and loaded into a
PostgreSQL database the benchmark tasks run against.

```
 ┌───────────────┐   GET /v1/history.json   ┌────────────────────┐
 │ WeatherAPI.com│◄─────────────────────────│  generate_data.py  │
 └───────┬───────┘   (10 cities × N days)    │  (WEATHERAPI_KEY)  │
         │                                   └─────────┬──────────┘
         │ JSON: location, daily, hourly               │
         ▼                                             │ pandas
 ┌───────────────────────┐                             │
 │ parse + normalize     │◄────────────────────────────┘
 └───────────┬───────────┘
             │ inject intentional quality issues (seed=42)
             │  • ~2% duplicates   • ~3% nulls   • ~1% invalid
             ▼
 ┌───────────────────────────────────────────────────────────┐
 │ benchmark/weather_platform/data/                          │
 │   locations.csv  daily_weather.csv  hourly_weather.csv    │
 │   manifest.json (row counts + checksums)                  │
 └───────────┬───────────────────────────────────────────────┘
             │  uv run agentguard db load
             │  (drops all benchmark objects, recreates
             │   schema.sql from scratch, loads typed CSVs)
             ▼
 ┌───────────────────────────────────────────────────────────┐
 │ PostgreSQL (agentguard database)                          │
 │   tables:  locations, daily_weather, hourly_weather,      │
 │            weather_alerts, data_quality_log               │
 │   views:   v_daily_weather_full, v_monthly_averages,      │
 │            v_extreme_weather, v_data_quality_summary      │
 └───────────────────────────────────────────────────────────┘
```

**Commands:**

```bash
# Step 1: fetch CSVs from WeatherAPI
uv run python scripts/generate_data.py --size small

# Step 2: FULL RECREATE - drops existing tables/views, applies schema.sql
#         from scratch, loads the CSVs fresh (idempotent, re-runnable)
uv run agentguard db load

# Alternative: apply schema without dropping existing objects
uv run agentguard db load --no-recreate

# Step 3: verify row counts and see injected quality issues
uv run agentguard db verify
```

**Why the dirty data?** Real-world data is messy. The injected duplicates,
nulls, and impossible values test whether the agent *notices* and *handles*
quality issues — or silently ignores them. Silent ignoring is a quality
failure even if the SQL "works".

---

## 3. Phase 2: Task Solving — Current Flow (Implemented)

What happens when you run `agentguard benchmark run task_001`.

```
 ┌───────────────────────────────────────────────────────────────────┐
 │ YOU:  uv run agentguard benchmark run task_001                    │
 └──────────────────────────────┬────────────────────────────────────┘
                                ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │ CLI (cli.py)                                                      │
 │  1. load_task("task_001") ──► benchmark/tasks/task_001.yaml       │
 │  2. create_agent(settings) ─► LLMAgent(AnthropicClient)           │
 │       provider = AGENTGUARD_LLM_PROVIDER (anthropic | mock)       │
 └──────────────────────────────┬────────────────────────────────────┘
                                ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │ LLMAgent.solve_task()                                             │
 │                                                                   │
 │   SYSTEM PROMPT (fixed persona):                                  │
 │   "You are an expert data engineer... respond with                │
 │    ## Reasoning, ```sql blocks, FILE: declarations"               │
 │                                                                   │
 │   USER PROMPT (built from task YAML):                             │
 │   # Task: Monthly Temperature Analysis                            │
 │   ## Description ... ## Context ...                               │
 │   ## Database Schema (schema_hint text) ... ## Your Task ...      │
 └──────────────────────────────┬────────────────────────────────────┘
                                ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │ LLM API CALL (one-shot)                                           │
 │                                                                   │
 │   anthropic: POST https://api.anthropic.com/v1/messages           │
 │   openai:    POST {base_url}/chat/completions                     │
 │                                                                   │
 │   retry on 429/529/5xx with exponential backoff (1s→2s→4s)        │
 └──────────────────────────────┬────────────────────────────────────┘
                                ▼  raw text response
 ┌───────────────────────────────────────────────────────────────────┐
 │ PARSE (_parse_response)                                           │
 │   regex-extract:                                                  │
 │     • ```sql blocks      ──► sql_queries[]                        │
 │     • FILE: <name> + block ─► files{}                             │
 │     • ## Reasoning       ──► reasoning                            │
 │   ──► AgentSolution                                               │
 └──────────────────────────────┬────────────────────────────────────┘
                                ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │ SAVE → results/runs/task_001_<YYYYMMDD_HHMMSS>.json               │
 │ (task_id, model, sql_queries, files, reasoning, raw_response)     │
 └──────────────────────────────┬────────────────────────────────────┘
                                ▼ (unless --no-evaluate)
 ┌───────────────────────────────────────────────────────────────────┐
 │ AUTO-EVALUATE (see Phase 3) → results/evaluations/*.json          │
 │   • runs each SQL query against your PostgreSQL database          │
 │   • scores Correctness / Data Quality / Security /                │
 │     Technical Debt / Governance                                   │
 │   • prints scores table with findings                             │
 └───────────────────────────────────────────────────────────────────┘
```

**Important:** this is a **single-shot** flow. The LLM answers blind from
the YAML's schema_hint text — it cannot see the real database, run its SQL,
or fix its own mistakes. That measures *generation quality* (a baseline),
not agentic behavior. See the next section for the planned agentic flow.

---

## 4. Phase 2b: Task Solving — Planned Agentic Flow

The target research-grade flow: a tool-use loop where the agent explores,
executes, self-corrects, and only then submits.

```
                    ┌─────────────────────────────────────┐
                    │            AGENT LOOP               │
                    │                                     │
   task prompt ────►│  ┌─────────┐      ┌─────────────┐   │
                    │  │  LLM    │─────►│ wants tool? │   │
                    │  │ (Claude)│      └──────┬──────┘   │
                    │  └─────────┘             │          │
                    │       ▲          no ┌────┴───┐ yes  │
                    │       │             │ submit │──┐   │
                    │       │             └────────┘  │   │
                    │       │                         ▼   │
                    │       │              ┌──────────────▼─┐
                    │       │              │  TOOL RESULTS  │
                    │       │              │ (observations) │
                    │       │              └────────┬───────┘
                    │       │                       │
                    │       │    ┌──────────────────┼─────────────┐
                    │       │    ▼                  ▼             ▼
                    │  ┌────┴──────┐      ┌──────────────┐ ┌──────────┐
                    │  │inspect_   │      │   run_sql    │ │read_file │
                    │  │schema     │      │ (PostgreSQL) │ │run_tests │
                    │  └───────────┘      └──────────────┘ └──────────┘
                    └─────────────────────────────────────┘
```

**Loop steps:**

1. Agent receives task + *live* schema (from `information_schema`, not YAML)
2. Agent calls `inspect_schema` → sees real tables/columns/data quirks
3. Agent writes SQL, calls `run_sql` → sees real results or a PostgreSQL error
4. On error: agent reads the error, rewrites the query, retries
5. Agent repeats until confident (or budget exhausted)
6. Agent submits final solution → `AgentSolution` → JSON artifact

**What this enables that single-shot can't:**
- Self-correction (agent fixes its own SQL errors)
- Discovery (agent finds the injected dirty data itself)
- Realistic behavior measurement (planning, tool use, iteration count)
- The revision loop uses `AGENTGUARD_MAX_AGENT_ATTEMPTS` (currently unused)

---

## 5. Phase 3: Evaluation (Implemented - Heuristic)

The evaluator consumes the saved solution artifact and scores it on five
dimensions — without ever contacting the LLM. Correctness is measured by
actually executing the agent's SQL against your PostgreSQL database.

> **Full definitions** of every metric, weight, regex check, and penalty:
> see [Evaluation Metrics](EVALUATION_METRICS.md).

```
 ┌──────────────────────┐      ┌───────────────────────────────────┐
 │ AgentSolution JSON   │      │        HEURISTIC EVALUATOR        │
 │ results/runs/*.json  │─────►│                                   │
 └──────────────────────┘      │  CORRECTNESS (35%)                │
                               │   • executes each SQL query       │
      ┌────────────────┐       │     against the real database     │
      │ PostgreSQL     │──────►│   • rows returned = pass          │
      │ (live DB)      │       │   • error / empty = fail          │
      └────────────────┘       │                                   │
                               │  DATA QUALITY (20%)               │
                               │   • regex scan: DISTINCT,         │
                               │     COALESCE, NULL handling,      │
                               │     BETWEEN, PARTITION BY         │
                               │                                   │
                               │  SECURITY (20%)                   │
                               │   • static scan: f-string SQL,    │
                               │     concatenation, hardcoded      │
                               │     passwords / API keys          │
                               │                                   │
                               │  TECHNICAL DEBT (15%)             │
                               │   • solution size, SELECT *,      │
                               │     long lines, missing tests     │
                               │                                   │
                               │  GOVERNANCE (10%)                 │
                               │   • destructive SQL (DROP/DELETE/ │
                               │     TRUNCATE), unmasked PII refs  │
                               └──────────────┬────────────────────┘
                                              ▼
                               ┌───────────────────────────────────┐
                               │  EvaluationResult JSON            │
                               │  results/evaluations/             │
                               │  {scores per dimension, weighted  │
                               │   total, findings, evaluated_sql} │
                               └──────────────┬────────────────────┘
                                              ▼
                               ┌───────────────────────────────────┐
                               │  Feedback Generator (planned)     │
                               │  (RQ4: does feedback reduce       │
                               │   violations on retry?)           │
                               └───────────────────────────────────┘
```

> **Note:** scoring is heuristic (pattern analysis + execution checks).
> Weights are initial estimates, not empirically validated. If PostgreSQL
> is unavailable, correctness is skipped and the other four dimensions are
> renormalized.

**Research questions the scores feed:**

| RQ | Question | Needs |
|----|----------|-------|
| RQ1 | Functionally correct but governance-unsafe? | Correctness + Governance scores |
| RQ2 | Most frequent failure modes? | Violation statistics across runs |
| RQ3 | Productivity vs technical debt? | Debt scores + attempt/size metrics |
| RQ4 | Does feedback reduce violations? | Revision loop + re-scoring |
| RQ5 | Compare agents/models? | Same tasks, multiple agents |

---

## 6. Results: Where They Live and How to View Them

### Result artifacts on disk

```
results/
├── runs/
│   └── task_001_20261115_222654.json     ← one file per benchmark run
└── evaluations/
    └── task_001_20261115_222700.json     ← one file per evaluation
```

### Anatomy of a run artifact

```json
{
  "task_id": "task_001",
  "agent": "claude-sonnet-4-5",
  "created_at": "2026-11-15T22:26:54",
  "sql_queries": ["SELECT l.name, ... FROM daily_weather dw ..."],
  "files": {"etl_pipeline.py": "..."},
  "reasoning": "## Reasoning ...",
  "raw_response": "<full LLM output>",
  "attempts": 1
}
```

### Anatomy of an evaluation artifact

```json
{
  "task_id": "task_001",
  "agent": "claude-sonnet-4-5",
  "scores": {
    "correctness": 1.0,
    "data_quality": 0.6,
    "security": 1.0,
    "technical_debt": 0.95,
    "governance": 1.0
  },
  "total": 0.93,
  "findings": ["Data quality: little evidence of NULL/duplicate handling"],
  "evaluated_sql": true,
  "query_results": [
    {
      "query": "SELECT ... FROM daily_weather ...",
      "status": "ok",
      "row_count": 35,
      "columns": ["location_name", "month", "avg_temp_c"],
      "rows": [["Kathmandu", "2026-11", "14.9"]]
    }
  ]
}
```

### Run history in PostgreSQL

Every `benchmark run` also upserts one row into the `benchmark_runs`
metadata table (created automatically, survives `db load`): task_id,
agent, the SQL it produced, the run/evaluation artifact paths, scores +
findings + per-query outputs (JSONB), and timestamps. `agentguard
evaluate` attaches (or re-attaches) evaluation data to the same row.

### How to view results today

```bash
# Run a task (produces run + evaluation artifacts automatically)
uv run agentguard benchmark run task_001
uv run agentguard benchmark run task_001 --agent mock   # no API cost

# Evaluate the latest saved run again
uv run agentguard evaluate

# Evaluate a specific run artifact
uv run agentguard evaluate --run results/runs/task_001_20261115_222654.json

# See everything AgentGuard knows about its config
uv run agentguard info

# Read artifacts directly
Get-Content results/runs/task_001_*.json      # Windows PowerShell
Get-Content results/evaluations/task_001_*.json
```

### Planned result commands (stubs exist, implementation pending)

```bash
uv run agentguard results summary    # aggregate scores across runs
uv run agentguard experiment run     # full experiment: N tasks × M agents × K reps
```

### Planned scored output (what `results summary` will show)

```
Task       Agent               Correct  Quality  Security  Debt  Govern  TOTAL
task_001   claude-sonnet-4-5     0.90     0.70     1.00    0.85   1.00    0.87
task_001   gpt-4o-mini           0.85     0.50     0.75    0.80   1.00    0.77
task_002   claude-sonnet-4-5     0.75     0.90     1.00    0.70   1.00    0.83
```

Weights: Correctness 35% · Data Quality 20% · Security 20% · Technical
Debt 15% · Governance 10% (heuristic defaults, renormalized over scored
dimensions).

---

## 7. What's Implemented vs Planned

| Stage | Component | Status |
|-------|-----------|--------|
| 1. Data | WeatherAPI fetcher → CSV → manifest | ✅ Implemented |
| 1. Data | PostgreSQL schema (tables + views) | ✅ Implemented (`agentguard db load`) |
| 1. Data | CSV → PostgreSQL loader (idempotent, typed) | ✅ Implemented (`agentguard db load`) |
| 1. Data | Quality verification (`db verify`, v_data_quality_summary) | ✅ Implemented |
| 2. Agent | Task YAML loading + validation | ✅ Implemented |
| 2. Agent | LLM agent (Anthropic + OpenAI-compatible) | ✅ Single-shot |
| 2. Agent | MockAgent (no API needed) | ✅ Implemented |
| 2. Agent | Tool-use agentic loop (run_sql, inspect_schema) | ⬜ Planned |
| 2. Agent | Revision loop (max_agent_attempts) | ⬜ Planned |
| 3. Evaluation | Heuristic evaluator (5 dimensions, SQL execution) | ✅ Implemented (basic) |
| 3. Evaluation | Reference solutions / ground truth comparison | ⬜ Planned |
| 3. Evaluation | Feedback generator (revision loop input) | ⬜ Planned |
| Results | Run artifacts (results/runs/*.json) | ✅ Implemented |
| Results | Evaluation artifacts (results/evaluations/*.json) | ✅ Implemented |
| Results | `benchmark_runs` PostgreSQL run log (SQL, artifacts, scores) | ✅ Implemented |
| Results | `results summary` / scoring aggregation | ⬜ Planned |
| Results | `experiment run` (batch research runs) | ⬜ Planned |

**Bottom line:** AgentGuard can today fetch real weather data, load it into
PostgreSQL with one command, have an LLM (or mock) solve tasks in a single
shot, and automatically evaluate the solution — running the agent's SQL
against the real database and scoring all five dimensions. The remaining
research-grade pieces are the agentic tool loop, ground-truth comparison,
and experiment aggregation.

---

*Last updated: November 2026*
