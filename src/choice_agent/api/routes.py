from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from choice_agent.agents.base import AgentContext
from choice_agent.agents.diet import EvaluationAgent
from choice_agent.config import Settings
from choice_agent.db_models import DecisionRecord, MealRecord, TraceRecord
from choice_agent.orchestration.diet import DietOrchestrator
from choice_agent.providers.model import ModelProvider, OpenAICompatibleProvider
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import (
    ChatRequest, ChatResponse, DecisionState, EvaluationRequest, FeedbackRequest,
    MealRequest, MealResponse, SlotBundle, SourceMode, TraceLabelRequest,
)


router = APIRouter()


def get_db(request: Request):
    yield from request.app.state.database.session()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_provider(request: Request) -> ModelProvider:
    return request.app.state.provider




def _truthy_header(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


def runtime_model_from_headers(
    base_settings: Settings,
    base_provider: ModelProvider,
    model_enabled: str | None,
    model_api_key: str | None,
    model_base_url: str | None,
    main_model: str | None,
    light_model: str | None,
) -> tuple[Settings, ModelProvider]:
    api_key = (model_api_key or "").strip()
    if not _truthy_header(model_enabled) or not api_key:
        return base_settings, base_provider
    runtime_settings = Settings(
        database_url=base_settings.database_url,
        model_api_key=api_key,
        model_base_url=(model_base_url or base_settings.model_base_url).strip() or base_settings.model_base_url,
        main_model=(main_model or base_settings.main_model).strip() or base_settings.main_model,
        light_model=(light_model or base_settings.light_model).strip() or base_settings.light_model,
        model_timeout_seconds=base_settings.model_timeout_seconds,
        enable_llm=True,
        debug=base_settings.debug,
    )
    return runtime_settings, OpenAICompatibleProvider(runtime_settings)


def get_runtime_model(
    request: Request,
    model_enabled: str | None = Header(default=None, alias="X-Choice-Agent-Model-Enabled"),
    model_api_key: str | None = Header(default=None, alias="X-Choice-Agent-Model-Api-Key"),
    model_base_url: str | None = Header(default=None, alias="X-Choice-Agent-Model-Base-Url"),
    main_model: str | None = Header(default=None, alias="X-Choice-Agent-Main-Model"),
    light_model: str | None = Header(default=None, alias="X-Choice-Agent-Light-Model"),
) -> tuple[Settings, ModelProvider]:
    return runtime_model_from_headers(
        request.app.state.settings,
        request.app.state.provider,
        model_enabled,
        model_api_key,
        model_base_url,
        main_model,
        light_model,
    )

def user_id(x_user_id: int = Header(default=1, alias="X-User-Id")) -> int:
    if x_user_id < 1:
        raise HTTPException(status_code=400, detail="X-User-Id 必须大于 0")
    return x_user_id


def meal_response(row: MealRecord, score: float = 0) -> MealResponse:
    return MealResponse(
        id=row.id, source_type=SourceMode(row.source_type), name=row.name,
        meal_time=row.meal_time, mood=row.mood, scene=row.scene,
        health_goal=row.health_goal, cuisine=row.cuisine, taste=row.taste,
        convenience=row.convenience, match_score=score,
    )


def trace_response(row: TraceRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "traceId": row.trace_id,
        "sessionId": row.session_id,
        "userId": row.user_id,
        "status": row.status,
        "eventCount": row.event_count,
        "durationMs": row.duration_ms,
        "errorMessage": row.error_message,
        "traceJson": row.trace_json,
        "expectedIntent": row.expected_intent,
        "expectedSlots": row.expected_slots,
        "expectedClarifyAction": row.expected_clarify_action,
        "labeledBy": row.labeled_by,
        "labeledAt": row.labeled_at.isoformat() if row.labeled_at else None,
        "labelNote": row.label_note,
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat(),
    }


@router.post("/api/v1/diet/sessions")
def create_session(
    uid: int = Depends(user_id), db: Session = Depends(get_db)
) -> dict[str, str]:
    return {"sessionId": DietRepository(db).create_session(uid).id}


@router.post("/api/v1/diet/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    uid: int = Depends(user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    provider: ModelProvider = Depends(get_provider),
    runtime_model: tuple[Settings, ModelProvider] | None = Depends(get_runtime_model),
) -> ChatResponse:
    active_settings, active_provider = (
        runtime_model if isinstance(runtime_model, tuple) else (settings, provider)
    )
    try:
        return DietOrchestrator(db, active_settings, active_provider).chat(uid, body)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/api/v1/diet/meals/personal", response_model=list[MealResponse])
def personal_meals(
    uid: int = Depends(user_id), db: Session = Depends(get_db)
) -> list[MealResponse]:
    return [meal_response(row) for row in DietRepository(db).list_meals(SourceMode.PERSONAL, uid)]


@router.post("/api/v1/diet/meals/personal", response_model=MealResponse)
def create_personal_meal(
    body: MealRequest, uid: int = Depends(user_id), db: Session = Depends(get_db)
) -> MealResponse:
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="餐食名称不能为空")
    return meal_response(DietRepository(db).create_meal(uid, body))


@router.put("/api/v1/diet/meals/personal/{meal_id}", response_model=MealResponse)
def update_personal_meal(
    meal_id: int,
    body: MealRequest,
    uid: int = Depends(user_id),
    db: Session = Depends(get_db),
) -> MealResponse:
    row = DietRepository(db).update_meal(uid, meal_id, body)
    if row is None:
        raise HTTPException(status_code=404, detail="个人餐食不存在")
    return meal_response(row)


