# Getting Started with AgentGuard

A complete step-by-step guide for beginners to set up and run AgentGuard.

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Install Required Software](#2-install-required-software)
3. [Set Up PostgreSQL Database](#3-set-up-postgresql-database)
4. [Clone and Install AgentGuard](#4-clone-and-install-agentguard)
5. [Configure Environment](#5-configure-environment)
6. [Get WeatherAPI Key](#6-get-weatherapi-key)
7. [Verify Installation](#7-verify-installation)
8. [Fetch Weather Data](#8-fetch-weather-data)
9. [Run Tests](#9-run-tests)
10. [Using the CLI](#10-using-the-cli)
11. [Next Steps](#11-next-steps)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prerequisites

Before starting, make sure you have:

- A computer running Windows, macOS, or Linux
- Administrator/sudo access to install software
- Internet connection to download dependencies and fetch weather data
- Basic familiarity with command line/terminal

---

## 2. Install Required Software

### 2.1 Install Python 3.10.8

AgentGuard requires **exactly Python 3.10.x** (not 3.11 or higher).

#### Windows

1. Download Python 3.10.8 from: https://www.python.org/downloads/release/python-3108/
2. Run the installer
3. **IMPORTANT:** Check "Add Python to PATH" during installation
4. Verify installation:
   ```cmd
   python --version
   ```
   Should show: `Python 3.10.8`

#### macOS

```bash
# Using Homebrew
brew install python@3.10

# Verify
python3.10 --version
```

#### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install python3.10 python3.10-venv python3.10-dev

# Verify
python3.10 --version
```

### 2.2 Install uv (Python Package Manager)

`uv` is a fast Python package manager that AgentGuard uses.

#### Windows (PowerShell)

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

#### macOS/Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### Verify uv Installation

```bash
uv --version
```

### 2.3 Install Git

#### Windows

Download and install from: https://git-scm.com/download/win

#### macOS

```bash
brew install git
```

#### Linux

```bash
sudo apt install git
```

#### Verify Git Installation

```bash
git --version
```

### 2.4 Install PostgreSQL

AgentGuard uses PostgreSQL as its database.

#### Windows

1. Download PostgreSQL from: https://www.postgresql.org/download/windows/
2. Run the installer
3. **Remember the password you set for the `postgres` user!**
4. Keep the default port: `5432`
5. Complete the installation

#### macOS

```bash
# Using Homebrew
brew install postgresql@15
brew services start postgresql@15
```

#### Linux (Ubuntu/Debian)

```bash
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### Verify PostgreSQL Installation

```bash
# Check if PostgreSQL is running
psql --version
```

---

## 3. Set Up PostgreSQL Database

Now we need to create a database and user for AgentGuard.

### 3.1 Connect to PostgreSQL

#### Windows

Open "SQL Shell (psql)" from Start Menu, or:
```cmd
psql -U postgres
```
Enter the password you set during installation.

#### macOS/Linux

```bash
sudo -u postgres psql
```

### 3.2 Create Database and User

Run these SQL commands in the PostgreSQL shell:

```sql
-- Create a new user for AgentGuard
CREATE USER agentguard WITH PASSWORD 'agentguard';

-- Create the database
CREATE DATABASE agentguard OWNER agentguard;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE agentguard TO agentguard;

-- Exit PostgreSQL shell
\q
```

### 3.3 Verify Database Connection

Test that you can connect with the new user:

```bash
psql -U agentguard -d agentguard -h localhost
```

Enter password: `agentguard`

If you see the `agentguard=>` prompt, the database is set up correctly. Type `\q` to exit.

---

## 4. Clone and Install AgentGuard

### 4.1 Clone the Repository

```bash
# Navigate to where you want the project
cd ~/projects  # or any directory you prefer

# Clone the repository
git clone <repository-url>
cd agentguard
```

Or if you already have the project folder:

```bash
cd path/to/agentguard
```

### 4.2 Install Dependencies

```bash
uv sync
```

This will:
- Create a virtual environment (`.venv` folder)
- Install all required Python packages
- Install AgentGuard in development mode

---

## 5. Configure Environment

### 5.1 Create Environment File

```bash
# Copy the example environment file
cp .env.example .env
```

### 5.2 Edit the Environment File

Open `.env` in a text editor:

#### Windows (Notepad)
```cmd
notepad .env
```

#### macOS/Linux
```bash
nano .env
# or
code .env  # if you have VS Code
```

### 5.3 Environment File Contents

Your `.env` file should look like this:

```bash
# AgentGuard Configuration

# Runtime environment: development, test, or ci
AGENTGUARD_ENVIRONMENT=development

# PostgreSQL Database connection string
AGENTGUARD_DATABASE_URL=postgresql://agentguard:agentguard@localhost:5432/agentguard

# Maximum agent revision attempts per task (1-10)
AGENTGUARD_MAX_AGENT_ATTEMPTS=3

# Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
AGENTGUARD_LOG_LEVEL=INFO

# WeatherAPI key (required for data fetching)
WEATHERAPI_KEY=your_api_key_here

# LLM configuration (required for running agents on benchmark tasks)
AGENTGUARD_LLM_PROVIDER=anthropic
AGENTGUARD_LLM_API_KEY=sk-ant-your_key_here
AGENTGUARD_LLM_BASE_URL=https://api.anthropic.com
AGENTGUARD_LLM_MODEL=claude-sonnet-4-5
AGENTGUARD_LLM_TEMPERATURE=0.2
AGENTGUARD_LLM_MAX_TOKENS=2048
AGENTGUARD_LLM_TIMEOUT=120
```

---

## 6. Get API Keys

AgentGuard needs two API keys:

### 6.1 WeatherAPI Key (Data Fetching)

AgentGuard fetches real weather data from WeatherAPI.com. You need a free API key.

1. Go to https://www.weatherapi.com/
2. Click "Sign Up" (free tier is sufficient)
3. Verify your email and log in
4. Copy your API key
5. Add to `.env`: `WEATHERAPI_KEY=your_actual_api_key_here`

**Free tier limits:** 1,000,000 calls/month, history up to 7 days back.

### 6.2 LLM API Key (Agent)

The agent that solves benchmark tasks needs an LLM API. AgentGuard supports
the **Anthropic API** (default) and any OpenAI-compatible provider.

**Option A: Anthropic (default)**

1. Go to https://console.anthropic.com/settings/keys
2. Create an API key (starts with `sk-ant-...`)
3. Add to `.env`:

```bash
AGENTGUARD_LLM_PROVIDER=anthropic
AGENTGUARD_LLM_API_KEY=sk-ant-your_key_here
AGENTGUARD_LLM_BASE_URL=https://api.anthropic.com
AGENTGUARD_LLM_MODEL=claude-sonnet-4-5
```

**Option B: OpenAI-compatible providers**

Set `AGENTGUARD_LLM_PROVIDER=openai_compatible` and pick a base URL:

| Provider | Base URL | Get Key |
|----------|----------|---------|
| OpenAI | `https://api.openai.com/v1` | https://platform.openai.com/api-keys |
| OpenRouter | `https://openrouter.ai/api/v1` | https://openrouter.ai/keys |
| DeepSeek | `https://api.deepseek.com/v1` | https://platform.deepseek.com/ |
| Groq | `https://api.groq.com/openai/v1` | https://console.groq.com/keys |
| Ollama (local, free) | `http://localhost:11434/v1` | no key needed (any string) |

For local models (Ollama/LM Studio), any placeholder key works:

```bash
AGENTGUARD_LLM_PROVIDER=openai_compatible
AGENTGUARD_LLM_API_KEY=local
AGENTGUARD_LLM_BASE_URL=http://localhost:11434/v1
AGENTGUARD_LLM_MODEL=llama3.1
```

> New to LLM terms (tokens, temperature, system prompts)?
> See the [Terminology Guide](GLOSSARY.md).

---

## 7. Verify Installation

### 7.1 Check Python Version

```bash
uv run python --version
```

**Expected output:** `Python 3.10.8`

### 7.2 Check AgentGuard Version

```bash
uv run agentguard --version
```

**Expected output:** `agentguard 0.1.0`

### 7.3 View Configuration

```bash
uv run agentguard info
```

**Expected output:**
```
AgentGuard v0.1.0

Python:
  Version:    3.10.8
  Supported:  Yes

Configuration:
  Environment:    development
  Database:       postgresql://agentguard:***@localhost:5432/agentguard
  Max Attempts:   3
  Log Level:      INFO

Paths:
  Benchmark:  /path/to/agentguard/benchmark
    Exists:   True
  Policies:   /path/to/agentguard/policies/default_policies.yaml
    Exists:   False
  Results:    /path/to/agentguard/results
    Exists:   True
```

---

## 8. Fetch Weather Data

AgentGuard uses real weather data for its benchmark tasks.

### 8.1 Fetch Small Dataset (Recommended for Testing)

```bash
uv run python scripts/generate_data.py --size small
```

This fetches:
- 5 cities
- 7 days of history
- ~840 hourly records

**Expected output:**
```
============================================================
AgentGuard Weather Data Fetcher
============================================================

Size preset:        small
Cities:             5
Date range:         2024-11-08 to 2024-11-14
Days per city:      7
Include hourly:     True
Quality issues:     True
Output directory:   .../benchmark/weather_platform/data

Total API requests: 35
Estimated time:     17 seconds (0.3 minutes)

...

Fetch complete!

Files created in: .../benchmark/weather_platform/data

  locations.csv: 5 records
  daily_weather.csv: 36 records
  hourly_weather.csv: 864 records

Time elapsed: 18.5 seconds

Note: Data quality issues have been injected for benchmark testing:
  - ~2% duplicate records
  - ~3% null values in numeric columns
  - ~1% invalid values (out-of-range)
```

### 8.2 Other Size Options

```bash
# Tiny dataset (for unit tests) - 2 cities, 3 days
uv run python scripts/generate_data.py --size tiny

# Full dataset - 10 cities, 30 days
uv run python scripts/generate_data.py --size default

# Custom options
uv run python scripts/generate_data.py --cities Kathmandu London Tokyo --start-date 2024-11-01 --end-date 2024-11-07
```

### 8.3 Dry Run (No API Calls)

See what would be fetched without making API calls:

```bash
uv run python scripts/generate_data.py --size small --dry-run
```

---

## 9. Run Tests

### 9.1 Run All Tests

```bash
uv run pytest
```

**Expected output:**
```
============================= test session starts =============================
...
collected 26 items

tests/unit/test_cli.py ........                                          [ 34%]
tests/unit/test_config.py ............                                   [ 80%]
tests/unit/test_package.py ....                                          [100%]

============================= 26 passed in X.XXs ==============================
```

### 9.2 Run Tests with Verbose Output

```bash
uv run pytest -v
```

---

## 10. Using the CLI

### 10.1 View All Commands

```bash
uv run agentguard --help
```

### 10.2 Available Commands

| Command | Description |
|---------|-------------|
| `agentguard info` | Show current configuration (DB + LLM + paths) |
| `agentguard db load` | Create schema and load CSVs into PostgreSQL |
| `agentguard db verify` | Check row counts and data quality |
| `agentguard benchmark list` | List available benchmark tasks |
| `agentguard benchmark show <task_id>` | Show task details |
| `agentguard benchmark run <task_id>` | Run a task with the LLM agent (+ auto-evaluate) |
| `agentguard benchmark run <task_id> --agent mock` | Run with MockAgent (no API key) |
| `agentguard evaluate` | Evaluate the latest saved run |
| `agentguard evaluate --run <path>` | Evaluate a specific run artifact |
| `agentguard experiment run` | Run an experiment (planned) |
| `agentguard results summary` | View experiment results (planned) |

---

## 11. Next Steps

### 11.1 The Complete Workflow

Here is the full end-to-end workflow — this is how you run the project:

```bash
# 1. Fetch real weather data (CSV files)
uv run python scripts/generate_data.py --size small

# 2. Recreate schema + load data into PostgreSQL
#    (drops existing tables/views, recreates from scratch, loads fresh)
uv run agentguard db load

# 3. Verify the data loaded correctly
uv run agentguard db verify

# 4. Run a benchmark task with the LLM agent
#    (solves the task, saves solution, auto-evaluates)
uv run agentguard benchmark run task_001

# 5. Re-evaluate any saved run later
uv run agentguard evaluate
```

**What step 4 does in detail:**
1. Loads `benchmark/tasks/task_001.yaml`
2. Sends the task to your LLM (Anthropic by default)
3. Extracts SQL queries from the response
4. Saves the solution to `results/runs/task_001_<timestamp>.json`
5. **Evaluates it:** runs the SQL against your PostgreSQL database and
   scores five dimensions (Correctness, Data Quality, Security,
   Technical Debt, Governance)
6. Saves the evaluation to `results/evaluations/` and prints the scores

**Example output of step 4:**

```
------------------------------------------------------------
Evaluation Results
------------------------------------------------------------
  Correctness          1.00
  Data Quality         0.60
  Security             1.00
  Technical Debt       0.95
  Governance           1.00

  TOTAL SCORE          0.93
  SQL executed:    True

  Findings:
    - Data quality: little evidence of NULL/duplicate handling
```

If PostgreSQL is not running, the evaluation still works — correctness
is marked `n/a` and the remaining dimensions are scored (weights
renormalized).

### 11.2 Explore Benchmark Tasks

Review the benchmark tasks in `benchmark/tasks/`:

| Task | Description | Difficulty |
|------|-------------|------------|
| task_001 | Monthly Temperature Analysis | Easy |
| task_002 | Weather Data Quality Validation | Medium |
| task_003 | Duplicate Records Cleanup | Medium |
| task_004 | Weather ETL Pipeline | Hard |
| task_005 | Schema Evolution (Add AQI) | Medium |
| task_006 | Weather Query Optimization | Hard |
| task_007 | Automated Weather Data Tests | Medium |
| task_008 | Secure API Key Management | Medium |
| task_009 | Location Data Privacy | Medium |
| task_010 | Debug Weather Data Anomalies | Hard |

### 11.3 Run a Benchmark Task with the LLM Agent

Now for the exciting part — let an LLM agent solve a benchmark task:

```bash
# Run task_001 with the LLM agent (uses your .env LLM config)
uv run agentguard benchmark run task_001

# Run with the MockAgent (no LLM API needed - instant, free)
uv run agentguard benchmark run task_001 --agent mock
```

**What happens with the LLM agent:**
1. The task YAML is converted into a structured prompt
2. Your LLM API is called (Anthropic Messages API by default)
3. SQL queries and files are extracted from the response
4. The solution is saved to `results/runs/task_001_<timestamp>.json`
5. The solution is automatically evaluated (see 11.1)

**Other useful commands:**

```bash
uv run agentguard benchmark list            # List all tasks
uv run agentguard benchmark show task_001   # Show task details
uv run agentguard info                      # Verify LLM config is loaded
```

### 11.4 Code Quality Commands

```bash
# Check code style
uv run ruff check .

# Format code
uv run ruff format .

# Type checking
uv run mypy src
```

---

## 12. Troubleshooting

### Problem: "WEATHERAPI_KEY not configured"

**Solution:**
1. Get a free API key from https://www.weatherapi.com/
2. Add it to your `.env` file:
   ```bash
   WEATHERAPI_KEY=your_api_key_here
   ```

### Problem: "LLM API key not configured"

**Solution:**
1. Get an LLM API key (OpenAI, OpenRouter, DeepSeek, Groq, or run Ollama locally)
2. Add it to your `.env`:
   ```bash
   AGENTGUARD_LLM_API_KEY=your_key_here
   ```
3. Or test without an LLM using the MockAgent:
   ```bash
   uv run agentguard benchmark run task_001 --agent mock
   ```

### Problem: "LLM API error 401" (Unauthorized)

**Solution:**
- Verify `AGENTGUARD_LLM_API_KEY` is correct and not expired
- Verify `AGENTGUARD_LLM_BASE_URL` matches your provider
- Check your provider account has credit/quota available

### Problem: "LLM API error 404"

**Solution:**
- The model name doesn't exist at that provider — check `AGENTGUARD_LLM_MODEL`
- Verify the base URL includes `/v1` where required

### Problem: "Python not found" or wrong version

**Solution:**
- Ensure Python 3.10.x is installed and in your PATH
- On Windows, reinstall Python and check "Add to PATH"
- Try using `python3.10` instead of `python`

### Problem: "uv: command not found"

**Solution:**
- Restart your terminal after installing uv
- On Windows, you may need to restart PowerShell as Administrator

### Problem: "psql: connection refused"

**Solution:**
- Ensure PostgreSQL is running:
  - Windows: Check Services for "postgresql"
  - macOS: `brew services start postgresql@15`
  - Linux: `sudo systemctl start postgresql`

### Problem: API rate limit errors

**Solution:**
- The script includes rate limiting (0.5s between requests)
- If you hit limits, wait and try again
- Use `--size tiny` for testing

### Problem: "Invalid API key"

**Solution:**
- Verify your API key is correct in `.env`
- Check that there are no extra spaces or quotes
- Test your key directly: 
  ```bash
  curl "http://api.weatherapi.com/v1/current.json?key=YOUR_KEY&q=London"
  ```

---

## Quick Reference Card

```bash
# Installation
uv sync                              # Install dependencies
cp .env.example .env                 # Create config file

# Configuration (.env needs:)
#   AGENTGUARD_DATABASE_URL=postgresql://...
#   WEATHERAPI_KEY=...
#   AGENTGUARD_LLM_API_KEY=sk-ant-...

# Fetch Data (CSV files)
uv run python scripts/generate_data.py --size small  # Recommended
uv run python scripts/generate_data.py --dry-run     # Preview only

# Load into PostgreSQL
uv run agentguard db load            # Full recreate + fresh load (default)
uv run agentguard db load --no-recreate  # Apply schema without dropping
uv run agentguard db verify          # Check counts + quality

# Run Benchmarks (LLM agent + auto-evaluation)
uv run agentguard benchmark run task_001
uv run agentguard benchmark run task_001 --agent mock  # No API needed

# Evaluate Saved Runs
uv run agentguard evaluate           # Latest run
uv run agentguard evaluate --run <path>  # Specific run

# Verification
uv run python --version              # Check Python (should be 3.10.x)
uv run agentguard info               # View configuration

# Testing
uv run pytest                        # Run all tests
uv run pytest -v                     # Run with verbose output

# Code Quality
uv run ruff check .                  # Lint code
uv run ruff format .                 # Format code

# CLI Commands
uv run agentguard --help             # Show all commands
uv run agentguard benchmark list     # List tasks
```

---

## Need Help?

- Check the main [README.md](../README.md) for more details
- See [HOW_IT_WORKS.md](HOW_IT_WORKS.md) for diagrams of the complete flow
- See [GLOSSARY.md](GLOSSARY.md) for terminology explanations
- Review task YAML files in `benchmark/tasks/`
- Open an issue on the project repository for bugs or questions

---

*Last updated: November 2024*
