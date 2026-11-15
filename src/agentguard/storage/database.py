"""Database operations for AgentGuard.

Handles connecting to PostgreSQL, creating the benchmark schema, loading
fetched CSV data into tables, and executing read-only SQL queries
(used by the evaluator to verify agent solutions).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, time
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Raised when a database operation fails."""


# Columns that must be integers (PostgreSQL INTEGER columns)
_INT_COLUMNS = {
    "location_id",
    "avg_humidity",
    "daily_will_it_rain",
    "daily_will_it_snow",
    "daily_chance_of_rain",
    "daily_chance_of_snow",
    "moon_illumination",
    "wind_degree",
    "is_day",
    "condition_code",
    "humidity",
    "cloud",
    "chance_of_rain",
    "chance_of_snow",
}

# Columns that must be floats (PostgreSQL DECIMAL columns)
_FLOAT_COLUMNS = {
    "latitude",
    "longitude",
    "max_temp_c",
    "min_temp_c",
    "avg_temp_c",
    "max_wind_kph",
    "total_precip_mm",
    "total_snow_cm",
    "avg_visibility_km",
    "uv_index",
    "temp_c",
    "feels_like_c",
    "dewpoint_c",
    "heatindex_c",
    "windchill_c",
    "wind_kph",
    "gust_kph",
    "pressure_mb",
    "precip_mm",
    "snow_cm",
    "visibility_km",
}

# Date/time columns that need parsing before insertion
_DATE_COLUMNS = {"date", "datetime"}

# Columns holding TIME values (strings like "06:19 AM" from WeatherAPI)
_TIME_COLUMNS = {"sunrise", "sunset", "moonrise", "moonset"}

# Time formats emitted by WeatherAPI / the fetcher
_TIME_FORMATS = ("%I:%M %p", "%H:%M:%S", "%H:%M")

# CSV file name -> target table
_CSV_TABLES = {
    "locations": "locations",
    "daily_weather": "daily_weather",
    "hourly_weather": "hourly_weather",
}

# Views defined in schema.sql (dropped before tables when recreating)
_SCHEMA_VIEWS = (
    "v_daily_weather_full",
    "v_monthly_averages",
    "v_extreme_weather",
    "v_data_quality_summary",
)

# Tables defined in schema.sql (dependency order does not matter with CASCADE)
_SCHEMA_TABLES = (
    "data_quality_log",
    "weather_alerts",
    "hourly_weather",
    "daily_weather",
    "locations",
)

