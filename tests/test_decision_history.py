from __future__ import annotations

import pytest

from choice_agent.decision.state_machine import DecisionRevisionError
from choice_agent.db_models import DecisionRecord
from choice_agent.repositories.decision_repository import DecisionRepository
from choice_agent.schemas import (
    Candidate,
    DecisionOutcome,
    DecisionState,
    Recommendation,
    RecommendationPoint,
)


def test_history_lists_only_current_user_decisions(database):
    with database.session_factory() as db:
        repository = DecisionRepository(db)
        own = DecisionState(
            decision_id="own",
            session_id="s1",
            domain="career",
            user_goal="两个 Offer 怎么选",
            owner_user_id=7,
            revision=1,
            candidates=[Candidate(candidate_id="a", name="A 公司")],
            recommendation=Recommendation(primary_candidate_id="a"),
        )
        other = DecisionState(
            decision_id="other",
            session_id="s2",
            domain="travel",
            user_goal="周末去哪玩",
            owner_user_id=8,
            revision=1,
        )
        repository.save(own)
        repository.save(other)

        rows = repository.list_for_user(7)

        assert [decision.decision_id for _, decision in rows] == ["own"]


def test_history_preserves_legacy_ownerless_user_one(database):
    with database.session_factory() as db:
        repository = DecisionRepository(db)
        legacy = DecisionState(
            decision_id="legacy",
            session_id="s1",
            domain="generic",
            user_goal="旧决策",
            revision=1,
        )
        repository.save(legacy)

        rows = repository.list_for_user(1)

        assert rows[0][1].decision_id == "legacy"
        assert rows[0][1].owner_user_id == 1


def test_repository_save_rejects_stale_outcome_revision(database):
    with database.session_factory() as db:
        repository = DecisionRepository(db)
        decision = DecisionState(
            decision_id="d1",
            session_id="s1",
            domain="shopping",
            user_goal="MacBook Air vs ThinkPad",
            owner_user_id=1,
            revision=1,
        )
        repository.save(decision)
        stale = decision.model_copy(deep=True)
        decision.outcome = DecisionOutcome(label="MacBook Air")
        decision.revision += 1
        repository.save(decision)
        stale.outcome = DecisionOutcome(label="ThinkPad")
        stale.revision += 1

        with pytest.raises(DecisionRevisionError):
            repository.save(stale)


def test_history_summary_can_be_derived_from_record(database):
    from choice_agent.api.routes import decision_history_summary

    with database.session_factory() as db:
        decision = DecisionState(
            decision_id="d1",
            session_id="s1",
            domain="shopping",
            user_goal="MacBook Air vs ThinkPad",
            owner_user_id=1,
            revision=1,
            candidates=[Candidate(candidate_id="mac", name="MacBook Air")],
            recommendation=Recommendation(
                primary_candidate_id="mac",
                reasons=[RecommendationPoint(text="更轻，续航更稳", candidate_id="mac")],
            ),
            outcome=DecisionOutcome(candidate_id="mac", label="MacBook Air"),
        )
        DecisionRepository(db).save(decision)
        row = db.get(DecisionRecord, "d1")

        summary = decision_history_summary(row, decision)

        assert summary.title == "MacBook Air vs ThinkPad"
        assert summary.current_recommendation == "MacBook Air"
        assert summary.final_choice == "MacBook Air"


def test_history_api_functions_list_detail_and_update_outcome(database):
    from fastapi import HTTPException
    from choice_agent.api.routes import (
        get_decision_history_detail,
        list_decision_history,
        save_decision_outcome,
    )
    from choice_agent.schemas import DecisionOutcomeRequest

    with database.session_factory() as db:
        DecisionRepository(db).save(DecisionState(
            decision_id="api-decision",
            session_id="s1",
            domain="career",
            user_goal="两个 Offer 怎么选",
            owner_user_id=7,
            revision=1,
            candidates=[Candidate(candidate_id="a", name="A 公司")],
            recommendation=Recommendation(primary_candidate_id="a"),
        ))

        listed = list_decision_history(limit=50, uid=7, db=db)
        assert listed.items[0].current_recommendation == "A 公司"

        detail = get_decision_history_detail("api-decision", uid=7, db=db)
        assert detail.decision.user_goal == "两个 Offer 怎么选"

        saved = save_decision_outcome(
            "api-decision",
            DecisionOutcomeRequest(candidate_id="a", label="A 公司", reason="更稳定", revision=1),
            uid=7,
            db=db,
        )
        assert saved.summary.final_choice == "A 公司"

        with pytest.raises(HTTPException) as error:
            save_decision_outcome(
                "api-decision",
                DecisionOutcomeRequest(candidate_id="a", label="A 公司", revision=1),
                uid=7,
                db=db,
            )
        assert error.value.status_code == 409
