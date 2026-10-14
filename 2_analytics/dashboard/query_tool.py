"""Run one validated read-only query against warehouse.duckdb."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from .sql_guard import validate_readonly_sql

MAX_ROWS = 200


class QueryFailed(Exception):
    """DuckDB rejected a query that had already passed the safety checks."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def execute_readonly_query(
    sql: str,
    db_path: str,
    allowed_tables: set[str],
    max_rows: int = MAX_ROWS,
) -> dict[str, Any]:
    """Validate, execute, and return a JSON-safe bounded result."""
    validated = validate_readonly_sql(sql, allowed_tables)
    limited = f"SELECT * FROM ({validated}) AS query_result LIMIT {max_rows + 1}"

    try:
        connection = duckdb.connect(db_path, read_only=True)
    except duckdb.Error as exc:
        raise QueryFailed(str(exc)) from exc

    try:
        frame = connection.execute(limited).fetchdf()
    except duckdb.Error as exc:
        raise QueryFailed(str(exc)) from exc
    finally:
        connection.close()

    truncated = len(frame) > max_rows
    if truncated:
        frame = frame.head(max_rows)

    rows = [_json_row(row) for row in frame.to_dict(orient="records")]
    return {
        "sql": validated,
        "columns": list(frame.columns),
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
    }


def _json_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_value(value) for key, value in row.items()}


def _format_timestamp(value: datetime) -> str:
    """DATE columns arrive as midnight timestamps; keep real times intact."""
    if (
        value.hour == 0
        and value.minute == 0
        and value.second == 0
        and value.microsecond == 0
        and value.tzinfo is None
    ):
        return value.date().isoformat()
    return value.isoformat()


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return _format_timestamp(value)
    if isinstance(value, datetime):
        return _format_timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if np.isnan(value):
            return None
        return float(value)
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, np.bool_):
        return bool(value)
    return value
