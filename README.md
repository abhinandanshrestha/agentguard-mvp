# AgentGuard

**Evaluating and Governing AI Agents in Data Engineering Workflows**

AgentGuard is a research framework for evaluating AI coding agents on realistic
data engineering tasks, measuring not just functional correctness but also
data quality, security, technical debt, and governance compliance.

**Key feature:** AgentGuard uses **real weather data** fetched live from
[WeatherAPI.com](https://www.weatherapi.com/) — not synthetic or mock data.
Agents work against actual PostgreSQL tables with real temperature readings,
humidity values, and weather conditions from cities worldwide.

> **Status:** MVP/Research Prototype — Core infrastructure complete, benchmark
> tasks defined, weather data integration ready. **85 tests passing.**

**Documentation:**
- [Getting Started Guide](docs/GETTING_STARTED.md) — step-by-step setup
- [How It Works](docs/HOW_IT_WORKS.md) — architecture diagrams and data flow
- [Evaluation Metrics](docs/EVALUATION_METRICS.md) — weights, checks, penalties
- [Terminology Guide](docs/GLOSSARY.md) — LLM/agent/data-engineering terms

## Overview

AI coding agents can produce solutions that pass functional tests while
introducing serious problems:

- **Security vulnerabilities** - hardcoded credentials, SQL injection
- **Data quality issues** - missing validation, null handling, duplicates
- **Technical debt** - excessive complexity, poor maintainability
- **Governance violations** - PII exposure, policy non-compliance

AgentGuard provides a framework to measure these dimensions independently,
enabling research into AI agent behavior beyond simple correctness metrics.

## Research Objective

> Can an AI coding agent complete realistic data-engineering tasks correctly
> while avoiding data-quality, security, technical-debt, and governance
> violations?

### Proposed Research Questions

- **RQ1:** How often are agent solutions functionally correct but governance-unsafe?
- **RQ2:** What failure modes occur most frequently?
- **RQ3:** What relationship exists between agent productivity and technical debt?
- **RQ4:** Can evaluator-generated feedback reduce governance violations?
- **RQ5:** How do different agents/models compare?

*Note: These are proposed research questions. Results have not yet been measured.*

## Architecture

```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                           DATA PIPELINE                                  │
  │  WeatherAPI.com ──► CSV files ──► PostgreSQL (real weather data)        │
  └─────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                         BENCHMARK TASK (YAML)                            │
  │  • Task description          • Schema hint (tables, columns, views)      │
  │  • Expected deliverables     • Evaluation criteria (planned)             │
  └─────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                            LLM AGENT                                     │
  │  Receives: system prompt + task + schema    Produces: SQL + files        │
  └─────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                      SOLUTION ARTIFACT (JSON)                            │
  │  results/runs/*.json: task_id, agent, sql_queries[], files{}, reasoning  │
  └─────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                    INDEPENDENT EVALUATOR                                 │
  │  (Agent never sees its own score)                                        │
  │                                                                          │
  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────┐│
  │  │Correctness │ │Data Quality│ │  Security  │ │Tech. Debt  │ │Governan.││
  │  │   (35%)    │ │   (20%)    │ │   (20%)    │ │   (15%)    │ │  (10%)  ││
  │  │            │ │            │ │            │ │            │ │         ││
  │  │Execute SQL │ │NULL/dedup  │ │Injection   │ │Code size   │ │PII check││
  │  │against DB  │ │patterns    │ │secrets     │ │SELECT *    │ │DROP/DEL ││
  │  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └────┬────┘│
  │        └──────────────┴──────────────┴──────────────┴─────────────┘     │
  │                                      │                                   │
  │                           Weighted Total Score                           │
  └─────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                           RESULTS                                        │
  │  • Evaluation artifact: results/evaluations/*.json                       │
  │  • benchmark_runs table: scores, findings, query outputs (JSONB)         │
  │  • Console report: per-dimension table + query results                   │
  └─────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                    FEEDBACK GENERATOR (planned)                          │
  │  Generate targeted feedback for agent revision loop                      │
  └─────────────────────────────────────────────────────────────────────────┘
```

### Agent Response Handling

The LLM agent parses responses looking for:
- **SQL queries** in ` ```sql ` fenced code blocks
- **Files** prefixed with `FILE: <filename>` followed by a code block

If the response is truncated (e.g., max_tokens limit), the parser recovers
any unterminated SQL block. The system prompt instructs the model to keep
reasoning brief (≤10 lines) and prioritize complete SQL output.

## Requirements

- **Python 3.10.8** (strictly `>=3.10,<3.11`)
- **PostgreSQL 13+** for data storage
- **uv** for dependency management
- **Git** for version control
- **WeatherAPI Key** (free) for fetching weather data
- **LLM API Key** for running agents on benchmark tasks

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd agentguard

# Install dependencies
uv sync

# Copy environment configuration
cp .env.example .env

# Edit .env to configure:
# 1. Your PostgreSQL connection
# 2. Your WeatherAPI key (get free key at https://www.weatherapi.com/)
```

## Quick Start

### 1. Verify Installation

```bash
# Check Python version (must be 3.10.x)
uv run python --version

# Show configuration
uv run agentguard info
```

### 2. Configure API Keys

**WeatherAPI** (data fetching) — get a free key at [WeatherAPI.com](https://www.weatherapi.com/):

```bash
WEATHERAPI_KEY=your_api_key_here
```

**LLM API** (agent) — default provider is **Anthropic**:

```bash
AGENTGUARD_LLM_PROVIDER=anthropic
AGENTGUARD_LLM_API_KEY=sk-ant-your_key_here
AGENTGUARD_LLM_BASE_URL=https://api.anthropic.com
AGENTGUARD_LLM_MODEL=claude-sonnet-4-5
AGENTGUARD_LLM_MAX_TOKENS=8192        # response token limit (default 8192)
AGENTGUARD_LLM_TEMPERATURE=0.2        # sampling temperature (default 0.2)
```

To use an OpenAI-compatible provider instead, set
`AGENTGUARD_LLM_PROVIDER=openai_compatible` and change the base URL and model:

| Provider | Base URL |
|----------|----------|
| OpenAI | `https://api.openai.com/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| Groq | `https://api.groq.com/openai/v1` |
| Ollama (local) | `http://localhost:11434/v1` |
| LM Studio (local) | `http://localhost:1234/v1` |

### 3. Fetch Weather Data

```bash
# Fetch small dataset (5 cities, 7 days) - recommended for testing
uv run python scripts/generate_data.py --size small

# Fetch default dataset (10 cities, 30 days)
uv run python scripts/generate_data.py

# Fetch tiny dataset (2 cities, 3 days) - for unit tests
uv run python scripts/generate_data.py --size tiny
```

### 4. Load Data into PostgreSQL

```bash
# Drops existing benchmark tables/views, recreates schema from scratch,
# and loads the CSV files fresh
uv run agentguard db load

# Verify row counts and data quality
uv run agentguard db verify

# Alternative: apply schema without dropping existing objects
uv run agentguard db load --no-recreate
```

Requires PostgreSQL running with credentials from `AGENTGUARD_DATABASE_URL`.

### 5. Run a Benchmark Task with the LLM Agent

```bash
# Run task_001 with the LLM agent (uses .env config), auto-evaluates
uv run agentguard benchmark run task_001

# Run with the MockAgent (no LLM API needed)
uv run agentguard benchmark run task_001 --agent mock

# List tasks and show details
uv run agentguard benchmark list
uv run agentguard benchmark show task_001
```

The agent's solution is saved to `results/runs/` and automatically
evaluated (correctness runs the SQL against your database). The
evaluation is saved to `results/evaluations/`.

Every run is also recorded in a `benchmark_runs` PostgreSQL table
(AgentGuard metadata, survives `db load`): task, agent, the SQL it ran,
run artifact path, evaluation scores/findings/query outputs, and
timestamps. Query it directly:

```sql
SELECT task_id, agent, total_score, evaluated_at
FROM benchmark_runs ORDER BY id DESC;
```

### 6. Evaluate Saved Solutions

```bash
# Evaluate the latest run artifact
uv run agentguard evaluate

# Evaluate a specific run
uv run agentguard evaluate --run results/runs/task_001_20261115_222654.json
```

Scores five dimensions (weights renormalized over scored dimensions):

| Dimension | Weight | How Scored |
|-----------|--------|------------|
| Correctness | 35% | Executes SQL against PostgreSQL; pass = returns rows |
| Data Quality | 20% | Regex checks for NULL/duplicate handling patterns |
| Security | 20% | Static scan for injection patterns, hardcoded secrets |
| Technical Debt | 15% | Code size, SELECT *, line length, test presence |
| Governance | 10% | Destructive SQL, PII handling without masking |

**Query output capture:** Each SQL query's results (columns, first 50 rows,
row count, errors) are saved in the evaluation artifact and `benchmark_runs`
table for inspection. See [Evaluation Metrics](docs/EVALUATION_METRICS.md)
for full details.

### 7. Run Tests

```bash
uv run pytest
```

### 8. Run Linting

```bash
uv run ruff check .
uv run ruff format --check .
```

## Weather Data Platform

AgentGuard uses real weather data from [WeatherAPI.com](https://www.weatherapi.com/)
to create realistic data engineering scenarios. The data includes:

### Data Tables

| Table | Description |
|-------|-------------|
| `locations` | City/location metadata (coordinates, timezone) |
| `daily_weather` | Daily weather summaries (temp, precip, conditions) |
| `hourly_weather` | Hourly observations (24 records per day per city) |
| `data_quality_log` | Audit log for data quality issues (empty by default) |

### Pre-built Views

| View | Description |
|------|-------------|
| `daily_weather_with_location` | daily_weather joined with location names |
| `hourly_weather_with_location` | hourly_weather joined with location names |
| `weather_summary` | Aggregated stats per city |
| `latest_conditions` | Most recent observation per city |

### Schema Design

The raw layer intentionally has **no unique or check constraints** — this allows
injected duplicates and invalid values to load. Tasks are expected to detect
and handle these issues via SQL (e.g., `ROW_NUMBER()` for dedup, `BETWEEN` for
range validation).

### Default Cities

Kathmandu, New York, London, Tokyo, Sydney, Dubai, Singapore, Paris, Mumbai, São Paulo

### Data Quality Issues (Intentional)

For benchmark testing, the data includes intentional quality issues (seed=42):
- **~2% duplicates** — Same records appearing twice
- **~3% null values** — Missing temperature/humidity readings (excluding PKs)
- **~1% invalid values** — Out-of-range humidity (150 or -10)

These issues test the agent's ability to handle real-world data quality challenges.

## Benchmark Tasks

AgentGuard includes 10 benchmark tasks across multiple difficulty levels:

| Task | Name | Difficulty | Primary Dimensions |
|------|------|------------|-------------------|
| 001 | Monthly Temperature Analysis | Easy | Correctness, Data Quality |
| 002 | Weather Data Quality Validation | Medium | Data Quality, Correctness |
| 003 | Duplicate Records Cleanup | Medium | Data Quality, Technical Debt |
| 004 | Weather ETL Pipeline | Hard | Correctness, Technical Debt |
| 005 | Schema Evolution (Add AQI) | Medium | Technical Debt, Governance |
| 006 | Weather Query Optimization | Hard | Technical Debt, Correctness |
| 007 | Automated Weather Data Tests | Medium | Technical Debt, Governance |
| 008 | Secure API Key Management | Medium | Security, Governance |
| 009 | Location Data Privacy | Medium | Governance, Security |
| 010 | Debug Weather Data Anomalies | Hard | Correctness, Data Quality |

## Project Structure

```
agentguard/
├── src/agentguard/          # Main package
│   ├── agent/               # Agent abstraction and providers
│   ├── benchmark/           # Task loading and data fetching
│   │   └── weather_fetcher.py  # WeatherAPI data fetcher
│   ├── evaluator/           # Independent evaluation framework
│   ├── feedback/            # Feedback generation
│   ├── experiments/         # Experiment configuration and running
│   ├── storage/             # Database and persistence
│   ├── api/                 # FastAPI REST API
│   ├── config.py            # Configuration management
│   └── cli.py               # Command-line interface
├── benchmark/               # Benchmark tasks and data
│   ├── tasks/               # Task definitions (YAML)
│   └── weather_platform/    # Weather data environment
│       ├── data/            # Generated CSV files
│       ├── sql/             # Database schema
│       ├── pipelines/       # ETL pipelines
│       └── tests/           # Data tests
├── policies/                # Governance policies
├── experiments/configs/     # Experiment configurations
├── scripts/                 # Utility scripts
│   └── generate_data.py     # Weather data fetcher script
├── tests/                   # Test suite
├── results/                 # Experiment outputs
└── docs/                    # Documentation
```

## CLI Commands

```bash
agentguard --help                 # Show help
agentguard --version              # Show version
agentguard info                   # Show configuration (DB + LLM + paths)
agentguard db load                # Create schema and load CSVs into PostgreSQL
agentguard db verify              # Check row counts and data quality
agentguard benchmark list         # List benchmark tasks
agentguard benchmark show task_001  # Show task details
agentguard benchmark run task_001 # Run a task with the LLM agent (+ auto-evaluate)
agentguard benchmark run task_001 --agent mock  # Run with MockAgent (no API)
agentguard evaluate               # Evaluate the latest saved run
agentguard evaluate --run <path>  # Evaluate a specific run artifact
agentguard experiment run         # Run an experiment (planned)
agentguard results summary        # Show results summary (planned)
```

## Configuration

Configuration is managed through environment variables. Copy `.env.example`
to `.env` and adjust as needed:

```bash
# Runtime environment
AGENTGUARD_ENVIRONMENT=development

# PostgreSQL Database connection string
AGENTGUARD_DATABASE_URL=postgresql://agentguard:agentguard@localhost:5432/agentguard

# Maximum agent attempts per task
AGENTGUARD_MAX_AGENT_ATTEMPTS=3

# Logging level
AGENTGUARD_LOG_LEVEL=INFO

# WeatherAPI key (required for data fetching)
WEATHERAPI_KEY=your_api_key_here

# LLM Configuration
AGENTGUARD_LLM_PROVIDER=anthropic          # anthropic | openai_compatible | mock
AGENTGUARD_LLM_API_KEY=sk-ant-xxx          # API key for the LLM provider
AGENTGUARD_LLM_BASE_URL=https://api.anthropic.com
AGENTGUARD_LLM_MODEL=claude-sonnet-4-5     # Model name
AGENTGUARD_LLM_MAX_TOKENS=8192             # Max response tokens (default 8192)
AGENTGUARD_LLM_TEMPERATURE=0.2             # Sampling temperature (default 0.2)
AGENTGUARD_LLM_TIMEOUT=120                 # Request timeout seconds (default 120)
```

### PostgreSQL Setup

Create the database and user:

```sql
CREATE USER agentguard WITH PASSWORD 'agentguard';
CREATE DATABASE agentguard OWNER agentguard;
GRANT ALL PRIVILEGES ON DATABASE agentguard TO agentguard;
```

Then load the schema and data with one command (after fetching data):

```bash
uv run agentguard db load
```

Or apply the schema manually:

```bash
psql -U agentguard -d agentguard -f benchmark/weather_platform/sql/schema.sql
```

## Development

### Code Quality

```bash
# Lint code
uv run ruff check .

# Format code
uv run ruff format .

# Type checking
uv run mypy src
```

### Running Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=agentguard

# Specific test file
uv run pytest tests/unit/test_config.py
```

## Limitations

This is an MVP research prototype with known limitations:

1. **No ground-truth comparison** — Correctness = "SQL runs and returns rows",
   not "answer matches reference solution" (planned)
2. **Heuristic scoring** — Weights are initial estimates, not empirically validated;
   per-task YAML evaluation criteria not yet consumed by evaluator
3. **Regex-based checks** — Security/data-quality patterns may miss subtle issues
   or trigger false positives (e.g., keywords in comments)
4. **API dependency** — Requires WeatherAPI.com key and internet connectivity
5. **Model variability** — LLM outputs vary between runs
6. **Limited data window** — Weather data fetched is typically 7–30 days; tasks
   should not assume 60-day windows exist

## Screenshots of the result:
![alt text](image.png)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

This is a research project. Contributions are welcome via pull requests.
Please ensure code passes linting and tests before submitting.
