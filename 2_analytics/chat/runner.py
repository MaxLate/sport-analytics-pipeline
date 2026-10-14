"""Run one chat turn through the ADK pipeline and read the query state."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agents import DB_PATH, build_pipeline
from .query_tool import QueryFailed, execute_readonly_query
from .semantic_layer import allowed_tables, compile_question, format_metric_answer
from .sql_guard import SqlRejected

APP_NAME = "sport_analytics"
USER_ID = "local"
OLLAMA_API_BASE = "http://localhost:11434"

_sessions = InMemorySessionService()
_runner: Runner | None = None


class ChatUnavailable(Exception):
    """The local model server could not be reached."""


@dataclass
class ChatResult:
    answer: str
    sql: str | None
    row_count: int | None
    truncated: bool
    error: str | None


_SMALL_TALK = re.compile(
    r"^(?:hi|hello|hey|yo|thanks|thank you|help|who are you|what can you do|"
    r"how are you(?: doing)?|how(?:'| i)s it going|"
    r"good (?:morning|afternoon|evening))"
    r"[\s!.?]*$",
    re.IGNORECASE,
)


def small_talk_answer(message: str) -> str | None:
    """Greetings never reach DuckDB."""
    if _SMALL_TALK.match(message.strip()):
        return (
            "I can answer questions about your recovery, sleep, workouts, "
            "and local weather."
        )
    return None


async def run_chat(message: str, session_id: str) -> ChatResult:
    greeting = small_talk_answer(message)
    if greeting:
        return ChatResult(
            answer=greeting,
            sql=None,
            row_count=None,
            truncated=False,
            error=None,
        )

    compiled = compile_question(message)
    if compiled:
        return _answer_compiled_question(compiled)

    os.environ.setdefault("OLLAMA_API_BASE", OLLAMA_API_BASE)
    await _ensure_session(session_id)
    answer = ""
    try:
        async for event in _get_runner().run_async(
            user_id=USER_ID,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
            state_delta={
                "user_question": message,
                "question_relevant": "",
                "semantic_plan": "",
                "executed_sql": "",
                "query_result": "",
                "query_error": "",
                "row_count": None,
                "truncated": False,
            },
        ):
            if _event_says_model_is_down(event):
                raise ChatUnavailable(_unavailable_message())
            if event.author == "answer_agent" and event.is_final_response():
                text = _event_text(event)
                if text:
                    answer = text.strip()
    except ChatUnavailable:
        raise
    except Exception as exc:
        if _is_unavailable(exc):
            raise ChatUnavailable(_unavailable_message()) from exc
        raise

    session = await _sessions.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    state = dict(session.state) if session and session.state else {}
    return _result_from_state(state, answer)


def _answer_compiled_question(compiled: dict) -> ChatResult:
    try:
        result = execute_readonly_query(
            compiled["sql"], str(DB_PATH), set(allowed_tables())
        )
    except (SqlRejected, QueryFailed) as exc:
        return ChatResult(
            answer="I couldn't answer that from your data.",
            sql=compiled["sql"],
            row_count=None,
            truncated=False,
            error=exc.reason,
        )
    value = result["rows"][0]["value"] if result["rows"] else None
    return ChatResult(
        answer=format_metric_answer(
            compiled["aggregation"], compiled["label"], value, compiled["period"]
        ),
        sql=result["sql"],
        row_count=result["row_count"],
        truncated=result["truncated"],
        error=None,
    )


async def _ensure_session(session_id: str) -> None:
    existing = await _sessions.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    if existing is None:
        await _sessions.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )


def _get_runner() -> Runner:
    global _runner
    if _runner is None:
        _runner = Runner(
            app_name=APP_NAME,
            agent=build_pipeline(),
            session_service=_sessions,
        )
    return _runner


def _result_from_state(state: dict, answer: str) -> ChatResult:
    error = state.get("query_error") or None
    sql = state.get("executed_sql") or None
    row_count = state.get("row_count")
    truncated = bool(state.get("truncated"))
    if state.get("question_relevant") != "yes" and not sql:
        return ChatResult(
            answer=answer
            or (
                "I can only answer questions about your recovery, sleep, "
                "workouts, and local weather."
            ),
            sql=None,
            row_count=None,
            truncated=False,
            error=None,
        )
    if error:
        if _is_guard_rejection(error):
            return ChatResult(
                answer="",
                sql=sql,
                row_count=row_count,
                truncated=truncated,
                error=error,
            )
        return ChatResult(
            answer=(
                "I couldn't answer that from your data. "
                "Ask about recovery, sleep, workouts, or weather."
            ),
            sql=sql,
            row_count=row_count,
            truncated=truncated,
            error=None,
        )
    if not sql:
        return ChatResult(
            answer="",
            sql=None,
            row_count=None,
            truncated=False,
            error="The assistant did not query the database.",
        )
    if not answer:
        if row_count == 0:
            answer = "The query returned no rows."
        else:
            answer = "The query ran, but no answer was produced."
    return ChatResult(
        answer=answer,
        sql=sql,
        row_count=row_count,
        truncated=truncated,
        error=None,
    )


def _is_guard_rejection(error: str) -> bool:
    text = error.lower()
    return "not allowed" in text or "read-only" in text or "exactly one sql" in text


def _event_text(event) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    return "\n".join(part.text for part in parts if getattr(part, "text", None))


def _event_says_model_is_down(event) -> bool:
    if not getattr(event, "error_code", None):
        return False
    return _message_is_unavailable(getattr(event, "error_message", "") or "")


def _is_unavailable(exc: BaseException) -> bool:
    current: BaseException | None = exc
    while current is not None:
        if type(current).__name__ in {
            "APIConnectionError",
            "ConnectError",
            "ConnectionError",
            "ConnectTimeout",
        }:
            return True
        if _message_is_unavailable(str(current)):
            return True
        current = current.__cause__ or current.__context__
    return False


def _message_is_unavailable(message: str) -> bool:
    text = message.lower()
    return "connection refused" in text or "failed to connect" in text


def _unavailable_message() -> str:
    return "Ollama is not available. Start it locally and try again."
