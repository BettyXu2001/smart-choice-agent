from choice_agent.evaluation.runner import EvaluationRunner, FaultInjectionModel
from choice_agent.evaluation.schemas import (
    CURRENT_PROMPT_VERSION,
    CURRENT_RULE_VERSION,
    EvaluationRunConfiguration,
    EvaluationRunCreate,
)
from choice_agent.evaluation.service import EvaluationService
from choice_agent.providers.model import DisabledProvider


def service(db):
    return EvaluationService(db, provider=DisabledProvider())


def test_core_regression_dataset_runs_real_orchestrator_and_captures_trace(database):
    with database.session_factory() as db:
        evaluation = service(db)
        dashboard = evaluation.dashboard(1)
        core = next(
            item for item in dashboard["datasets"]
            if item["name"] == "core-regression" and item["version"] == "v3"
        )
        assert core["caseCount"] == 20
        assert all(case["caseData"].get("fixtureActual") is None for case in core["caseSnapshots"])

        run = evaluation.create_run(1, EvaluationRunCreate(dataset_id=core["id"], version_label="core-test"))
        assert run["status"] == "completed"
        assert len(run["results"]) == 20
        assert {result["outputs"]["mode"] for result in run["results"]} == {"orchestrator"}
        assert all(result["outputs"].get("turns") for result in run["results"])
        assert all(result["traceSnapshot"].get("traceId") for result in run["results"])
        assert all(result["traceSnapshot"].get("relatedTraces") for result in run["results"])
        assert run["summary"]["performance"]["latencySampleCount"] == 20
        assert run["summary"]["performance"]["averageLatencyMs"] is not None
        assert run["summary"]["performance"]["totalTokens"] is None
        assert run["summary"]["routingDiagnostics"]["sampleCount"] == 5
        assert run["summary"]["groups"]["byCaseType"]["routing"]["caseCounts"]["total"] == 5


def test_fault_injection_dataset_is_separate_and_exercises_web_search_path(database):
    with database.session_factory() as db:
        evaluation = service(db)
        dashboard = evaluation.dashboard(1)
        fault = next(
            item for item in dashboard["datasets"]
            if item["name"] == "fault-injection-reliability" and item["version"] == "v2"
        )
        assert fault["caseCount"] == 8
        assert all("fault-injection-reliability" in case["caseData"]["tags"] for case in fault["caseSnapshots"])
        assert all(case["caseData"].get("fixtureActual") is None for case in fault["caseSnapshots"])
        search_cases = [case for case in fault["caseSnapshots"] if case["caseData"].get("setup", {}).get("mockSearch")]
        assert search_cases

        run = evaluation.create_run(1, EvaluationRunCreate(dataset_id=fault["id"], version_label="fault-test", limit=20))
        assert run["status"] == "completed"
        assert {result["status"] for result in run["results"]} == {"passed"}
        assert {result["outputs"]["mode"] for result in run["results"]} == {"orchestrator"}
        assert all(result["traceSnapshot"].get("traceId") for result in run["results"])

        by_seed = {
            case["caseData"]["setup"]["seedId"]: result
            for case, result in zip(fault["caseSnapshots"], run["results"], strict=True)
        }
        timeout = by_seed["fault-injection-v2.model-timeout"]
        invalid_json = by_seed["fault-injection-v2.model-invalid-json"]
        transport = by_seed["fault-injection-v2.search-transport-error"]
        invalid_search = by_seed["fault-injection-v2.search-invalid-response"]
        agent_failure = by_seed["fault-injection-v2.agent-execution-failure"]

        assert timeout["outputs"]["execution"]["status"] == "success"
        assert timeout["outputs"]["decisionState"]["domainState"]["assistance"]["analysis"]["mode"] == "rules_fallback"
        assert invalid_json["outputs"]["execution"]["status"] == "success"
        assert "JSONDecodeError" in str(invalid_json["traceSnapshot"]["traceJson"]["timeline"])
        assert transport["outputs"]["decisionState"]["domainState"]["source"]["mode"] == "fixture"
        assert "Web Search 失败，已回退 fixture" in str(
            transport["outputs"]["decisionState"]["domainState"]["source"]["warnings"]
        )
        assert invalid_search["outputs"]["execution"]["status"] == "error"
        assert invalid_search["traceSnapshot"]["status"] == "FAILED"
        assert invalid_search["traceSnapshot"]["traceJson"]["metadata"]["commitStatus"] == "rolled_back"
        assert agent_failure["outputs"]["execution"]["status"] == "error"
        assert "CandidateAgent execution failed: simulated" in agent_failure["outputs"]["execution"]["errorMessage"]
        assert agent_failure["traceSnapshot"]["status"] == "FAILED"

        summary_metrics = {item["id"]: item for item in run["summary"]["metrics"]}
        assert summary_metrics["llm_fallback_success"]["value"] == 1
        assert summary_metrics["search_fallback_success"]["value"] == 1
        assert summary_metrics["agent_execution_failure_rate"]["numerator"] >= 2
        assert summary_metrics["agent_execution_failure_rate"]["denominator"] > summary_metrics["agent_execution_failure_rate"]["numerator"]
        assert summary_metrics["average_response_time_ms"]["value"] is not None


