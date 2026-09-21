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
        "search_fallback_success",
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


def test_evaluation_summary_aggregates_latency_tokens_cost_and_coverage():
    summary = summarize_results([
        {
            "status": "passed",
            "assertions": [],
            "traceSnapshot": {"observability": {
                "latencyMs": 100,
                "providerCallCount": 1,
                "totalTokens": 50,
                "estimatedCost": 0.001,
                "knownEstimatedCost": 0.001,
                "unreportedUsageCallCount": 0,
                "unknownPriceCallCount": 0,
            }},
        },
        {
            "status": "passed",
            "assertions": [],
            "traceSnapshot": {"observability": {
                "latencyMs": 300,
                "providerCallCount": 1,
                "totalTokens": 150,
                "estimatedCost": None,
                "knownEstimatedCost": None,
                "unreportedUsageCallCount": 0,
                "unknownPriceCallCount": 1,
            }},
        },
    ])

    performance = summary["performance"]
    assert performance["averageLatencyMs"] == 200
    assert performance["p95LatencyMs"] == 300
    assert performance["totalTokens"] == 200
    assert performance["averageTokensPerCase"] == 100
    assert performance["knownEstimatedCost"] == 0.001
    assert performance["estimatedTotalCost"] is None
    assert performance["unknownPriceCallCount"] == 1


def test_evaluation_summary_uses_trace_observations_for_agent_failure_rate_and_latency():
    summary = summarize_results([
        {
            "status": "passed",
            "assertions": [],
            "metrics": {
                "agent_execution_failure_rate": {
                    "numerator": 1, "denominator": 4, "eligibleCount": 4,
                    "evaluatedCount": 4, "failures": [{"agentName": "CandidateAgent"}],
                },
                "average_response_time_ms": {
                    "numerator": 120, "denominator": 1, "eligibleCount": 1,
                    "evaluatedCount": 1, "failures": [],
                },
            },
        },
        {
            "status": "passed",
            "assertions": [],
            "metrics": {
                "agent_execution_failure_rate": {
                    "numerator": 0, "denominator": 6, "eligibleCount": 6,
                    "evaluatedCount": 6, "failures": [],
                },
                "average_response_time_ms": {
                    "numerator": 280, "denominator": 1, "eligibleCount": 1,
                    "evaluatedCount": 1, "failures": [],
                },
            },
        },
    ])

    metrics = {item["id"]: item for item in summary["metrics"]}
    assert metrics["agent_execution_failure_rate"]["value"] == 0.1
    assert metrics["agent_execution_failure_rate"]["numerator"] == 1
    assert metrics["agent_execution_failure_rate"]["denominator"] == 10
    assert metrics["agent_execution_failure_rate"]["failures"] == [{"agentName": "CandidateAgent"}]
    assert metrics["average_response_time_ms"]["value"] == 200
    assert metrics["average_response_time_ms"]["method"] == "trace_observation"


def test_evaluation_summary_reports_method_and_deterministic_coverage():
    summary = summarize_results([{
        "status": "passed",
        "assertions": [
            {"metricId": "hard_constraint_satisfaction", "passed": True, "eligible": True, "evaluationMethod": "deterministic"},
            {"metricId": "intent_accuracy", "passed": None, "eligible": False, "evaluationMethod": "manual"},
        ],
    }])

    metrics = {item["id"]: item for item in summary["metrics"]}
    assert metrics["hard_constraint_satisfaction"]["evaluationMethod"] == "deterministic"
    assert metrics["intent_accuracy"]["evaluationMethod"] == "manual"
    assert metrics["intent_accuracy"]["value"] is None
    assert metrics["constraint_extraction_accuracy"]["evaluationMethod"] == "not_evaluated"
    assert summary["coverage"]["deterministicEvaluatedMetricCount"] == 1
    assert summary["coverage"]["deterministicMetricCount"] == 16
    assert summary["coverage"]["deterministicMetricRate"] == 1 / 16
    assert summary["coverage"]["manualReviewMetricIds"] == ["intent_accuracy"]
    assert "constraint_extraction_accuracy" in summary["coverage"]["notEvaluatedMetricIds"]
