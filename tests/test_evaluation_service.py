import pytest
from pydantic import ValidationError

from choice_agent.evaluation.schemas import (
    CURRENT_PROMPT_VERSION,
    CURRENT_RULE_VERSION,
    EvaluationCaseCreate,
    EvaluationCaseUpdate,
    EvaluationDatasetCreate,
    EvaluationRunConfiguration,
    EvaluationRunCreate,
)
from choice_agent.evaluation.service import EvaluationConfigurationError, EvaluationService
from choice_agent.providers.model import DisabledProvider
from choice_agent.repositories.evaluation_repository import EvaluationConflictError


def service(db):
    return EvaluationService(db, provider=DisabledProvider())


def test_evaluation_dashboard_seeds_versioned_regression_datasets_and_runs_core(database):
    with database.session_factory() as db:
        evaluation = service(db)
        dashboard = evaluation.dashboard(1)
        assert len(dashboard["metricDefinitions"]) == 18
        datasets = {item["name"]: item for item in dashboard["datasets"]}
        assert datasets["core-regression"]["version"] == "v1"
        assert datasets["core-regression"]["caseCount"] == 20
        assert datasets["fault-injection-reliability"]["version"] == "v2"
        assert datasets["fault-injection-reliability"]["caseCount"] == 8
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
        assert datasets["fault-injection-reliability"]["version"] == "v2"
        assert datasets["fault-injection-reliability"]["caseCount"] == 8


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


def run_configuration(label, model):
    return EvaluationRunConfiguration(
        model=model,
        provider="disabled",
        prompt_version=CURRENT_PROMPT_VERSION,
        rule_version=CURRENT_RULE_VERSION,
        run_label=label,
    )


def test_evaluation_run_persists_typed_configuration_and_legacy_fields(database):
    with database.session_factory() as db:
        evaluation = service(db)
        run = evaluation.create_run(
            1,
            EvaluationRunCreate(
                version_label="baseline-v1",
                model_name="baseline-model",
                run_configuration=run_configuration("baseline", "baseline-model"),
                limit=1,
            ),
        )

        assert run["modelName"] == "baseline-model"
        assert run["runConfiguration"] == {
            "model": "baseline-model",
            "provider": "disabled",
            "promptVersion": CURRENT_PROMPT_VERSION,
            "ruleVersion": CURRENT_RULE_VERSION,
            "runLabel": "baseline",
        }
        assert run["config"]["runConfiguration"] == run["runConfiguration"]
        assert len(run["results"]) == 1


def test_same_dataset_runs_baseline_and_candidate_and_compares_exact_case_set(database):
    with database.session_factory() as db:
        evaluation = service(db)
        dataset = next(
            item for item in evaluation.dashboard(1)["datasets"]
            if item["name"] == "core-regression"
        )
        baseline = evaluation.create_run(
            1,
            EvaluationRunCreate(
                dataset_id=dataset["id"],
                version_label="baseline-v1",
                run_configuration=run_configuration("baseline", "model-v1"),
                limit=2,
            ),
        )
        candidate = evaluation.create_run(
            1,
            EvaluationRunCreate(
                dataset_id=dataset["id"],
                version_label="candidate-v2",
                run_configuration=run_configuration("candidate", "model-v2"),
                limit=2,
            ),
        )

        baseline_keys = {
            (item["caseId"], item["caseRevision"], item["repetition"])
            for item in baseline["results"]
        }
        candidate_keys = {
            (item["caseId"], item["caseRevision"], item["repetition"])
            for item in candidate["results"]
        }
        assert baseline["datasetHash"] == candidate["datasetHash"]
        assert baseline_keys == candidate_keys

        comparison = evaluation.compare_runs(1, baseline["id"], candidate["id"])
        assert comparison["baselineRun"]["summary"]["caseCounts"]["total"] == 2
        assert comparison["candidateRun"]["summary"]["caseCounts"]["total"] == 2
        assert len(comparison["baselineRun"]["summary"]["metrics"]) == 18
        assert len(comparison["candidateRun"]["summary"]["metrics"]) == 18
        assert comparison["baselineRun"]["summary"]["categoryScores"]
        assert comparison["candidateRun"]["summary"]["categoryScores"]
        assert sum(comparison["caseDiffCounts"].values()) == 2
        assert len(comparison["caseDiffs"]) == 2

        dashboard_comparison = evaluation.dashboard(1)["comparison"]
        assert dashboard_comparison["baselineRunId"] == baseline["id"]
        assert dashboard_comparison["candidateRunId"] == candidate["id"]
        assert "scoreDelta" in dashboard_comparison

        with pytest.raises(KeyError):
            evaluation.compare_runs(2, baseline["id"], candidate["id"])


def test_run_configuration_rejects_conflicting_legacy_model():
    with pytest.raises(ValidationError, match="冲突"):
        EvaluationRunCreate(
            model_name="legacy-model",
            run_configuration=run_configuration("candidate", "new-model"),
        )


def test_run_configuration_rejects_unregistered_prompt_version():
    with pytest.raises(ValidationError, match="promptVersion"):
        EvaluationRunConfiguration(
            model="model",
            provider="disabled",
            prompt_version="unknown",
            rule_version=CURRENT_RULE_VERSION,
            run_label="candidate",
        )

def test_configured_provider_must_be_enabled(database):
    with database.session_factory() as db:
        evaluation = service(db)
        configured = EvaluationRunConfiguration(
            model="model",
            provider="configured",
            prompt_version=CURRENT_PROMPT_VERSION,
            rule_version=CURRENT_RULE_VERSION,
            run_label="candidate",
        )
        with pytest.raises(EvaluationConfigurationError, match="未启用"):
            evaluation.create_run(1, EvaluationRunCreate(run_configuration=configured, limit=1))


def test_request_fingerprint_includes_effective_run_configuration(database):
    with database.session_factory() as db:
        evaluation = service(db)
        evaluation.create_run(
            1,
            EvaluationRunCreate(
                request_id="configured-request",
                run_configuration=run_configuration("baseline", "model-v1"),
                limit=1,
            ),
        )
        with pytest.raises(EvaluationConflictError):
            evaluation.create_run(
                1,
                EvaluationRunCreate(
                    request_id="configured-request",
                    run_configuration=run_configuration("baseline", "model-v2"),
                    limit=1,
                ),
            )
