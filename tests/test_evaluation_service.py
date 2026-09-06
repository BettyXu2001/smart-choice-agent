import pytest
from pydantic import ValidationError

from choice_agent.evaluation.schemas import EvaluationCaseCreate, EvaluationDatasetCreate, EvaluationRunCreate, EvaluationCaseUpdate
from choice_agent.evaluation.service import EvaluationService
from choice_agent.providers.model import DisabledProvider
from choice_agent.repositories.evaluation_repository import EvaluationConflictError


def service(db):
    return EvaluationService(db, provider=DisabledProvider())


def test_evaluation_dashboard_seeds_versioned_regression_datasets_and_runs_core(database):
    with database.session_factory() as db:
        evaluation = service(db)
        dashboard = evaluation.dashboard(1)
        assert len(dashboard["metricDefinitions"]) == 17
        datasets = {item["name"]: item for item in dashboard["datasets"]}
        assert datasets["core-regression"]["version"] == "v1"
        assert datasets["core-regression"]["caseCount"] == 20
        assert datasets["fault-injection-reliability"]["caseCount"] == 6
        assert all(
            case["caseData"].get("fixtureActual") is None
            for case in datasets["core-regression"]["caseSnapshots"]
        )

        run = evaluation.create_run(1, EvaluationRunCreate(version_label="test-v1"))
        assert run["status"] == "completed"
        assert run["datasetName"] == "core-regression"
        assert len(run["results"]) == 20
        assert run["summary"]["caseCounts"] == {"total": 20, "passed": 20, "failed": 0, "error": 0, "notEvaluated": 0}
        assert run["summary"]["coverage"]["evaluatedQualityMetrics"] > 0


def test_starter_seed_is_idempotent_and_backfills_existing_database(database):
    with database.session_factory() as db:
        evaluation = service(db)
        manual = evaluation.create_case(
            1,
            EvaluationCaseCreate(
                title="手工历史 Case",
                original_question="历史问题",
                expected_behavior="保留手工 Case",
                case_data={"domain": "generic", "messages": ["历史问题"]},
            ),
        )
        evaluation.ensure_starter_cases(1)
        first = evaluation.dashboard(1)
        evaluation.ensure_starter_cases(1)
        second = evaluation.dashboard(1)

        assert any(case["id"] == manual["id"] for case in second["cases"])
        assert len(first["cases"]) == len(second["cases"])
        datasets = {item["name"]: item for item in second["datasets"]}
        assert datasets["core-regression"]["caseCount"] == 20
        assert datasets["fault-injection-reliability"]["caseCount"] == 6


def test_evaluation_dataset_is_versioned_snapshot(database):
    with database.session_factory() as db:
        evaluation = service(db)
        dashboard = evaluation.dashboard(1)
        case_id = dashboard["cases"][0]["id"]
        dataset = evaluation.create_dataset(
            1,
            EvaluationDatasetCreate(name="custom-regression", version="v1", case_ids=[case_id]),
        )

        assert dataset["caseCount"] == 1
        assert dataset["caseSnapshots"][0]["id"] == case_id
        with pytest.raises(EvaluationConflictError):
            evaluation.create_dataset(
                1,
                EvaluationDatasetCreate(name="custom-regression", version="v1", case_ids=[case_id]),
            )


def test_evaluation_case_cannot_be_manually_verified(database):
    with database.session_factory() as db:
        evaluation = service(db)
        case = evaluation.dashboard(1)["cases"][0]
        with pytest.raises(EvaluationConflictError):
            evaluation.update_case(
                1,
                case["id"],
                EvaluationCaseUpdate(revision=case["revision"], status="verified"),
            )


def test_evaluation_request_id_replays_same_run(database):
    with database.session_factory() as db:
        evaluation = service(db)
        first = evaluation.create_run(1, EvaluationRunCreate(request_id="same", version_label="test-v1"))
        second = evaluation.create_run(1, EvaluationRunCreate(request_id="same", version_label="test-v1"))
        assert first["id"] == second["id"]

        with pytest.raises(EvaluationConflictError):
            evaluation.create_run(1, EvaluationRunCreate(request_id="same", version_label="test-v2"))


def test_evaluation_run_limit_remains_twenty():
    with pytest.raises(ValidationError):
        EvaluationRunCreate(limit=21)
