"""Synthetic raw data for demo mode and CI."""

import importlib
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sample = importlib.import_module("1_elt.1_load.sample.load_sample_data")


def _snapshot(path):
    con = duckdb.connect(str(path), read_only=True)
    try:
        return {
            table: con.execute(f"SELECT * FROM {table} ORDER BY ALL").fetchall()
            for table in sample.RAW_TABLES
        }
    finally:
        con.close()


def test_loads_every_raw_table(tmp_path):
    path = tmp_path / "warehouse.duckdb"
    sample.load_sample_data(path)

    data = _snapshot(path)
    assert len(data["whoop.whoop_recoveries"]) == sample.DAYS
    assert len(data["weather.weather_daily"]) == sample.DAYS
    assert len(data["whoop.whoop_sleeps"]) > sample.DAYS
    assert data["whoop.whoop_workouts"]


def test_is_deterministic(tmp_path):
    first, second = tmp_path / "a.duckdb", tmp_path / "b.duckdb"
    sample.load_sample_data(first)
    sample.load_sample_data(second)

    assert _snapshot(first) == _snapshot(second)


def test_refuses_existing_raw_data_without_force(tmp_path):
    path = tmp_path / "warehouse.duckdb"
    sample.load_sample_data(path)

    with pytest.raises(SystemExit):
        sample.load_sample_data(path)
    sample.load_sample_data(path, force=True)
