import json

import pytest
from sqlalchemy import select

from choice_agent.db_models import TraceRecord
from choice_agent.decision.execution import ExecutionMode, plan_execution
from choice_agent.decision.validation import RecommendationInvariantError, validate_recommendation
from choice_agent.domains.shopping import ShoppingProfile
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.schemas import (
    Candidate,
    CandidateState,
    Criterion,
    DecisionCommandRequest,
    DecisionQuestion,
    DecisionState,
    GenericDecisionMessageRequest,
    GenericDecisionRequest,
    Recommendation,
)


def _state() -> DecisionState:
    return DecisionState(
        decision_id="d",
        session_id="s",
        domain="shopping",
        criteria=[Criterion(key="price", label="价格")],
        candidates=[Candidate(candidate_id="a", name="A", attributes={"price": 10})],
        candidate_state={"a": CandidateState(status="active")},
        domain_state={
            "candidatePool": [{"candidateId": "a", "name": "A", "attributes": {"price": 10}}],
            "conversationFields": {
                "category": {"value": "laptop"},
                "usage": {"value": "office"},
            },
        },
    )


def test_execution_planner_selects_minimum_safe_path():
    profile = ShoppingProfile()
    baseline = _state()

    unchanged = baseline.model_copy(deep=True)
    assert plan_execution(profile, unchanged, baseline, {"turn_intent": "explain"}).mode == ExecutionMode.EXPLAIN_ONLY

    rerank = baseline.model_copy(deep=True)
    rerank.criteria[0].weight = 2
    assert plan_execution(profile, rerank, baseline, {}).mode == ExecutionMode.RERANK

    refresh = baseline.model_copy(deep=True)
    refresh.domain_state["conversationFields"]["category"]["value"] = "phone"
    assert plan_execution(profile, refresh, baseline, {}).mode == ExecutionMode.REFRESH

    hypothetical = baseline.model_copy(deep=True)
    assert plan_execution(profile, hypothetical, baseline, {"is_hypothetical": True}).mode == ExecutionMode.WHAT_IF

    missing_pool = baseline.model_copy(deep=True)
    missing_pool.domain_state["candidatePool"] = []
    assert plan_execution(profile, missing_pool, baseline, {}).mode == ExecutionMode.REFRESH


def test_recommendation_invariant_rejects_inactive_reference():
    decision = _state()
    decision.recommendation = Recommendation(primary_candidate_id="missing")
    with pytest.raises(RecommendationInvariantError, match="非活动候选"):
        validate_recommendation(decision)


def _trace(db, trace_id):
    row = db.scalar(select(TraceRecord).where(TraceRecord.trace_id == trace_id))
    assert row is not None
    return row.trace_json if isinstance(row.trace_json, dict) else json.loads(row.trace_json)


def test_real_turns_record_refresh_rerank_and_explain_only_paths(database):
    offer = "比较两个 Offer\n以下为演示候选：\nA 公司：成长快但波动大；B 公司：平台成熟且稳定。"
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        first = service.create(1, GenericDecisionRequest(
            message=offer,
            domain="generic",
            context={"demoMode": True, "searchMode": "web"},
            request_id="execution-create",
        ))
        reranked = service.message(1, first.decision_state.decision_id, GenericDecisionMessageRequest(
            message="更看重稳定",
            expected_revision=first.decision_state.revision,
            request_id="execution-rerank",
        ))
        explained = service.message(1, first.decision_state.decision_id, GenericDecisionMessageRequest(
            message="为什么不选 A 公司？",
            expected_revision=reranked.decision_state.revision,
            request_id="execution-explain",
        ))
        rerank_trace = _trace(db, reranked.trace_id)
        explain_trace = _trace(db, explained.trace_id)

    assert rerank_trace["metadata"]["executionMode"] == "rerank"
    assert any(node["stage"] == "Ranking" and node["status"] == "success" for node in rerank_trace["timeline"])
    assert not any(node["stage"] == "CandidateAgent" for node in rerank_trace["timeline"])
    assert explain_trace["metadata"]["executionMode"] == "explain_only"
    assert explain_trace["metadata"]["executionProfile"] == "demo_deterministic"
    assert not any(node["stage"] in {"CandidateAgent", "RankAgent"} for node in explain_trace["timeline"])
    assert any(node["stage"] == "Final Validation" and node["status"] == "success" for node in explain_trace["timeline"])


