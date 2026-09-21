import pytest
from pydantic import ValidationError

from choice_agent.evaluation.runner import EvaluationRunner, deterministic_gate_status
from choice_agent.evaluation.schemas import EvaluationAssertion
from choice_agent.providers.model import DisabledProvider


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
