#################################################################################
##### Loads Open-Meteo weather JSON (archive + forecast) into DuckDB.     #####
##### Unlike WHOOP's append-only/skip-by-ID pattern, weather rows for     #####
##### recent days can be revised, so this loader UPSERTS by date_day      #####
##### (delete any existing rows for the dates in the new batch, then      #####
##### insert the new batch) instead of skipping existing rows.            #####
#################################################################################

import json
import os
import re
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

# Get project root directory (4 levels up: weather -> 1_load -> 1_elt -> project_root)
project_root = Path(__file__).parent.parent.parent.parent
data_dir = project_root / "0_data" / "raw" / "weather"
db_path = Path(
    os.environ.get(
        "WAREHOUSE_PATH", project_root / "0_data" / "database" / "warehouse.duckdb"
    )
)
db_dir = db_path.parent

TABLE_NAME = "weather.weather_daily"


def get_newest_file_by_prefix(prefix: str) -> Path | None:
    """
    Finds the newest file with the given prefix and deletes older ones.
    Files are expected to be named like: prefix_YYYY-MM-DD.json
    """
    if not data_dir.exists():
        return None

    pattern = re.compile(rf"^{re.escape(prefix)}_(\d{{4}}-\d{{2}}-\d{{2}})\.json$")
    matching_files = []

    for file_path in data_dir.glob(f"{prefix}_*.json"):
        match = pattern.match(file_path.name)
        if match:
            try:
                date_str = match.group(1)
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                matching_files.append((file_date, file_path))
            except ValueError:
                continue

    if not matching_files:
        return None

    matching_files.sort(key=lambda x: x[0], reverse=True)
    newest_date, newest_file = matching_files[0]

    deleted_count = 0
    for _date, file_path in matching_files[1:]:
        try:
            file_path.unlink()
            deleted_count += 1
            print(f"  Deleted older file: {file_path.name}")
        except Exception as e:
            print(f"  Could not delete {file_path.name}: {e}")

    if deleted_count > 0:
        print(
            f"  Kept newest {prefix} file: {newest_file.name} (deleted {deleted_count} older file(s))"
        )
    else:
        print(f"  Using {prefix} file: {newest_file.name}")

    return newest_file


def payload_to_dataframe(payload: dict, source_endpoint: str) -> pd.DataFrame:
    """Convert Open-Meteo's {"daily": {"time": [...], "var": [...]}} shape
    into one row per day."""
    daily = payload.get("daily", {})
    if not daily or not daily.get("time"):
        return pd.DataFrame()

    df = pd.DataFrame(daily)
    df = df.rename(columns={"time": "date_day"})
    df["date_day"] = pd.to_datetime(df["date_day"]).dt.date
    df["source_endpoint"] = source_endpoint
    df["ingested_at"] = datetime.now()
    return df


def load_to_duckdb(dataframes: list[pd.DataFrame]):
    """Upsert-by-date: for each incoming batch, delete any existing rows for
    the same date_day values, then insert the batch."""
    db_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS weather;")

    for df in dataframes:
        if df is None or df.empty:
            continue

        temp_table = "temp_weather_daily"
        con.register(temp_table, df)

        table_exists = (
            con.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'weather' AND table_name = 'weather_daily'"
            ).fetchone()[0]
            > 0
        )

        if table_exists:
            con.execute(
                f"DELETE FROM {TABLE_NAME} WHERE date_day IN "
                f"(SELECT date_day FROM {temp_table})"
            )
            con.execute(f"INSERT INTO {TABLE_NAME} SELECT * FROM {temp_table}")
            print(f"Upserted {len(df)} day(s) into {TABLE_NAME}")
        else:
            con.execute(f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM {temp_table}")
            print(f"Created table {TABLE_NAME} with {len(df)} day(s)")

        con.unregister(temp_table)

    con.close()
    print(f"\nLoading complete! Data saved to: {db_path}")


if __name__ == "__main__":
    print("Scanning for weather data files...")
    archive_file = get_newest_file_by_prefix("archive")
    forecast_file = get_newest_file_by_prefix("forecast")

    frames = []

    if archive_file:
        with open(archive_file) as f:
            archive_payload = json.load(f)
        archive_df = payload_to_dataframe(archive_payload, "archive")
        print(f"  Loaded {len(archive_df)} days from {archive_file.name}")
        frames.append(archive_df)

    if forecast_file:
        with open(forecast_file) as f:
            forecast_payload = json.load(f)
        forecast_df = payload_to_dataframe(forecast_payload, "forecast")
        print(f"  Loaded {len(forecast_df)} days from {forecast_file.name}")
        frames.append(forecast_df)

    if not frames:
        print("No weather files found to load.")
    else:
        print("\nLoading data into DuckDB...")
        load_to_duckdb(frames)
