"""Two-step ADK workflow: query DuckDB, then answer from those rows."""

from __future__ import annotations

import os
from pathlib import Path

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.tool_context import ToolContext

from .query_tool import QueryFailed, execute_readonly_query
from .semantic_layer import allowed_tables, lookup_question
from .sql_guard import SqlRejected

DB_PATH = Path(
    os.environ.get(
        "WAREHOUSE_PATH",
        Path(__file__).resolve().parents[2]
        / "0_data"
        / "database"
        / "warehouse.duckdb",
    )
).resolve()
DEFAULT_MODEL = "ollama_chat/llama3.2:latest"

SCOPE_INSTRUCTION = """
You decide whether the user's question can be answered from this person's
recovery, sleep, workout, and local weather data.

User question: {user_question?}

Call lookup_semantic_layer once. Pass a comma-separated list of topics chosen
only from: recovery, sleep, moon, workouts, weather, availability, dates.
Pass an empty string when the question is a greeting or about any other subject.
Do not answer the user.
""".strip()

SQL_INSTRUCTION = """
Relevance: {question_relevant?}

User question: {user_question?}

Semantic plan:
{semantic_plan?}

If relevance is not yes, do not call run_readonly_query.
If relevance is yes, call run_readonly_query once. Use only tables, columns,
and joins from the semantic plan. Prefer marts.fct_daily_overview when it
already contains the measures. Filter dates with date_day, except year, month,
week, and day, which exist only on marts.dim_dates. For a whole month use a
half-open date range, for example March 2026 is date_day >= DATE '2026-03-01'
AND date_day < DATE '2026-04-01'. Never reduce a requested month to one day.
If the tool returns an error, call it once more with a corrected query. Do not
answer the user.
""".strip()

ANSWER_INSTRUCTION = """
The user asked: {user_question?}

Relevance: {question_relevant?}
Semantic plan: {semantic_plan?}
Executed SQL: {executed_sql?}
Row count: {row_count?}
Result truncated: {truncated?}
Rows: {query_result?}
Query error: {query_error?}

If relevance is no, say that you can only answer questions about recovery,
sleep, workouts, and local weather. Otherwise answer in a few plain
sentences, using only the rows above. If the query error is non-empty, say
the question could not be answered. If the row count is 0, say there were no
matching rows. Do not invent numbers, dates, or causes. Do not give medical advice.
""".strip()


def build_pipeline() -> SequentialAgent:
    """Scope the question, query DuckDB, then answer. The order is fixed."""
    scope_agent = LlmAgent(
        name="scope_agent",
        model=_model(),
        description="Checks the question and looks up semantic models and joins.",
        instruction=SCOPE_INSTRUCTION,
        tools=[_semantic_tool()],
        include_contents="none",
    )
    sql_agent = LlmAgent(
        name="sql_agent",
        model=_model(),
        description="Writes and runs one read-only analytics query.",
        instruction=SQL_INSTRUCTION,
        tools=[_query_tool()],
        include_contents="none",
    )
    answer_agent = LlmAgent(
        name="answer_agent",
        model=_model(),
        description="Answers from the query result only.",
        instruction=ANSWER_INSTRUCTION,
        tools=[],
        include_contents="none",
    )
    return SequentialAgent(
        name="analytics_chat",
        description="Queries DuckDB, then answers from the result.",
        sub_agents=[scope_agent, sql_agent, answer_agent],
    )


def _model() -> LiteLlm:
    model_name = os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
    return LiteLlm(model=model_name)


def _semantic_tool():
    def lookup_semantic_layer(topics: str, tool_context: ToolContext) -> dict:
        """Find which semantic models and joins can answer the question.

        Args:
            topics: Comma-separated topic names, or an empty string.
        """
        question = str(tool_context.state.get("user_question") or "")
        result = lookup_question(question, topics)
        tool_context.state["question_relevant"] = "yes" if result["relevant"] else "no"
        tool_context.state["semantic_plan"] = result["plan"]
        return {
            "relevant": result["relevant"],
            "topics": result["topics"],
            "plan": result["plan"],
        }

    return lookup_semantic_layer


def _query_tool():
    def run_readonly_query(sql: str, tool_context: ToolContext) -> dict:
        """Run one read-only DuckDB query against the analytics database.

        Args:
            sql: A single SELECT or WITH query using only allowed tables.
        """
        try:
            result = execute_readonly_query(sql, str(DB_PATH), set(allowed_tables()))
        except (SqlRejected, QueryFailed) as exc:
            tool_context.state["executed_sql"] = sql
            tool_context.state["query_result"] = None
            tool_context.state["row_count"] = None
            tool_context.state["truncated"] = False
            tool_context.state["query_error"] = exc.reason
            return {"error": exc.reason}

        tool_context.state["executed_sql"] = result["sql"]
        tool_context.state["query_result"] = result["rows"]
        tool_context.state["row_count"] = result["row_count"]
        tool_context.state["truncated"] = result["truncated"]
        tool_context.state["query_error"] = ""
        return result

    return run_readonly_query
