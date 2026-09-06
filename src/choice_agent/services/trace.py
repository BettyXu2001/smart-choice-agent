from __future__ import annotations

from datetime import datetime
from time import perf_counter
from typing import Any, Callable

from sqlalchemy.orm import Session

from choice_agent.db_models import AgentRunRecord, TraceRecord
from choice_agent.repositories.trace_repository import TraceRepository
from choice_agent.schemas import AgentRun


_SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "apiKey",
    "model_api_key",
    "search_api_key",
    "token",
    "password",
    "secret",
}
_TEXT_LIMIT = 32 * 1024
_RAW_MODEL_LIMIT = 64 * 1024


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


def _limit_text(value: str, limit: int = _TEXT_LIMIT) -> str | dict[str, Any]:
    if len(value) <= limit:
        return value
    return {"text": value[:limit], "truncated": True, "originalLength": len(value)}


def _redact(value: Any, key_hint: str | None = None) -> Any:
    key_lower = (key_hint or "").lower()
    if key_lower and any(marker.lower() in key_lower for marker in _SENSITIVE_KEYS):
        return "[REDACTED]"
    value = _jsonable(value)
    if isinstance(value, dict):
        return {str(key): _redact(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _limit_text(value)
    return value


def _stable_id(item: Any, fallback: str) -> str:
    if isinstance(item, dict):
        for key in ("candidateId", "candidate_id", "evidenceId", "evidence_id", "sourceId", "source_id", "key"):
            if item.get(key) is not None:
                return str(item[key])
    return fallback


def _snapshot_decision(decision: Any) -> dict[str, Any]:
    domain_state = getattr(decision, "domain_state", {}) or {}
    domain_state_keys = {
        "analysis",
        "assistance",
        "candidatePool",
        "composition",
        "conversationFields",
        "currentAnalysis",
        "displayBlocks",
        "intent",
        "selection",
        "slots",
        "source",
        "suggestedDomain",
    }
    selected_domain_state = {
        key: value for key, value in domain_state.items()
        if key in domain_state_keys
    }
    payload = {
        "decisionId": getattr(decision, "decision_id", None),
        "sessionId": getattr(decision, "session_id", None),
        "domain": getattr(decision, "domain", None),
        "revision": getattr(decision, "revision", None),
        "userGoal": getattr(decision, "user_goal", None),
        "intent": getattr(getattr(decision, "intent", None), "value", getattr(decision, "intent", None)),
        "intentKey": getattr(decision, "intent_key", None),
        "status": getattr(getattr(decision, "status", None), "value", getattr(decision, "status", None)),
        "nextAction": getattr(getattr(decision, "next_action", None), "value", getattr(decision, "next_action", None)),
        "constraints": getattr(decision, "constraints", []),
        "criteria": getattr(decision, "criteria", []),
        "candidates": getattr(decision, "candidates", []),
        "candidateState": getattr(decision, "candidate_state", {}),
        "evidence": getattr(decision, "evidence", []),
        "recommendation": getattr(decision, "recommendation", None),
        "composition": getattr(decision, "composition", None),
        "excludedCandidates": getattr(decision, "excluded_candidates", []),
        "sources": getattr(decision, "sources", []),
        "searchRuns": getattr(decision, "search_runs", []),
        "riskFlags": getattr(decision, "risk_flags", []),
        "domainState": selected_domain_state,
    }
    return _redact(payload)


def _diff(before: Any, after: Any, path: str = "", limit: int = 120) -> list[dict[str, Any]]:
    if before == after or limit <= 0:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            next_path = f"{path}.{key}" if path else str(key)
            if key not in before:
                changes.append({"type": "add", "path": next_path, "after": after[key]})
            elif key not in after:
                changes.append({"type": "remove", "path": next_path, "before": before[key]})
            else:
                changes.extend(_diff(before[key], after[key], next_path, limit - len(changes)))
            if len(changes) >= limit:
                changes.append({"type": "truncated", "path": path or "$", "limit": limit})
                return changes[: limit + 1]
        return changes
    if isinstance(before, list) and isinstance(after, list):
        before_map = {_stable_id(item, str(index)): item for index, item in enumerate(before)}
        after_map = {_stable_id(item, str(index)): item for index, item in enumerate(after)}
        if before_map.keys() != after_map.keys():
            return [{"type": "replace", "path": path or "$", "before": before, "after": after}]
        changes = []
        for key in sorted(after_map):
            changes.extend(_diff(before_map[key], after_map[key], f"{path}[{key}]", limit - len(changes)))
            if len(changes) >= limit:
                changes.append({"type": "truncated", "path": path or "$", "limit": limit})
                return changes[: limit + 1]
        return changes
    return [{"type": "replace", "path": path or "$", "before": before, "after": after}]


def _recommendation_summary(value: Any) -> dict[str, Any] | None:
    value = _jsonable(value)
    if not isinstance(value, dict):
        return None
    return {
        "primaryCandidateId": value.get("primaryCandidateId") or value.get("primary_candidate_id"),
        "alternativeCandidateIds": value.get("alternativeCandidateIds") or value.get("alternative_candidate_ids") or [],
        "summary": value.get("summary") or "",
    }


class TraceScope:
    def __init__(self, db: Session, trace_id: str, session_id: str, user_id: int):
        self.db = db
        self.repository = TraceRepository(db)
        self.trace_id = trace_id
        self.session_id = session_id
        self.user_id = user_id
        self.started = perf_counter()
        self.events: list[dict[str, Any]] = []
        self.timeline: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {"schemaVersion": 2}
        self.turn_summary: dict[str, Any] = {}
        self.recommendation_before: dict[str, Any] | None = None
        self.initial_snapshot: dict[str, Any] | None = None
        self.commit_status = "attempted"
        self.status = "SUCCESS"
        self.error_message: str | None = None
        self.closed = False

    def begin_turn(
        self,
        decision: Any,
        message: str,
        request_kind: str,
        expected_revision: int | None = None,
    ) -> None:
        self.initial_snapshot = _snapshot_decision(decision)
        self.recommendation_before = _recommendation_summary(getattr(decision, "recommendation", None))
        self.metadata.update(
            {
                "decisionId": getattr(decision, "decision_id", None),
                "domain": getattr(decision, "domain", None),
                "revisionBefore": getattr(decision, "revision", None),
                "expectedRevision": expected_revision,
                "requestKind": request_kind,
            }
        )
        self.turn_summary = {
            "userMessage": message,
            "requestKind": request_kind,
            "status": "running",
        }

    def record_state(self, stage: str, before: Any, after: Any, summary: str) -> list[dict[str, Any]]:
        changes = _diff(_snapshot_decision(before) if not isinstance(before, dict) else before,
                        _snapshot_decision(after) if not isinstance(after, dict) else after)
        if changes:
            self.node(
                stage=stage,
                kind="operation",
                status="success",
                summary=summary,
                output_payload={"changeCount": len(changes)},
                changes=changes,
            )
        return changes

    def node(
        self,
        stage: str,
        kind: str,
        status: str,
        summary: str,
        input_payload: Any = None,
        output_payload: Any = None,
        changes: list[dict[str, Any]] | None = None,
        refs: dict[str, Any] | None = None,
        parent_id: str | None = None,
        error: str | None = None,
    ) -> str:
        node_id = f"t{len(self.timeline) + 1}"
        node = {
            "eventId": node_id,
            "parentId": parent_id,
            "sequence": len(self.timeline) + 1,
            "stage": stage,
            "kind": kind,
            "status": status,
            "startedAt": datetime.now().isoformat(),
            "durationMs": 0,
            "summary": summary,
            "input": _redact(input_payload),
            "output": _redact(output_payload),
            "changes": _redact(changes or []),
            "refs": _redact(refs or {}),
        }
        if error:
            node["error"] = _redact(error)
        self.timeline.append(node)
        return node_id

    def start_node(self, stage: str, kind: str, summary: str, input_payload: Any = None) -> str:
        node_id = self.node(stage, kind, "running", summary, input_payload=input_payload)
        self.timeline[-1]["_startedPerf"] = perf_counter()
        return node_id

    def finish_node(
        self,
        node_id: str,
        status: str,
        output_payload: Any = None,
        changes: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> None:
        node = next((item for item in self.timeline if item["eventId"] == node_id), None)
        if node is None:
            return
        started = node.pop("_startedPerf", None)
        if started is not None:
            node["durationMs"] = int((perf_counter() - started) * 1000)
        node["status"] = status
        node["output"] = _redact(output_payload)
        node["changes"] = _redact(changes or [])
        if error:
            node["error"] = _redact(error)

    def snapshot(self, decision: Any) -> dict[str, Any]:
        return _snapshot_decision(decision)

    def diff(self, before: dict[str, Any], after: Any) -> list[dict[str, Any]]:
        return _diff(before, _snapshot_decision(after))

    def mark_committed(self, decision: Any) -> None:
        self.commit_status = "committed"
        self.metadata["revisionAfter"] = getattr(decision, "revision", None)
        self.turn_summary["status"] = self.status.lower()
        self.turn_summary["intent"] = getattr(getattr(decision, "intent", None), "value", getattr(decision, "intent", None))
        self.turn_summary["recommendationChange"] = self.recommendation_change(decision)

    def recommendation_change(self, decision: Any) -> dict[str, Any]:
        before = self.recommendation_before
        after = _recommendation_summary(getattr(decision, "recommendation", None))
        if before is None and after is None:
            status = "no_recommendation"
        elif before is None:
            status = "initial"
        elif after is None:
            status = "cleared"
        elif before.get("primaryCandidateId") != after.get("primaryCandidateId") or before.get("alternativeCandidateIds") != after.get("alternativeCandidateIds"):
            status = "changed"
        else:
            status = "unchanged"
        return {"status": status, "before": before, "after": after}

    def model_call(
        self,
        stage: str,
        model: str | None,
        system_prompt: str,
        user_prompt: str,
        call: Callable[[], Any],
    ) -> Any:
        node_id = self.start_node(
            stage,
            "model",
            f"调用模型 {model or 'unknown'}",
            input_payload={
                "model": model,
                "systemPrompt": system_prompt,
                "userPrompt": user_prompt,
            },
        )
        try:
            result = call()
        except Exception as error:
            self.finish_node(
                node_id,
                "failed",
                output_payload={"errorType": type(error).__name__, "error": str(error)},
                error=f"{type(error).__name__}: {error}",
            )
            raise
        self.finish_node(node_id, "success", output_payload={"result": result})
        return result

    def event(self, event_type: str, phase: str, input_payload: Any, output_payload: Any) -> None:
        self.events.append(
            {
                "stepOrder": len(self.events) + 1,
                "eventType": event_type,
                "phase": phase,
                "inputPayload": _redact(input_payload),
                "outputPayload": _redact(output_payload),
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
        self.commit_status = "rolled_back"
        self.error_message = f"{type(error).__name__}: {error}"
        self.event("REQUEST_FAILED", "ERROR", None, self.error_message)
        self.node("Failure", "operation", "failed", "请求处理失败，业务状态已回滚", output_payload={"error": self.error_message}, error=self.error_message)

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
            "schemaVersion": 2,
            "metadata": {**self.metadata, "commitStatus": self.commit_status},
            "turnSummary": self.turn_summary,
            "recommendationChange": self.turn_summary.get("recommendationChange"),
            "initialSnapshot": self.initial_snapshot,
            "timeline": [
                {key: value for key, value in item.items() if key != "_startedPerf"}
                for item in self.timeline
            ],
            "events": self.events,
        }
        self.repository.save(
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
