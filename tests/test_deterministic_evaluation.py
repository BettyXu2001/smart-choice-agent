import pytest
from pydantic import ValidationError

from choice_agent.evaluation.deterministic import evaluate_auto_assertion, evaluate_repetition_stability
from choice_agent.evaluation.metrics import DETERMINISTIC_TARGET_METRIC_IDS
from choice_agent.evaluation.runner import EvaluationRunner, deterministic_gate_status
from choice_agent.evaluation.schemas import EvaluationAssertion
from choice_agent.providers.model import DisabledProvider


def state(*, primary="a", revision=1, what_if=False):
    return {
        "domain": "generic",
        "intent": "compare",
        "revision": revision,
        "constraints": [{"key": "budget", "value": 100, "kind": "hard"}],
        "excludedCandidates": ["b"],
        "candidateState": {"b": {"status": "eliminated", "reason": "不满足硬约束"}},
        "candidates": [
            {
                "candidateId": "a",
                "name": "A",
                "attributes": {"price": 80},
                "evidence": [
                    {
                        "evidenceId": "ev-a",
                        "candidateId": "a",
                        "recordedRevision": 1,
                        "claim": "A price is supported",
                        "claimStatus": "supported",
                    }
                ],
            },
            {"candidateId": "b", "name": "B", "attributes": {"price": 120}, "eliminated": True},
            {"candidateId": "c", "name": "C", "attributes": {"price": 90}},
        ],
        "recommendation": {
            "primaryCandidateId": primary,
            "alternativeCandidateIds": [],
            "rankingMethod": "score",
            "summary": f"Recommend {primary}",
            "reasons": [
                {"candidateId": primary, "evidenceIds": ["ev-a"], "text": "Evidence supports this recommendation."}
            ],
            "tradeoffDetails": [],
        },
        "domainState": {
            "conversationFields": {
                "budget": {"value": 80 if revision > 1 else 100},
                "preference": {"value": "stable"},
            },
            "assistance": {
                "facts": ["budget 80" if revision > 1 else "budget 100"],
                "currentAnalysis": {"hypothetical": False},
                "whatIfAnalysis": {"hypothetical": what_if},
                "analysis": {"mode": "rules_fallback"},
            },
        },
    }


def outputs_with_turns(*, after_primary="a", what_if=False):
    before = state(primary="a", revision=1)
    after = state(primary=after_primary, revision=2, what_if=what_if)
    return {
        "execution": {"status": "success"},
        "speechText": "A recommendation without forbidden fact",
        "decisionState": after,
        "turns": [
            {"message": "start", "decisionState": before},
            {"message": "follow up", "decisionState": after},
        ],
        "traceSnapshot": {
            "relatedTraces": [
                {
                    "traceJson": {
                        "timeline": [
                            {"kind": "model", "status": "failed"},
                            {"kind": "fallback", "status": "completed"},
                        ],
                        "events": [
                            {"eventType": "AGENT_CALL", "agentName": "CandidateAgent", "status": "SUCCEEDED"},
                            {"eventType": "AGENT_CALL", "agentName": "RankAgent", "status": "FAILED", "errorMessage": "simulated"},
                        ],
                    }
                }
            ]
        },
    }




def outputs_for_what_if():
    current = outputs_with_turns()
    hypothetical = state(primary="a", revision=1, what_if=True)
    current["decisionState"] = hypothetical
    current["turns"][1]["decisionState"] = hypothetical
    return current

def assert_auto_passes(metric_id, expected, outputs):
    result = evaluate_auto_assertion(metric_id, expected, outputs)
    assert result.passed is True, result
    assert result.evaluation_method == "deterministic"


