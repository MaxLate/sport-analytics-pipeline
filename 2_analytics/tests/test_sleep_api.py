"""The sleep endpoint carries what the Sleep page analyses."""

import importlib
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

api = importlib.import_module("2_analytics.api.main")


@pytest.mark.skipif(not Path(api.DUCKDB_PATH).exists(), reason="warehouse not built")
def test_sleep_query_exposes_wake_up_date_and_temperature():
    con = duckdb.connect(api.DUCKDB_PATH, read_only=True)
    try:
        frame = con.execute(f"SELECT * FROM ({api.SLEEP_SQL}) LIMIT 50").fetchdf()
    finally:
        con.close()

    assert {"wake_up_date", "temperature_min_celsius", "nap"} <= set(frame.columns)
    assert frame["temperature_min_celsius"].notna().any()


@pytest.mark.skipif(not Path(api.DUCKDB_PATH).exists(), reason="warehouse not built")
def test_workouts_query_has_the_training_fields():
    con = duckdb.connect(api.DUCKDB_PATH, read_only=True)
    try:
        frame = con.execute(f"SELECT * FROM ({api.WORKOUTS_SQL}) LIMIT 1").fetchdf()
    finally:
        con.close()

    assert {
        "date_day",
        "workout_start_time",
        "activity_name",
        "is_sport_exercise",
        "duration_minutes",
        "activity_strain",
        "average_heart_rate",
        "max_heart_rate",
    } <= set(frame.columns)
