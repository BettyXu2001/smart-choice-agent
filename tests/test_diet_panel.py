import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from choice_agent.api.routes import diet_command, diet_state
from choice_agent.config import Settings
from choice_agent.db_models import FeedbackRecord, MessageRecord, TraceRecord
from choice_agent.decision.state_machine import DecisionRevisionError
from choice_agent.orchestration.diet import DietOrchestrator
from choice_agent.providers.model import DisabledProvider
from choice_agent.repositories.decision_repository import DecisionRepository
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import (
    ChatRequest, DietPanelCommand, FeedbackRequest, MealRequest, SourceMode,
)


def setup_chat(db, message="晚餐想吃清淡一点"):
    service = DietOrchestrator(db, Settings(), DisabledProvider())
    response = service.chat(1, ChatRequest(message=message))
    return service, response


def command(service, response, fields, identifier="edit-1", type="update_fields"):
    return service.command(1, response.session_id, DietPanelCommand(
        command_id=identifier, expected_revision=response.decision_state.revision,
        type=type, payload={"fields": fields}))


def send_feedback(service, response, action, item_id=None, identifier=None):
    selected = item_id if item_id is not None else response.display_blocks[0].id
    return service.feedback(1, FeedbackRequest(
        session_id=response.session_id,
        item_id=selected,
        action=action,
        request_id=identifier or f"{action.lower()}-1",
        expected_revision=response.decision_state.revision,
        rating=2 if action == "DISLIKE" else 5,
    ))


def test_feedback_like_records_preference_and_agent_confirmation(database):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        liked_id = first.display_blocks[0].id
        result = send_feedback(service, first, "LIKE")

        assert "已记录这条偏好" in result.speech_text
        assert result.decision_state.recommendation == first.decision_state.recommendation
        assert result.decision_state.domain_state["feedbackRound"]["status"] == "active"
        assert str(liked_id) in result.decision_state.domain_state["feedbackRound"]["likedCandidateIds"]
        row = db.scalar(select(FeedbackRecord))
        assert row.action == "LIKE"
        assert row.item_id == liked_id
        trace = db.scalar(select(TraceRecord).where(TraceRecord.trace_id == result.trace_id))
        assert trace.trace_json["metadata"]["feedbackType"] == "LIKE"
        node = next(item for item in trace.trace_json["timeline"] if item["stage"] == "Feedback")
        assert node["input"]["originalRecommendation"]["primaryCandidateId"]
        assert node["output"]["newRecommendation"]["primaryCandidateId"]


def test_feedback_adopt_records_outcome_and_ends_round(database):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        adopted = first.display_blocks[0]
        result = send_feedback(service, first, "ADOPT")

        assert f"已采纳「{adopted.name}」" in result.speech_text
        assert result.decision_state.outcome.candidate_id == str(adopted.id)
        assert result.decision_state.outcome.label == adopted.name
        assert result.decision_state.domain_state["feedbackRound"]["status"] == "adopted"
        with pytest.raises(ValueError, match="已结束"):
            service.feedback(1, FeedbackRequest(
                session_id=first.session_id,
                item_id=adopted.id,
                action="LIKE",
                request_id="after-adopt",
                expected_revision=result.decision_state.revision,
            ))


def test_feedback_dislike_excludes_only_selected_and_recomputes(database):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        disliked = first.display_blocks[0]
        original_ids = [item.id for item in first.display_blocks]
        original_slots = first.decision_state.domain_state["slots"]
        original_constraints = first.decision_state.constraints
        result = send_feedback(service, first, "DISLIKE")
        result_ids = [item.id for item in result.display_blocks]

        assert result.speech_text.startswith("这款不太合适，我帮你换一个。")
        assert disliked.id not in result_ids
        assert str(disliked.id) in result.decision_state.excluded_candidates
        assert result.decision_state.domain_state["slots"] == original_slots
        assert result.decision_state.constraints == original_constraints
        assert not set(result_ids) & {disliked.id}
        assert any(item_id in result_ids for item_id in original_ids[1:])
        trace = db.scalar(select(TraceRecord).where(TraceRecord.trace_id == result.trace_id))
        feedback_index = next(i for i, item in enumerate(trace.trace_json["timeline"]) if item["stage"] == "Feedback")
        filter_index = next(i for i, item in enumerate(trace.trace_json["timeline"]) if item["stage"] == "Hard Filter")
        assert feedback_index < filter_index
        node = trace.trace_json["timeline"][feedback_index]
        assert node["output"]["feedbackType"] == "DISLIKE"
        assert node["output"]["originalRecommendation"]["primaryCandidateId"] == str(disliked.id)
        assert node["output"]["newRecommendation"]["primaryCandidateId"] != str(disliked.id)
        hard_filter = trace.trace_json["timeline"][filter_index]
        assert any(item["reasonCode"] == "user_excluded" for item in hard_filter["output"]["eliminated"])


