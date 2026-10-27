"""The chat's semantic lookup decides scope, tables, and joins."""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

semantic_layer = importlib.import_module("2_analytics.chat.semantic_layer")
lookup_question = semantic_layer.lookup_question
compile_question = semantic_layer.compile_question
format_metric_answer = semantic_layer.format_metric_answer


def test_recovery_question_uses_the_recovery_table_and_the_date_join():
    result = lookup_question("What was my average recovery in March?")
    tables = {model["table"] for model in result["models"]}
    assert result["relevant"] is True
    assert "marts.fct_whoop_recovery" in tables
    assert "marts.dim_dates" in tables
    assert any(
        join == "marts.fct_whoop_recovery.date_day = marts.dim_dates.date_day"
        for join in result["joins"]
    )
    assert "year, month, week, and day exist only on marts.dim_dates" in result["plan"]


def test_sleep_and_weather_join_on_wake_up_date():
    result = lookup_question("Does colder weather line up with my sleep performance?")
    assert "sleep" in result["topics"]
    assert "weather" in result["topics"]
    assert any(
        "wake_up_date = marts.fct_weather_daily.date_day" in join
        for join in result["joins"]
    )


def test_unrelated_question_is_out_of_scope():
    result = lookup_question("How do I bake bread?", topics=["cooking"])
    assert result["relevant"] is False
    assert result["models"] == []
    assert result["joins"] == []


def test_count_question_compiles_to_one_filtered_aggregate():
    compiled = compile_question("How many runs did I do in March 2026?")
    assert compiled is not None
    assert compiled["aggregation"] == "count"
    assert compiled["label"] == "runs"
    assert "COUNT(*)" in compiled["sql"]
    assert "marts.fct_whoop_workouts" in compiled["sql"]
    assert "'Run'" in compiled["sql"]
    assert "'Trail Run'" in compiled["sql"]
    assert "DATE '2026-03-01'" in compiled["sql"]
    assert "DATE '2026-04-01'" in compiled["sql"]
    assert "fct_daily_overview" not in compiled["sql"]
    assert "total_strain" not in compiled["sql"]


def test_average_question_uses_the_matching_measure():
    compiled = compile_question("What was my average recovery in March 2026?")
    assert compiled["aggregation"] == "average"
    assert "AVG(recovery_score)" in compiled["sql"]
    assert "marts.fct_whoop_recovery" in compiled["sql"]


def test_open_ended_question_stays_with_the_agents():
    assert (
        compile_question("Does colder weather line up with my sleep performance?")
        is None
    )


def test_count_question_filters_on_any_seed_activity():
    compiled = compile_question("How many HIIT workouts have I done?")
    assert compiled is not None
    assert "activity_name IN ('HIIT')" in compiled["sql"]
    assert compiled["label"] == "HIIT workouts"


def test_year_question_uses_a_full_year_range():
    compiled = compile_question("How many runs did I do in 2026?")
    assert "DATE '2026-01-01'" in compiled["sql"]
    assert "DATE '2027-01-01'" in compiled["sql"]
    assert compiled["period"] == "2026"


def test_questions_with_unparsed_parts_stay_with_the_agents():
    for question in [
        "How many workouts did I do last week?",
        "What was my average recovery score this month?",
        "How many football workouts have I done?",
        "How many runs per month did I do in 2026?",
        "Which sport has the highest strain?",
        "How many runs did I do on weekends?",
    ]:
        assert compile_question(question) is None, question


def test_count_answer_is_one_sentence():
    assert format_metric_answer("count", "runs", 8, "March 2026") == (
        "You have done 8 runs in March 2026."
    )
    assert format_metric_answer("count", "runs", 1, "March 2026") == (
        "You have done 1 run in March 2026."
    )


def test_agent_topics_are_limited_to_the_semantic_layer():
    result = lookup_question("tell me something", topics=["recovery"])
    assert result["topics"] == ["recovery"]
    assert any(
        model["table"] == "marts.fct_whoop_recovery" for model in result["models"]
    )