@pytest.mark.parametrize(
    ("metric_id", "expected", "outputs"),
    [
        ("intent_accuracy", {"domain": "generic", "intent": "compare"}, outputs_with_turns()),
        ("constraint_extraction_accuracy", {"constraints": [{"key": "budget", "value": 100}]}, outputs_with_turns()),
        ("correction_update_accuracy", {"beforeTurn": 0, "afterTurn": 1, "checks": [{"path": "domainState.conversationFields.budget.value", "expected": 80}]}, outputs_with_turns()),
        ("hard_constraint_satisfaction", {}, outputs_with_turns()),
        ("exclusion_correctness", {"includes": ["b"], "excludes": ["a"]}, outputs_with_turns()),
        ("sensitivity_to_condition_change", {"beforeTurn": 0, "afterTurn": 1, "mode": "changed", "expectedPrimaryCandidateId": "c"}, outputs_with_turns(after_primary="c")),
        ("reason_recommendation_consistency", {"requireReasons": True, "requirePrimaryReference": True}, outputs_with_turns()),
        ("evidence_reference_validity", {"requireReferences": True, "requireCandidateMatch": True}, outputs_with_turns()),
        ("unsupported_fact_rate", {"forbiddenFacts": ["never appears"]}, outputs_with_turns()),
        ("excluded_candidate_recommend_rate", {}, outputs_with_turns()),
        ("multi_turn_state_retention", {"beforeTurn": 0, "afterTurn": 1, "paths": ["domainState.conversationFields.preference.value"]}, outputs_with_turns()),
        ("correction_coverage", {"afterTurn": 1, "targets": [{"path": "domainState.conversationFields.budget.value", "expected": 80}]}, outputs_with_turns()),
        ("what_if_isolation", {"beforeTurn": 0, "afterTurn": 1}, outputs_for_what_if()),
        ("llm_fallback_success", {}, outputs_with_turns()),
        ("agent_execution_failure_rate", {"maximumRate": 0.5}, outputs_with_turns()),
    ],
)
def test_auto_evaluators_have_deterministic_success_paths(metric_id, expected, outputs):
    assert_auto_passes(metric_id, expected, outputs)


def test_repetition_stability_covers_recommendation_stability():
    first = outputs_with_turns()
    second = outputs_with_turns()
    result = evaluate_repetition_stability([first, second])

    assert result.passed is True
    assert result.evaluation_method == "deterministic"


def test_all_target_metrics_have_direct_deterministic_coverage_in_tests():
    covered = {
        "intent_accuracy",
        "constraint_extraction_accuracy",
        "correction_update_accuracy",
        "hard_constraint_satisfaction",
        "exclusion_correctness",
        "recommendation_stability",
        "sensitivity_to_condition_change",
        "reason_recommendation_consistency",
        "evidence_reference_validity",
        "unsupported_fact_rate",
        "excluded_candidate_recommend_rate",
        "multi_turn_state_retention",
        "correction_coverage",
        "what_if_isolation",
        "llm_fallback_success",
        "agent_execution_failure_rate",
    }
    assert covered == set(DETERMINISTIC_TARGET_METRIC_IDS)


def test_unsupported_fact_without_structured_claims_is_not_evaluated():
    current = outputs_with_turns()
    current["decisionState"]["candidates"][0]["evidence"] = []

    result = evaluate_auto_assertion("unsupported_fact_rate", {}, current)

    assert result.passed is None
    assert result.evaluation_method == "not_evaluated"
    assert result.reason == "普通自然语言 claim 需要人工审阅"


def test_required_manual_assertion_is_rejected():
    with pytest.raises(ValidationError):
        EvaluationAssertion(
            metric_id="intent_accuracy",
            operator="manual",
            required=True,
            evaluation_method="manual",
        )


def test_regression_gate_uses_only_required_deterministic_assertions():
    optional_manual = {
        "metricId": "intent_accuracy",
        "required": False,
        "passed": None,
        "evaluationMethod": "manual",
    }
    assert deterministic_gate_status([
        {"metricId": "hard_constraint_satisfaction", "required": True, "passed": True, "evaluationMethod": "deterministic"},
        optional_manual,
    ]) == "passed"
    assert deterministic_gate_status([
        {"metricId": "hard_constraint_satisfaction", "required": True, "passed": False, "evaluationMethod": "deterministic"},
        optional_manual,
    ]) == "failed"
    assert deterministic_gate_status([
        {"metricId": "hard_constraint_satisfaction", "required": True, "passed": None, "evaluationMethod": "not_evaluated"},
    ]) == "not_evaluated"
    assert deterministic_gate_status([
        {"metricId": "hard_constraint_satisfaction", "required": True, "passed": False, "evaluationMethod": "deterministic"},
        {"metricId": "intent_accuracy", "required": True, "passed": None, "evaluationMethod": "not_evaluated"},
    ]) == "failed"


def test_missing_generic_path_is_not_evaluated(database):
    with database.session_factory() as db:
        runner = EvaluationRunner(db, provider=DisabledProvider())
        result = runner._evaluate_assertion(
            {"metricId": "intent_accuracy", "path": "missing.value", "operator": "equals", "expected": "x"},
            {},
        )
    assert result["passed"] is None
    assert result["eligible"] is False
    assert result["evaluationMethod"] == "not_evaluated"
    assert result["missingReason"]