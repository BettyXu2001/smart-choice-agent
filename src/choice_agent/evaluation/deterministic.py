from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeterministicResult:
    passed: bool | None
    actual: Any
    reason: str | None = None

    @property
    def evaluation_method(self) -> str:
        return "deterministic" if self.passed is not None else "not_evaluated"


def evaluate_auto_assertion(metric_id: str, expected: Any, outputs: dict[str, Any]) -> DeterministicResult:
    evaluator = _AUTO_EVALUATORS.get(metric_id)
    if evaluator is None:
        return DeterministicResult(None, None, f"指标 {metric_id} 没有确定性 auto evaluator")
    try:
        return evaluator(_as_dict(expected), outputs)
    except (KeyError, TypeError, ValueError, IndexError) as error:
        return DeterministicResult(None, None, f"确定性评测输入不足：{error}")


def recommendation_signature(outputs: dict[str, Any]) -> dict[str, Any] | None:
    state = _final_state(outputs)
    recommendation = state.get("recommendation")
    if not isinstance(recommendation, dict):
        return None
    return {
        "primaryCandidate": _candidate_identity(state, recommendation.get("primaryCandidateId")),
        "alternativeCandidates": sorted(
            _candidate_identity(state, item)
            for item in recommendation.get("alternativeCandidateIds") or []
        ),
        "rankingMethod": recommendation.get("rankingMethod"),
    }


def _candidate_identity(state: dict[str, Any], candidate_id: Any) -> str | None:
    if candidate_id is None:
        return None
    domain_state = state.get("domainState") or {}
    candidates = list(state.get("candidates") or [])
    if isinstance(domain_state, dict):
        candidates.extend(domain_state.get("manualCandidates") or [])
        candidates.extend(domain_state.get("candidatePool") or [])
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("candidateId")) == str(candidate_id):
            return str(candidate.get("name") or candidate.get("title") or candidate_id)
    return str(candidate_id)


def evaluate_repetition_stability(peer_outputs: list[dict[str, Any]]) -> DeterministicResult:
    if len(peer_outputs) < 2:
        return DeterministicResult(None, None, "recommendation_stability 至少需要 2 次 repetition")
    signatures = [recommendation_signature(outputs) for outputs in peer_outputs]
    if any(signature is None for signature in signatures):
        return DeterministicResult(None, signatures, "至少一次 repetition 缺少 Recommendation")
    return DeterministicResult(all(item == signatures[0] for item in signatures[1:]), signatures)


