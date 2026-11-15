#!/usr/bin/env python3
"""Generate weather benchmark data from WeatherAPI.com.

This script fetches historical weather data for multiple cities and saves
it as CSV files for use in AgentGuard benchmark tasks.

Usage:
    # Fetch default data (10 cities, 30 days)
    uv run python scripts/generate_data.py

    # Fetch small dataset (5 cities, 7 days)
    uv run python scripts/generate_data.py --size small

    # Fetch tiny dataset (2 cities, 3 days, no hourly)
    uv run python scripts/generate_data.py --size tiny

    # Custom output directory
    uv run python scripts/generate_data.py --output ./my_data

    # Skip manifest generation
    uv run python scripts/generate_data.py --skip-manifest

    # Disable data quality issues injection
    uv run python scripts/generate_data.py --no-quality-issues

Environment Variables:
    WEATHERAPI_KEY: Your WeatherAPI.com API key (required)
                    Get a free key at https://www.weatherapi.com/
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging for the script."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Fetch weather data from WeatherAPI.com for AgentGuard benchmarks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--size",
        choices=["tiny", "small", "default"],
        default="default",
        help="Dataset size preset (default: default)",
    )

    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output directory (default: benchmark/weather_platform/data)",
    )

    parser.add_argument(
        "--skip-manifest",
        action="store_true",
        help="Skip generating manifest.json",
    )

    parser.add_argument(
        "--no-quality-issues",
        action="store_true",
        help="Disable injection of data quality issues",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date for data fetch (YYYY-MM-DD)",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date for data fetch (YYYY-MM-DD)",
    )

    parser.add_argument(
        "--cities",
        type=str,
        nargs="+",
        default=None,
        help="List of cities to fetch (overrides size preset)",
    )

    parser.add_argument(
        "--no-hourly",
        action="store_true",
        help="Skip fetching hourly data (faster, smaller dataset)",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fetched without making API calls",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    logger = setup_logging(args.verbose)

    # Import here to allow --help without dependencies
    from agentguard.benchmark.weather_fetcher import WeatherConfig, WeatherDataFetcher
    from agentguard.config import get_weather_settings

    # Check API key
    settings = get_weather_settings()
    if not settings.is_configured:
        logger.error(
            "WeatherAPI key not configured!\n"
            "Set WEATHERAPI_KEY in your .env file.\n"
            "Get a free key at https://www.weatherapi.com/"
        )
        return 1

    logger.info(f"Using API key: {settings.safe_api_key}")

    # Determine output directory
    if args.output:
        output_dir = args.output
    else:
        project_root = Path(__file__).parent.parent
        output_dir = project_root / "benchmark" / "weather_platform" / "data"

    # Build configuration
    if args.size == "tiny":
        config = WeatherConfig.tiny()
    elif args.size == "small":
        config = WeatherConfig.small()
    else:
        config = WeatherConfig.default()

    # Apply command line overrides
    if args.no_quality_issues:
        config.inject_quality_issues = False

    if args.no_hourly:
        config.include_hourly = False

    if args.start_date:
        config.start_date = date.fromisoformat(args.start_date)

    if args.end_date:
        config.end_date = date.fromisoformat(args.end_date)

    if args.cities:
        config.cities = [
            {"name": city, "country": "Unknown", "query": city}
            for city in args.cities
        ]

    # Calculate stats
    total_days = (config.end_date - config.start_date).days + 1
    total_requests = len(config.cities) * total_days
    estimated_time = total_requests * config.rate_limit_delay

    print()
    print("=" * 60)
    print("AgentGuard Weather Data Fetcher")
    print("=" * 60)
    print()
    print(f"Size preset:        {args.size}")
    print(f"Cities:             {len(config.cities)}")
    print(f"Date range:         {config.start_date} to {config.end_date}")
    print(f"Days per city:      {total_days}")
    print(f"Include hourly:     {config.include_hourly}")
    print(f"Quality issues:     {config.inject_quality_issues}")
    print(f"Output directory:   {output_dir}")
    print()
    print(f"Total API requests: {total_requests}")
    print(f"Estimated time:     {estimated_time:.0f} seconds ({estimated_time/60:.1f} minutes)")
    print()

    if args.dry_run:
        print("DRY RUN - No API calls will be made")
        print()
        print("Cities to fetch:")
        for city in config.cities:
            print(f"  - {city['name']} ({city.get('country', 'Unknown')})")
        return 0

    # Confirm before proceeding for large fetches
    if total_requests > 100:
        print("This will make many API requests.")
        response = input("Continue? [y/N]: ").strip().lower()
        if response != "y":
            print("Aborted.")
            return 0

    start_time = time.time()

    try:
        fetcher = WeatherDataFetcher(config)

        logger.info("Starting weather data fetch...")
        paths = fetcher.save_to_csv(output_dir)

        if not args.skip_manifest:
            fetcher.generate_manifest(output_dir)

        elapsed = time.time() - start_time

        print()
        print("-" * 60)
        print()
        print("Fetch complete!")
        print()
        print(f"Files created in: {output_dir}")
        print()

        for name, path in paths.items():
            import pandas as pd
            df = pd.read_csv(path)
            print(f"  {name}.csv: {len(df):,} records")

        print()
        print(f"Time elapsed: {elapsed:.1f} seconds")
        print()

        if config.inject_quality_issues:
            print("Note: Data quality issues have been injected for benchmark testing:")
            print(f"  - ~{config.duplicate_rate*100:.0f}% duplicate records")
            print(f"  - ~{config.null_rate*100:.0f}% null values in numeric columns")
            print(f"  - ~{config.invalid_rate*100:.0f}% invalid values (out-of-range)")
            print()

        return 0

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Failed to fetch weather data: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
