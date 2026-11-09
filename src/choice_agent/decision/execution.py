from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
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
    diagnostics: dict[str, Any] = field(default_factory=dict)


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


def plan_execution(profile, decision: DecisionState, baseline: dict[str, Any] | None, data: dict[str, Any]) -> ExecutionPlan:
    requested = data.get("requested_execution_mode")
    requested = ExecutionMode(requested) if requested else None
    if data.get("is_hypothetical"):
        return _plan(ExecutionMode.WHAT_IF, "本轮是假设分析，隔离正式决策状态")
    current = _decision_inputs(decision)
    changed_fields = _changed_conversation_fields(baseline["fields"], current["fields"]) if baseline else set()
    diagnostics = {"changedFields": sorted(changed_fields)}
    attribute = profile.budget_attribute()
    if attribute:
        diagnostics.update(_budget_change(baseline, current, attribute))
        if diagnostics["budgetChangeDirection"] != "unchanged":
            diagnostics["budgetCoverage"] = _budget_coverage(profile, decision, diagnostics)
    if requested and requested != ExecutionMode.RERANK:
        return _plan(requested, "命令显式指定执行范围", diagnostics)
    if baseline is None or not profile.supports_incremental_execution(data):
        # Preserve explicit Diet recompute commands; its normal turns remain FULL.
        mode = requested or ExecutionMode.FULL
        if mode == ExecutionMode.RERANK and not decision.domain_state.get("candidatePool"):
            mode = ExecutionMode.REFRESH
        return _plan(mode, "首次执行或当前领域尚未启用增量执行", diagnostics)
    if not decision.domain_state.get("candidatePool"):
        return _plan(ExecutionMode.REFRESH, "候选池缺失", diagnostics)
    if changed_fields.intersection(profile.retrieval_sensitive_fields()):
        return _plan(ExecutionMode.REFRESH, "检索敏感字段发生变化", diagnostics)
    if attribute and diagnostics["budgetChangeDirection"] != "unchanged":
        direction = diagnostics["budgetChangeDirection"]
        coverage = diagnostics["budgetCoverage"]
        if profile.budget_requires_refresh(direction, coverage):
            return _plan(ExecutionMode.REFRESH, f"预算变化（{direction}），当前候选覆盖不足或领域方案需要重新检索：{coverage['reason']}", diagnostics)
        return _plan(ExecutionMode.RERANK, f"预算变化（{direction}），收紧约束或已证明覆盖新范围，复用候选池", diagnostics)
    if requested == ExecutionMode.RERANK or baseline != current:
        return _plan(ExecutionMode.RERANK, "比较条件、偏好或候选状态发生变化", diagnostics)
    reason = "本轮只询问已有结论" if data.get("turn_intent") == "explain" else "本轮没有改变正式决策输入"
    return _plan(ExecutionMode.EXPLAIN_ONLY, reason, diagnostics)


def _plan(mode: ExecutionMode, reason: str, diagnostics: dict[str, Any] | None = None) -> ExecutionPlan:
    path = _PATHS[mode]
    all_steps = {step for steps in _PATHS.values() for step in steps}
    return ExecutionPlan(mode, reason, path, {step: reason for step in sorted(all_steps.difference(path))}, diagnostics or {})


def _positive_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return isfinite(value) and value > 0
    except OverflowError:
        return False


def _budget_snapshot(inputs: dict[str, Any], attribute: str, *, validate: bool = False) -> dict[str, Any]:
    raw = _field_value(inputs["fields"].get("budget"))
    valid = raw is None or _positive_number(raw)
    if not valid and validate:
        raise ValueError("预算必须是正有限数值")
    bounds = []
    sources = []
    for constraint in inputs["constraints"]:
        if constraint["key"] != attribute or constraint["kind"] != "hard":
            continue
        value, operator = constraint.get("value"), constraint.get("operator")
        sources.append(constraint.get("source"))
        if operator in {"lt", "lte"} and not _positive_number(value):
            if validate:
                raise ValueError("预算硬约束必须使用正有限数值")
            valid = False
        elif operator in {"lt", "lte"}:
            bounds.append((value, operator == "lte"))
        else:
            valid = False
    effective = min(bounds) if bounds else (None, True)
    # Even unconfirmed suggestions are supplied to search, but are not hard filters.
    query_bounds = [*bounds]
    if _positive_number(raw):
        query_bounds.append((raw, True))
    query = min(query_bounds) if query_bounds else (None, True)
    return {"field": raw, "effective": effective, "query": query, "valid": valid, "sources": sources}