def test_feedback_is_idempotent_and_rejects_stale_or_non_current_candidate(database):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        request = FeedbackRequest(
            session_id=first.session_id,
            item_id=first.display_blocks[0].id,
            action="LIKE",
            request_id="feedback-once",
            expected_revision=first.decision_state.revision,
        )
        result = service.feedback(1, request)
        replay = service.feedback(1, request)
        assert replay.decision_state.revision == result.decision_state.revision
        assert db.scalar(select(func.count()).select_from(FeedbackRecord)) == 1
        with pytest.raises(ValueError, match="当前推荐候选"):
            service.feedback(1, request.model_copy(update={
                "request_id": "not-current",
                "item_id": 999999,
                "expected_revision": result.decision_state.revision,
            }))
        with pytest.raises(DecisionRevisionError):
            service.feedback(1, request.model_copy(update={"request_id": "stale"}))


def test_feedback_failure_rolls_back_record_message_and_decision(database, monkeypatch):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        original_save = service.decisions.save

        def fail_after_save(decision):
            original_save(decision)
            raise RuntimeError("simulated feedback persistence failure")

        monkeypatch.setattr(service.decisions, "save", fail_after_save)
        with pytest.raises(RuntimeError, match="simulated feedback"):
            send_feedback(service, first, "LIKE")
        restored = service.state(1, first.session_id)["decisionState"]
        assert restored["revision"] == first.decision_state.revision
        assert db.scalar(select(func.count()).select_from(FeedbackRecord)) == 0
        assert db.scalar(select(func.count()).select_from(MessageRecord)) == 2
        assert db.scalar(select(TraceRecord).where(TraceRecord.status == "FAILED"))


def test_feedback_dislike_keeps_exclusion_when_no_alternative_exists(database):
    with database.session_factory() as db:
        repository = DietRepository(db)
        for row in repository.list_meals(SourceMode.PERSONAL, 1):
            db.delete(row)
        db.commit()
        only = repository.create_meal(1, MealRequest(
            name="唯一清淡晚餐",
            meal_time=["晚餐"],
            taste=["清淡"],
        ))
        service = DietOrchestrator(db, Settings(), DisabledProvider())
        first = service.chat(1, ChatRequest(
            message="晚餐想吃清淡一点",
            source_mode=SourceMode.PERSONAL,
        ))
        assert [item.id for item in first.display_blocks] == [only.id]

        result = send_feedback(service, first, "DISLIKE")
        assert result.display_blocks == []
        assert str(only.id) in result.decision_state.excluded_candidates
        assert "暂时没有新的合适结果" in result.speech_text
        assert result.decision_state.domain_state["slots"] == first.decision_state.domain_state["slots"]


def test_feedback_dislike_recomputes_meal_plan_without_selected_candidate(database):
    with database.session_factory() as db:
        service, first = setup_chat(db, "帮我规划三餐")
        disliked = first.display_blocks[0]
        original_slots = first.decision_state.domain_state["slots"]

        result = send_feedback(service, first, "DISLIKE")
        planned_ids = [
            item.candidate_id for item in result.decision_state.composition.items
            if item.candidate_id is not None
        ]
        assert str(disliked.id) not in planned_ids
        assert result.decision_state.domain_state["slots"] == original_slots


def test_feedback_rejects_cross_user_session(database):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        with pytest.raises(KeyError, match="无权访问"):
            service.feedback(2, FeedbackRequest(
                session_id=first.session_id,
                item_id=first.display_blocks[0].id,
                action="LIKE",
                request_id="other-user",
                expected_revision=first.decision_state.revision,
            ))


