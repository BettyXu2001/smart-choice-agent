import pytest

from choice_agent.decision.state_machine import DecisionRevisionError
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.repositories.decision_repository import DecisionRepository
from choice_agent.schemas import GenericDecisionMessageRequest, GenericDecisionRequest


def test_generic_orchestrator_creates_persisted_travel_decision(database):
    with database.session_factory() as db:
        response = GenericDecisionOrchestrator(db).create(
            1,
            GenericDecisionRequest(
                message="周末从上海出发两天一夜，不想太累，人少一点",
                domain="travel",
            ),
        )
        decision = response.decision_state
        assert decision.domain == "travel"
        assert decision.revision == 1
        assert decision.candidates
        assert decision.recommendation.primary_candidate_id == decision.candidates[0].candidate_id
        assert [run.agent_name for run in decision.agent_runs] == [
            "IntentAgent", "UnderstandingAgent", "ClarificationAgent",
            "CandidateAgent", "CriticAgent", "ExplanationAgent", "RiskAgent",
        ]
        assert decision.domain_state["source"]["mode"] == "fixture"
        persisted = DecisionRepository(db).get(decision.decision_id)
        assert persisted is not None
        assert persisted.recommendation.summary == decision.recommendation.summary


def test_generic_orchestrator_rejects_stale_revision(database):
    with database.session_factory() as db:
        orchestrator = GenericDecisionOrchestrator(db)
        response = orchestrator.create(1, GenericDecisionRequest(message="周末出去玩", domain="travel"))
        with pytest.raises(DecisionRevisionError):
            orchestrator.message(
                1,
                response.decision_state.decision_id,
                GenericDecisionMessageRequest(message="希望更轻松", expected_revision=0),
            )


def test_generic_orchestrator_accepts_current_revision(database):
    with database.session_factory() as db:
        orchestrator = GenericDecisionOrchestrator(db)
        first = orchestrator.create(1, GenericDecisionRequest(message="周末出去玩", domain="travel"))
        second = orchestrator.message(
            1,
            first.decision_state.decision_id,
            GenericDecisionMessageRequest(
                message="更想人少一点",
                expected_revision=first.decision_state.revision,
            ),
        )
        assert second.decision_state.revision == 2
        assert second.decision_state.domain_state["messages"][-1]["content"] == "更想人少一点"