from __future__ import annotations

from datetime import datetime
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from choice_agent.db_models import AgentRunRecord, TraceRecord
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import AgentRun


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class TraceScope:
    def __init__(self, db: Session, trace_id: str, session_id: str, user_id: int):
        self.db = db
        self.repository = DietRepository(db)
        self.trace_id = trace_id
        self.session_id = session_id
        self.user_id = user_id
        self.started = perf_counter()
        self.events: list[dict[str, Any]] = []
        self.status = "SUCCESS"
        self.error_message: str | None = None
        self.closed = False

    def event(self, event_type: str, phase: str, input_payload: Any, output_payload: Any) -> None:
        self.events.append(
            {
                "stepOrder": len(self.events) + 1,
                "eventType": event_type,
                "phase": phase,
                "inputPayload": _jsonable(input_payload),
                "outputPayload": _jsonable(output_payload),
                "createdAt": datetime.now().isoformat(),
            }
        )

    def agent_run(self, run: AgentRun, decision_id: str) -> None:
        run_payload = _jsonable(run.model_dump(by_alias=True))
        event = {
            "stepOrder": len(self.events) + 1,
            "eventType": "AGENT_CALL",
            "phase": "AGENT",
            **run_payload,
            "createdAt": datetime.now().isoformat(),
        }
        self.events.append(event)
        self.db.add(
            AgentRunRecord(
                trace_id=self.trace_id,
                decision_id=decision_id,
                agent_name=run.agent_name,
                model_name=run.model_name,
                status=run.status,
                latency_ms=run.latency_ms,
                input_payload=_jsonable(run.input_payload),
                output_payload=_jsonable(run.output_payload),
                error_message=run.error_message,
            )
        )
        self.db.flush()

    def fail(self, error: Exception) -> None:
        self.status = "FAILED"
        self.error_message = f"{type(error).__name__}: {error}"
        self.event("REQUEST_FAILED", "ERROR", None, self.error_message)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        duration_ms = int((perf_counter() - self.started) * 1000)
        payload = {
            "traceId": self.trace_id,
            "sessionId": self.session_id,
            "userId": self.user_id,
            "status": self.status,
            "durationMs": duration_ms,
            "events": self.events,
        }
        self.repository.save_trace(
            TraceRecord(
                trace_id=self.trace_id,
                session_id=self.session_id,
                user_id=self.user_id,
                status=self.status,
                event_count=len(self.events),
                duration_ms=duration_ms,
                error_message=self.error_message,
                trace_json=payload,
            )
        )

    def __enter__(self) -> "TraceScope":
        return self

    def __exit__(self, exc_type: Any, exc: Exception | None, traceback: Any) -> None:
        if exc is not None:
            self.fail(exc)
        self.close()