def test_diet_travel_dataset_runs_balanced_repeat_evaluation(database):
    with database.session_factory() as db:
        evaluation = service(db)
        dataset = next(
            item for item in evaluation.dashboard(1)["datasets"]
            if item["name"] == "diet-travel-evaluation" and item["version"] == "v1"
        )
        assert dataset["caseCount"] == 20
        assert sum(case["caseData"]["domain"] == "diet" for case in dataset["caseSnapshots"]) == 10
        assert sum(case["caseData"]["domain"] == "travel" for case in dataset["caseSnapshots"]) == 10

        run = evaluation.create_run(
            1,
            EvaluationRunCreate(
                dataset_id=dataset["id"],
                version_label="diet-travel-v1-test",
                limit=20,
                repeat=2,
            ),
        )
        case_by_id = {case["id"]: case for case in dataset["caseSnapshots"]}
        assert all(result["status"] != "error" for result in run["results"])
        reliable_seeds = {
            "diet-travel-v1.diet-route",
            "diet-travel-v1.diet-recommendation",
            "diet-travel-v1.diet-safety",
            "diet-travel-v1.travel-route",
            "diet-travel-v1.travel-model-timeout",
            "diet-travel-v1.travel-search-fallback",
            "diet-travel-v1.travel-agent-failure",
        }
        assert all(
            result["status"] == "passed"
            for result in run["results"]
            if case_by_id[result["caseId"]]["caseData"]["setup"]["seedId"] in reliable_seeds
        )
        assert len(run["results"]) == 40
        assert run["summary"]["caseCounts"]["total"] == 40
        assert set(run["summary"]["groups"]["byDomain"]) == {"diet", "travel"}
        assert run["summary"]["groups"]["byDomain"]["diet"]["caseCounts"]["total"] == 20
        assert run["summary"]["groups"]["byDomain"]["travel"]["caseCounts"]["total"] == 20
        assert run["summary"]["routingDiagnostics"]["sampleCount"] == 4
        metrics = {item["id"]: item for item in run["summary"]["metrics"]}
        assert len(metrics) == 23
        assert metrics["recommendation_stability"]["value"] == 1
        assert metrics["llm_fallback_success"]["value"] == 1
        assert metrics["search_fallback_success"]["value"] == 1
        assert metrics["average_response_time_ms"]["value"] is not None


class RecordingModel(FaultInjectionModel):
    enabled = True

    def __init__(self):
        super().__init__("valid")
        self.models = []

    def complete_json(self, **kwargs):
        self.models.append(kwargs["model"])
        return super().complete_json(**kwargs)


def execution_configuration(provider):
    return EvaluationRunConfiguration(
        model="candidate-model",
        provider=provider,
        prompt_version=CURRENT_PROMPT_VERSION,
        rule_version=CURRENT_RULE_VERSION,
        run_label="candidate",
    )


def test_runner_applies_model_and_provider_configuration_to_real_orchestrator(database):
    with database.session_factory() as db:
        evaluation = service(db)
        core = next(
            item for item in evaluation.dashboard(1)["datasets"]
            if item["name"] == "core-regression" and item["version"] == "v3"
        )
        case = next(
            item for item in core["caseSnapshots"]
            if "offer" in item["caseData"]["tags"]
        )
        provider = RecordingModel()
        runner = EvaluationRunner(db, provider=provider)

        configured = runner.run_case(1, case, execution_configuration("configured"))
        assert configured.status == "passed"
        assert configured.trace_snapshot["traceId"]
        assert provider.models
        assert set(provider.models) == {"candidate-model"}

        provider.models.clear()
        disabled = runner.run_case(1, case, execution_configuration("disabled"))
        assert disabled.status == "passed"
        assert disabled.trace_snapshot["traceId"]
        assert provider.models == []


def test_runner_captures_full_rerank_and_explain_only_execution_paths(database):
    case = {
        "originalQuestion": "比较两个 Offer",
        "caseData": {
            "domain": "generic",
            "setup": {"context": {"demoMode": True}},
            "messages": [
                "比较两个 Offer\n以下为演示候选：\nA 公司：成长快但波动大；B 公司：平台成熟且稳定。",
                "更看重稳定",
                "为什么不选 A 公司？",
            ],
            "tags": ["execution-path"],
        },
    }
    with database.session_factory() as db:
        output = EvaluationRunner(db, provider=DisabledProvider()).run_case(1, case)

    assert output.status == "not_evaluated"
    traces = output.trace_snapshot["relatedTraces"]
    assert [trace["traceJson"]["metadata"]["executionMode"] for trace in traces] == [
        "full",
        "rerank",
        "explain_only",
    ]
    assert all(trace["traceJson"]["metadata"].get("executedPath") for trace in traces)
    assert traces[-1]["traceJson"]["metadata"]["candidatePool"]["reused"] is True
