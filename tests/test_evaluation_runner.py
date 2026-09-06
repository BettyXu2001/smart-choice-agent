from choice_agent.evaluation.schemas import EvaluationRunCreate
from choice_agent.evaluation.service import EvaluationService
from choice_agent.providers.model import DisabledProvider


def service(db):
    return EvaluationService(db, provider=DisabledProvider())


def test_core_regression_dataset_runs_real_orchestrator_and_captures_trace(database):
    with database.session_factory() as db:
        evaluation = service(db)
        dashboard = evaluation.dashboard(1)
        core = next(item for item in dashboard["datasets"] if item["name"] == "core-regression")
        assert core["caseCount"] == 20
        assert all(case["caseData"].get("fixtureActual") is None for case in core["caseSnapshots"])

        run = evaluation.create_run(1, EvaluationRunCreate(dataset_id=core["id"], version_label="core-test"))
        assert run["status"] == "completed"
        assert len(run["results"]) == 20
        assert {result["outputs"]["mode"] for result in run["results"]} == {"orchestrator"}
        assert all(result["outputs"].get("turns") for result in run["results"])
        assert all(result["traceSnapshot"].get("traceId") for result in run["results"])


def test_fault_injection_dataset_is_separate_and_exercises_web_search_path(database):
    with database.session_factory() as db:
        evaluation = service(db)
        dashboard = evaluation.dashboard(1)
        fault = next(item for item in dashboard["datasets"] if item["name"] == "fault-injection-reliability")
        assert fault["caseCount"] == 6
        assert all("fault-injection-reliability" in case["caseData"]["tags"] for case in fault["caseSnapshots"])
        search_cases = [case for case in fault["caseSnapshots"] if case["caseData"].get("setup", {}).get("mockSearch")]
        assert search_cases

        run = evaluation.create_run(1, EvaluationRunCreate(dataset_id=fault["id"], version_label="fault-test", limit=20))
        assert run["status"] == "partial"
        statuses = [result["status"] for result in run["results"]]
        assert statuses.count("passed") == 4
        assert statuses.count("error") == 2
        errors = " ".join(result["errorMessage"] or "" for result in run["results"])
        assert "Web Search" in errors
