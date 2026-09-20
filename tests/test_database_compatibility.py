import sqlite3

from sqlalchemy import inspect, select

from choice_agent.config import Settings
from choice_agent.database import Database
from choice_agent.db_models import AgentRunRecord
from choice_agent.schemas import AgentRun


def test_create_all_adds_agent_run_observability_columns_to_legacy_database(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute("""
        CREATE TABLE agent_run (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id VARCHAR(128) NOT NULL,
            decision_id VARCHAR(64) NOT NULL,
            agent_name VARCHAR(128) NOT NULL,
            model_name VARCHAR(128),
            status VARCHAR(32) NOT NULL,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            input_payload JSON,
            output_payload JSON,
            error_message TEXT,
            created_at DATETIME NOT NULL
        )
    """)
    connection.execute(
        "INSERT INTO agent_run "
        "(trace_id, decision_id, agent_name, status, latency_ms, created_at) "
        "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        ("legacy-trace", "legacy-decision", "LegacyAgent", "SUCCESS", 3),
    )
    connection.commit()
    connection.close()

    database = Database(Settings(database_url=f"sqlite:///{path}"))
    database.create_all()
    database.create_all()

    columns = {item["name"] for item in inspect(database.engine).get_columns("agent_run")}
    assert {
        "provider", "prompt_version", "input_tokens", "output_tokens", "total_tokens",
        "estimated_cost", "retry_count", "fallback_used", "fallback_reason",
    } <= columns
    with database.session_factory() as db:
        row = db.scalar(select(AgentRunRecord).where(AgentRunRecord.trace_id == "legacy-trace"))
        assert row is not None
        assert row.provider is None
        assert row.total_tokens is None
        assert row.fallback_used is None


def test_legacy_agent_run_json_loads_without_observability_fields():
    run = AgentRun.model_validate({
        "agentName": "LegacyAgent",
        "modelName": "legacy-model",
        "status": "SUCCESS",
        "latencyMs": 8,
    })

    assert run.provider is None
    assert run.total_tokens is None
    assert run.retry_count is None
    assert run.fallback_used is None
