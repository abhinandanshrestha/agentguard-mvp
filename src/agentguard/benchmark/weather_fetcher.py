"""Weather data fetcher for AgentGuard benchmark.

Fetches historical weather data from WeatherAPI.com for multiple cities
over a configurable date range. Creates structured datasets suitable for
data engineering benchmark tasks.

API Documentation: https://www.weatherapi.com/docs/
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from agentguard.config import get_weather_settings

logger = logging.getLogger(__name__)


# Default cities for weather data collection
DEFAULT_CITIES: list[dict[str, Any]] = [
    {"name": "Kathmandu", "country": "Nepal", "query": "Kathmandu"},
    {"name": "New York", "country": "USA", "query": "New York"},
    {"name": "London", "country": "UK", "query": "London"},
    {"name": "Tokyo", "country": "Japan", "query": "Tokyo"},
    {"name": "Sydney", "country": "Australia", "query": "Sydney"},
    {"name": "Dubai", "country": "UAE", "query": "Dubai"},
    {"name": "Singapore", "country": "Singapore", "query": "Singapore"},
    {"name": "Paris", "country": "France", "query": "Paris"},
    {"name": "Mumbai", "country": "India", "query": "Mumbai"},
    {"name": "São Paulo", "country": "Brazil", "query": "Sao Paulo"},
]


@dataclass
class WeatherConfig:
    """Configuration for weather data fetching.

    Attributes:
        cities: List of city configurations to fetch data for.
        start_date: Start date for historical data (inclusive).
        end_date: End date for historical data (inclusive).
        include_hourly: Whether to include hourly data (24 records per day).
        rate_limit_delay: Seconds to wait between API calls.
        inject_quality_issues: Whether to inject data quality issues for testing.
        duplicate_rate: Fraction of records to duplicate (0.0-0.1).
        null_rate: Fraction of fields to set to null (0.0-0.1).
        invalid_rate: Fraction of records with invalid values (0.0-0.1).
    """

    cities: list[dict[str, Any]] = field(default_factory=lambda: DEFAULT_CITIES.copy())
    start_date: date = field(default_factory=lambda: date.today() - timedelta(days=30))
    end_date: date = field(default_factory=lambda: date.today() - timedelta(days=1))
    include_hourly: bool = True
    rate_limit_delay: float = 0.5  # WeatherAPI free tier: 1M calls/month

    # Data quality issues (for benchmark testing)
    inject_quality_issues: bool = True
    duplicate_rate: float = 0.02  # 2% duplicates
    null_rate: float = 0.03  # 3% nulls
    invalid_rate: float = 0.01  # 1% invalid values

    @classmethod
    def tiny(cls) -> WeatherConfig:
        """Minimal config for unit tests."""
        return cls(
            cities=DEFAULT_CITIES[:2],
            start_date=date.today() - timedelta(days=3),
            end_date=date.today() - timedelta(days=1),
            include_hourly=False,
            inject_quality_issues=False,
        )

    @classmethod
    def small(cls) -> WeatherConfig:
        """Small config for quick testing."""
        return cls(
            cities=DEFAULT_CITIES[:5],
            start_date=date.today() - timedelta(days=7),
            end_date=date.today() - timedelta(days=1),
            include_hourly=True,
            inject_quality_issues=True,
        )

    @classmethod
    def default(cls) -> WeatherConfig:
        """Default config for full benchmark."""
        return cls(
            cities=DEFAULT_CITIES,
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() - timedelta(days=1),
            include_hourly=True,
            inject_quality_issues=True,
        )


class WeatherDataFetcher:
    """Fetches and processes weather data from WeatherAPI.com.

    This class handles:
    - Fetching historical weather data for multiple cities
    - Parsing and normalizing the API response
    - Creating structured DataFrames for locations, daily, and hourly data
    - Optionally injecting data quality issues for benchmark testing
    """

    BASE_URL = "http://api.weatherapi.com/v1/history.json"

    def __init__(self, config: WeatherConfig | None = None):
        """Initialize the weather data fetcher.

        Args:
            config: Weather fetching configuration. Uses default if None.
        """
        self.config = config or WeatherConfig.default()
        self._settings = get_weather_settings()
        self._locations: list[dict[str, Any]] = []
        self._daily_weather: list[dict[str, Any]] = []
        self._hourly_weather: list[dict[str, Any]] = []
        self._fetch_metadata: dict[str, Any] = {}

    @property
    def api_key(self) -> str:
        """Get the API key from settings."""
        if not self._settings.is_configured:
            raise ValueError(
                "WeatherAPI key not configured. "
                "Set WEATHERAPI_KEY in your .env file. "
                "Get a free key at https://www.weatherapi.com/"
            )
        return self._settings.weatherapi_key

    def fetch_all(self) -> dict[str, pd.DataFrame]:
        """Fetch weather data for all configured cities and dates.

        Returns:
            Dictionary with DataFrames: 'locations', 'daily_weather', 'hourly_weather'

        Raises:
            ValueError: If API key is not configured.
            requests.RequestException: If API request fails.
        """
        logger.info(
            f"Fetching weather data for {len(self.config.cities)} cities "
            f"from {self.config.start_date} to {self.config.end_date}"
        )

        self._locations = []
        self._daily_weather = []
        self._hourly_weather = []

        total_days = (self.config.end_date - self.config.start_date).days + 1
        total_requests = len(self.config.cities) * total_days

        logger.info(f"Total API requests to make: {total_requests}")

        request_count = 0
        for city_config in self.config.cities:
            self._fetch_city_data(city_config)
            request_count += total_days
            logger.info(
                f"Completed {city_config['name']}: "
                f"{request_count}/{total_requests} requests"
            )

        # Convert to DataFrames
        data = {
            "locations": pd.DataFrame(self._locations),
            "daily_weather": pd.DataFrame(self._daily_weather),
        }

        if self.config.include_hourly and self._hourly_weather:
            data["hourly_weather"] = pd.DataFrame(self._hourly_weather)

        # Inject quality issues if configured
        if self.config.inject_quality_issues:
            data = self._inject_quality_issues(data)

        # Store metadata
        self._fetch_metadata = {
            "fetched_at": datetime.now().isoformat(),
            "cities_count": len(self.config.cities),
            "date_range": {
                "start": self.config.start_date.isoformat(),
                "end": self.config.end_date.isoformat(),
            },
            "records": {name: len(df) for name, df in data.items()},
            "quality_issues_injected": self.config.inject_quality_issues,
        }

        logger.info(f"Fetch complete. Records: {self._fetch_metadata['records']}")
        return data

    def _fetch_city_data(self, city_config: dict[str, Any]) -> int:
        """Fetch all historical data for a single city.

        Args:
            city_config: City configuration dict with 'name', 'country', 'query'.

        Returns:
            The location_id assigned to this city.
        """
        location_id = len(self._locations) + 1
        location_added = False

        current_date = self.config.start_date
        while current_date <= self.config.end_date:
            response = self._fetch_day(city_config["query"], current_date)

            if response and not location_added:
                # Extract location data from first successful response
                loc = response.get("location", {})
                self._locations.append({
                    "location_id": location_id,
                    "name": loc.get("name", city_config["name"]),
                    "region": loc.get("region", ""),
                    "country": loc.get("country", city_config["country"]),
                    "latitude": loc.get("lat"),
                    "longitude": loc.get("lon"),
                    "timezone_id": loc.get("tz_id", ""),
                    "query_string": city_config["query"],
                })
                location_added = True

            if response:
                self._parse_forecast_day(response, location_id, current_date)

            current_date += timedelta(days=1)

            # Rate limiting
            if self.config.rate_limit_delay > 0:
                time.sleep(self.config.rate_limit_delay)

        return location_id

    def _fetch_day(self, query: str, dt: date) -> dict[str, Any] | None:
        """Fetch weather data for a single city and date.

        Args:
            query: City query string (name, coordinates, etc.)
            dt: Date to fetch data for.

        Returns:
            API response as dict, or None if request failed.
        """
        params = {
            "key": self.api_key,
            "q": query,
            "dt": dt.isoformat(),
        }

        try:
            response = requests.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch {query} for {dt}: {e}")
            return None

    def _parse_forecast_day(
        self, response: dict[str, Any], location_id: int, dt: date
    ) -> None:
        """Parse forecast day data from API response.

        Args:
            response: Full API response dict.
            location_id: ID of the location.
            dt: Date of the forecast.
        """
        forecast = response.get("forecast", {})
        forecast_days = forecast.get("forecastday", [])

        if not forecast_days:
            return

        day_data = forecast_days[0]
        day_summary = day_data.get("day", {})
        astro = day_data.get("astro", {})

        # Daily weather record
        self._daily_weather.append({
            "location_id": location_id,
            "date": dt.isoformat(),
            "max_temp_c": day_summary.get("maxtemp_c"),
            "min_temp_c": day_summary.get("mintemp_c"),
            "avg_temp_c": day_summary.get("avgtemp_c"),
            "max_wind_kph": day_summary.get("maxwind_kph"),
            "total_precip_mm": day_summary.get("totalprecip_mm"),
            "total_snow_cm": day_summary.get("totalsnow_cm"),
            "avg_visibility_km": day_summary.get("avgvis_km"),
            "avg_humidity": day_summary.get("avghumidity"),
            "daily_will_it_rain": day_summary.get("daily_will_it_rain"),
            "daily_chance_of_rain": day_summary.get("daily_chance_of_rain"),
            "daily_will_it_snow": day_summary.get("daily_will_it_snow"),
            "daily_chance_of_snow": day_summary.get("daily_chance_of_snow"),
            "condition_text": day_summary.get("condition", {}).get("text"),
            "condition_code": day_summary.get("condition", {}).get("code"),
            "uv_index": day_summary.get("uv"),
            "sunrise": astro.get("sunrise"),
            "sunset": astro.get("sunset"),
            "moonrise": astro.get("moonrise"),
            "moonset": astro.get("moonset"),
            "moon_phase": astro.get("moon_phase"),
            "moon_illumination": astro.get("moon_illumination"),
        })

        # Hourly weather records
        if self.config.include_hourly:
            for hour_data in day_data.get("hour", []):
                self._hourly_weather.append({
                    "location_id": location_id,
                    "datetime": hour_data.get("time"),
                    "temp_c": hour_data.get("temp_c"),
                    "feels_like_c": hour_data.get("feelslike_c"),
                    "wind_kph": hour_data.get("wind_kph"),
                    "wind_degree": hour_data.get("wind_degree"),
                    "wind_dir": hour_data.get("wind_dir"),
                    "pressure_mb": hour_data.get("pressure_mb"),
                    "precip_mm": hour_data.get("precip_mm"),
                    "snow_cm": hour_data.get("snow_cm"),
                    "humidity": hour_data.get("humidity"),
                    "cloud": hour_data.get("cloud"),
                    "visibility_km": hour_data.get("vis_km"),
                    "uv_index": hour_data.get("uv"),
                    "gust_kph": hour_data.get("gust_kph"),
                    "is_day": hour_data.get("is_day"),
                    "condition_text": hour_data.get("condition", {}).get("text"),
                    "condition_code": hour_data.get("condition", {}).get("code"),
                    "chance_of_rain": hour_data.get("chance_of_rain"),
                    "chance_of_snow": hour_data.get("chance_of_snow"),
                    "dewpoint_c": hour_data.get("dewpoint_c"),
                    "heatindex_c": hour_data.get("heatindex_c"),
                    "windchill_c": hour_data.get("windchill_c"),
                })

    def _inject_quality_issues(
        self, data: dict[str, pd.DataFrame]
    ) -> dict[str, pd.DataFrame]:
        """Inject data quality issues for benchmark testing.

        Args:
            data: Dictionary of DataFrames to modify.

        Returns:
            Modified DataFrames with injected issues.
        """
        import random

        random.seed(42)  # Reproducible issues

        logger.info("Injecting data quality issues for benchmark testing...")

        for name, df in data.items():
            if df.empty:
                continue

            n_records = len(df)

            # Inject duplicates
            if self.config.duplicate_rate > 0:
                n_duplicates = int(n_records * self.config.duplicate_rate)
                if n_duplicates > 0:
                    dup_indices = random.sample(range(n_records), min(n_duplicates, n_records))
                    duplicates = df.iloc[dup_indices].copy()
                    data[name] = pd.concat([df, duplicates], ignore_index=True)
                    logger.info(f"  {name}: Added {len(duplicates)} duplicate records")

            # Inject nulls in numeric columns.
            # Join keys (location_id) are never nulled: a record without its
            # location cannot be loaded (NOT NULL FK) and is not a realistic
            # measurement-level quality issue.
            if self.config.null_rate > 0:
                numeric_cols = df.select_dtypes(include=["float64", "int64"]).columns
                numeric_cols = [
                    col for col in numeric_cols if col not in ("location_id",)
                ]
                for col in numeric_cols:
                    n_nulls = int(n_records * self.config.null_rate)
                    if n_nulls > 0:
                        null_indices = random.sample(range(n_records), min(n_nulls, n_records))
                        data[name].loc[null_indices, col] = None

            # Inject invalid values (negative temperatures, out-of-range humidity)
            if self.config.invalid_rate > 0 and name in ("daily_weather", "hourly_weather"):
                n_invalid = int(n_records * self.config.invalid_rate)
                if n_invalid > 0:
                    invalid_indices = random.sample(range(len(data[name])), min(n_invalid, len(data[name])))
                    if "avg_humidity" in data[name].columns:
                        data[name].loc[invalid_indices[:n_invalid//2], "avg_humidity"] = 150  # Invalid: >100
                    if "humidity" in data[name].columns:
                        data[name].loc[invalid_indices[:n_invalid//2], "humidity"] = -10  # Invalid: <0
                    logger.info(f"  {name}: Injected {n_invalid} invalid values")

        return data

    def save_to_csv(self, output_dir: Path) -> dict[str, Path]:
        """Save fetched data to CSV files.

        Args:
            output_dir: Directory to save CSV files.

        Returns:
            Dictionary mapping table names to file paths.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        data = self.fetch_all()
        paths = {}

        for name, df in data.items():
            csv_path = output_dir / f"{name}.csv"
            df.to_csv(csv_path, index=False)
            paths[name] = csv_path
            logger.info(f"Saved {len(df)} records to {csv_path}")

        return paths

    def generate_manifest(self, output_dir: Path) -> dict[str, Any]:
        """Generate a manifest file describing the generated data.

        Args:
            output_dir: Directory containing the CSV files.

        Returns:
            Manifest dictionary.
        """
        output_dir = Path(output_dir)

        # Re-read data to get accurate counts after quality issues
        data = {}
        for name in ["locations", "daily_weather", "hourly_weather"]:
            csv_path = output_dir / f"{name}.csv"
            if csv_path.exists():
                data[name] = pd.read_csv(csv_path)

        manifest = {
            "generated_at": datetime.now().isoformat(),
            "generator": "WeatherDataFetcher",
            "version": "1.0.0",
            "source": "WeatherAPI.com",
            "config": {
                "cities_count": len(self.config.cities),
                "date_range": {
                    "start": self.config.start_date.isoformat(),
                    "end": self.config.end_date.isoformat(),
                },
                "include_hourly": self.config.include_hourly,
                "quality_issues_injected": self.config.inject_quality_issues,
            },
            "tables": {},
        }

        for name, df in data.items():
            csv_path = output_dir / f"{name}.csv"
            if csv_path.exists():
                with csv_path.open("rb") as f:
                    checksum = hashlib.md5(f.read()).hexdigest()  # noqa: S324
            else:
                checksum = None

            manifest["tables"][name] = {
                "rows": len(df),
                "columns": list(df.columns),
                "file": f"{name}.csv",
                "checksum_md5": checksum,
            }

        # Save manifest
        manifest_path = output_dir / "manifest.json"
        with manifest_path.open("w") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"Saved manifest to {manifest_path}")
        return manifest
