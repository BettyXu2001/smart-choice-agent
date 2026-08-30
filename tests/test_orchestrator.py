from datetime import datetime, timedelta

import pytest

from choice_agent.api.routes import evaluate
from choice_agent.config import Settings
from choice_agent.orchestration.diet import DietOrchestrator
from choice_agent.providers.model import DisabledProvider
from choice_agent.db_models import TraceRecord
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import (
    ChatRequest, ClarifyAction, EvaluationRequest, FeedbackRequest, Intent, MealRequest,
    SlotBundle, SourceMode, TraceLabelRequest,
)


def orchestrator(db):
    return DietOrchestrator(db, Settings(), DisabledProvider())


def test_recommendation_persists_decision_agents_and_trace(database):
    with database.session_factory() as db:
        response = orchestrator(db).chat(
            1,
            ChatRequest(message="晚餐想吃清淡一点", source_mode=SourceMode.PUBLIC),
        )
        assert response.response_type == "ANSWER"
        assert response.display_blocks
        names = [run.agent_name for run in response.decision_state.agent_runs]
        assert names == [
            "IntentAgent", "UnderstandingAgent", "ClarificationAgent",
            "CandidateAgent", "CriticAgent", "ExplanationAgent", "RiskAgent",
        ]
        trace = DietRepository(db).trace(1, response.trace_id)
        assert trace is not None
        assert trace.event_count >= 8


def test_clarification_and_follow_up_reuse_slots(database):
    with database.session_factory() as db:
        first = orchestrator(db).chat(1, ChatRequest(message="推荐吃什么"))
        assert first.response_type == "CLARIFY"
        assert "mealTime" in first.missing_slots
        second = orchestrator(db).chat(
            1, ChatRequest(session_id=first.session_id, message="晚餐，想清淡点")
        )
        assert second.response_type == "ANSWER"


def test_adjust_excludes_previous_recommendations(database):
    with database.session_factory() as db:
        first = orchestrator(db).chat(
            1, ChatRequest(message="晚餐想吃清淡一点", source_mode=SourceMode.PUBLIC)
        )
        old_ids = {meal.id for meal in first.display_blocks}
        second = orchestrator(db).chat(
            1,
            ChatRequest(
                session_id=first.session_id,
                message="换一个",
                source_mode=SourceMode.PUBLIC,
            ),
        )
        assert old_ids.isdisjoint({meal.id for meal in second.display_blocks})


def test_plan_and_health_guard(database):
    with database.session_factory() as db:
        plan = orchestrator(db).chat(1, ChatRequest(message="帮我规划三餐，想清淡一点"))
        assert plan.response_type == "ANSWER"
        assert plan.decision_state.intent.value == "MEAL_PLAN"
        risk = orchestrator(db).chat(1, ChatRequest(message="糖尿病吃什么能治好"))
        assert risk.display_blocks == []
        assert risk.decision_state.risk_flags
        assert "咨询医生" in risk.speech_text


def test_personal_meal_crud_and_empty_source(database):
    with database.session_factory() as db:
        repository = DietRepository(db)
        assert repository.list_meals(SourceMode.PERSONAL, 99) == []
        created = repository.create_meal(
            99,
            MealRequest(name="测试餐", meal_time=["晚餐"], taste=["清淡"]),
        )
        assert created.id
        updated = repository.update_meal(
            99,
            created.id,
            MealRequest(name="测试餐更新", meal_time=["午餐"], taste=["咸鲜"]),
        )
        assert updated.name == "测试餐更新"
        assert repository.delete_meal(99, created.id)


def test_evaluation_report_aggregates_nested_metrics(database):
    with database.session_factory() as db:
        response = orchestrator(db).chat(1, ChatRequest(message="晚餐想吃清淡一点"))
        repository = DietRepository(db)
        repository.label_trace(
            1,
            response.trace_id,
            TraceLabelRequest(
                expected_intent=Intent.MEAL_RECOMMENDATION,
                expected_slots=SlotBundle(meal_time=["晚餐"]),
                expected_clarify_action=ClarifyAction.READY,
            ),
        )
        repository.save_feedback(
            1,
            FeedbackRequest(
                session_id=response.session_id,
                item_id=response.display_blocks[0].id,
                action="ADOPT",
                rating=5,
            ),
        )
        now = datetime.now()
        report = evaluate(
            EvaluationRequest(
                start_at=now - timedelta(minutes=5),
                end_at=now + timedelta(minutes=5),
            ),
            uid=1,
            db=db,
            settings=Settings(),
            provider=DisabledProvider(),
        )
        result = report["traceResults"][0]
        assert report["totalTraces"] == 1
        assert report["labeledTraces"] == 1
        assert report["metricAverages"]["intentAccuracy"] == 1.0
        assert report["metricAverages"]["slotAccuracy"] == 1.0
        assert report["metricAverages"]["clarifyNecessityAccuracy"] == 1.0
        assert result["userFeedbackScore"] == 1.0
        assert result["detail"]["feedbackCount"] == 1
        assert result["detail"]["predictedSlots"]["mealTime"] == ["晚餐"]


