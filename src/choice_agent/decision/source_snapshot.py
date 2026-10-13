from __future__ import annotations

from copy import deepcopy

_ALLOWED_SOURCES = {"database", "web", "fixture", "manual"}


def source_snapshot(decision, data: dict) -> dict:
    source = decision.domain_state.get("source", {})
    kinds = {item.kind for item in decision.sources if item.kind in _ALLOWED_SOURCES}
    kinds.update(candidate.origin for candidate in decision.candidates if candidate.origin in _ALLOWED_SOURCES)
    actual = "hybrid" if len(kinds) > 1 else next(iter(kinds), source.get("mode", "manual"))
    if actual not in _ALLOWED_SOURCES | {"hybrid"}:
        actual = "hybrid" if actual == "hybrid" else "manual"
    plan = data.get("execution_plan")
    mode = getattr(getattr(plan, "mode", None), "value", None)
    retrieved = mode in {"full", "refresh"}
    reused = mode in {"rerank", "explain_only", "what_if"}
    warnings = list(dict.fromkeys(source.get("warnings", [])))
    reason = getattr(plan, "reason", None) or source.get("recallReason") or "沿用当前候选状态"
    return deepcopy({
        "source": actual,
        "retrieved": retrieved,
        "reusedCandidatePool": reused,
        "triggerReason": reason,
        "candidateCount": len(decision.domain_state.get("candidatePool", decision.candidates)),
        "fallback": bool(warnings) or "fallback" in str(source.get("recallReason", "")),
        "warnings": warnings,
    })