from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Any, Callable
from uuid import uuid4

from fastapi import Request
from fastapi.responses import StreamingResponse

from choice_agent.config import Settings
from choice_agent.decision.state_machine import DecisionRevisionError
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.providers.model import ModelProvider
from choice_agent.providers.search import SearchProviderError
from choice_agent.schemas import (
    DecisionCommandRequest,
    GenericDecisionMessageRequest,
    GenericDecisionRequest,
)


class DecisionEventStream:
    def __init__(self, request_id: str, command_id: str | None = None):
        self.request_id = request_id
        self.command_id = command_id
        self.sequence = 0
        self.events: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=100)
        self.closed = threading.Event()

    def progress(self, payload: dict[str, Any]) -> None:
        self.emit({"type": "progress", **payload})

    def final(self, response: dict[str, Any]) -> None:
        self.emit({"type": "final", "response": response})
        self.finish()

    def error(self, code: str, message: str) -> None:
        self.emit({"type": "error", "error": {"code": code, "message": message}})
        self.finish()

    def finish(self) -> None:
        if not self.closed.is_set():
            self.closed.set()
            self.events.put(None)

    def close(self) -> None:
        self.closed.set()

    def emit(self, payload: dict[str, Any]) -> None:
        if self.closed.is_set():
            return
        self.sequence += 1
        event = {
            "requestId": self.request_id,
            "commandId": self.command_id,
            "sequence": self.sequence,
            **payload,
        }
        self.events.put(event)


def _request_id(body: GenericDecisionRequest | GenericDecisionMessageRequest | DecisionCommandRequest) -> str:
    return getattr(body, "request_id", None) or getattr(body, "command_id", None) or uuid4().hex


def _error_code(error: Exception) -> tuple[str, str]:
    if isinstance(error, SearchProviderError):
        return "search_provider_failed", str(error)
    if isinstance(error, DecisionRevisionError):
        return "revision_conflict", str(error)
    if isinstance(error, KeyError):
        return "not_found", str(error)
    if isinstance(error, ValueError):
        return "bad_request", str(error)
    return "internal_error", "请求处理失败"


def _run_worker(
    request: Request,
    uid: int,
    settings: Settings,
    provider: ModelProvider,
    stream: DecisionEventStream,
    operation: Callable[[GenericDecisionOrchestrator], Any],
) -> None:
    try:
        with request.app.state.database.session_factory() as db:
            orchestrator = GenericDecisionOrchestrator(
                db,
                settings=settings,
                provider=provider,
                progress=stream.progress,
            )
            response = operation(orchestrator)
            if not stream.closed.is_set():
                stream.final(response.model_dump(mode="json", by_alias=True))
    except Exception as error:
        code, message = _error_code(error)
        if not stream.closed.is_set():
            stream.error(code, message)


def _queue_get(events: queue.Queue[dict[str, Any] | None]) -> dict[str, Any] | None | TimeoutError:
    try:
        return events.get(timeout=0.25)
    except queue.Empty:
        return TimeoutError()


async def _event_generator(request: Request, stream: DecisionEventStream):
    while True:
        if await request.is_disconnected():
            stream.close()
            break
        event = await asyncio.to_thread(_queue_get, stream.events)
        if isinstance(event, TimeoutError):
            continue
        if event is None:
            break
        yield json.dumps(event, ensure_ascii=False) + "\n"


def stream_create_decision(
    request: Request,
    uid: int,
    body: GenericDecisionRequest,
    settings: Settings,
    provider: ModelProvider,
) -> StreamingResponse:
    stream = DecisionEventStream(_request_id(body))
    worker = threading.Thread(
        target=_run_worker,
        args=(request, uid, settings, provider, stream, lambda orchestrator: orchestrator.create(uid, body)),
        daemon=True,
    )
    worker.start()
    return StreamingResponse(_event_generator(request, stream), media_type="application/x-ndjson")


def stream_message_decision(
    request: Request,
    uid: int,
    decision_id: str,
    body: GenericDecisionMessageRequest,
    settings: Settings,
    provider: ModelProvider,
) -> StreamingResponse:
    stream = DecisionEventStream(_request_id(body))
    worker = threading.Thread(
        target=_run_worker,
        args=(request, uid, settings, provider, stream, lambda orchestrator: orchestrator.message(uid, decision_id, body)),
        daemon=True,
    )
    worker.start()
    return StreamingResponse(_event_generator(request, stream), media_type="application/x-ndjson")


def stream_command_decision(
    request: Request,
    uid: int,
    decision_id: str,
    body: DecisionCommandRequest,
    settings: Settings,
    provider: ModelProvider,
) -> StreamingResponse:
    stream = DecisionEventStream(_request_id(body), body.command_id)
    worker = threading.Thread(
        target=_run_worker,
        args=(request, uid, settings, provider, stream, lambda orchestrator: orchestrator.command(uid, decision_id, body)),
        daemon=True,
    )
    worker.start()
    return StreamingResponse(_event_generator(request, stream), media_type="application/x-ndjson")