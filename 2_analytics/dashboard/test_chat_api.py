"""HTTP contract for the analytics chat, with the model runner mocked."""

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

api = importlib.import_module("2_analytics.dashboard.api")
chat_runner = importlib.import_module("2_analytics.dashboard.chat_runner")
agents = importlib.import_module("2_analytics.dashboard.chat_agents")

ChatResult = chat_runner.ChatResult
ChatUnavailable = chat_runner.ChatUnavailable


@pytest.fixture
def client():
    return TestClient(api.app)


def test_pipeline_scopes_then_queries_then_answers():
    pipeline = agents.build_pipeline()
    assert [agent.name for agent in pipeline.sub_agents] == [
        "scope_agent",
        "sql_agent",
        "answer_agent",
    ]
    assert pipeline.sub_agents[0].tools
    assert pipeline.sub_agents[1].tools
    assert not pipeline.sub_agents[2].tools
    assert all(agent.include_contents == "none" for agent in pipeline.sub_agents)


def test_chat_returns_the_answer_and_the_sql(client, monkeypatch):
    async def fake_run_chat(message, session_id):
        assert message == "average recovery"
        assert session_id == "session-1"
        return ChatResult(
            answer="Average recovery is 70.",
            sql="SELECT avg(recovery_score) FROM marts.fct_whoop_recovery",
            row_count=3,
            truncated=False,
            error=None,
        )

    monkeypatch.setattr(api, "run_chat", fake_run_chat)
    response = client.post(
        "/chat",
        json={"message": "average recovery", "session_id": "session-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Average recovery is 70."
    assert body["sql"].startswith("SELECT avg")
    assert body["row_count"] == 3
    assert body["truncated"] is False
    assert body["error"] is None


def test_empty_result_is_still_an_answer(client, monkeypatch):
    async def fake_run_chat(message, session_id):
        return ChatResult(
            answer="The query returned no rows.",
            sql="SELECT 1 FROM marts.fct_whoop_workouts WHERE false",
            row_count=0,
            truncated=False,
            error=None,
        )

    monkeypatch.setattr(api, "run_chat", fake_run_chat)
    response = client.post("/chat", json={"message": "workouts", "session_id": "s"})
    assert response.status_code == 200
    assert response.json()["row_count"] == 0
    assert "no rows" in response.json()["answer"]


def test_model_outage_is_unavailable(client, monkeypatch):
    async def fake_run_chat(message, session_id):
        raise ChatUnavailable("Ollama is not available")

    monkeypatch.setattr(api, "run_chat", fake_run_chat)
    response = client.post("/chat", json={"message": "recovery", "session_id": "s"})
    assert response.status_code == 503
    assert "Ollama" in response.json()["detail"]


def test_rejected_query_is_an_error(client, monkeypatch):
    async def fake_run_chat(message, session_id):
        return ChatResult(
            answer="",
            sql=None,
            row_count=None,
            truncated=False,
            error="Table is not allowed: main.secret",
        )

    monkeypatch.setattr(api, "run_chat", fake_run_chat)
    response = client.post("/chat", json={"message": "secrets", "session_id": "s"})
    assert response.status_code == 422
    assert "not allowed" in response.json()["detail"]


def test_out_of_scope_question_does_not_require_sql():
    result = chat_runner._result_from_state(
        {"question_relevant": "no", "semantic_plan": "out of scope"},
        answer="I can only answer questions about your training data.",
    )
    assert result.error is None
    assert result.sql is None
    assert "training data" in result.answer


def test_greeting_does_not_query_the_database():
    answer = chat_runner.small_talk_answer("How are you?")
    assert answer is not None
    assert "recovery" in answer
    assert chat_runner.small_talk_answer("How is my recovery?") is None


def test_database_error_becomes_a_plain_answer():
    result = chat_runner._result_from_state(
        {
            "query_error": 'Binder Error: Referenced column "year" not found',
            "executed_sql": "SELECT year FROM marts.fct_daily_overview",
            "row_count": None,
            "truncated": False,
        },
        answer="",
    )
    assert result.error is None
    assert "couldn't answer" in result.answer
    assert "Binder Error" not in result.answer
    assert result.sql.startswith("SELECT year")


def test_blank_message_is_rejected(client, monkeypatch):
    async def fake_run_chat(message, session_id):
        raise AssertionError("runner should not be called")

    monkeypatch.setattr(api, "run_chat", fake_run_chat)
    response = client.post("/chat", json={"message": "   ", "session_id": "s"})
    assert response.status_code == 400
