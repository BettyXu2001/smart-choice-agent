from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from choice_agent.schemas import DecisionState


class ExecutionMode(str, Enum):
    FULL = "full"
    REFRESH = "refresh"
    RERANK = "rerank"
    EXPLAIN_ONLY = "explain_only"
    WHAT_IF = "what_if"


@dataclass(frozen=True)
class ExecutionPlan:
    mode: ExecutionMode
    reason: str
    planned_path: tuple[str, ...]
    skip_reasons: dict[str, str]


_PATHS = {
    ExecutionMode.FULL: ("intent", "understanding", "clarification", "candidate_refresh", "critic", "explanation", "validation", "safety"),
    ExecutionMode.REFRESH: ("candidate_refresh", "critic", "explanation", "validation", "safety"),
    ExecutionMode.RERANK: ("rerank", "critic", "explanation", "validation", "safety"),
    ExecutionMode.EXPLAIN_ONLY: ("explanation", "validation", "safety"),
    ExecutionMode.WHAT_IF: ("what_if", "validation", "safety"),
}


def command_execution_mode(mode: str) -> ExecutionMode:
    return {
        "full": ExecutionMode.FULL,
        "refresh": ExecutionMode.REFRESH,
        "rank": ExecutionMode.RERANK,
    }[mode]


def plan_execution(profile, decision: DecisionState, baseline: DecisionState | None, data: dict[str, Any]) -> ExecutionPlan:
    requested = data.get("requested_execution_mode")
    if requested:
        mode = requested if isinstance(requested, ExecutionMode) else ExecutionMode(requested)
        if mode == ExecutionMode.RERANK and not decision.domain_state.get("candidatePool"):
            mode = ExecutionMode.REFRESH
            reason = "候选池缺失，升级为候选刷新"
        else:
            reason = "命令显式指定执行范围"
        return _plan(mode, reason)
    if data.get("is_hypothetical"):
        return _plan(ExecutionMode.WHAT_IF, "本轮是假设分析，隔离正式决策状态")
    if baseline is None or not profile.supports_incremental_execution(data):
        return _plan(ExecutionMode.FULL, "首次执行或当前领域尚未启用增量执行")
    if not decision.domain_state.get("candidatePool"):
        return _plan(ExecutionMode.REFRESH, "候选池缺失")
    changed_fields = _changed_conversation_fields(baseline, decision)
    if changed_fields.intersection(profile.retrieval_sensitive_fields()):
        return _plan(ExecutionMode.REFRESH, "检索敏感字段发生变化")
    if _decision_inputs(baseline) != _decision_inputs(decision):
        return _plan(ExecutionMode.RERANK, "比较条件、偏好或候选状态发生变化")
    if data.get("turn_intent") == "explain":
        return _plan(ExecutionMode.EXPLAIN_ONLY, "本轮只询问已有结论")
    return _plan(ExecutionMode.EXPLAIN_ONLY, "本轮没有改变正式决策输入")


def _plan(mode: ExecutionMode, reason: str) -> ExecutionPlan:
    path = _PATHS[mode]
    all_steps = {step for steps in _PATHS.values() for step in steps}
    return ExecutionPlan(mode, reason, path, {step: reason for step in sorted(all_steps.difference(path))})


def _changed_conversation_fields(before: DecisionState, after: DecisionState) -> set[str]:
    old = before.domain_state.get("conversationFields", {})
    new = after.domain_state.get("conversationFields", {})
    keys = set(old).union(new)
    return {key for key in keys if _field_value(old.get(key)) != _field_value(new.get(key))}


def _field_value(field: Any) -> Any:
    return field.get("value") if isinstance(field, dict) else field


def _decision_inputs(decision: DecisionState) -> dict[str, Any]:
    assistance = decision.domain_state.get("assistance", {})
    return {
        "fields": decision.domain_state.get("conversationFields", {}),
        "constraints": [item.model_dump(mode="json", by_alias=True) for item in decision.constraints],
        "criteria": [item.model_dump(mode="json", by_alias=True) for item in decision.criteria],
        "excluded": decision.excluded_candidates,
        "manualCandidates": decision.domain_state.get("manualCandidates", []),
        "facts": assistance.get("facts", []),
    }
