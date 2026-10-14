"""Reject anything except one read-only query against allowlisted tables."""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

BLOCKED_FUNCTIONS = {
    "read_blob",
    "read_csv",
    "read_csv_auto",
    "read_json",
    "read_json_auto",
    "read_json_objects",
    "read_ndjson",
    "read_ndjson_auto",
    "read_parquet",
    "read_text",
    "read_xlsx",
    "glob",
    "parquet_scan",
    "sqlite_scan",
    "postgres_scan",
    "mysql_scan",
    "iceberg_scan",
    "delta_scan",
    "sniff_csv",
}


class SqlRejected(Exception):
    """The chat tried to run SQL the dashboard will not execute."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def validate_readonly_sql(sql: str, allowed_tables: set[str]) -> str:
    """Return normalized SQL, or raise SqlRejected."""
    text = (sql or "").strip()
    if not text:
        raise SqlRejected("SQL is empty")

    try:
        statements = sqlglot.parse(text, read="duckdb")
    except ParseError as exc:
        raise SqlRejected("SQL could not be parsed") from exc

    statements = [statement for statement in statements if statement is not None]
    if len(statements) != 1:
        raise SqlRejected("Exactly one SQL statement is allowed")

    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise SqlRejected("Only a single read-only query is allowed")

    allowed = {name.lower() for name in allowed_tables}
    cte_names = {
        cte.alias_or_name.lower()
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }

    for table in statement.find_all(exp.Table):
        name = (table.name or "").lower()
        schema = (table.db or "").lower()
        if not schema and name in cte_names:
            continue
        qualified = f"{schema}.{name}" if schema else name
        if qualified not in allowed:
            raise SqlRejected(f"Table is not allowed: {qualified}")

    for func in statement.find_all(exp.Func):
        func_name = (func.sql_name() or "").lower()
        if func_name in BLOCKED_FUNCTIONS:
            raise SqlRejected(f"Function is not allowed: {func_name}")

    return statement.sql(dialect="duckdb")