@router.delete("/api/v1/diet/meals/personal/{meal_id}", status_code=204)
def delete_personal_meal(
    meal_id: int, uid: int = Depends(user_id), db: Session = Depends(get_db)
) -> Response:
    if not DietRepository(db).delete_meal(uid, meal_id):
        raise HTTPException(status_code=404, detail="个人餐食不存在")
    return Response(status_code=204)


@router.get("/api/v1/diet/meals/public", response_model=list[MealResponse])
def public_meals(db: Session = Depends(get_db)) -> list[MealResponse]:
    return [meal_response(row) for row in DietRepository(db).list_meals(SourceMode.PUBLIC)]


@router.get("/api/v1/diet/slot-options")
def slot_options(db: Session = Depends(get_db)) -> dict[str, list[str]]:
    return DietRepository(db).slot_options()


@router.post("/api/v1/diet/feedback", status_code=204)
def feedback(
    body: FeedbackRequest, uid: int = Depends(user_id), db: Session = Depends(get_db)
) -> Response:
    DietRepository(db).save_feedback(uid, body)
    return Response(status_code=204)


@router.get("/api/v1/diet/debug/traces/{trace_id}")
def get_trace(
    trace_id: str, uid: int = Depends(user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    row = DietRepository(db).trace(uid, trace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Trace 不存在")
    return trace_response(row)


@router.get("/api/v1/diet/debug/sessions/{session_id}/traces")
def session_traces(
    session_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    uid: int = Depends(user_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return [
        trace_response(row)
        for row in DietRepository(db).session_traces(uid, session_id, limit)
    ]


@router.get("/api/v1/diet/debug/traces")
def list_traces(
    start_at: datetime = Query(alias="startAt"),
    end_at: datetime = Query(alias="endAt"),
    only_unlabeled: bool = Query(default=False, alias="onlyUnlabeled"),
    limit: int = Query(default=200, ge=1, le=1000),
    uid: int = Depends(user_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    if start_at >= end_at:
        raise HTTPException(status_code=400, detail="Trace 查询时间范围不合法")
    return [
        trace_response(row)
        for row in DietRepository(db).traces(uid, start_at, end_at, only_unlabeled, limit)
    ]


@router.put("/api/v1/diet/debug/traces/{trace_id}/label", status_code=204)
def label_trace(
    trace_id: str,
    body: TraceLabelRequest,
    uid: int = Depends(user_id),
    db: Session = Depends(get_db),
) -> Response:
    if DietRepository(db).label_trace(uid, trace_id, body) is None:
        raise HTTPException(status_code=404, detail="Trace 不存在或无权限标注")
    return Response(status_code=204)


@router.post("/api/v1/diet/evaluations")
def evaluate(
    body: EvaluationRequest,
    uid: int = Depends(user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    provider: ModelProvider = Depends(get_provider),
    runtime_model: tuple[Settings, ModelProvider] | None = Depends(get_runtime_model),
) -> dict[str, Any]:
    active_settings, active_provider = (
        runtime_model if isinstance(runtime_model, tuple) else (settings, provider)
    )
    if body.start_at >= body.end_at:
        raise HTTPException(status_code=400, detail="评估时间范围不合法")
    rows = DietRepository(db).traces(uid, body.start_at, body.end_at, False, body.limit)
    results: list[dict[str, Any]] = []
    evaluator = EvaluationAgent(active_provider, active_settings.light_model)
    for row in rows:
        context = AgentContext(
            session_id=row.session_id,
            trace_id=row.trace_id,
            user_id=uid,
            message="",
            decision=DecisionState(decision_id=row.trace_id, session_id=row.session_id),
            data={
                "trace": row.trace_json,
                "expected_intent": row.expected_intent,
                "expected_clarify_action": row.expected_clarify_action,
                "include_llm_judge": body.include_llm_judge,
            },
        )
        metrics = evaluator.execute(context)
        llm_judge = metrics.pop("llmJudge", None)
        rule_score = metrics["score"]
        combined_score = (
            round((rule_score + llm_judge["score"]) / 2, 4)
            if llm_judge else rule_score
        )
        results.append({
            "traceId": row.trace_id,
            "sessionId": row.session_id,
            "score": combined_score,
            "ruleScore": rule_score,
            "llmJudgeScore": llm_judge["score"] if llm_judge else None,
            "userFeedbackScore": None,
            "metrics": metrics,
            "detail": {
                "status": row.status,
                "eventCount": row.event_count,
                "llmJudgeRequested": body.include_llm_judge,
                "llmJudgeAvailable": bool(llm_judge),
                "llmJudge": llm_judge,
            },
        })
    labeled = [row for row in rows if row.labeled_at is not None]
    avg = (
        round(sum(result["score"] for result in results) / len(results), 4)
        if results else None
    )
    metric_averages = {
        key: round(sum(item["metrics"][key] for item in results) / len(results), 4)
        for key in ("intentAccuracy", "clarifyAccuracy")
    } if results else {}
    return {
        "startAt": body.start_at.isoformat(),
        "endAt": body.end_at.isoformat(),
        "totalTraces": len(rows),
        "labeledTraces": len(labeled),
        "avgScore": avg,
        "metricAverages": metric_averages,
        "traceResults": results,
        "llmJudgeEnabled": body.include_llm_judge and active_provider.enabled,
    }


@router.get("/api/v1/decisions/{decision_id}", response_model=DecisionState)
def get_decision(decision_id: str, db: Session = Depends(get_db)) -> DecisionState:
    row = db.get(DecisionRecord, decision_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Decision 不存在")
    return DecisionState.model_validate(row.state_json)