def test_evaluation_report_scores_failed_trace_as_fallback(database):
    with database.session_factory() as db:
        now = datetime.now()
        db.add(
            TraceRecord(
                trace_id="failed-trace",
                session_id="failed-session",
                user_id=1,
                status="FAILED",
                event_count=1,
                duration_ms=42,
                error_message="boom",
                trace_json={
                    "traceId": "failed-trace",
                    "sessionId": "failed-session",
                    "userId": 1,
                    "status": "FAILED",
                    "durationMs": 42,
                    "events": [
                        {
                            "eventType": "REQUEST_FAILED",
                            "phase": "ERROR",
                            "outputPayload": "boom",
                        }
                    ],
                },
                created_at=now,
            )
        )
        db.commit()
        report = evaluate(
            EvaluationRequest(
                start_at=now - timedelta(minutes=5),
                end_at=now + timedelta(minutes=5),
            ),
            uid=1,
            db=db,
            settings=Settings(),
            provider=DisabledProvider(),
        )
        metrics = report["traceResults"][0]["metrics"]
        assert metrics["fallbackRate"] == 1.0
        assert metrics["fallbackScore"] == 0.0
        assert metrics["safetyCompliance"] == 0.0


def test_chat_expected_revision_rejects_stale_session(database):
    with database.session_factory() as db:
        first = orchestrator(db).chat(
            1,
            ChatRequest(message="晚餐想吃清淡一点", source_mode=SourceMode.PUBLIC),
        )
        assert first.decision_state.revision == 1
        with pytest.raises(ValueError, match="Decision revision mismatch"):
            orchestrator(db).chat(
                1,
                ChatRequest(
                    session_id=first.session_id,
                    message="换一个",
                    source_mode=SourceMode.PUBLIC,
                    expected_revision=0,
                ),
            )


def test_chat_expected_revision_accepts_current_session_revision(database):
    with database.session_factory() as db:
        first = orchestrator(db).chat(
            1,
            ChatRequest(message="晚餐想吃清淡一点", source_mode=SourceMode.PUBLIC),
        )
        second = orchestrator(db).chat(
            1,
            ChatRequest(
                session_id=first.session_id,
                message="换一个",
                source_mode=SourceMode.PUBLIC,
                expected_revision=first.decision_state.revision,
            ),
        )
        assert second.response_type == "ANSWER"
        assert second.decision_state.revision == 2

def test_diet_recommendation_records_default_selection_insights(database):
    with database.session_factory() as db:
        response = orchestrator(db).chat(
            1,
            ChatRequest(message="晚餐想吃清淡一点", source_mode=SourceMode.PUBLIC),
        )
        selection = response.decision_state.domain_state["selection"]
        assert selection["strategy"] == "ranked"
        assert selection["candidateCount"] >= len(response.display_blocks)
        assert selection["eligibleCount"] == selection["candidateCount"]
        assert "按匹配度排序" in selection["tags"]


def test_diet_recommendation_can_avoid_recent_candidates_with_context(database):
    with database.session_factory() as db:
        first = orchestrator(db).chat(
            1,
            ChatRequest(message="晚餐想吃清淡一点", source_mode=SourceMode.PUBLIC),
        )
        first_ids = {meal.id for meal in first.display_blocks}
        second = orchestrator(db).chat(
            1,
            ChatRequest(
                session_id=first.session_id,
                message="晚餐想吃清淡一点",
                source_mode=SourceMode.PUBLIC,
                context={"selectionStrategy": "least_recent", "avoidRecentCount": 3},
            ),
        )
        second_ids = {meal.id for meal in second.display_blocks}
        selection = second.decision_state.domain_state["selection"]
        assert selection["strategy"] == "least_recent"
        assert selection["recentExcludedCount"] == min(3, selection["candidateCount"])
        assert first_ids.isdisjoint(second_ids)
