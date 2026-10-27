"""Read the dbt-style semantic model and turn a question into tables and joins."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

LAYER_PATH = Path(__file__).with_name("semantic_layer.yml")


@lru_cache(maxsize=1)
def load_semantic_layer(path: str = str(LAYER_PATH)) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    models = {model["name"]: model for model in document["semantic_models"]}
    return {
        "topics": document["topics"],
        "models": models,
        "aggregations": document.get("aggregations", {}),
        "filters": document.get("filters", []),
        "measures": document.get("measures", []),
    }


def allowed_tables() -> frozenset[str]:
    """The chat may query exactly the tables declared as semantic models."""
    return frozenset(
        model["model"] for model in load_semantic_layer()["models"].values()
    )


_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


# Words the compiler cannot express. A question containing one goes to the agents
# instead of being answered with that part silently dropped.
_UNSUPPORTED = re.compile(
    r"\b(?:today|yesterday|tonight|week|weeks|weekly|weekend|weekends|weekday|"
    r"weekdays|month|months|monthly|year|years|yearly|daily|last|this|past|"
    r"previous|recent|recently|since|between|ago|per|each|by|which|when|where|"
    r"compare|compared|versus|vs|trend|than|morning|evening|night|and|or)\b"
)
_PLAIN_COUNT = re.compile(
    r"\b(?:how many|number of|count of)\s+"
    r"(?:workouts?|sessions?|training sessions?|trainings?)\b"
)


def compile_question(question: str) -> dict[str, str] | None:
    """Build one aggregate query when every part of the question is understood."""
    layer = load_semantic_layer()
    text = question.lower()
    aggregation = _aggregation_for(text, layer["aggregations"])
    if aggregation is None or _UNSUPPORTED.search(text):
        return None

    period = _period_for(text)
    if period is None and _mentions_a_period(text):
        return None
    matched_filters = _filters_for(text, layer["filters"])
    if len(matched_filters) > 1:
        return None
    matched_filter = matched_filters[0] if matched_filters else None
    measure = _measure_for(text, aggregation, layer["measures"])
    if aggregation == "count":
        if matched_filter is None and not _PLAIN_COUNT.search(text):
            return None
        model_name = matched_filter["model"] if matched_filter else "workouts"
        expression = "COUNT(*)"
        label = matched_filter["label"] if matched_filter else "workouts"
        where = _filter_sql(matched_filter)
    else:
        if measure is None or aggregation not in measure["aggs"]:
            return None
        if matched_filter and matched_filter["model"] != measure["model"]:
            return None
        model_name = measure["model"]
        expression = f"{_sql_agg(aggregation)}({measure['expr']})"
        label = measure["label"]
        where = _filter_sql(matched_filter)
        if measure.get("where"):
            where = f"{where} AND {measure['where']}" if where else measure["where"]

    table = layer["models"][model_name]["model"]
    if period:
        date_sql = f"date_day >= DATE '{period['start']}' AND date_day < DATE '{period['end']}'"
        where = f"{where} AND {date_sql}" if where else date_sql
    sql = f"SELECT {expression} AS value FROM {table}"
    if where:
        sql = f"{sql} WHERE {where}"
    return {
        "sql": sql,
        "aggregation": aggregation,
        "label": label,
        "period": period["label"] if period else "",
    }


def format_metric_answer(aggregation: str, label: str, value: Any, period: str) -> str:
    """Turn one aggregate value into the sentence the user asked for."""
    when = f" in {period}" if period else ""
    if aggregation == "count":
        count = 0 if value is None else int(value)
        noun = label[:-1] if count == 1 and label.endswith("s") else label
        return f"You have done {count} {noun}{when}."
    if value is None:
        return f"There is no {label}{when}."
    number = int(value) if float(value).is_integer() else round(float(value), 1)
    verbs = {"average": "average", "sum": "total", "max": "highest"}
    return f"Your {verbs[aggregation]} {label}{when} was {number}."


def lookup_question(
    question: str, topics: list[str] | str | None = None
) -> dict[str, Any]:
    """Return whether the question is in scope, and the models and joins to use."""
    layer = load_semantic_layer()
    selected = _topics_for(question, topics, layer["topics"])
    if not selected:
        return {
            "relevant": False,
            "topics": [],
            "models": [],
            "joins": [],
            "plan": "The question is not about recovery, sleep, workouts, or weather.",
        }

    model_names: list[str] = []
    for topic in selected:
        for name in layer["topics"][topic]["models"]:
            if name not in model_names:
                model_names.append(name)

    models = [layer["models"][name] for name in model_names]
    joins = _joins_between(models)
    return {
        "relevant": True,
        "topics": selected,
        "models": [_model_summary(model) for model in models],
        "joins": joins,
        "plan": _plan_text(selected, models, joins),
    }


def _topics_for(
    question: str, requested: list[str] | str | None, topics: dict
) -> list[str]:
    found = []
    for name in _normalize_topics(requested):
        if name in topics and name not in found:
            found.append(name)
    text = question.lower()
    for name, topic in topics.items():
        if name in found:
            continue
        if any(keyword.lower() in text for keyword in topic["keywords"]):
            found.append(name)
    return found


def _normalize_topics(requested: list[str] | str | None) -> list[str]:
    if requested is None:
        return []
    if isinstance(requested, str):
        raw_parts = re.split(r"[,;\n]", requested)
    else:
        raw_parts = []
        for item in requested:
            raw_parts.extend(re.split(r"[,;\n]", str(item)))
    return [part.strip().lower() for part in raw_parts if part.strip()]


def _joins_between(models: list[dict]) -> list[str]:
    joins = []
    for left_index, left in enumerate(models):
        left_entities = {entity["name"]: entity for entity in left.get("entities", [])}
        for right in models[left_index + 1 :]:
            for entity in right.get("entities", []):
                match = left_entities.get(entity["name"])
                if match is None:
                    continue
                joins.append(
                    f"{left['model']}.{match['expr']} = {right['model']}.{entity['expr']}"
                )
    return joins


def _model_summary(model: dict) -> dict[str, Any]:
    return {
        "name": model["name"],
        "table": model["model"],
        "grain": model["grain"],
        "columns": list(model["columns"]),
        "notes": model.get("notes", ""),
    }


def _aggregation_for(text: str, aggregations: dict[str, list[str]]) -> str | None:
    for name, phrases in aggregations.items():
        if any(phrase in text for phrase in phrases):
            return name
    return None


def _mentions_a_period(text: str) -> bool:
    names = "|".join(_MONTHS)
    return bool(re.search(rf"\b(?:{names}|20\d{{2}})\b", text))


def _period_for(text: str) -> dict[str, str] | None:
    names = "|".join(_MONTHS)
    if len(re.findall(r"\b20\d{2}\b", text)) > 1:
        return None
    match = re.search(rf"\b({names})\s+(20\d{{2}})\b", text)
    if match is None:
        year_match = re.search(r"\b(?:in|during)\s+(20\d{2})\b", text)
        if year_match is None or re.search(rf"\b(?:{names})\b", text):
            return None
        year = int(year_match.group(1))
        return {
            "label": str(year),
            "start": f"{year:04d}-01-01",
            "end": f"{year + 1:04d}-01-01",
        }
    month = _MONTHS[match.group(1)]
    year = int(match.group(2))
    next_month = 1 if month == 12 else month + 1
    next_year = year + 1 if month == 12 else year
    return {
        "label": f"{match.group(1).title()} {year}",
        "start": f"{year:04d}-{month:02d}-01",
        "end": f"{next_year:04d}-{next_month:02d}-01",
    }


def _filters_for(text: str, filters: list[dict]) -> list[dict]:
    return [
        item
        for item in filters
        if any(re.search(rf"\b{re.escape(term)}\b", text) for term in item["terms"])
    ]


def _measure_for(text: str, aggregation: str, measures: list[dict]) -> dict | None:
    ranked = sorted(
        measures,
        key=lambda item: max(len(term) for term in item["terms"]),
        reverse=True,
    )
    for item in ranked:
        if aggregation not in item["aggs"]:
            continue
        if any(re.search(rf"\b{re.escape(term)}\b", text) for term in item["terms"]):
            return item
    return None


def _filter_sql(matched_filter: dict | None) -> str:
    if matched_filter is None:
        return ""
    values = ", ".join(_quote(value) for value in matched_filter["values"])
    return f"{matched_filter['column']} IN ({values})"


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sql_agg(aggregation: str) -> str:
    return {"average": "AVG", "sum": "SUM", "max": "MAX"}[aggregation]


def _plan_text(topics: list[str], models: list[dict], joins: list[str]) -> str:
    lines = [f"Topics: {', '.join(topics)}", "Use only these tables and columns:"]
    for model in models:
        columns = ", ".join(model["columns"])
        lines.append(f"- {model['model']} ({model['grain']}): {columns}")
        if model.get("notes"):
            lines.append(f"  {model['notes']}")
    if joins:
        lines.append("Allowed joins:")
        lines.extend(f"- {join}" for join in joins)
    else:
        lines.append("No join is required.")
    lines.append(
        "year, month, week, and day exist only on marts.dim_dates. "
        "Filter every other table with date_day."
    )
    return "\n".join(lines)
