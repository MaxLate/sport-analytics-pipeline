"""Safety checks for the analytics chat's read-only SQL tool."""

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sql_guard = importlib.import_module("2_analytics.chat.sql_guard")
SqlRejected = sql_guard.SqlRejected
validate_readonly_sql = sql_guard.validate_readonly_sql

ALLOWED = {
    "marts.fct_whoop_recovery",
    "marts.fct_whoop_sleeps",
    "marts.fct_whoop_sleep_quality",
    "marts.fct_whoop_workouts",
    "marts.dim_whoop_workouts",
    "marts.fct_weather_daily",
    "marts.dim_dates",
    "marts.fct_daily_overview",
    "marts.data_check",
}


def _validate(sql: str) -> str:
    return validate_readonly_sql(sql, ALLOWED)


def test_allows_aggregate_on_an_approved_table():
    sql = _validate(
        "SELECT avg(recovery_score) AS avg_recovery FROM marts.fct_whoop_recovery"
    )
    assert "fct_whoop_recovery" in sql.lower()
    assert "avg" in sql.lower()


def test_allows_join_across_approved_tables():
    sql = _validate(
        """
        SELECT s.date_day, s.sleep_performance, w.temperature_min_celsius
        FROM marts.fct_whoop_sleep_quality s
        LEFT JOIN marts.fct_weather_daily w ON s.wake_up_date = w.date_day
        """
    )
    assert "fct_whoop_sleep_quality" in sql.lower()
    assert "fct_weather_daily" in sql.lower()


def test_allows_cte_that_reads_only_approved_tables():
    sql = _validate(
        """
        WITH recent AS (
            SELECT date_day, activity_strain
            FROM marts.fct_whoop_workouts
            WHERE date_day >= DATE '2026-01-01'
        )
        SELECT activity_strain FROM recent
        """
    )
    assert "recent" in sql.lower()


def test_allows_union_of_approved_tables():
    sql = _validate(
        """
        SELECT date_day FROM marts.fct_whoop_recovery
        UNION ALL
        SELECT date_day FROM marts.fct_weather_daily
        """
    )
    assert "union" in sql.lower()


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO marts.fct_whoop_recovery VALUES (1, DATE '2026-01-01', 50)",
        "UPDATE marts.fct_whoop_recovery SET recovery_score = 0",
        "DELETE FROM marts.fct_whoop_recovery",
        "DROP TABLE marts.fct_whoop_recovery",
        "CREATE TABLE evil AS SELECT 1",
        "ATTACH 'other.duckdb' AS other",
        "COPY marts.fct_whoop_recovery TO 'out.csv'",
        "PRAGMA database_list",
    ],
)
def test_rejects_statements_that_are_not_queries(sql):
    with pytest.raises(SqlRejected):
        _validate(sql)


def test_rejects_multiple_statements():
    with pytest.raises(SqlRejected):
        _validate(
            "SELECT 1 FROM marts.fct_whoop_recovery; DROP TABLE marts.fct_whoop_recovery"
        )


def test_rejects_unapproved_tables():
    with pytest.raises(SqlRejected):
        _validate("SELECT * FROM main.secret_notes")


def test_rejects_unqualified_tables():
    with pytest.raises(SqlRejected):
        _validate("SELECT * FROM fct_whoop_recovery")


def test_rejects_file_read_functions():
    with pytest.raises(SqlRejected):
        _validate("SELECT * FROM read_csv_auto('/etc/passwd')")


def test_rejects_read_parquet_inside_a_cte():
    with pytest.raises(SqlRejected):
        _validate(
            """
            WITH leaked AS (SELECT * FROM read_parquet('secrets.parquet'))
            SELECT * FROM leaked
            """
        )


def test_rejects_empty_sql():
    with pytest.raises(SqlRejected):
        _validate("   ")