def _intent(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    state = _selected_state(outputs, expected)
    checks = {}
    for key in ("domain", "intent"):
        if key in expected:
            checks[key] = {"expected": expected[key], "actual": state.get(key)}
    if not checks:
        return DeterministicResult(None, None, "缺少 domain/intent 金标签")
    return DeterministicResult(all(item["actual"] == item["expected"] for item in checks.values()), checks)


def _constraint(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    state = _selected_state(outputs, expected)
    checks = expected.get("checks")
    if isinstance(checks, list) and checks:
        return _evaluate_checks(state, checks)
    gold = expected.get("constraints")
    if not isinstance(gold, list) or not gold:
        return DeterministicResult(None, None, "缺少结构化 constraint 金标签")
    actual = state.get("constraints") or []
    matched = [_contains_mapping(actual, item) for item in gold if isinstance(item, dict)]
    if not matched:
        return DeterministicResult(None, actual, "constraint 金标签为空")
    return DeterministicResult(all(matched), {"expected": gold, "actual": actual})


def _correction(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    before = _turn_state(outputs, int(expected.get("beforeTurn", -2)))
    after = _turn_state(outputs, int(expected.get("afterTurn", -1)))
    revision_ok = _revision_advanced(before, after, expected)
    checks = _evaluate_checks(after, expected.get("checks") or [])
    absent = _evaluate_checks(after, expected.get("absentChecks") or [])
    evaluated = [revision_ok]
    if checks.passed is not None:
        evaluated.append(checks.passed)
    if absent.passed is not None:
        evaluated.append(absent.passed)
    if len(evaluated) == 1 and not expected.get("revisionOnly"):
        return DeterministicResult(None, None, "缺少纠正后的结构化 checks")
    return DeterministicResult(all(evaluated), {"revisionAdvanced": revision_ok, "checks": checks.actual, "absentChecks": absent.actual})


def _hard_constraint(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    state = _selected_state(outputs, expected)
    recommendation = state.get("recommendation")
    if not isinstance(recommendation, dict) or not recommendation.get("primaryCandidateId"):
        return DeterministicResult(None, None, "缺少可判定 Recommendation")
    primary = str(recommendation["primaryCandidateId"])
    excluded = {str(item) for item in state.get("excludedCandidates") or []}
    candidates = {str(item.get("candidateId")): item for item in state.get("candidates") or [] if isinstance(item, dict)}
    candidate = candidates.get(primary)
    if candidate is None:
        return DeterministicResult(False, {"primaryCandidateId": primary, "candidateExists": False})
    violations = []
    if primary in excluded:
        violations.append("excluded")
    if candidate.get("eliminated"):
        violations.append("eliminated")
    state_entry = (state.get("candidateState") or {}).get(primary)
    if isinstance(state_entry, dict) and str(state_entry.get("status", "")).lower() in {"excluded", "eliminated", "rejected"}:
        violations.append("candidate_state")
    checks = _evaluate_checks(candidate, expected.get("candidateChecks") or [])
    passed = not violations and checks.passed is not False
    return DeterministicResult(passed, {"primaryCandidateId": primary, "violations": violations, "candidateChecks": checks.actual})


def _exclusion(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    state = _selected_state(outputs, expected)
    actual = {str(item) for item in state.get("excludedCandidates") or []}
    candidate_ids = {str(item.get("candidateId")) for item in state.get("candidates") or [] if isinstance(item, dict)}
    expected_exact = expected.get("exact")
    include = {str(item) for item in expected.get("includes") or []}
    exclude = {str(item) for item in expected.get("excludes") or []}
    if expected_exact is not None:
        passed = actual == {str(item) for item in expected_exact}
    elif include or exclude:
        passed = include <= actual and not (exclude & actual)
    elif "minimumCount" in expected:
        passed = len(actual) >= int(expected["minimumCount"])
    else:
        passed = actual <= candidate_ids
    return DeterministicResult(passed, {"excludedCandidates": sorted(actual), "candidateIds": sorted(candidate_ids)})


def _sensitivity(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    before = _turn_state(outputs, int(expected.get("beforeTurn", -2)))
    after = _turn_state(outputs, int(expected.get("afterTurn", -1)))
    before_id = _primary_candidate(before)
    after_id = _primary_candidate(after)
    mode = expected.get("mode")
    if mode not in {"changed", "unchanged"}:
        return DeterministicResult(None, None, "缺少 changed/unchanged 预期")
    passed = before_id != after_id if mode == "changed" else before_id == after_id
    if "expectedPrimaryCandidateId" in expected:
        passed = passed and after_id == expected["expectedPrimaryCandidateId"]
    return DeterministicResult(passed, {"before": before_id, "after": after_id, "mode": mode})


def _reason_consistency(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    state = _selected_state(outputs, expected)
    recommendation = state.get("recommendation")
    if not isinstance(recommendation, dict):
        return DeterministicResult(None, None, "缺少 Recommendation")
    points = [
        item
        for key in ("reasons", "tradeoffDetails")
        for item in recommendation.get(key) or []
        if isinstance(item, dict)
    ]
    if expected.get("requireReasons", True) and not points:
        return DeterministicResult(False, {"pointCount": 0})
    candidates = {str(item.get("candidateId")): item for item in state.get("candidates") or [] if isinstance(item, dict)}
    evidence = _evidence_index(state)
    invalid_candidates = sorted({str(item["candidateId"]) for item in points if item.get("candidateId") and str(item["candidateId"]) not in candidates})
    invalid_evidence = sorted({str(evidence_id) for item in points for evidence_id in item.get("evidenceIds") or [] if str(evidence_id) not in evidence})
    primary = recommendation.get("primaryCandidateId")
    primary_referenced = any(str(item.get("candidateId")) == str(primary) for item in points if item.get("candidateId"))
    passed = not invalid_candidates and not invalid_evidence
    if expected.get("requirePrimaryReference"):
        passed = passed and primary_referenced
    return DeterministicResult(passed, {
        "pointCount": len(points),
        "invalidCandidateIds": invalid_candidates,
        "invalidEvidenceIds": invalid_evidence,
        "primaryReferenced": primary_referenced,
    })


def _evidence_validity(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    state = _selected_state(outputs, expected)
    evidence = _evidence_index(state)
    recommendation = state.get("recommendation") or {}
    points = [
        item
        for key in ("reasons", "tradeoffDetails")
        for item in recommendation.get(key) or []
        if isinstance(item, dict)
    ]
    references = [str(value) for item in points for value in item.get("evidenceIds") or []]
    if not references:
        return DeterministicResult(False if expected.get("requireReferences", True) else None, {"references": []}, "Recommendation 没有 Evidence 引用")
    missing = sorted({value for value in references if value not in evidence})
    wrong_candidate = []
    future_revision = []
    revision = state.get("revision")
    for point in points:
        point_candidate = point.get("candidateId")
        for evidence_id in point.get("evidenceIds") or []:
            item = evidence.get(str(evidence_id))
            if not item:
                continue
            if (
                expected.get("requireCandidateMatch", False)
                and point_candidate
                and item.get("candidateId")
                and str(point_candidate) != str(item.get("candidateId"))
            ):
                wrong_candidate.append(str(evidence_id))
            recorded = item.get("recordedRevision")
            if isinstance(recorded, int) and isinstance(revision, int) and recorded > revision:
                future_revision.append(str(evidence_id))
    actual = {
        "referenceCount": len(references),
        "missingEvidenceIds": sorted(set(missing)),
        "wrongCandidateEvidenceIds": sorted(set(wrong_candidate)),
        "futureRevisionEvidenceIds": sorted(set(future_revision)),
    }
    return DeterministicResult(not any(actual[key] for key in actual if key.endswith("Ids")), actual)


def _unsupported_fact(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    forbidden = [str(item) for item in expected.get("forbiddenFacts") or []]
    if forbidden:
        text = _output_text(outputs)
        found = [item for item in forbidden if item in text]
        return DeterministicResult(not found, {"forbiddenFacts": forbidden, "found": found})
    statuses = {str(item) for item in expected.get("unsupportedStatuses") or ["unsupported", "rejected"]}
    evidence = list(_evidence_index(_selected_state(outputs, expected)).values())
    structured = [item for item in evidence if item.get("claim") or item.get("claimStatus")]
    if not structured:
        return DeterministicResult(None, None, "普通自然语言 claim 需要人工审阅")
    unsupported = [item.get("evidenceId") for item in structured if str(item.get("claimStatus", "")).lower() in statuses]
    return DeterministicResult(not unsupported, {"claimCount": len(structured), "unsupportedEvidenceIds": unsupported})


def _excluded_recommendation(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    state = _selected_state(outputs, expected)
    recommendation = state.get("recommendation")
    if not isinstance(recommendation, dict):
        return DeterministicResult(None, None, "缺少 Recommendation")
    excluded = {str(item) for item in state.get("excludedCandidates") or []}
    excluded.update(
        str(item.get("candidateId"))
        for item in state.get("candidates") or []
        if isinstance(item, dict) and item.get("eliminated")
    )
    if not excluded:
        return DeterministicResult(None, None, "没有排除或淘汰候选")
    recommended = {
        str(item)
        for item in [recommendation.get("primaryCandidateId"), *(recommendation.get("alternativeCandidateIds") or [])]
        if item
    }
    overlap = sorted(excluded & recommended)
    return DeterministicResult(not overlap, {"recommended": sorted(recommended), "excluded": sorted(excluded), "overlap": overlap})


def _retention(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    before = _turn_state(outputs, int(expected.get("beforeTurn", -2)))
    after = _turn_state(outputs, int(expected.get("afterTurn", -1)))
    paths = expected.get("paths") or []
    if paths:
        values = []
        passed = True
        for path in paths:
            before_found, before_value = _path_lookup(before, str(path))
            after_found, after_value = _path_lookup(after, str(path))
            values.append({"path": path, "before": before_value, "after": after_value})
            passed = passed and before_found and after_found and before_value == after_value
        return DeterministicResult(passed, values)
    before_projection = _formal_projection(before)
    after_projection = _formal_projection(after)
    return DeterministicResult(before_projection == after_projection, {"before": before_projection, "after": after_projection})


def _correction_coverage(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    after = _turn_state(outputs, int(expected.get("afterTurn", -1)))
    targets = expected.get("targets") or expected.get("checks") or []
    if not targets:
        return DeterministicResult(None, None, "缺少纠正目标，无法定义分母")
    return _evaluate_checks(after, targets)


def _what_if(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    before = _turn_state(outputs, int(expected.get("beforeTurn", -2)))
    after = _turn_state(outputs, int(expected.get("afterTurn", -1)))
    before_projection = _formal_projection(before)
    after_projection = _formal_projection(after)
    found, hypothetical = _path_lookup(after, "domainState.assistance.whatIfAnalysis.hypothetical")
    require_hypothetical = expected.get("requireHypothetical", True)
    passed = before_projection == after_projection and (not require_hypothetical or (found and hypothetical is True))
    return DeterministicResult(passed, {"formalStateUnchanged": before_projection == after_projection, "hypothetical": hypothetical})


def _llm_fallback(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    nodes = _trace_nodes(outputs)
    failed_model = [node for node in nodes if node.get("kind") == "model" and str(node.get("status", "")).lower() == "failed"]
    fallback_nodes = [node for node in nodes if node.get("kind") == "fallback" or "fallback" in str(node).lower()]
    state = _final_state(outputs)
    analysis_mode = _path_lookup(state, "domainState.assistance.analysis.mode")[1]
    recommendation = state.get("recommendation")
    execution_success = _path_lookup(outputs, "execution.status")[1] == "success"
    actual = {
        "failedModelCallCount": len(failed_model),
        "fallbackNodeCount": len(fallback_nodes),
        "analysisMode": analysis_mode,
        "executionSuccess": execution_success,
        "hasRecommendation": isinstance(recommendation, dict) and bool(recommendation.get("primaryCandidateId")),
    }
    if not failed_model:
        return DeterministicResult(None, actual, "没有真实失败的 model Trace node")
    return DeterministicResult(
        execution_success and bool(fallback_nodes) and analysis_mode == "rules_fallback" and actual["hasRecommendation"],
        actual,
    )


def _agent_failure(expected: dict[str, Any], outputs: dict[str, Any]) -> DeterministicResult:
    events = [event for event in _trace_events(outputs) if event.get("eventType") == "AGENT_CALL"]
    if not events:
        return DeterministicResult(None, None, "Trace 中没有 AgentRun")
    failures = [event for event in events if str(event.get("status", "")).upper() == "FAILED"]
    maximum = expected.get("maximumRate")
    rate = len(failures) / len(events)
    if maximum is None:
        return DeterministicResult(True, {"failures": len(failures), "total": len(events), "rate": rate})
    return DeterministicResult(rate <= float(maximum), {"failures": len(failures), "total": len(events), "rate": rate})


def _selected_state(outputs: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    if "turn" in expected:
        return _turn_state(outputs, int(expected["turn"]))
    return _final_state(outputs)


def _final_state(outputs: dict[str, Any]) -> dict[str, Any]:
    state = outputs.get("decisionState")
    return state if isinstance(state, dict) else {}


def _turn_state(outputs: dict[str, Any], index: int) -> dict[str, Any]:
    turns = outputs.get("turns")
    if not isinstance(turns, list) or not turns:
        raise ValueError("缺少 turns")
    turn = turns[index]
    state = turn.get("decisionState") if isinstance(turn, dict) else None
    if not isinstance(state, dict):
        raise ValueError(f"turn {index} 缺少 DecisionState")
    return state


def _revision_advanced(before: dict[str, Any], after: dict[str, Any], expected: dict[str, Any]) -> bool:
    before_revision = before.get("revision")
    after_revision = after.get("revision")
    if not isinstance(before_revision, int) or not isinstance(after_revision, int):
        return False
    minimum = int(expected.get("minimumRevisionDelta", 1))
    return after_revision - before_revision >= minimum


def _primary_candidate(state: dict[str, Any]) -> Any:
    recommendation = state.get("recommendation")
    return recommendation.get("primaryCandidateId") if isinstance(recommendation, dict) else None


def _evaluate_checks(root: dict[str, Any], checks: list[Any]) -> DeterministicResult:
    if not checks:
        return DeterministicResult(None, [], "没有 checks")
    actual_checks = []
    passed = True
    for raw in checks:
        if not isinstance(raw, dict) or not raw.get("path"):
            raise ValueError("check 必须包含 path")
        found, actual = _path_lookup(root, str(raw["path"]))
        operator = raw.get("operator", "equals")
        expected = raw.get("expected")
        result = found and _compare(operator, actual, expected)
        actual_checks.append({"path": raw["path"], "operator": operator, "expected": expected, "actual": actual, "found": found, "passed": result})
        passed = passed and result
    return DeterministicResult(passed, actual_checks)


def _compare(operator: str, actual: Any, expected: Any) -> bool:
    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator == "contains":
        return _contains(actual, expected)
    if operator == "not_contains":
        return not _contains(actual, expected)
    if operator == "includes_all":
        return all(_contains(actual, item) for item in _as_list(expected))
    if operator == "excludes_all":
        return all(not _contains(actual, item) for item in _as_list(expected))
    if operator == "non_empty":
        return bool(actual)
    if operator == "empty":
        return not bool(actual)
    raise ValueError(f"不支持的 check operator：{operator}")


def _formal_projection(state: dict[str, Any]) -> dict[str, Any]:
    domain_state = state.get("domainState") or {}
    assistance = domain_state.get("assistance") if isinstance(domain_state, dict) else None
    formal_domain_state = {
        "conversationFields": domain_state.get("conversationFields") if isinstance(domain_state, dict) else None,
        "facts": assistance.get("facts") if isinstance(assistance, dict) else None,
        "currentAnalysis": assistance.get("currentAnalysis") if isinstance(assistance, dict) else None,
    }
    return {
        "domain": state.get("domain"),
        "intent": state.get("intent"),
        "constraints": state.get("constraints") or [],
        "criteria": state.get("criteria") or [],
        "candidates": state.get("candidates") or [],
        "excludedCandidates": state.get("excludedCandidates") or [],
        "recommendation": recommendation_signature({"decisionState": state}),
        "domainState": formal_domain_state,
    }


def _evidence_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = [item for item in state.get("evidence") or [] if isinstance(item, dict)]
    for candidate in state.get("candidates") or []:
        if isinstance(candidate, dict):
            values.extend(item for item in candidate.get("evidence") or [] if isinstance(item, dict))
    return {
        str(item.get("evidenceId")): item
        for item in values
        if item.get("evidenceId")
    }


def _trace_documents(outputs: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = outputs.get("traceSnapshot") or {}
    related = snapshot.get("relatedTraces") if isinstance(snapshot, dict) else None
    snapshots = related if isinstance(related, list) and related else [snapshot]
    documents = []
    for item in snapshots:
        trace = item.get("traceJson") if isinstance(item, dict) else None
        if isinstance(trace, dict):
            documents.append(trace)
    return documents


def _trace_nodes(outputs: dict[str, Any]) -> list[dict[str, Any]]:
    return [node for trace in _trace_documents(outputs) for node in trace.get("timeline") or [] if isinstance(node, dict)]


def _trace_events(outputs: dict[str, Any]) -> list[dict[str, Any]]:
    return [event for trace in _trace_documents(outputs) for event in trace.get("events") or [] if isinstance(event, dict)]


def _output_text(outputs: dict[str, Any]) -> str:
    state = _final_state(outputs)
    recommendation = state.get("recommendation") or {}
    values = [outputs.get("speechText"), recommendation.get("summary")]
    values.extend(item.get("text") for key in ("reasons", "tradeoffDetails") for item in recommendation.get(key) or [] if isinstance(item, dict))
    return "\n".join(str(value) for value in values if value)


def _contains_mapping(values: list[Any], expected: dict[str, Any]) -> bool:
    return any(
        isinstance(value, dict) and all(value.get(key) == item for key, item in expected.items())
        for value in values
    )


def _path_lookup(value: Any, path: str) -> tuple[bool, Any]:
    current = value
    if path.startswith("decisionState."):
        path = path[len("decisionState."):]
    for part in path.split(".") if path else []:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.lstrip("-").isdigit():
            index = int(part)
            if -len(current) <= index < len(current):
                current = current[index]
            else:
                return False, None
        else:
            return False, None
    return True, current


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, dict):
        return any(_contains(key, expected) or _contains(value, expected) for key, value in actual.items())
    if isinstance(actual, list):
        return any(_contains(item, expected) for item in actual)
    if actual is None:
        return False
    return str(expected) in str(actual)


_AUTO_EVALUATORS = {
    "intent_accuracy": _intent,
    "constraint_extraction_accuracy": _constraint,
    "correction_update_accuracy": _correction,
    "hard_constraint_satisfaction": _hard_constraint,
    "exclusion_correctness": _exclusion,
    "recommendation_stability": lambda expected, outputs: DeterministicResult(None, None, "等待 repetition 配对"),
    "sensitivity_to_condition_change": _sensitivity,
    "reason_recommendation_consistency": _reason_consistency,
    "evidence_reference_validity": _evidence_validity,
    "unsupported_fact_rate": _unsupported_fact,
    "excluded_candidate_recommend_rate": _excluded_recommendation,
    "multi_turn_state_retention": _retention,
    "correction_coverage": _correction_coverage,
    "what_if_isolation": _what_if,
    "llm_fallback_success": _llm_fallback,
    "agent_execution_failure_rate": _agent_failure,
}
