import pytest
from fastapi import HTTPException

from choice_agent.api.routes import create_decision, get_decision, message_decision
from choice_agent.schemas import GenericDecisionMessageRequest, GenericDecisionRequest


def test_generic_decision_api_create_and_get(database):
    with database.session_factory() as db:
        created = create_decision(
            GenericDecisionRequest(
                message="周末从上海出发两天一夜，不想太累",
                domain="travel",
            ),
            uid=1,
            db=db,
        )
        decision = created.decision_state
        assert decision.domain == "travel"
        assert decision.revision == 1
        assert created.display_blocks

        loaded = get_decision(decision.decision_id, db=db)
        assert loaded.decision_id == decision.decision_id


def test_generic_decision_api_rejects_stale_message(database):
    with database.session_factory() as db:
        created = create_decision(
            GenericDecisionRequest(message="周末出去玩", domain="travel"),
            uid=1,
            db=db,
        )
        with pytest.raises(HTTPException) as error:
            message_decision(
                created.decision_state.decision_id,
                GenericDecisionMessageRequest(message="更想人少", expected_revision=0),
                uid=1,
                db=db,
            )
        assert error.value.status_code == 409

def test_generic_decision_api_command_and_owner(database):
    from choice_agent.api.routes import command_decision
    from choice_agent.schemas import DecisionCommandRequest

    with database.session_factory() as db:
        created = create_decision(
            GenericDecisionRequest(message="周末从上海出发两天一夜", domain="travel"),
            uid=1,
            db=db,
        )
        updated = command_decision(
            created.decision_state.decision_id,
            DecisionCommandRequest(
                command_id="api-weight",
                type="set_criterion_weight",
                expected_revision=created.decision_state.revision,
                payload={"criterionKey": "travel_hours", "weight": 0},
            ),
            uid=1,
            db=db,
        )
        assert updated.decision_state.revision == 2
        with pytest.raises(HTTPException) as error:
            get_decision(created.decision_state.decision_id, uid=2, db=db)
        assert error.value.status_code == 404