def test_replace_clear_and_follow_up_preserve_user_state(database):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        edited = command(service, first, {"mealTime": ["午餐"], "taste": [], "healthGoal": []})
        assert edited.decision_state.domain_state["slots"]["mealTime"] == ["午餐"]
        assert edited.decision_state.domain_state["slots"]["taste"] == []
        assert edited.response_type == "CLARIFY"
        assert edited.decision_state.recommendation is None
        assert edited.display_blocks == []
        follow = service.chat(1, ChatRequest(session_id=first.session_id, message="我想要方便一点",
                                             expected_revision=edited.decision_state.revision))
        assert follow.decision_state.domain_state["slots"]["taste"] == []
        assert not any(c.key == "taste" for c in follow.decision_state.constraints)
        assert follow.decision_state.domain_state["dietFieldState"]["taste"]["cleared"]
        corrected = service.chat(1, ChatRequest(session_id=first.session_id, message="餐次改成早餐，口味改成咸鲜",
                                                expected_revision=follow.decision_state.revision))
        assert corrected.decision_state.domain_state["slots"]["mealTime"] == ["早餐"]
        assert corrected.decision_state.domain_state["slots"]["taste"] == ["咸鲜"]


def test_text_clear_and_deny_are_not_positive_preferences(database):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        second = service.chat(1, ChatRequest(session_id=first.session_id, message="口味不限"))
        assert second.decision_state.domain_state["slots"]["taste"] == []
        third = service.chat(1, ChatRequest(session_id=first.session_id, message="不要清淡"))
        assert "清淡" not in third.decision_state.domain_state["slots"]["taste"]
        assert "清淡" in next(c.values for c in third.decision_state.constraints if c.key == "diet_exclusion")


def test_receipt_idempotency_recovery_and_conflict(database):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        body = DietPanelCommand(command_id="once", expected_revision=1, type="update_fields",
                                payload={"fields": {"mealTime": ["午餐"]}})
        result = service.command(1, first.session_id, body)
        retry = service.command(1, first.session_id, body)
        assert retry.decision_state.revision == result.decision_state.revision == 2
        assert db.scalar(select(func.count()).select_from(MessageRecord)) == 4
        state = service.state(1, first.session_id)["decisionState"]
        assert state["revision"] == 2
        assert len(state["messages"]) == 4
        assert len(state["domainState"]["dietTurns"]) == 2
        assert "dietReceipts" not in state["domainState"]
        with pytest.raises(ValueError, match="不同操作"):
            service.command(1, first.session_id, body.model_copy(update={"payload": {"fields": {"taste": []}}}))
        with pytest.raises(DecisionRevisionError):
            command(service, first, {"taste": []}, identifier="stale")


def test_chat_retry_does_not_append_messages(database):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        request = ChatRequest(session_id=first.session_id, request_id="chat-once", message="换一批", expected_revision=1)
        second = service.chat(1, request)
        replay = service.chat(1, request)
        assert second.decision_state.revision == replay.decision_state.revision == 2
        assert db.scalar(select(func.count()).select_from(MessageRecord)) == 4


def test_panel_failure_rolls_back_all_business_writes(database, monkeypatch):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        original_save = service.decisions.save
        def fail_after_save(decision):
            original_save(decision)
            raise RuntimeError("simulated persistence failure")
        monkeypatch.setattr(service.decisions, "save", fail_after_save)
        with pytest.raises(RuntimeError, match="simulated"):
            command(service, first, {"mealTime": ["午餐"]})
        restored = service.state(1, first.session_id)
        assert restored["decisionState"]["revision"] == 1
        assert restored["decisionState"]["domainState"]["slots"]["mealTime"] == ["晚餐"]
        assert db.scalar(select(func.count()).select_from(MessageRecord)) == 2
        assert db.scalar(select(TraceRecord).where(TraceRecord.status == "FAILED"))


