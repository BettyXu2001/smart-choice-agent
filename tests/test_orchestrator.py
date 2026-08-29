from datetime import datetime, timedelta

from choice_agent.api.routes import evaluate
from choice_agent.config import Settings
from choice_agent.orchestration.diet import DietOrchestrator
from choice_agent.providers.model import DisabledProvider
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import ChatRequest, EvaluationRequest, MealRequest, SourceMode


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
        orchestrator(db).chat(1, ChatRequest(message="晚餐想吃清淡一点"))
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
        assert report["totalTraces"] == 1
        assert report["metricAverages"]["intentAccuracy"] == 1.0
