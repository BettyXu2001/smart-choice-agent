from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from time import perf_counter
from typing import Any

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
        try:
            output = agent.execute(context)
            run = AgentRun(
                agent_name=agent.name,
                model_name=agent.model_name,
                latency_ms=int((perf_counter() - started) * 1000),
                input_payload=input_payload,
                output_payload=output,
            )
        except Exception as error:
            run = AgentRun(
                agent_name=agent.name,
                model_name=agent.model_name,
                status="FAILED",
                latency_ms=int((perf_counter() - started) * 1000),
                input_payload=input_payload,
                error_message=f"{type(error).__name__}: {error}",
            )
            context.decision.agent_runs.append(run)
            self.trace_scope.agent_run(run, context.decision.decision_id)
            raise
        context.decision.agent_runs.append(run)
        self.trace_scope.agent_run(run, context.decision.decision_id)
        return output
