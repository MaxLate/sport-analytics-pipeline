"""
Daily incremental weather extract for the configured location via Open-Meteo's forecast
endpoint (past_days covers today + a lookback window, so late corrections to
recent days get picked up on the next run). This is the script Airflow calls
on the daily schedule.
"""

import datetime
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
from config_loader import Config  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from open_meteo_client import fetch_forecast  # noqa: E402


def main():
    config = Config()
    raw_dir = project_root / "0_data" / "raw" / "weather"
    raw_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching weather forecast/recent data for {config.weather_city}...")
    payload = fetch_forecast(
        latitude=config.weather_latitude,
        longitude=config.weather_longitude,
        timezone=config.weather_timezone,
        past_days=7,
    )

    out_file = raw_dir / f"forecast_{datetime.date.today().isoformat()}.json"
    with open(out_file, "w") as f:
        json.dump(payload, f, indent=2)

    n_days = len(payload.get("daily", {}).get("time", []))
    print(f"  Fetched {n_days} days")
    print(f"  Saved to: {out_file}")


if __name__ == "__main__":
    main()
