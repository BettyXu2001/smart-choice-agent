from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session


from choice_agent.api.decision_stream import stream_command_decision, stream_create_decision, stream_message_decision
from choice_agent.agents.base import AgentContext
from choice_agent.agents.diet import EvaluationAgent
from choice_agent.config import Settings
from choice_agent.db_models import MealRecord, TraceRecord
from choice_agent.decision.state_machine import DecisionRevisionError
from choice_agent.orchestration.diet import DietOrchestrator
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.providers.model import ModelProvider, OpenAICompatibleProvider
from choice_agent.providers.search import SearchProviderError
from choice_agent.repositories.decision_repository import DecisionRepository
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import (
    ChatRequest, ChatResponse, DietPanelCommand, DecisionCommandRequest, DecisionState, EvaluationRequest, FeedbackRequest,
    GenericDecisionMessageRequest, GenericDecisionRequest, GenericDecisionResponse, SearchCapabilitiesResponse,
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
        search_provider=base_settings.search_provider,
        search_api_key=base_settings.search_api_key,
        search_base_url=base_settings.search_base_url,
        search_model=base_settings.search_model,
        search_timeout_seconds=base_settings.search_timeout_seconds,
        search_max_queries=base_settings.search_max_queries,
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

@router.get("/api/v1/search/capabilities", response_model=SearchCapabilitiesResponse)
def search_capabilities(settings: Settings = Depends(get_settings)) -> SearchCapabilitiesResponse:
    default_mode = settings.search_provider
    if default_mode == "openai":
        default_mode = "web"
    if default_mode not in {"fixture", "web", "auto"}:
        default_mode = "fixture"
    return SearchCapabilitiesResponse(
        supported_domains=["shopping", "travel"],
        web_search_configured=bool(settings.search_api_key.strip()),
        default_search_mode=default_mode,
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


@router.post("/api/v1/decisions/stream")
def create_decision_stream(
    request: Request,
    body: GenericDecisionRequest,
    uid: int = Depends(user_id),
    settings: Settings = Depends(get_settings),
    provider: ModelProvider = Depends(get_provider),
    runtime_model: tuple[Settings, ModelProvider] | None = Depends(get_runtime_model),
) -> StreamingResponse:
    active_settings, active_provider = runtime_model if isinstance(runtime_model, tuple) else (settings, provider)
    return stream_create_decision(request, uid, body, active_settings, active_provider)


@router.post("/api/v1/decisions/{decision_id}/messages/stream")
def message_decision_stream(
    request: Request,
    decision_id: str,
    body: GenericDecisionMessageRequest,
    uid: int = Depends(user_id),
    settings: Settings = Depends(get_settings),
    provider: ModelProvider = Depends(get_provider),
    runtime_model: tuple[Settings, ModelProvider] | None = Depends(get_runtime_model),
) -> StreamingResponse:
    active_settings, active_provider = runtime_model if isinstance(runtime_model, tuple) else (settings, provider)
    return stream_message_decision(request, uid, decision_id, body, active_settings, active_provider)


@router.post("/api/v1/decisions/{decision_id}/commands/stream")
def command_decision_stream(
    request: Request,
    decision_id: str,
    body: DecisionCommandRequest,
    uid: int = Depends(user_id),
    settings: Settings = Depends(get_settings),
    provider: ModelProvider = Depends(get_provider),
    runtime_model: tuple[Settings, ModelProvider] | None = Depends(get_runtime_model),
) -> StreamingResponse:
    active_settings, active_provider = runtime_model if isinstance(runtime_model, tuple) else (settings, provider)
    return stream_command_decision(request, uid, decision_id, body, active_settings, active_provider)
@router.post("/api/v1/decisions", response_model=GenericDecisionResponse)
def create_decision(
    body: GenericDecisionRequest,
    uid: int = Depends(user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    provider: ModelProvider = Depends(get_provider),
    runtime_model: tuple[Settings, ModelProvider] | None = Depends(get_runtime_model),
) -> GenericDecisionResponse:
    active_settings, active_provider = runtime_model if isinstance(runtime_model, tuple) else (settings if isinstance(settings, Settings) else Settings(), provider if hasattr(provider, "enabled") else None)
    try:
        return GenericDecisionOrchestrator(db, settings=active_settings, provider=active_provider).create(uid, body)
    except SearchProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/api/v1/decisions/{decision_id}/messages", response_model=GenericDecisionResponse)
def message_decision(
    decision_id: str,
    body: GenericDecisionMessageRequest,
    uid: int = Depends(user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    provider: ModelProvider = Depends(get_provider),
    runtime_model: tuple[Settings, ModelProvider] | None = Depends(get_runtime_model),
) -> GenericDecisionResponse:
    active_settings, active_provider = runtime_model if isinstance(runtime_model, tuple) else (settings if isinstance(settings, Settings) else Settings(), provider if hasattr(provider, "enabled") else None)
    try:
        return GenericDecisionOrchestrator(db, settings=active_settings, provider=active_provider).message(uid, decision_id, body)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DecisionRevisionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SearchProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

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
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DecisionRevisionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SearchProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/api/v1/diet/sessions/{session_id}/state")
def diet_state(session_id: str, uid: int = Depends(user_id), db: Session = Depends(get_db),
               settings: Settings = Depends(get_settings), provider: ModelProvider = Depends(get_provider)):
    try:
        return DietOrchestrator(db, settings, provider).state(uid, session_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/api/v1/diet/sessions/{session_id}/commands", response_model=ChatResponse)
def diet_command(session_id: str, body: DietPanelCommand, uid: int = Depends(user_id),
                 db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
                 provider: ModelProvider = Depends(get_provider),
                 runtime_model: tuple[Settings, ModelProvider] | None = Depends(get_runtime_model)):
    active_settings, active_provider = runtime_model if isinstance(runtime_model, tuple) else (settings if isinstance(settings, Settings) else Settings(), provider if hasattr(provider, "enabled") else None)
    try:
        return DietOrchestrator(db, active_settings, active_provider).command(uid, session_id, body)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DecisionRevisionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
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


def _feedback_score(feedbacks: list[Any]) -> float | None:
    scores: list[float] = []
    for feedback in feedbacks:
        if feedback.rating is not None:
            scores.append(feedback.rating / 5)
        elif feedback.action == "ADOPT":
            scores.append(1.0)
        elif feedback.action == "LIKE":
            scores.append(0.8)
        elif feedback.action == "DISLIKE":
            scores.append(0.0)
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


def _combined_score(
    rule_score: float,
    llm_judge: dict[str, Any] | None,
    user_feedback_score: float | None,
) -> float:
    judge_score = None
    if llm_judge and isinstance(llm_judge.get("score"), (int, float)):
        judge_score = float(llm_judge["score"])
    if judge_score is not None and user_feedback_score is not None:
        return round(0.6 * rule_score + 0.1 * judge_score + 0.3 * user_feedback_score, 4)
    if judge_score is not None:
        return round(0.8 * rule_score + 0.2 * judge_score, 4)
    if user_feedback_score is not None:
        return round(0.7 * rule_score + 0.3 * user_feedback_score, 4)
    return rule_score


def _metric_averages(results: list[dict[str, Any]]) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for result in results:
        for key, value in result["metrics"].items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            buckets.setdefault(key, []).append(float(value))
    return {key: round(sum(values) / len(values), 4) for key, values in buckets.items()}


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
    repository = DietRepository(db)
    rows = repository.traces(uid, body.start_at, body.end_at, False, body.limit)
    session_ids = list(dict.fromkeys(row.session_id for row in rows))
    feedbacks_by_session: dict[str, list[Any]] = {session_id: [] for session_id in session_ids}
    for feedback in repository.feedbacks(uid, session_ids, body.start_at, body.end_at):
        feedbacks_by_session.setdefault(feedback.session_id, []).append(feedback)

    results: list[dict[str, Any]] = []
    evaluator = EvaluationAgent(active_provider, active_settings.light_model)
    for row in rows:
        feedbacks = feedbacks_by_session.get(row.session_id, [])
        context = AgentContext(
            session_id=row.session_id,
            trace_id=row.trace_id,
            user_id=uid,
            message="",
            decision=DecisionState(decision_id=row.trace_id, session_id=row.session_id),
            data={
                "trace": row.trace_json,
                "expected_intent": row.expected_intent,
                "expected_slots": row.expected_slots,
                "expected_clarify_action": row.expected_clarify_action,
                "include_llm_judge": body.include_llm_judge,
                "feedbacks": feedbacks,
            },
        )
        metrics = evaluator.execute(context)
        llm_judge = metrics.pop("llmJudge", None)
        evaluation_detail = metrics.pop("evaluationDetail", {})
        rule_score = metrics.pop("score")
        user_feedback_score = _feedback_score(feedbacks)
        combined_score = _combined_score(rule_score, llm_judge, user_feedback_score)
        results.append({
            "traceId": row.trace_id,
            "sessionId": row.session_id,
            "score": combined_score,
            "ruleScore": rule_score,
            "llmJudgeScore": llm_judge["score"] if llm_judge and isinstance(llm_judge.get("score"), (int, float)) else None,
            "userFeedbackScore": user_feedback_score,
            "metrics": metrics,
            "detail": {
                **evaluation_detail,
                "status": row.status,
                "eventCount": row.event_count,
                "llmJudgeRequested": body.include_llm_judge,
                "llmJudgeAvailable": bool(llm_judge and isinstance(llm_judge.get("score"), (int, float))),
                "llmJudge": llm_judge,
            },
        })
    labeled = [row for row in rows if row.labeled_at is not None]
    avg = (
        round(sum(result["score"] for result in results) / len(results), 4)
        if results else None
    )
    return {
        "startAt": body.start_at.isoformat(),
        "endAt": body.end_at.isoformat(),
        "totalTraces": len(rows),
        "labeledTraces": len(labeled),
        "avgScore": avg,
        "metricAverages": _metric_averages(results),
        "traceResults": results,
        "llmJudgeEnabled": body.include_llm_judge and active_provider.enabled,
    }

@router.post("/api/v1/decisions/{decision_id}/commands", response_model=GenericDecisionResponse)
def command_decision(
    decision_id: str,
    body: DecisionCommandRequest,
    uid: int = Depends(user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    provider: ModelProvider = Depends(get_provider),
    runtime_model: tuple[Settings, ModelProvider] | None = Depends(get_runtime_model),
) -> GenericDecisionResponse:
    active_settings, active_provider = runtime_model if isinstance(runtime_model, tuple) else (settings if isinstance(settings, Settings) else Settings(), provider if hasattr(provider, "enabled") else None)
    try:
        return GenericDecisionOrchestrator(db, settings=active_settings, provider=active_provider).command(uid, decision_id, body)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DecisionRevisionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SearchProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/api/v1/decisions/{decision_id}", response_model=DecisionState)
def get_decision(
    decision_id: str,
    uid: int = Depends(user_id),
    db: Session = Depends(get_db),
) -> DecisionState:
    resolved_uid = uid if isinstance(uid, int) else 1
    decision = DecisionRepository(db).get_for_user(decision_id, resolved_uid)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision 不存在或无权访问")
    from choice_agent.decision.conversation import public_decision
    return public_decision(decision)


@router.post("/api/v1/decision-domains/resolve")
def resolve_decision_domain(body: GenericDecisionRequest):
    from choice_agent.domains.registry import DomainRegistry
    try:
        return DomainRegistry().identify(body.message, body.domain)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
