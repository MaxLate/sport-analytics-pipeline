"""The chat's semantic layer must match the dbt project it describes."""

import csv
import importlib
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

semantic_layer = importlib.import_module("2_analytics.chat.semantic_layer")
chat_agents = importlib.import_module("2_analytics.chat.agents")

ACTIVITY_SEED = ROOT / "1_elt" / "2_transform" / "seeds" / "activity_mapping.csv"


def _referenced_columns() -> dict[str, set[str]]:
    layer = semantic_layer.load_semantic_layer()
    referenced: dict[str, set[str]] = {}
    for model in layer["models"].values():
        columns = referenced.setdefault(model["model"], set())
        columns.update(model.get("columns", []))
        columns.update(entity["expr"] for entity in model.get("entities", []))
        columns.update(measure["expr"] for measure in model.get("measures", []))
    for item in layer["filters"] + layer["measures"]:
        table = layer["models"][item["model"]]["model"]
        referenced[table].add(item.get("column") or item["expr"])
    return referenced


def test_filter_values_exist_in_the_activity_seed():
    with open(ACTIVITY_SEED, encoding="utf-8") as handle:
        aligned = {row["aligned_activity_name"] for row in csv.DictReader(handle)}

    for item in semantic_layer.load_semantic_layer()["filters"]:
        missing = set(item["values"]) - aligned
        assert (
            not missing
        ), f"filter {item['label']!r} uses unknown activities {missing}"


def test_every_seed_activity_has_a_filter():
    with open(ACTIVITY_SEED, encoding="utf-8") as handle:
        aligned = {row["aligned_activity_name"] for row in csv.DictReader(handle)}

    covered = {
        value
        for item in semantic_layer.load_semantic_layer()["filters"]
        for value in item["values"]
    }
    missing = aligned - covered
    assert not missing, f"add filters to semantic_layer.yml for {sorted(missing)}"


@pytest.mark.skipif(not chat_agents.DB_PATH.exists(), reason="warehouse not built")
def test_every_referenced_column_exists_in_the_warehouse():
    con = duckdb.connect(str(chat_agents.DB_PATH), read_only=True)
    try:
        for table, columns in _referenced_columns().items():
            schema, name = table.split(".")
            actual = {
                row[0]
                for row in con.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = ? AND table_name = ?",
                    [schema, name],
                ).fetchall()
            }
            assert actual, f"{table} does not exist"
            missing = columns - actual
            assert not missing, f"{table} is missing {sorted(missing)}"
    finally:
        con.close()
