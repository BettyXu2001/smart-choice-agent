import pytest

from choice_agent.evaluation.comparison import (
    EvaluationComparisonError,
    classify_case_diff,
    compare_runs,
)


def run(run_id, label, *, dataset_hash="same", mode="fixture", status="completed"):
    return {
        "id": run_id,
        "status": status,
        "datasetId": "dataset",
        "datasetName": "regression",
        "datasetVersion": "v1",
        "datasetHash": dataset_hash,
        "evaluatorVersion": "evaluation-v1",
        "mode": mode,
        "runConfiguration": {
            "model": f"model-{label}",
            "provider": "disabled",
            "promptVersion": "prompt-v1",
            "ruleVersion": "rule-v1",
            "runLabel": label,
        },
    }


def result(result_id, case_id, status, passed, *, repetition=1, metric_id="intent_accuracy"):
    return {
        "id": result_id,
        "caseId": case_id,
        "caseRevision": 1,
        "repetition": repetition,
        "status": status,
        "assertions": [
            {
                "metricId": metric_id,
                "passed": passed,
                "eligible": True,
                "required": True,
            }
        ],
    }


@pytest.mark.parametrize(
    ("baseline", "candidate", "expected"),
    [
        ({"status": "failed", "score": 0}, {"status": "passed", "score": 100}, "fixed"),
        ({"status": "passed", "score": 100}, {"status": "error", "score": None}, "new_failure"),
        ({"status": "failed", "score": 25}, {"status": "failed", "score": 50}, "improved"),
        ({"status": "passed", "score": 100}, {"status": "not_evaluated", "score": None}, "regressed"),
        ({"status": "passed", "score": 100}, {"status": "passed", "score": 100}, "unchanged"),
    ],
)
def test_case_diff_classifies_all_outcomes(baseline, candidate, expected):
    assert classify_case_diff(baseline, candidate) == expected


def test_comparison_groups_repetitions_and_reports_directional_metric_delta():
    baseline_results = [
        result("b1", "case-a", "failed", False, repetition=1, metric_id="unsupported_fact_rate"),
        result("b2", "case-a", "failed", False, repetition=2, metric_id="unsupported_fact_rate"),
    ]
    candidate_results = [
        result("c1", "case-a", "passed", True, repetition=1, metric_id="unsupported_fact_rate"),
        result("c2", "case-a", "passed", True, repetition=2, metric_id="unsupported_fact_rate"),
    ]

    comparison = compare_runs(
        run("baseline", "baseline"),
        run("candidate", "candidate"),
        baseline_results,
        candidate_results,
        case_titles={"case-a": "事实引用"},
    )

    assert comparison["caseDiffCounts"]["fixed"] == 1
    assert len(comparison["caseDiffs"]) == 1
    assert comparison["caseDiffs"][0]["title"] == "事实引用"
    assert comparison["caseDiffs"][0]["baseline"]["resultIds"] == ["b1", "b2"]
    metric_delta = next(
        item for item in comparison["aggregateDelta"]["metrics"]
        if item["metricId"] == "unsupported_fact_rate"
    )
    assert metric_delta["rawDelta"] == -1
    assert metric_delta["qualityDelta"] == 1
    assert comparison["baselineRun"]["summary"]["caseCounts"]["failed"] == 2
    assert comparison["candidateRun"]["summary"]["caseCounts"]["passed"] == 2


def test_comparison_rejects_different_case_revision_or_repetition_set():
    with pytest.raises(EvaluationComparisonError, match="集合不一致"):
        compare_runs(
            run("baseline", "baseline"),
            run("candidate", "candidate"),
            [result("b1", "case-a", "passed", True)],
            [result("c1", "case-a", "passed", True, repetition=2)],
        )


@pytest.mark.parametrize(
    ("baseline", "candidate", "message"),
    [
        (run("a", "candidate"), run("b", "candidate"), "标签"),
        (run("a", "baseline", dataset_hash="a"), run("b", "candidate", dataset_hash="b"), "Dataset"),
        (run("a", "baseline", mode="fixture"), run("b", "candidate", mode="live_model"), "运行模式"),
        (run("a", "baseline", status="running"), run("b", "candidate"), "尚未完成"),
    ],
)
def test_comparison_rejects_incompatible_runs(baseline, candidate, message):
    with pytest.raises(EvaluationComparisonError, match=message):
        compare_runs(
            baseline,
            candidate,
            [result("b1", "case-a", "passed", True)],
            [result("c1", "case-a", "passed", True)],
        )