def test_command_refresh_and_demo_are_deterministic(database):
    class MustNotRunModel:
        enabled = True
        calls = 0

        def complete_json(self, **kwargs):
            self.calls += 1
            raise AssertionError("demoMode must disable model calls")

    model = MustNotRunModel()
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db, provider=model)
        first = service.create(1, GenericDecisionRequest(
            message="买电脑，预算 8000",
            domain="shopping",
            context={"demoMode": True, "searchMode": "web"},
            request_id="demo-deterministic",
        ))
        refreshed = service.command(1, first.decision_state.decision_id, DecisionCommandRequest(
            command_id="refresh-category",
            type="update_fields",
            payload={"fields": {"category": "headphones"}},
            expected_revision=first.decision_state.revision,
        ))
        trace = _trace(db, refreshed.trace_id)

    assert model.calls == 0
    assert first.decision_state.domain_state["source"]["mode"] == "fixture"
    assert trace["metadata"]["executionMode"] == "refresh"
    assert trace["metadata"]["executionProfile"] == "demo_deterministic"
    assert all("耳机" in candidate.name for candidate in refreshed.decision_state.candidates)


def test_non_retrieval_commands_reuse_candidate_pool(database):
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        first = service.create(1, GenericDecisionRequest(
            message="买电脑，预算 8000",
            domain="shopping",
            request_id="command-rerank-create",
        ))
        constrained = service.command(1, first.decision_state.decision_id, DecisionCommandRequest(
            command_id="command-rerank-constraint",
            type="set_constraint",
            payload={"constraint": {"key": "performance", "kind": "hard", "operator": "gte", "value": 80}},
            expected_revision=first.decision_state.revision,
        ))
        trace = _trace(db, constrained.trace_id)

    assert trace["metadata"]["executionMode"] == "rerank"
    assert trace["metadata"]["candidatePool"]["reused"] is True
    assert not any(node["stage"] == "Candidate Retrieval" and node["status"] == "success" for node in trace["timeline"])

def test_optional_decision_question_is_not_blocking():
    question = DecisionQuestion(key="weight:price", question="价格有多重要？", reason="可能改变排序")
    assert question.kind == "optional"
    assert question.required is False


def test_blocking_clarification_and_progress_share_structured_execution_semantics(database):
    progress = []
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db, progress=progress.append)
        blocked = service.create(1, GenericDecisionRequest(
            message="想出去旅行",
            domain="travel",
            request_id="blocking-clarification-trace",
        ))
        blocked_trace = _trace(db, blocked.trace_id)
        ready = service.message(1, blocked.decision_state.decision_id, GenericDecisionMessageRequest(
            message="从上海出发两天一夜",
            expected_revision=blocked.decision_state.revision,
            request_id="ready-after-clarification",
        ))
        ready_trace = _trace(db, ready.trace_id)

    assert blocked.decision_state.status.value == "clarifying"
    assert blocked.decision_state.unanswered_questions[0].required is True
    assert blocked_trace["metadata"]["executionMode"] == "blocking_clarification"
    clarification = next(node for node in blocked_trace["timeline"] if node["stage"] == "ClarificationAgent")
    assert clarification["output"]["clarificationKind"] == "blocking"
    assert clarification["output"]["required"] is True
    assert ready_trace["metadata"]["executionMode"] == "refresh"
    planned = [event for event in progress if event["stage"] == "execution_planned"]
    assert planned and planned[-1]["executionMode"] == "refresh"
    assert progress[-1]["stage"] == "recommendation_ready"
    assert progress[-1]["status"] == "decided"
    assert ready_trace["metadata"]["candidatePool"]["candidateCount"] > 0
    assert ready_trace["metadata"]["candidatePool"]["searchRunCount"] > 0
