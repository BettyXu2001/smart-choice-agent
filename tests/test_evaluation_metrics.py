from choice_agent.evaluation.metrics import METRIC_DEFINITIONS, summarize_results


def test_evaluation_metric_catalog_contains_all_dashboard_metrics():
    assert [item.metric_id for item in METRIC_DEFINITIONS] == [
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
        "average_response_time_ms",
    ]


def test_evaluation_summary_scores_quality_metrics_and_marks_missing():
    summary = summarize_results([
        {
            "status": "failed",
            "assertions": [
                {"metricId": "intent_accuracy", "passed": True, "eligible": True},
                {"metricId": "constraint_extraction_accuracy", "passed": False, "eligible": True},
                {"metricId": "unsupported_fact_rate", "passed": False, "eligible": True},
            ],
        }
    ])

    metrics = {item["id"]: item for item in summary["metrics"]}
    assert metrics["intent_accuracy"]["value"] == 1.0
    assert metrics["constraint_extraction_accuracy"]["value"] == 0.0
    assert metrics["unsupported_fact_rate"]["value"] == 1.0
    assert metrics["hard_constraint_satisfaction"]["missingReason"] == "not_applicable"
    assert summary["coverage"]["evaluatedQualityMetrics"] == 3
    assert summary["caseCounts"]["failed"] == 1
    assert summary["overallScore"] is not None
