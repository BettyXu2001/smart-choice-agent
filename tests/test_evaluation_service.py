import pytest

from choice_agent.evaluation.schemas import EvaluationDatasetCreate, EvaluationRunCreate, EvaluationCaseUpdate
from choice_agent.evaluation.service import EvaluationService
from choice_agent.providers.model import DisabledProvider
from choice_agent.repositories.evaluation_repository import EvaluationConflictError


def service(db):
    return EvaluationService(db, provider=DisabledProvider())


def test_evaluation_dashboard_seeds_bad_cases_and_runs_fixture_regression(database):
    with database.session_factory() as db:
        evaluation = service(db)
        dashboard = evaluation.dashboard(1)
        assert len(dashboard["metricDefinitions"]) == 17
        assert dashboard["cases"]

        run = evaluation.create_run(1, EvaluationRunCreate(version_label="test-v1"))
        assert run["status"] == "completed"
        assert run["results"]
        assert run["summary"]["coverage"]["evaluatedQualityMetrics"] > 0
        assert run["summary"]["caseCounts"]["total"] == len(run["results"])


def test_evaluation_dataset_is_versioned_snapshot(database):
    with database.session_factory() as db:
        evaluation = service(db)
        dashboard = evaluation.dashboard(1)
        case_id = dashboard["cases"][0]["id"]
        dataset = evaluation.create_dataset(
            1,
            EvaluationDatasetCreate(name="core-regression", version="v1", case_ids=[case_id]),
        )

        assert dataset["caseCount"] == 1
        assert dataset["caseSnapshots"][0]["id"] == case_id
        with pytest.raises(EvaluationConflictError):
            evaluation.create_dataset(
                1,
                EvaluationDatasetCreate(name="core-regression", version="v1", case_ids=[case_id]),
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