def test_api_owner_revision_and_validation(database):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        body = DietPanelCommand(command_id="owner", expected_revision=1, type="update_fields", payload={"fields": {"taste": []}})
        for call in [lambda: diet_state(first.session_id, uid=2, db=db),
                     lambda: diet_command(first.session_id, body, uid=2, db=db)]:
            with pytest.raises(HTTPException) as error:
                call()
            assert error.value.status_code == 404
        bad = body.model_copy(update={"payload": {"fields": {"ownerUserId": ["2"]}}})
        with pytest.raises(HTTPException) as error:
            diet_command(first.session_id, bad, uid=1, db=db, settings=Settings(), provider=DisabledProvider())
        assert error.value.status_code == 400
        assert service.state(1, first.session_id)["decisionState"]["revision"] == 1


def test_plan_and_risk_survive_panel_edit(database):
    with database.session_factory() as db:
        service, first = setup_chat(db, "帮我规划三餐")
        edited = command(service, first, {"healthGoal": ["清淡"]})
        assert edited.decision_state.composition
        assert len(edited.decision_state.composition.items) == 3
        risk = service.chat(1, ChatRequest(session_id=first.session_id, message="糖尿病怎么吃能治好"))
        guarded = command(service, risk, {"taste": []}, identifier="risk-edit")
        assert guarded.decision_state.risk_flags
        assert guarded.decision_state.candidates == []
        assert guarded.decision_state.composition is None
        assert guarded.display_blocks == []


class GuessingProvider:
    enabled = True
    def complete_json(self, system, prompt, model):
        return {"intent": "MEAL_RECOMMENDATION", "confidence": .8,
                "slots": {"taste": ["清淡"]}}


def test_inferred_fields_confirmation_and_clear_protection(database):
    with database.session_factory() as db:
        service = DietOrchestrator(db, Settings(), GuessingProvider())
        first = service.chat(1, ChatRequest(message="晚餐推荐"))
        meta = first.decision_state.domain_state["dietFieldState"]
        assert meta["mealTime"]["confirmed"]
        assert meta["taste"]["source"] == "model"
        assert not meta["taste"]["confirmed"]
        confirmed = command(service, first, ["taste"], type="confirm_fields")
        assert confirmed.decision_state.domain_state["dietFieldState"]["taste"]["confirmed"]
        cleared = command(service, confirmed, {"taste": []}, identifier="clear")
        continued = service.chat(1, ChatRequest(session_id=first.session_id, message="推荐一下"))
        assert continued.decision_state.domain_state["slots"]["taste"] == []


def test_source_change_and_invalid_field_value(database):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        changed = service.command(1, first.session_id, DietPanelCommand(command_id="source", expected_revision=1,
            type="set_source", payload={"sourceMode": "PERSONAL"}))
        assert changed.decision_state.context["sourceMode"] == "PERSONAL"
        assert service.state(1, first.session_id)["sourceMode"] == "PERSONAL"
        with pytest.raises(ValueError, match="不支持"):
            command(service, changed, {"exclusions": ["不存在的食材"]})


def test_legacy_source_is_not_claimed_as_confirmed(database):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        stored = DecisionRepository(db).get(first.decision_state.decision_id)
        stored.domain_state.pop("dietFieldState")
        stored.revision += 1
        DecisionRepository(db).save(stored)
        state = service.state(1, first.session_id)["decisionState"]
        assert state["domainState"]["dietFieldState"]["taste"]["source"] == "legacy"
        assert not state["domainState"]["dietFieldState"]["taste"]["confirmed"]


def test_explicit_old_to_new_value_does_not_keep_old_value(database):
    with database.session_factory() as db:
        service, first = setup_chat(db)
        updated = service.chat(1, ChatRequest(session_id=first.session_id, message="晚餐改成午餐"))
        assert updated.decision_state.domain_state["slots"]["mealTime"] == ["午餐"]


def test_model_conflict_with_confirmed_value_asks_instead_of_overwriting(database):
    with database.session_factory() as db:
        service, first = setup_chat(db, "晚餐想吃咸鲜的")
        service.provider = GuessingProvider()
        updated = service.chat(1, ChatRequest(session_id=first.session_id, message="还有什么推荐"))
        assert updated.decision_state.domain_state["slots"]["taste"] == ["咸鲜"]
        assert updated.response_type == "CLARIFY"
        assert "仍按" in updated.clarify_question
