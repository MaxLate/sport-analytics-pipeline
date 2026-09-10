"""
One-time/manual historical weather backfill for the configured location via Open-Meteo's
archive API. Not part of the daily Airflow DAG — run manually once to
populate weather history back to (e.g.) the WHOOP data start date.

Usage:
    uv run python 1_elt/0_extract/weather/extract_weather_backfill.py \
        --start-date 2025-01-01 --end-date 2026-08-28
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
from config_loader import Config  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from open_meteo_client import fetch_archive  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--end-date",
        default=(datetime.date.today() - datetime.timedelta(days=6)).isoformat(),
        help="YYYY-MM-DD (default: 6 days ago, archive API's typical availability lag)",
    )
    args = parser.parse_args()

    config = Config()
    raw_dir = project_root / "0_data" / "raw" / "weather"
    raw_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"Fetching weather archive for {config.weather_city} "
        f"({args.start_date} to {args.end_date})..."
    )
    payload = fetch_archive(
        latitude=config.weather_latitude,
        longitude=config.weather_longitude,
        timezone=config.weather_timezone,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    out_file = raw_dir / f"archive_{datetime.date.today().isoformat()}.json"
    with open(out_file, "w") as f:
        json.dump(payload, f, indent=2)

    n_days = len(payload.get("daily", {}).get("time", []))
    print(f"  Fetched {n_days} days")
    print(f"  Saved to: {out_file}")


if __name__ == "__main__":
    main()