def _budget_change(baseline: dict[str, Any] | None, current: dict[str, Any], attribute: str) -> dict[str, Any]:
    old = _budget_snapshot(baseline or {"fields": {}, "constraints": []}, attribute)
    new = _budget_snapshot(current, attribute, validate=True)
    old_constraints = [c for c in (baseline or {}).get("constraints", []) if c["key"] == attribute and c["kind"] == "hard"]
    new_constraints = [c for c in current["constraints"] if c["key"] == attribute and c["kind"] == "hard"]
    changed = old["field"] != new["field"] or old_constraints != new_constraints
    direction = "unchanged"
    if changed:
        if not old["valid"] or not new["valid"]:
            direction = "unknown"
        elif old["field"] is None and new["field"] is not None:
            direction = "first_set"
        elif old["effective"][0] is None and new["effective"][0] is not None:
            direction = "first_set"
        else:
            def comparable(bound):
                return (float("inf") if bound[0] is None else bound[0], bound[1])
            comparisons = [(old["effective"], new["effective"]), (old["query"], new["query"]),
                           ((old["field"], True), (new["field"], True))]
            if any(comparable(after) > comparable(before) for before, after in comparisons):
                removed = ((new["field"] is None and old["field"] is not None)
                           or (new["effective"][0] is None and old["effective"][0] is not None))
                direction = "removed" if removed else "relaxed"
            elif any(comparable(after) < comparable(before) for before, after in comparisons):
                direction = "tightened"
    def display(value):
        return str(value) if isinstance(value, float) and not isfinite(value) else value
    return {
        "oldBudget": display(old["field"]), "newBudget": display(new["field"]),
        "oldEffectiveBudget": old["effective"][0], "newEffectiveBudget": new["effective"][0],
        "newSearchBudget": new["query"][0], "budgetChangeDirection": direction,
        "budgetConstraintSources": new["sources"], "budgetConstraintsChanged": old_constraints != new_constraints,
    }


def _coverage_scope(profile, decision: DecisionState, fixed_fixture: bool) -> dict[str, Any]:
    inputs = _decision_inputs(decision)
    keys = profile.retrieval_sensitive_fields() if fixed_fixture else set(inputs["fields"]) - {"budget"}
    scope = {
        "domain": decision.domain,
        "searchMode": decision.context.get("searchMode", "fixture"),
        "fields": {key: _field_value(inputs["fields"].get(key)) for key in sorted(keys)},
    }
    if str(scope["searchMode"]).lower() == "auto":
        scope["webEnabled"] = bool(getattr(getattr(profile, "web_provider", None), "enabled", False))
    if not fixed_fixture:
        scope["constraints"] = [
            c for c in inputs["constraints"]
            if not (c["key"] == profile.budget_attribute() and c["kind"] == "hard" and c["operator"] in {"lt", "lte"})
        ]
        scope["criteria"] = inputs["criteria"]
    return scope


def bind_budget_coverage(profile, decision: DecisionState, declaration: dict[str, Any] | None, run, candidate_ids: list[str]) -> dict[str, Any] | None:
    """Bind an internal Provider guarantee, never an LLM response or candidate price."""
    if not profile.budget_attribute() or not isinstance(declaration, dict) or declaration.get("complete") is not True or run is None:
        return None
    independent = declaration.get("budgetIndependent") is True
    maximum = declaration.get("maxBudget")
    if not independent and not _positive_number(maximum):
        return None
    return {
        "version": 1, "complete": True, "budgetIndependent": independent,
        "maxBudget": maximum if not independent else None,
        "provider": run.provider, "runId": run.run_id,
        "scope": _coverage_scope(profile, decision, independent and run.mode == "fixture"), "candidateIds": sorted(candidate_ids),
    }


def _budget_coverage(profile, decision: DecisionState, change: dict[str, Any]) -> dict[str, Any]:
    result = {"sufficient": False, "budgetIndependent": False, "reason": "缺少可靠的检索覆盖声明"}
    coverage = decision.domain_state.get("source", {}).get("budgetCoverage")
    if not isinstance(coverage, dict) or coverage.get("version") != 1 or coverage.get("complete") is not True:
        return result
    independent = coverage.get("budgetIndependent") is True
    run = decision.search_runs[-1] if decision.search_runs else None
    ids = coverage.get("candidateIds")
    pool = decision.domain_state.get("candidatePool") or []
    pool_ids = {item.get("candidateId") for item in pool if isinstance(item, dict)}
    if (not run or coverage.get("runId") != run.run_id or coverage.get("provider") != run.provider
            or not isinstance(ids, list) or not ids or not all(isinstance(item, str) and item in pool_ids for item in ids)
            or coverage.get("scope") != _coverage_scope(profile, decision, independent and run.mode == "fixture")):
        result["reason"] = "覆盖声明与当前检索作用域、来源或候选池不匹配"
        return result
    maximum, budget = coverage.get("maxBudget"), change["newEffectiveBudget"]
    bounded = (
        change["budgetChangeDirection"] != "unknown"
        and _positive_number(maximum)
        and _positive_number(budget)
        and maximum >= budget
    )
    if independent or bounded:
        return {
            "sufficient": True, "budgetIndependent": independent, "sourceMode": run.mode,
            "reason": "Provider 明确保证当前作用域覆盖新预算范围",
        }
    result["reason"] = "新预算范围超出 Provider 已证明的覆盖上界"
    return result


def capture_execution_baseline(decision: DecisionState) -> dict[str, Any]:
    """Copy only planner inputs; history, traces and receipts can be very large."""
    return deepcopy(_decision_inputs(decision))


def _changed_conversation_fields(old: dict[str, Any], new: dict[str, Any]) -> set[str]:
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