# AgentGuard metadata table: one row per benchmark run. Deliberately NOT part
# of schema.sql / drop_all so run history survives database recreation.
_RUNS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS benchmark_runs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(50) NOT NULL,
    agent VARCHAR(100) NOT NULL,
    sql_query TEXT,
    run_artifact TEXT NOT NULL,
    evaluation_artifact TEXT,
    scores JSONB,
    total_score NUMERIC(6, 4),
    findings JSONB,
    query_output JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    evaluated_at TIMESTAMPTZ,
    CONSTRAINT uq_benchmark_runs_artifact UNIQUE (run_artifact)
)
"""


class Database:
    """PostgreSQL database operations for the benchmark.

    Attributes:
        engine: SQLAlchemy engine connected to the database.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    @classmethod
    def from_settings(cls, settings: Any) -> Database:
        """Create a Database from AgentGuard settings.

        Converts the default `postgresql://` URL to the psycopg3 driver
        (`postgresql+psycopg://`) since psycopg2 is not installed.

        Args:
            settings: AgentGuard Settings instance.

        Returns:
            Connected Database instance.
        """
        url = settings.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)

        try:
            engine = create_engine(url, pool_pre_ping=True)
            # Verify connectivity eagerly so failures surface early
            with engine.connect():
                pass
        except Exception as e:
            raise DatabaseError(
                f"Cannot connect to database ({settings.safe_database_url}): {e}"
            ) from e

        return cls(engine)

    def create_schema(self, schema_path: Path) -> None:
        """Execute a schema SQL file (CREATE TABLE/VIEW statements).

        The schema file must be idempotent (IF NOT EXISTS / OR REPLACE),
        which the bundled schema.sql is.

        Args:
            schema_path: Path to the schema.sql file.
        """
        sql = Path(schema_path).read_text(encoding="utf-8")
        with self.engine.begin() as conn:
            conn.execute(text(sql))
        logger.info("Schema applied from %s", schema_path)

    def drop_all(self) -> None:
        """Drop all benchmark views and tables (full recreate support).

        Drops views first (they depend on tables), then tables with
        CASCADE. Objects that do not exist are skipped.
        """
        with self.engine.begin() as conn:
            for view in _SCHEMA_VIEWS:
                conn.execute(text(f"DROP VIEW IF EXISTS {view} CASCADE"))
            for table in _SCHEMA_TABLES:
                conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        logger.info("Dropped all benchmark views and tables")

    # ------------------------------------------------------------------
    # Benchmark run log (metadata table, survives database recreation)
    # ------------------------------------------------------------------

    def ensure_runs_table(self) -> None:
        """Create the benchmark_runs metadata table if it does not exist."""
        with self.engine.begin() as conn:
            conn.execute(text(_RUNS_TABLE_DDL))
        logger.info("benchmark_runs table ensured")

    def record_run(
        self,
        *,
        task_id: str,
        agent: str,
        sql_queries: list[str],
        run_artifact: str,
    ) -> int:
        """Insert (or update) a benchmark run record.

        Upserts on the run_artifact path, so re-running or re-evaluating the
        same artifact is idempotent.

        Args:
            task_id: Benchmark task identifier.
            agent: Agent/model name that produced the solution.
            sql_queries: SQL queries the agent produced.
            run_artifact: Path of the saved run artifact JSON.

        Returns:
            The benchmark_runs row id.
        """
        sql = text(
            "INSERT INTO benchmark_runs (task_id, agent, sql_query, run_artifact)"
            " VALUES (:task_id, :agent, :sql_query, :run_artifact)"
            " ON CONFLICT (run_artifact) DO UPDATE"
            " SET task_id = EXCLUDED.task_id,"
            "     agent = EXCLUDED.agent,"
            "     sql_query = EXCLUDED.sql_query"
            " RETURNING id"
        )
        joined_sql = "\n\n-- ---\n\n".join(sql_queries) or None
        with self.engine.begin() as conn:
            run_id = conn.execute(
                sql,
                {
                    "task_id": task_id,
                    "agent": agent,
                    "sql_query": joined_sql,
                    "run_artifact": run_artifact,
                },
            ).scalar_one()
        logger.info("Recorded benchmark run id=%s (%s)", run_id, task_id)
        return int(run_id)

    def record_evaluation(
        self,
        *,
        run_artifact: str,
        evaluation_artifact: str,
        scores: dict[str, float],
        total: float,
        findings: list[str],
        query_results: list[dict[str, Any]],
        evaluated_at: str,
    ) -> None:
        """Attach evaluation results to an existing benchmark_runs row.

        Args:
            run_artifact: Path of the run artifact (upsert key).
            evaluation_artifact: Path of the saved evaluation JSON.
            scores: Per-dimension scores.
            total: Weighted total score.
            findings: Evaluator findings.
            query_results: Per-query execution outputs.
            evaluated_at: ISO timestamp of the evaluation.
        """
        sql = text(
            "UPDATE benchmark_runs"
            " SET evaluation_artifact = :evaluation_artifact,"
            "     scores = CAST(:scores AS JSONB),"
            "     total_score = :total,"
            "     findings = CAST(:findings AS JSONB),"
            "     query_output = CAST(:query_output AS JSONB),"
            "     evaluated_at = CAST(:evaluated_at AS TIMESTAMPTZ)"
            " WHERE run_artifact = :run_artifact"
        )
        with self.engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "run_artifact": run_artifact,
                    "evaluation_artifact": evaluation_artifact,
                    "scores": json.dumps(scores),
                    "total": total,
                    "findings": json.dumps(findings),
                    "query_output": json.dumps(query_results),
                    "evaluated_at": evaluated_at,
                },
            )
        logger.info("Attached evaluation to benchmark_runs (%s)", run_artifact)

    def load_csvs(self, data_dir: Path, truncate: bool = True) -> dict[str, int]:
        """Load benchmark CSV files into their tables.

        Args:
            data_dir: Directory containing locations.csv, daily_weather.csv,
                hourly_weather.csv.
            truncate: Clear target tables before loading (makes reloads
                idempotent).

        Returns:
            Mapping of table name to number of rows loaded.

        Raises:
            DatabaseError: If a required CSV file is missing or loading fails.
        """
        data_dir = Path(data_dir)
        loaded: dict[str, int] = {}

        for csv_name, table in _CSV_TABLES.items():
            csv_path = data_dir / f"{csv_name}.csv"
            if not csv_path.exists():
                raise DatabaseError(f"Required data file not found: {csv_path}")

            df = self._prepare_dataframe(pd.read_csv(csv_path))

            try:
                with self.engine.begin() as conn:
                    if truncate:
                        # data_quality_log/weather_alerts reference these
                        # tables, but are empty in practice; TRUNCATE with
                        # CASCADE is safe.
                        conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))

                    # Direct executemany insert: values are already plain
                    # Python objects (int/float/date/time/None) from
                    # _prepare_dataframe, so psycopg3 adapts them natively
                    # without pandas' type inference quirks.
                    insert_sql = text(
                        f"INSERT INTO {table} ({', '.join(df.columns)}) "  # noqa: S608
                        f"VALUES ({', '.join(f':{col}' for col in df.columns)})"
                    )
                    conn.execute(insert_sql, df.to_dict(orient="records"))
            except Exception as e:
                raise DatabaseError(f"Failed to load {csv_name} into {table}: {e}") from e

            loaded[table] = len(df)
            logger.info("Loaded %d rows into %s", len(df), table)

        return loaded

    def _prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare a DataFrame for insertion with correct types.

        - Parses date/datetime columns to Python date/datetime objects
        - Parses time columns ("06:19 AM") to Python time objects; values
          like "Does not set today" become NULL
        - Converts integer columns to Python int (handles injected NaNs)
        - Converts float columns to Python float
        - Converts all missing values to None (not NaN/pd.NA) so psycopg
          sends proper NULLs

        Column dtypes are deliberately NOT coerced to object wholesale;
        an explicit dtype map is passed to to_sql instead (see load_csvs).

        Args:
            df: Raw DataFrame read from CSV.

        Returns:
            DataFrame ready for to_sql.
        """
        df = df.copy()

        for col in df.columns:
            if col in _DATE_COLUMNS:
                parsed = pd.to_datetime(df[col], errors="coerce")
                if col == "date":
                    values = [None if pd.isna(v) else v for v in parsed.dt.date]
                else:
                    values = [
                        None if pd.isna(v) else v.to_pydatetime() for v in parsed
                    ]
            elif col in _TIME_COLUMNS:
                values = [_parse_time(v) for v in df[col]]
            elif col in _INT_COLUMNS:
                numeric = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                values = [None if pd.isna(v) else int(v) for v in numeric]
            elif col in _FLOAT_COLUMNS:
                numeric = pd.to_numeric(df[col], errors="coerce").astype(float)
                values = [None if pd.isna(v) else float(v) for v in numeric]
            else:
                values = [None if pd.isna(v) else str(v) for v in df[col]]
            # dtype=object is critical: assigning a plain list would let
            # pandas coerce [75, 57, None] back to float64 (None -> NaN).
            df[col] = pd.Series(values, index=df.index, dtype=object)

        return df

    def execute_readonly_query(self, sql: str) -> tuple[list[str], list[tuple]]:
        """Execute a read-only SQL query and return (columns, rows).

        Blocks non-SELECT statements as a safety measure.

        Args:
            sql: SQL query text (must be SELECT or WITH).

        Returns:
            Tuple of (column names, list of row tuples).

        Raises:
            DatabaseError: If the query is not read-only or fails to execute.
        """
        _assert_readonly(sql)

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql))
                columns = list(result.keys())
                rows = result.fetchall()
                return columns, rows
        except DatabaseError:
            raise
        except Exception as e:
            raise DatabaseError(f"Query failed: {e}") from e

    def table_counts(self) -> dict[str, int]:
        """Return row counts for the benchmark tables."""
        counts: dict[str, int] = {}
        with self.engine.connect() as conn:
            for table in _CSV_TABLES.values():
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))  # noqa: S608
                counts[table] = int(result.scalar() or 0)
        return counts

    def quality_summary(self) -> dict[str, dict[str, Any]]:
        """Return a data-quality summary using the bundled views.

        Returns:
            Mapping of table name to quality metrics, or empty dict if the
            view does not exist.
        """
        try:
            cols, rows = self.execute_readonly_query(
                "SELECT * FROM v_data_quality_summary"
            )
        except DatabaseError:
            return {}

        summary: dict[str, dict[str, Any]] = {}
        for row in rows:
            record = dict(zip(cols, row, strict=False))
            summary[str(record.get("table_name"))] = record
        return summary


# Statements that must never be executed through execute_readonly_query
_FORBIDDEN_SQL = (
    "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER",
    "CREATE", "GRANT", "REVOKE", "COPY", "VACUUM", "CALL", "DO",
)


def _parse_time(value: Any) -> time | None:
    """Parse a time string ("06:19 AM") into a datetime.time.

    Unparseable values (NaN, "Does not set today", etc.) become None.

    Args:
        value: Raw value from the CSV.

    Returns:
        Parsed time or None.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text_value = str(value).strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text_value, fmt).time()
        except ValueError:
            continue
    return None


def _assert_readonly(sql: str) -> None:
    """Raise DatabaseError if the SQL is not a read-only query.

    Args:
        sql: SQL text to check.

    Raises:
        DatabaseError: If the SQL contains forbidden statements.
    """
    stripped = sql.strip().rstrip(";").strip()
    # Leading comment lines (common in LLM output) must not break first-word
    # detection; the forbidden-keyword scan still runs on the full text.
    meaningful = "\n".join(
        line for line in stripped.splitlines() if not line.lstrip().startswith("--")
    ).strip()
    first_word = meaningful.split()[0].upper() if meaningful.split() else ""

    if first_word not in ("SELECT", "WITH", "TABLE", "VALUES", "EXPLAIN"):
        raise DatabaseError(
            f"Only read-only queries (SELECT/WITH) are allowed, got: {first_word}"
        )

    # Detect forbidden keywords appearing anywhere (e.g., "SELECT ...; DROP ...")
    upper = stripped.upper()
    for keyword in _FORBIDDEN_SQL:
        if f";{keyword}" in f";{upper}" or f"; {keyword}" in f"; {upper}":
            raise DatabaseError(f"Forbidden statement detected: {keyword}")
