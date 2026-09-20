from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable

from choice_agent.schemas import AgentRun, DecisionState


def _safe_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _safe_payload(value.model_dump(mode="json", by_alias=True))
    if isinstance(value, dict):
        return {str(key): _safe_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_payload(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass
class AgentContext:
    session_id: str
    trace_id: str
    user_id: int
    message: str
    decision: DecisionState
    data: dict[str, Any]
    progress: Callable[[dict[str, Any]], None] | None = None
    trace: Any | None = None

    def emit_progress(self, stage: str, message: str, **payload: Any) -> None:
        if self.progress is None:
            return
        self.progress({"stage": stage, "message": message, **payload})


class BaseAgent(ABC):
    name = "BaseAgent"
    model_name: str | None = None

    @abstractmethod
    def execute(self, context: AgentContext) -> dict[str, Any]:
        raise NotImplementedError


class AgentRuntime:
    def __init__(self, trace_scope: Any):
        self.trace_scope = trace_scope

    def run(self, agent: BaseAgent, context: AgentContext) -> dict[str, Any]:
        started = perf_counter()
        input_payload = _safe_payload({"message": context.message, "data": context.data})
        before = self.trace_scope.snapshot(context.decision) if hasattr(self.trace_scope, "snapshot") else None
        if hasattr(self.trace_scope, "begin_agent_call"):
            self.trace_scope.begin_agent_call()
        node_id = (
            self.trace_scope.start_node(agent.name, "agent", f"调用 {agent.name}", input_payload)
            if hasattr(self.trace_scope, "start_node")
            else None
        )
        try:
            output = agent.execute(context)
            telemetry = self.trace_scope.end_agent_call() if hasattr(self.trace_scope, "end_agent_call") else {}
            run = AgentRun(
                agent_name=agent.name,
                model_name=telemetry.pop("model_name", None) or agent.model_name,
                latency_ms=int((perf_counter() - started) * 1000),
                input_payload=input_payload,
                output_payload=output,
                **telemetry,
            )
        except Exception as error:
            telemetry = self.trace_scope.end_agent_call() if hasattr(self.trace_scope, "end_agent_call") else {}
            changes = self.trace_scope.diff(before, context.decision) if before is not None and hasattr(self.trace_scope, "diff") else []
            run = AgentRun(
                agent_name=agent.name,
                model_name=telemetry.pop("model_name", None) or agent.model_name,
                status="FAILED",
                latency_ms=int((perf_counter() - started) * 1000),
                input_payload=input_payload,
                error_message=f"{type(error).__name__}: {error}",
                **telemetry,
            )
            context.decision.agent_runs.append(run)
            self.trace_scope.agent_run(run, context.decision.decision_id)
            if node_id and hasattr(self.trace_scope, "finish_node"):
                self.trace_scope.finish_node(
                    node_id,
                    "failed",
                    output_payload={"error": run.error_message},
                    changes=changes,
                    error=run.error_message,
                )
            raise
        changes = self.trace_scope.diff(before, context.decision) if before is not None and hasattr(self.trace_scope, "diff") else []
        context.decision.agent_runs.append(run)
        self.trace_scope.agent_run(run, context.decision.decision_id)
        if node_id and hasattr(self.trace_scope, "finish_node"):
            self.trace_scope.finish_node(node_id, "success", output_payload=output, changes=changes)
        return output
