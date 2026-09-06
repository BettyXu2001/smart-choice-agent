from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from choice_agent.api.routes import get_db, get_provider, get_settings, user_id
from choice_agent.config import Settings
from choice_agent.evaluation.schemas import (
    EvaluationCaseCreate,
    EvaluationCaseUpdate,
    EvaluationDatasetCreate,
    EvaluationReviewUpdate,
    EvaluationRunCreate,
)
from choice_agent.evaluation.service import EvaluationService
from choice_agent.providers.model import ModelProvider
from choice_agent.repositories.evaluation_repository import EvaluationConflictError


router = APIRouter(prefix="/api/v1/evaluations")


def service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    provider: ModelProvider = Depends(get_provider),
) -> EvaluationService:
    return EvaluationService(db, settings=settings, provider=provider)


@router.get("/dashboard")
def dashboard(uid: int = Depends(user_id), evaluation: EvaluationService = Depends(service)) -> dict[str, Any]:
    return evaluation.dashboard(uid)


@router.get("/cases")
def list_cases(
    status: str | None = None,
    error_type: str | None = Query(default=None, alias="errorType"),
    module: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    uid: int = Depends(user_id),
    evaluation: EvaluationService = Depends(service),
) -> dict[str, Any]:
    rows = evaluation.repository.list_cases(uid, status=status, error_type=error_type, module=module, query=q, limit=limit)
    return {"cases": [evaluation.case_response(row) for row in rows]}


@router.post("/cases", status_code=201)
def create_case(
    body: EvaluationCaseCreate,
    uid: int = Depends(user_id),
    evaluation: EvaluationService = Depends(service),
) -> dict[str, Any]:
    return evaluation.create_case(uid, body)


@router.get("/cases/{case_id}")
def get_case(case_id: str, uid: int = Depends(user_id), evaluation: EvaluationService = Depends(service)) -> dict[str, Any]:
    row = evaluation.repository.get_case(uid, case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case 不存在或无权限访问")
    return evaluation.case_response(row)


@router.put("/cases/{case_id}")
def update_case(
    case_id: str,
    body: EvaluationCaseUpdate,
    uid: int = Depends(user_id),
    evaluation: EvaluationService = Depends(service),
) -> dict[str, Any]:
    try:
        return evaluation.update_case(uid, case_id, body)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except EvaluationConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/datasets")
def list_datasets(
    limit: int = Query(default=100, ge=1, le=200),
    uid: int = Depends(user_id),
    evaluation: EvaluationService = Depends(service),
) -> dict[str, Any]:
    rows = evaluation.repository.list_datasets(uid, limit)
    return {"datasets": [evaluation.dataset_response(row) for row in rows]}


@router.post("/datasets", status_code=201)
def create_dataset(
    body: EvaluationDatasetCreate,
    uid: int = Depends(user_id),
    evaluation: EvaluationService = Depends(service),
) -> dict[str, Any]:
    try:
        return evaluation.create_dataset(uid, body)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except EvaluationConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, uid: int = Depends(user_id), evaluation: EvaluationService = Depends(service)) -> dict[str, Any]:
    row = evaluation.repository.get_dataset(uid, dataset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Dataset 不存在或无权限访问")
    return evaluation.dataset_response(row)


@router.get("/runs")
def list_runs(
    limit: int = Query(default=50, ge=1, le=100),
    uid: int = Depends(user_id),
    evaluation: EvaluationService = Depends(service),
) -> dict[str, Any]:
    rows = evaluation.repository.list_runs(uid, limit)
    return {"runs": [evaluation.run_response(row) for row in rows]}


@router.post("/runs", status_code=201)
def create_run(
    body: EvaluationRunCreate,
    uid: int = Depends(user_id),
    evaluation: EvaluationService = Depends(service),
) -> dict[str, Any]:
    try:
        return evaluation.create_run(uid, body)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except EvaluationConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/runs/{run_id}")
def get_run(run_id: str, uid: int = Depends(user_id), evaluation: EvaluationService = Depends(service)) -> dict[str, Any]:
    row = evaluation.repository.get_run(uid, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run 不存在或无权限访问")
    return evaluation.run_response(row, include_results=True)


@router.put("/results/{result_id}/review")
def review_result(
    result_id: str,
    body: EvaluationReviewUpdate,
    uid: int = Depends(user_id),
    evaluation: EvaluationService = Depends(service),
) -> dict[str, Any]:
    try:
        return evaluation.update_review(uid, result_id, body)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
