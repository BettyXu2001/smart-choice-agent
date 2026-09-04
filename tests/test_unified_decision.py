import pytest

from choice_agent.decision.evidence import EvidenceValidator
from choice_agent.orchestration.diet import DietOrchestrator
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.providers.model import DisabledProvider
from choice_agent.providers.search import OpenAIWebSearchProvider
from choice_agent.schemas import (
    Candidate, ChatRequest, DecisionCommandRequest, DecisionState, Evidence,
    GenericDecisionMessageRequest, GenericDecisionRequest, SourceDocument,
)
from choice_agent.config import Settings
from choice_agent.agents.base import AgentContext


def test_unknown_request_uses_generic_clarification_without_fixture(database):
    with database.session_factory() as db:
        response = GenericDecisionOrchestrator(db).create(
            1, GenericDecisionRequest(message="帮我选一个更合适的方案")
        )
        assert response.decision_state.domain == "generic"
        assert response.decision_state.status.value == "clarifying"
        assert response.decision_state.candidates == []
        assert response.decision_state.unanswered_questions


def test_travel_and_shopping_share_unified_stage_names(database):
    with database.session_factory() as db:
        orchestrator = GenericDecisionOrchestrator(db)
        travel = orchestrator.create(
            1, GenericDecisionRequest(message="周末从上海出发两天一夜", domain="travel")
        )
        shopping = orchestrator.create(
            1, GenericDecisionRequest(message="想买一台适合出差的轻薄笔记本", domain="shopping")
        )
        travel_names = [item.agent_name for item in travel.decision_state.agent_runs]
        shopping_names = [item.agent_name for item in shopping.decision_state.agent_runs]
        assert travel_names == shopping_names
        assert travel_names == [
            "IntentAgent", "UnderstandingAgent", "ClarificationAgent",
            "CandidateAgent", "CriticAgent", "ExplanationAgent", "RiskAgent",
        ]


def test_context_goal_owner_and_messages_survive_follow_up(database):
    with database.session_factory() as db:
        orchestrator = GenericDecisionOrchestrator(db)
        first = orchestrator.create(
            7,
            GenericDecisionRequest(
                message="周末从上海出发两天一夜",
                domain="travel",
                context={"searchMode": "fixture", "workspace": "compare", "revision": 999},
            ),
        )
        second = orchestrator.message(
            7,
            first.decision_state.decision_id,
            GenericDecisionMessageRequest(
                message="更想人少一点",
                expected_revision=first.decision_state.revision,
                context={"workspace": "refine"},
            ),
        )
        state = second.decision_state
        assert state.owner_user_id == 7
        assert state.user_goal == "周末从上海出发两天一夜"
        assert state.context["workspace"] == "refine"
        assert "revision" not in state.context
        assert [item.role for item in state.messages] == ["user", "assistant", "user", "assistant"]
        with pytest.raises(KeyError):
            orchestrator.message(
                8,
                state.decision_id,
                GenericDecisionMessageRequest(message="偷看", expected_revision=state.revision),
            )


def test_weight_command_reuses_candidate_pool_and_is_idempotent(database):
    with database.session_factory() as db:
        orchestrator = GenericDecisionOrchestrator(db)
        first = orchestrator.create(
            1, GenericDecisionRequest(message="周末从上海出发两天一夜", domain="travel")
        )
        before_runs = len(first.decision_state.search_runs)
        request = DecisionCommandRequest(
            command_id="weight-1",
            type="set_criterion_weight",
            expected_revision=first.decision_state.revision,
            payload={"criterionKey": "travel_hours", "weight": 0},
        )
        second = orchestrator.command(1, first.decision_state.decision_id, request)
        assert second.decision_state.revision == 2
        assert len(second.decision_state.search_runs) == before_runs
        assert second.decision_state.agent_runs[0].agent_name == "RankAgent"
        assert second.decision_state.edit_events[-1].command_id == "weight-1"
        replay = orchestrator.command(1, first.decision_state.decision_id, request)
        assert replay.decision_state.revision == 2
        assert len(replay.decision_state.edit_events) == 1


def test_diet_session_advances_one_decision(database):
    with database.session_factory() as db:
        orchestrator = DietOrchestrator(db, Settings(), DisabledProvider())
        first = orchestrator.chat(1, ChatRequest(message="晚餐想吃清淡一点"))
        second = orchestrator.chat(
            1,
            ChatRequest(
                session_id=first.session_id,
                message="换一个",
                expected_revision=first.decision_state.revision,
            ),
        )
        assert second.decision_state.decision_id == first.decision_state.decision_id
        assert second.decision_state.user_goal == "晚餐想吃清淡一点"
        assert len(second.decision_state.messages) == 4


