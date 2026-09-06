from __future__ import annotations

import json

from sqlalchemy import select

from choice_agent.db_models import TraceRecord
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.repositories.profile_repository import ProfileRepository
from choice_agent.schemas import DecisionCommandRequest, GenericDecisionRequest, UserProfile


def save_profile(db, user_id=1):
    ProfileRepository(db).save(
        user_id,
        UserProfile(
            budget_habit="预算偏保守",
            preferred_cities=["上海", "杭州"],
            diet_preferences=["清淡"],
            notes="更看重续航",
        ),
    )


def test_profile_injection_applies_domain_soft_preference(database):
    with database.session_factory() as db:
        save_profile(db)
        result = GenericDecisionOrchestrator(db).create(
            1, GenericDecisionRequest(message="买电脑", domain="shopping")
        )

        fields = result.decision_state.domain_state["conversationFields"]
        assert fields["priority"]["source"] == "user_profile"
        assert fields["priority"]["confirmed"] is False
        assert result.decision_state.domain_state["profileSuggestions"][0]["source"] == "user_profile"
        assert any(item.source == "user_profile" for item in result.decision_state.assumptions)
        assert next(c.weight for c in result.decision_state.criteria if c.key == "battery") == 2.0
        assert not any(c.kind.value == "hard" and c.source == "user_profile" for c in result.decision_state.constraints)


def test_profile_injection_filters_by_domain(database):
    with database.session_factory() as db:
        save_profile(db)
        result = GenericDecisionOrchestrator(db).create(
            1, GenericDecisionRequest(message="买电脑", domain="shopping")
        )

        payload = json.dumps(
            result.decision_state.domain_state["profileSuggestions"], ensure_ascii=False
        )
        assert "清淡" not in payload
        assert "上海" not in payload
        assert "杭州" not in payload


def test_current_user_input_overrides_profile_preference(database):
    with database.session_factory() as db:
        save_profile(db)
        result = GenericDecisionOrchestrator(db).create(
            1, GenericDecisionRequest(message="买电脑，更看重性能", domain="shopping")
        )

        fields = result.decision_state.domain_state["conversationFields"]
        assert fields["priority"]["value"] == "性能"
        assert fields["priority"]["source"] == "conversation"
        assert next(c.weight for c in result.decision_state.criteria if c.key == "performance") == 2.2
        assert next(c.weight for c in result.decision_state.criteria if c.key == "battery") == 1.0


def test_empty_profile_preserves_existing_flow(database):
    with database.session_factory() as db:
        result = GenericDecisionOrchestrator(db).create(
            1,
            GenericDecisionRequest(
                message="周末从上海出发两天一夜，不想太累，人少一点",
                domain="travel",
            ),
        )

        assert result.decision_state.domain == "travel"
        assert result.decision_state.candidates
        assert "profileSuggestions" not in result.decision_state.domain_state


def test_profile_trace_and_current_decision_changes_do_not_update_long_term_profile(database):
    with database.session_factory() as db:
        save_profile(db)
        service = GenericDecisionOrchestrator(db)
        result = service.create(1, GenericDecisionRequest(message="买电脑", domain="shopping"))
        service.command(
            1,
            result.decision_state.decision_id,
            DecisionCommandRequest(
                command_id="ignore-profile",
                type="update_fields",
                expected_revision=result.decision_state.revision,
                payload={"fields": {"priority": None}},
            ),
        )

        profile = ProfileRepository(db).get(1)
        assert profile.notes == "更看重续航"
        trace = db.scalar(select(TraceRecord).where(TraceRecord.trace_id == result.trace_id))
        assert trace is not None
        assert "profileSuggestions" in trace.trace_json["initialSnapshot"]["domainState"]
        assert any(node["stage"] == "User Profile" for node in trace.trace_json["timeline"])


def test_diet_profile_is_soft_and_current_input_replaces_it(database):
    with database.session_factory() as db:
        save_profile(db)
        result = GenericDecisionOrchestrator(db).create(
            1, GenericDecisionRequest(message="晚餐吃什么", domain="diet")
        )
        state = result.decision_state.domain_state["dietFieldState"]["taste"]
        assert state["source"] == "user_profile"
        assert state["confirmed"] is False
        assert any(c.key == "taste" and c.kind.value == "soft" and c.source == "user_profile" for c in result.decision_state.constraints)
        assert not any(c.kind.value == "hard" and c.source == "user_profile" for c in result.decision_state.constraints)

        overridden = GenericDecisionOrchestrator(db).create(
            1, GenericDecisionRequest(message="晚餐想吃咸鲜", domain="diet")
        )
        assert overridden.decision_state.domain_state["slots"]["taste"] == ["咸鲜"]
        assert overridden.decision_state.domain_state["dietFieldState"]["taste"]["source"] == "conversation"