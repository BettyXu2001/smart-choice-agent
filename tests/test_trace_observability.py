import json

from sqlalchemy import select

from choice_agent.db_models import TraceRecord
from choice_agent.decision.ranking import AttributeCriterionEvaluator, GenericRankingEngine
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.schemas import (
    Candidate,
    Constraint,
    Criterion,
    DecisionState,
    GenericDecisionMessageRequest,
    GenericDecisionRequest,
    MissingValuePolicy,
)


def _trace_json(db, trace_id):
    row = db.scalar(select(TraceRecord).where(TraceRecord.trace_id == trace_id))
    assert row is not None
    return row.trace_json if isinstance(row.trace_json, dict) else json.loads(row.trace_json)


def test_trace_timeline_records_decision_process(database):
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        result = service.create(
            1,
            GenericDecisionRequest(
                message="买电脑，预算 8000",
                domain="shopping",
                context={"searchMode": "fixture"},
                request_id="trace-observability",
            ),
        )
        trace = _trace_json(db, result.trace_id)

    stages = [node["stage"] for node in trace["timeline"]]
    assert trace["schemaVersion"] == 2
    assert trace["metadata"]["commitStatus"] == "committed"
    assert trace["turnSummary"]["userMessage"] == "买电脑，预算 8000"
    assert "User Message" in stages
    assert "IntentAgent" in stages
    assert "UnderstandingAgent" in stages
    assert "Candidate Retrieval" in stages
    assert "Evidence" in stages
    assert "Hard Filter" in stages
    assert "Ranking" in stages
    assert "ExplanationAgent" in stages
    assert trace["recommendationChange"]["status"] == "initial"
    assert all("model_api_key" not in json.dumps(node) for node in trace["timeline"])


def test_trace_records_model_fallback(database):
    class FailingModel:
        enabled = True

        def complete_json(self, **kwargs):
            raise RuntimeError("secret should stay as ordinary error text")

    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db, provider=FailingModel())
        first = service.create(1, GenericDecisionRequest(message="买电脑，预算 8000", domain="shopping"))
        result = service.message(
            1,
            first.decision_state.decision_id,
            GenericDecisionMessageRequest(
                message="再帮我想想",
                request_id="trace-model-fallback",
                expected_revision=first.decision_state.revision,
            ),
        )
        trace = _trace_json(db, result.trace_id)

    fallback = [node for node in trace["timeline"] if node["status"] == "fallback"]
    assert fallback
    assert any("模型理解不可用" in node["summary"] for node in fallback)


def test_ranking_diagnostics_include_hard_filter_reason():
    decision = DecisionState(
        decision_id="d",
        session_id="s",
        domain="shopping",
        criteria=[Criterion(key="quality", label="Quality", missing_policy=MissingValuePolicy.NEUTRAL)],
        constraints=[Constraint(key="price", kind="hard", operator="lte", value=100)],
        excluded_candidates=["user"],
    )
    candidates = [
        Candidate(candidate_id="ok", name="OK", attributes={"price": 80, "quality": 80}),
        Candidate(candidate_id="hard", name="Hard", attributes={"price": 120, "quality": 80}),
        Candidate(candidate_id="missing", name="Missing", attributes={"quality": 80}),
        Candidate(candidate_id="user", name="User", attributes={"price": 80, "quality": 80}),
    ]
    diagnostics = {}
    ranked = GenericRankingEngine().rank(
        decision,
        candidates,
        AttributeCriterionEvaluator(),
        diagnostics=diagnostics,
    )

    assert [item.candidate_id for item in ranked] == ["ok"]
    assert diagnostics["counts"]["hardConstraintExcluded"] == 1
    assert diagnostics["counts"]["missingDataExcluded"] == 1
    assert diagnostics["counts"]["userExcluded"] == 1
    hard = next(item for item in diagnostics["eliminated"] if item["candidateId"] == "hard")
    assert hard["reasonCode"] == "hard_constraint_violation"
    assert hard["constraint"] == {
        "key": "price",
        "operator": "lte",
        "expected": 100,
        "actual": 120,
        "source": "user",
    }
