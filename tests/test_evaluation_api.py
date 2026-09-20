import pytest
from fastapi import HTTPException

from choice_agent.api.evaluations import compare_runs
from choice_agent.evaluation.comparison import EvaluationComparisonError


class ComparisonService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def compare_runs(self, owner_id, baseline_run_id, candidate_run_id):
        if self.error:
            raise self.error
        return {
            "ownerId": owner_id,
            "baselineRunId": baseline_run_id,
            "candidateRunId": candidate_run_id,
            **(self.result or {}),
        }


def test_comparison_api_returns_service_report():
    response = compare_runs("baseline", "candidate", uid=7, evaluation=ComparisonService({"ok": True}))
    assert response == {
        "ownerId": 7,
        "baselineRunId": "baseline",
        "candidateRunId": "candidate",
        "ok": True,
    }


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (KeyError("missing"), 404),
        (EvaluationComparisonError("not comparable"), 409),
    ],
)
def test_comparison_api_maps_domain_errors(error, status_code):
    with pytest.raises(HTTPException) as captured:
        compare_runs("baseline", "candidate", uid=1, evaluation=ComparisonService(error=error))
    assert captured.value.status_code == status_code
