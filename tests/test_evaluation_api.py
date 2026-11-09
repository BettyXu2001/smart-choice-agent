import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException

from choice_agent.api.evaluations import compare_runs
from choice_agent.evaluation.comparison import EvaluationComparisonError


def test_module_filter_applies_limit_after_exact_matching_and_owner_filter(web):
    from choice_agent.db_models import EvaluationCaseRecord

    owner = web.call("GET", "/api/v1/identity")[1]["userId"]
    base = datetime(2026, 1, 1)
    with web.app.state.database.session_factory() as db:
        for index in range(205):
            db.add(EvaluationCaseRecord(
                id=f"module-{index:03}", owner_user_id=owner, title=f"case {index}",
                original_question="question", expected_behavior="expected", status="open",
                error_type="理解错误", modules=["target"] if index < 3 else ["target-extra"],
                updated_at=base + timedelta(seconds=index),
            ))
        db.add(EvaluationCaseRecord(
            id="other-owner", owner_user_id=owner + 1, title="private",
            original_question="question", expected_behavior="expected", status="open",
            error_type="理解错误", modules=["target"], updated_at=base + timedelta(days=1),
        ))
        db.commit()
    status, result, _ = web.call("GET", "/api/v1/evaluations/cases?module=target&limit=2&status=open&q=case")
    assert status == 200
    assert [row["id"] for row in result["cases"]] == ["module-002", "module-001"]
    assert web.call("GET", "/api/v1/evaluations/cases?module=missing&limit=2")[1] == {"cases": []}
    with web.app.state.database.session_factory() as db:
        for identifier in ("module-000", "module-001", "module-002"):
            db.get(EvaluationCaseRecord, identifier).updated_at = base
        db.commit()
    result = web.call("GET", "/api/v1/evaluations/cases?module=target&limit=10")[1]
    assert [row["id"] for row in result["cases"]] == ["module-002", "module-001", "module-000"]
    result = web.call("GET", "/api/v1/evaluations/cases?limit=1")[1]
    assert [row["id"] for row in result["cases"]] == ["module-204"]


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


def test_case_concurrent_stale_edit_returns_409_and_preserves_audit(web):
    from choice_agent.api.evaluations import update_case
    from choice_agent.evaluation.schemas import EvaluationCaseUpdate
    from choice_agent.evaluation.service import EvaluationService
    web.call("GET", "/api/v1/identity")
    status, created, _ = web.call("POST", "/api/v1/evaluations/cases",
                                  {"title": "original", "originalQuestion": "q", "expectedBehavior": "e"})
    assert status == 201
    with web.app.state.database.session_factory() as stale_db:
        service = EvaluationService(stale_db)
        row = service.repository.get_case(created["ownerUserId"], created["id"])
        assert row.revision == 1
        assert web.call("PUT", f"/api/v1/evaluations/cases/{created['id']}",
                        {"revision": 1, "title": "winning edit"})[0] == 200
        with pytest.raises(HTTPException) as caught:
            update_case(created["id"], EvaluationCaseUpdate(revision=1, title="stale overwrite"),
                        uid=created["ownerUserId"], evaluation=service)
        assert caught.value.status_code == 409
    status, final, _ = web.call("GET", f"/api/v1/evaluations/cases/{created['id']}")
    assert status == 200 and final["title"] == "winning edit" and final["revision"] == 2
    assert len(final["auditEvents"]) == 2


def test_regression_sync_records_conflict_without_overwriting_editor(database, monkeypatch):
    from choice_agent.db_models import EvaluationRunRecord
    from choice_agent.evaluation.service import EvaluationService
    from choice_agent.evaluation.schemas import EvaluationCaseCreate
    from choice_agent.repositories.evaluation_repository import EvaluationRepository
    with database.session_factory() as db:
        service = EvaluationService(db)
        created = service.create_case(7, EvaluationCaseCreate(title="original", original_question="q",
                                     expected_behavior="e", fix_version="fix", status="awaiting_regression"))
        run = EvaluationRunRecord(id="sync-run", owner_user_id=7, request_id="req", fingerprint="fp",
                                  version_label="test", status="completed", summary_json={"preserved": True})
        db.add(run)
        db.commit()
        original_update = service.repository.update_case
        def race(row, revision, changes):
            with database.session_factory() as other:
                repo = EvaluationRepository(other)
                repo.update_case(repo.get_case(7, row.id), revision, {"title": "new editor change"})
            return original_update(row, revision, changes)
        monkeypatch.setattr(service.repository, "update_case", race)
        service._sync_case_regression_status(7, run, [{"caseId": created["id"], "caseRevision": 1, "status": "passed"}])
        response = service.run_response(run)
        assert response["status"] == "completed" and response["summary"]["preserved"] is True
        assert response["summary"]["caseSyncWarnings"][0]["caseId"] == created["id"]
        final = service.repository.get_case(7, created["id"])
        assert final.title == "new editor change" and final.status == "awaiting_regression" and final.revision == 2


def test_case_update_clears_nullable_fields_but_preserves_omitted_values(web):
    web.call("GET", "/api/v1/identity")
    _, created, _ = web.call("POST", "/api/v1/evaluations/cases", {
        "title": "original", "originalQuestion": "q", "expectedBehavior": "expected",
        "actualBehavior": "old actual", "diagnosis": "old diagnosis", "fixPlan": "old plan",
        "fixVersion": "old version", "modules": ["module"],
    })
    path = "/api/v1/evaluations/cases/" + created["id"]
    status, renamed, _ = web.call("PUT", path, {"revision": 1, "title": "renamed"})
    assert status == 200 and renamed["diagnosis"] == "old diagnosis" and renamed["fixVersion"] == "old version"
    status, cleared, _ = web.call("PUT", path, {
        "revision": 2, "actualBehavior": None, "diagnosis": None, "fixPlan": None,
        "fixVersion": None, "modules": [],
    })
    assert status == 200 and cleared["revision"] == 3 and len(cleared["auditEvents"]) == 3
    assert all(cleared[key] is None for key in ("actualBehavior", "diagnosis", "fixPlan", "fixVersion"))
    assert cleared["title"] == "renamed" and cleared["expectedBehavior"] == "expected" and cleared["modules"] == []
    assert web.call("GET", path)[1] == cleared
    assert web.call("PUT", path, {"revision": 2, "diagnosis": "stale"})[0] == 409
    other = web.fork()
    other.call("GET", "/api/v1/identity")
    assert other.call("PUT", path, {"revision": 3, "diagnosis": "foreign"})[0] == 404
    assert web.call("GET", path)[1] == cleared


@pytest.mark.parametrize("field,value", [
    ("title", None), ("expectedBehavior", None), ("errorType", None), ("modules", None),
    ("status", None), ("caseData", None), ("title", ""), ("expectedBehavior", " "),
])
def test_case_update_rejects_invalid_nonnullable_values_without_writing(web, field, value):
    web.call("GET", "/api/v1/identity")
    _, created, _ = web.call("POST", "/api/v1/evaluations/cases",
                             {"title": "original", "originalQuestion": "q", "expectedBehavior": "expected"})
    path = "/api/v1/evaluations/cases/" + created["id"]
    status, error, _ = web.call("PUT", path, {"revision": 1, field: value})
    assert status == 422 and error["errors"]
    assert web.call("GET", path)[1] == created