def test_evidence_validator_rejects_url_not_returned_by_tool():
    source = SourceDocument(
        source_id="web:1", title="Allowed", url="https://allowed.example/a", kind="web"
    )
    candidate = Candidate(
        candidate_id="a",
        name="A",
        evidence=[
            Evidence(
                key="price", value=100, source_title="Invented",
                source_url="https://invented.example/a",
            )
        ],
    )
    validated, evidence, warnings = EvidenceValidator().validate([candidate], [source])
    assert evidence[0].verification_status.value == "rejected"
    assert warnings
    assert validated[0].evidence_ids


def test_web_search_retries_and_uses_returned_citations():
    calls = []
    payload = {
        "id": "resp-1",
        "output_text": '{"candidates":[{"id":"a","name":"A","attributes":{"price":100},"evidence":[{"key":"price","value":100,"sourceTitle":"Allowed","sourceUrl":"https://allowed.example/a"}]}]}',
        "output": [{"content": [{"type": "output_text", "text": "", "annotations": [
            {"type": "url_citation", "url": "https://allowed.example/a", "title": "Allowed"}
        ]}]}],
    }

    def transport(request, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise TimeoutError("retry")
        return payload

    provider = OpenAIWebSearchProvider(
        "key", "https://api.openai.com/v1", "gpt-test", transport=transport
    )
    decision = DecisionState(
        decision_id="d", session_id="s", domain="shopping", user_goal="选电脑"
    )
    context = AgentContext("s", "t", 1, "选电脑", decision, {})
    result = provider.search(context)
    assert len(calls) == 2
    assert result.sources[0].url == "https://allowed.example/a"
    validated, evidence, warnings = EvidenceValidator().validate(result.candidates, result.sources)
    assert evidence[0].verification_status.value == "verified"
    assert not warnings
    assert validated[0].origin == "web"
@pytest.mark.parametrize("message", ["吃什么", "晚餐想吃清淡一点", "帮我规划三餐"])
def test_diet_generic_entry_returns_serializable_blocks_and_real_question(database, message):
    with database.session_factory() as db:
        result = GenericDecisionOrchestrator(db).create(
            1, GenericDecisionRequest(message=message, domain="diet")
        )
        assert all(isinstance(item, dict) for item in result.display_blocks)
        if result.decision_state.status.value == "clarifying":
            assert result.speech_text in result.decision_state.clarifying_questions
        else:
            assert result.display_blocks


def test_diet_command_then_chat_uses_current_revision_and_slots(database):
    with database.session_factory() as db:
        diet = DietOrchestrator(db, Settings(), DisabledProvider())
        generic = GenericDecisionOrchestrator(db)
        first = diet.chat(1, ChatRequest(message="晚餐想吃清淡一点"))
        state = first.decision_state
        edited = generic.command(1, state.decision_id, DecisionCommandRequest(
            command_id="diet-weight", type="set_criterion_weight",
            expected_revision=state.revision,
            payload={"criterionKey": "taste", "weight": 2},
        ))
        continued = diet.chat(1, ChatRequest(
            session_id=first.session_id, message="换一个",
            expected_revision=edited.decision_state.revision,
        ))
        assert continued.decision_state.revision == edited.decision_state.revision + 1
        assert next(item for item in continued.decision_state.criteria if item.key == "taste").weight == 2
        assert continued.decision_state.domain_state["slots"] == first.decision_state.domain_state["slots"]


def test_diet_plan_command_keeps_composition_and_health_guard(database):
    with database.session_factory() as db:
        orchestrator = GenericDecisionOrchestrator(db)
        first = orchestrator.create(1, GenericDecisionRequest(message="帮我规划三餐", domain="diet"))
        edited = orchestrator.command(1, first.decision_state.decision_id, DecisionCommandRequest(
            command_id="plan-again", type="generate_recommendation",
            expected_revision=first.decision_state.revision,
        ))
        assert edited.decision_state.composition
        assert edited.decision_state.agent_runs[0].agent_name == "PlanningAgent"
        risk = orchestrator.message(1, first.decision_state.decision_id, GenericDecisionMessageRequest(
            message="糖尿病怎么吃能治好", expected_revision=edited.decision_state.revision,
        ))
        guarded = orchestrator.command(1, first.decision_state.decision_id, DecisionCommandRequest(
            command_id="risk-again", type="generate_recommendation",
            expected_revision=risk.decision_state.revision,
        ))
        assert guarded.decision_state.candidates == []
        assert guarded.decision_state.recommendation is None
        assert guarded.decision_state.composition is None
        assert [item.agent_name for item in guarded.decision_state.agent_runs] == ["RiskAgent"]


def test_search_mode_survives_follow_up_and_manual_candidate_survives_refresh(database):
    with database.session_factory() as db:
        orchestrator = GenericDecisionOrchestrator(db)
        first = orchestrator.create(1, GenericDecisionRequest(
            message="周末从上海出发两天一夜", domain="travel", context={"searchMode": "auto"}
        ))
        second = orchestrator.message(1, first.decision_state.decision_id, GenericDecisionMessageRequest(
            message="人少", expected_revision=first.decision_state.revision,
        ))
        assert second.decision_state.context["searchMode"] == "auto"
        assert second.decision_state.status.value == "decided"
        added = orchestrator.command(1, second.decision_state.decision_id, DecisionCommandRequest(
            command_id="manual-add", type="add_candidate", expected_revision=second.decision_state.revision,
            payload={"candidate": {"candidateId": "manual:test", "name": "自选地点", "origin": "web"}},
        ))
        refreshed = orchestrator.command(1, second.decision_state.decision_id, DecisionCommandRequest(
            command_id="refresh", type="refresh_candidates", expected_revision=added.decision_state.revision,
        ))
        candidate = next(item for item in refreshed.decision_state.candidates if item.candidate_id == "manual:test")
        assert candidate.origin == "manual"


def test_hard_numeric_constraints_and_missing_neutral_scoring():
    from choice_agent.decision.ranking import AttributeCriterionEvaluator, GenericRankingEngine
    from choice_agent.schemas import Constraint, Criterion
    decision = DecisionState(decision_id="d", session_id="s", domain="shopping",
        criteria=[Criterion(key="quality", label="Quality", weight=1)],
        constraints=[Constraint(key="price", kind="hard", operator="lte", value=100)])
    candidates = [
        Candidate(candidate_id="a", name="A", attributes={"price": 80}),
        Candidate(candidate_id="b", name="B", attributes={"price": 120, "quality": 100}),
        Candidate(candidate_id="c", name="C", attributes={"quality": 100}),
    ]
    ranked = GenericRankingEngine().rank(decision, candidates, AttributeCriterionEvaluator())
    assert [item.candidate_id for item in ranked] == ["a"]
    assert ranked[0].score == 0.5
    assert ranked[0].score_breakdown[0].raw_value is None


@pytest.mark.parametrize("weight", [float("nan"), float("inf"), -1])
def test_invalid_weights_are_rejected(weight):
    from choice_agent.decision.commands import apply_command
    from choice_agent.schemas import Criterion
    decision = DecisionState(decision_id="d", session_id="s", domain="generic",
        criteria=[Criterion(key="quality", label="Quality")])
    with pytest.raises(ValueError):
        apply_command(decision, DecisionCommandRequest(
            command_id="bad-weight", type="set_criterion_weight", expected_revision=0,
            payload={"criterionKey": "quality", "weight": weight},
        ))


def test_web_attribute_without_matching_verified_evidence_is_not_scored():
    from choice_agent.decision.ranking import AttributeCriterionEvaluator
    from choice_agent.schemas import Criterion
    decision = DecisionState(decision_id="d", session_id="s", domain="shopping")
    candidate = Candidate(candidate_id="a", name="A", origin="web", attributes={"price": 100})
    assert AttributeCriterionEvaluator().evaluate(Criterion(key="price", label="Price"), candidate, decision) is None


def test_stale_repository_write_cannot_overwrite_new_revision(database):
    from choice_agent.repositories.decision_repository import DecisionRepository
    from choice_agent.decision.state_machine import DecisionRevisionError
    with database.session_factory() as db:
        state = GenericDecisionOrchestrator(db).create(
            1, GenericDecisionRequest(message="周末从上海出发两天一夜", domain="travel")
        ).decision_state
        stale = state.model_copy(deep=True)
        state.revision += 1
        DecisionRepository(db).save(state)
        stale.revision += 1
        with pytest.raises(DecisionRevisionError):
            DecisionRepository(db).save(stale)
        assert DecisionRepository(db).get(state.decision_id).revision == 2


def test_diet_weight_edits_do_not_change_new_session_defaults(database):
    with database.session_factory() as db:
        orchestrator = GenericDecisionOrchestrator(db)
        first = orchestrator.create(1, GenericDecisionRequest(message="晚餐想吃清淡一点", domain="diet"))
        default = next(item.weight for item in first.decision_state.criteria if item.key == "taste")
        orchestrator.command(1, first.decision_state.decision_id, DecisionCommandRequest(
            command_id="isolated", type="set_criterion_weight", expected_revision=first.decision_state.revision,
            payload={"criterionKey": "taste", "weight": default + 2},
        ))
        fresh = orchestrator.create(1, GenericDecisionRequest(message="晚餐想吃清淡一点", domain="diet"))
        assert next(item.weight for item in fresh.decision_state.criteria if item.key == "taste") == default


def test_generic_manual_candidates_follow_shared_comparison_pipeline(database):
    with database.session_factory() as db:
        orchestrator = GenericDecisionOrchestrator(db)
        result = orchestrator.create(1, GenericDecisionRequest(message="帮我比较两个方案", domain="generic"))
        for index, fit in enumerate([30, 80]):
            result = orchestrator.command(1, result.decision_state.decision_id, DecisionCommandRequest(
                command_id=f"manual-{index}", type="add_candidate",
                expected_revision=result.decision_state.revision,
                payload={"candidate": {"candidateId": f"manual:{index}", "name": f"方案 {index}",
                    "attributes": {"fit": fit, "cost": 50, "risk": 50}}},
            ))
            if index == 0:
                assert result.decision_state.status.value == "clarifying"
                assert result.decision_state.recommendation is None
        assert result.decision_state.recommendation.primary_candidate_id == "manual:1"
        assert result.decision_state.recommendation.generated_from_revision == result.decision_state.revision
        assert "用户输入" in result.speech_text


@pytest.mark.parametrize("message,category", [
    ("想买手机方便出门用", "phone"), ("想买耳机通勤听音乐", "headphones"),
    ("想买家电比较节能", "appliance"),
])
def test_shopping_fixture_respects_product_category(database, message, category):
    with database.session_factory() as db:
        result = GenericDecisionOrchestrator(db).create(
            1, GenericDecisionRequest(message=message, domain="shopping")
        )
        assert result.decision_state.candidates
        assert all(item.candidate_id.startswith(category) for item in result.decision_state.candidates)


def test_web_parser_joins_text_blocks_and_accepts_tool_sources():
    decision = DecisionState(decision_id="d", session_id="s", domain="shopping", user_goal="选电脑")
    context = AgentContext("s", "t", 1, "选电脑", decision, {})
    provider = OpenAIWebSearchProvider("key", "https://api.openai.com/v1", "gpt-test")
    result = provider._parse({"output": [
        {"type": "web_search_call", "action": {"sources": [
            {"type": "url", "url": "https://example.com/product"}
        ]}},
        {"content": [
            {"type": "output_text", "text": '{"candidates":['},
            {"type": "output_text", "text": '{"id":"a","name":"A","attributes":{},"evidence":[]}]}'},
        ]},
    ]}, context)
    assert result.candidates[0].candidate_id == "a"
    assert result.sources[0].url == "https://example.com/product"


def test_command_id_reuse_with_different_payload_is_rejected(database):
    with database.session_factory() as db:
        orchestrator = GenericDecisionOrchestrator(db)
        result = orchestrator.create(1, GenericDecisionRequest(message="周末从上海出发两天一夜", domain="travel"))
        request = DecisionCommandRequest(command_id="collision", type="set_criterion_weight",
            expected_revision=result.decision_state.revision,
            payload={"criterionKey": "travel_hours", "weight": 2})
        orchestrator.command(1, result.decision_state.decision_id, request)
        with pytest.raises(ValueError, match="commandId"):
            orchestrator.command(1, result.decision_state.decision_id, request.model_copy(
                update={"payload": {"criterionKey": "travel_hours", "weight": 3}}
            ))


def test_model_cannot_downgrade_rule_health_risk(database):
    class MisclassifyingProvider:
        enabled = True

        def complete_json(self, *args, **kwargs):
            return {"intent": "MEAL_RECOMMENDATION", "slots": {}, "confidence": 1}

    with database.session_factory() as db:
        result = GenericDecisionOrchestrator(db, provider=MisclassifyingProvider()).create(
            1, GenericDecisionRequest(message="糖尿病怎么吃能治好", domain="diet")
        )
        assert result.decision_state.intent.value == "HEALTH_RISK"
        assert result.decision_state.candidates == []
        assert result.decision_state.recommendation is None
