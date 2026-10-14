"""Execution of the chat's read-only DuckDB query."""

import importlib
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

query_tool = importlib.import_module("2_analytics.dashboard.query_tool")
sql_guard = importlib.import_module("2_analytics.dashboard.sql_guard")

execute_readonly_query = query_tool.execute_readonly_query
SqlRejected = sql_guard.SqlRejected
QueryFailed = query_tool.QueryFailed

ALLOWED = {"marts.fct_whoop_recovery"}


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "warehouse.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA marts")
    con.execute(
        """
        CREATE TABLE marts.fct_whoop_recovery (
            date_day DATE,
            recovery_score DOUBLE
        )
        """
    )
    con.execute(
        """
        INSERT INTO marts.fct_whoop_recovery VALUES
            (DATE '2026-01-01', 80),
            (DATE '2026-01-02', NULL),
            (DATE '2026-01-03', 60)
        """
    )
    con.close()
    return path


def test_runs_an_aggregate_and_serializes_nulls(database):
    result = execute_readonly_query(
        "SELECT date_day, recovery_score FROM marts.fct_whoop_recovery ORDER BY date_day",
        str(database),
        ALLOWED,
    )
    assert result["row_count"] == 3
    assert result["truncated"] is False
    assert result["rows"][1]["recovery_score"] is None
    assert result["rows"][0]["date_day"] == "2026-01-01"
    assert result["columns"] == ["date_day", "recovery_score"]


def test_caps_returned_rows(database):
    result = execute_readonly_query(
        "SELECT date_day FROM marts.fct_whoop_recovery ORDER BY date_day",
        str(database),
        ALLOWED,
        max_rows=2,
    )
    assert result["row_count"] == 2
    assert result["truncated"] is True


def test_rejected_sql_does_not_change_the_database(database):
    with pytest.raises(SqlRejected):
        execute_readonly_query(
            "DELETE FROM marts.fct_whoop_recovery",
            str(database),
            ALLOWED,
        )
    con = duckdb.connect(str(database), read_only=True)
    count = con.execute("SELECT count(*) FROM marts.fct_whoop_recovery").fetchone()[0]
    con.close()
    assert count == 3


def test_invalid_column_raises_query_failed(database):
    with pytest.raises(QueryFailed):
        execute_readonly_query(
            "SELECT missing_column FROM marts.fct_whoop_recovery",
            str(database),
            ALLOWED,
        )
