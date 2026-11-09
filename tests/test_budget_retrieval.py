"""Budget routing tests exercise real State, Provider, ranking and transactions."""
from copy import deepcopy
import json

import pytest
from sqlalchemy import select

from choice_agent.db_models import TraceRecord
from choice_agent.decision.conversation import fields, patch_fields
from choice_agent.decision.execution import (
    ExecutionMode, bind_budget_coverage, capture_execution_baseline, plan_execution,
)
from choice_agent.decision.ranking import GenericRankingEngine
from choice_agent.domains.registry import DomainRegistry
from choice_agent.domains.shopping import ShoppingProfile
from choice_agent.domains.travel import TravelProfile
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.providers.candidates import FixtureCandidateProvider
from choice_agent.providers.search import OpenAIWebSearchProvider
from choice_agent.schemas import (
    Constraint, DecisionCommandRequest, DecisionState, GenericDecisionMessageRequest,
    GenericDecisionRequest, SearchRun,
)


def _state(budget=5000, domain="shopping"):
    decision = DecisionState(decision_id="d", session_id="s", domain=domain,
                             context={"searchMode": "fixture"})
    fields(decision)
    if budget is not None:
        patch_fields(decision, {"budget": budget})
    decision.domain_state["candidatePool"] = [
        {"candidateId": "a", "name": "A", "attributes": {"price": 4000, "budget": 4000}},
        {"candidateId": "expensive", "name": "Expensive", "attributes": {"price": 12000}},
    ]
    return decision


def _certify(profile, decision, maximum=None, independent=True):
    run = SearchRun(run_id="run", provider="controlled", mode="fixture", query="test")
    decision.search_runs.append(run)
    declaration = {"complete": True, "budgetIndependent": independent, "maxBudget": maximum}
    decision.domain_state["source"] = {"mode": "fixture", "budgetCoverage": bind_budget_coverage(
        profile, decision, declaration, run,
        [item["candidateId"] for item in decision.domain_state["candidatePool"]],
    )}


@pytest.mark.parametrize("old,new,covered,mode,direction", [
    (5000,4000,False,"rerank","tightened"),
    (5000,8000,False,"refresh","relaxed"),
    (5000,8000,True,"rerank","relaxed"),
    (5000,None,False,"refresh","removed"),
    (5000,None,True,"rerank","removed"),
    (None,5000,False,"refresh","first_set"),
    (None,5000,True,"rerank","first_set"),
    (5000,5000,False,"explain_only","unchanged"),
])
def test_budget_direction_and_coverage_matrix(old, new, covered, mode, direction):
    profile, decision = ShoppingProfile(), _state(old)
    if covered:
        _certify(profile, decision)
    baseline = capture_execution_baseline(decision)
    patch_fields(decision, {"budget": new})
    plan = plan_execution(profile, decision, baseline, {})
    assert plan.mode.value == mode
    assert plan.diagnostics["budgetChangeDirection"] == direction
    assert plan.diagnostics["oldBudget"] == old
    assert plan.diagnostics["newBudget"] == new


@pytest.mark.parametrize("maximum,expected", [(7000,"refresh"),(8000,"rerank"),(9000,"rerank")])
def test_bounded_provider_guarantee(maximum, expected):
    profile, decision = ShoppingProfile(), _state()
    _certify(profile, decision, maximum, independent=False)
    baseline = capture_execution_baseline(decision)
    patch_fields(decision, {"budget": 8000})
    assert plan_execution(profile, decision, baseline, {}).mode.value == expected
    patch_fields(decision, {"budget": None})
    assert plan_execution(profile, decision, baseline, {}).mode == ExecutionMode.REFRESH


@pytest.mark.parametrize("damage", ["missing", "run", "scope", "pool", "malformed", "complete"])
def test_stale_or_unproven_coverage_cannot_be_inferred_from_highest_price(damage):
    profile, decision = ShoppingProfile(), _state()
    _certify(profile, decision)
    baseline = capture_execution_baseline(decision)
    certificate = decision.domain_state["source"]["budgetCoverage"]
    if damage == "missing":
        decision.domain_state["source"].pop("budgetCoverage")
    elif damage == "run":
        certificate["runId"] = "old"
    elif damage == "scope":
        certificate["scope"]["searchMode"] = "web"
    elif damage == "pool":
        decision.domain_state["candidatePool"].pop(0)
    elif damage == "malformed":
        certificate["candidateIds"] = [{}]
    else:
        certificate["complete"] = "true"
    patch_fields(decision, {"budget": 8000})
    assert plan_execution(profile, decision, baseline, {}).mode == ExecutionMode.REFRESH


@pytest.mark.parametrize("value", [True,False,0,-1,float("nan"),float("inf"),"8000"])
def test_invalid_new_numeric_budget_is_rejected(value):
    profile, decision = ShoppingProfile(), _state()
    baseline = capture_execution_baseline(decision)
    with pytest.raises(ValueError):
        patch_fields(decision, {"budget": value})
    decision.constraints = [Constraint(key="price", kind="hard", operator="lte", value=value)]
    with pytest.raises(ValueError, match="预算硬约束"):
        plan_execution(profile, decision, baseline, {})


def test_budget_constraints_sources_strictness_and_legacy_values():
    profile, decision = ShoppingProfile(), _state()
    decision.constraints.append(Constraint(key="price", kind="hard", operator="lte", value=3000, source="user"))
    baseline = capture_execution_baseline(decision)
    patch_fields(decision, {"budget": None})
    plan = plan_execution(profile, decision, baseline, {})
    assert plan.diagnostics["newEffectiveBudget"] == 3000
    assert decision.constraints[0].source == "user"
    assert plan.mode == ExecutionMode.REFRESH

    decision = _state(None)
    decision.constraints = [Constraint(key="price", kind="hard", operator="lt", value=5000)]
    baseline = capture_execution_baseline(decision)
    decision.constraints[0].operator = "lte"
    assert plan_execution(profile, decision, baseline, {}).diagnostics["budgetChangeDirection"] == "relaxed"
    decision.constraints[0].value = "legacy"
    baseline = capture_execution_baseline(decision)
    decision.constraints[0].value = 8000
    assert plan_execution(profile, decision, baseline, {}).diagnostics["budgetChangeDirection"] == "unknown"


def test_direct_constraint_expansion_is_not_hidden_by_old_field():
    profile, decision = ShoppingProfile(), _state()
    baseline = capture_execution_baseline(decision)
    decision.constraints = [Constraint(key="price", kind="hard", operator="lte", value=8000, source="user")]
    plan = plan_execution(profile, decision, baseline, {})
    assert plan.mode == ExecutionMode.REFRESH
    assert plan.diagnostics["newEffectiveBudget"] == 8000
    assert plan.diagnostics["budgetChangeDirection"] == "relaxed"


def test_unconfirmed_model_budget_is_search_input_not_hard_constraint():
    profile, decision = ShoppingProfile(), _state(None)
    baseline = capture_execution_baseline(decision)
    patch_fields(decision, {"budget": 5000}, source="model", confirmed=False)
    plan = plan_execution(profile, decision, baseline, {})
    assert plan.mode == ExecutionMode.REFRESH
    assert plan.diagnostics["newEffectiveBudget"] is None
    assert not decision.constraints
    baseline = capture_execution_baseline(decision)
    patch_fields(decision, {"budget": 5000}, source="panel", confirmed=True)
    assert plan_execution(profile, decision, baseline, {}).mode == ExecutionMode.REFRESH


def test_priority_and_explicit_rerank_cannot_override_search_safety():
    profile, decision = ShoppingProfile(), _state()
    baseline = capture_execution_baseline(decision)
    patch_fields(decision, {"priority": "performance"})
    assert plan_execution(profile, decision, baseline, {}).mode == ExecutionMode.RERANK
    patch_fields(decision, {"budget": 8000})
    assert plan_execution(profile, decision, baseline, {"requested_execution_mode": "rerank"}).mode == ExecutionMode.REFRESH
    assert plan_execution(profile, decision, baseline, {"is_hypothetical": True, "requested_execution_mode": "rerank"}).mode == ExecutionMode.WHAT_IF
    assert plan_execution(profile, decision, None, {}).mode == ExecutionMode.FULL


class BudgetProvider:
    name = "controlled"
    enabled = True

    def __init__(self, coverage=None):
        self.coverage = coverage
        self.calls = []
        self.fail = False

    def search(self, context):
        if self.fail:
            raise RuntimeError("search interrupted")
        attribute = "budget" if context.decision.domain == "travel" else "price"
        limits = [c.value for c in context.decision.constraints if c.key == attribute and c.kind.value == "hard" and c.operator == "lte"]
        budget = min(limits) if limits else None
        self.calls.append({"budget": budget, "fields": deepcopy(context.decision.domain_state["conversationFields"])})
        maximum = self.coverage.get("maxBudget") if self.coverage else budget
        if self.coverage and self.coverage.get("budgetIndependent"):
            maximum = None
        fixtures = [
            {"id": key, "name": name, "attributes": {
                attribute: price, "performance": score, "portability": score,
                "battery": score, "durability": score, "support": score,
                "relaxation": score, "nature": score, "crowd_level": 100-score,
                "travel_hours": 2,
            }}
            for key,name,price,score in [("basic","Basic",3800,50),("balanced","Balanced",4800,70),("premium","Premium",7600,99)]
            if maximum is None or price <= maximum
        ]
        result = FixtureCandidateProvider("controlled", fixtures).search(context)
        result.budget_coverage = deepcopy(self.coverage)
        return result


def _service(db, provider, domain="shopping"):
    profile = TravelProfile(provider) if domain == "travel" else ShoppingProfile(provider)
    return GenericDecisionOrchestrator(db, registry=DomainRegistry([profile]))


def _create(service, budget=5000, domain="shopping"):
    message = "从上海出发两天一夜" if domain == "travel" else "买电脑"
    if budget is not None:
        message += f"，预算 {budget}"
    return service.create(1, GenericDecisionRequest(message=message, domain=domain, context={"searchMode":"web"}, request_id="create"))


def _say(service, result, message, identifier):
    return service.message(1, result.decision_state.decision_id, GenericDecisionMessageRequest(
        message=message, expected_revision=result.decision_state.revision, request_id=identifier))


def _command(service, result, kind, payload, identifier):
    return service.command(1, result.decision_state.decision_id, DecisionCommandRequest(
        type=kind, payload=payload, command_id=identifier, expected_revision=result.decision_state.revision))


def _trace(db, result):
    row = db.scalar(select(TraceRecord).where(TraceRecord.trace_id == result.trace_id))
    return row.trace_json if isinstance(row.trace_json, dict) else json.loads(row.trace_json)


def _assert_valid(result, limit=None, attribute="price"):
    decision = result.decision_state
    assert decision.candidates
    ranking = GenericRankingEngine()
    assert all(ranking.hard_constraint_failure(decision, c) is None for c in decision.candidates)
    if limit is not None:
        assert all(c.attributes[attribute] <= limit for c in decision.candidates)
    assert decision.recommendation
    refs = [decision.recommendation.primary_candidate_id, *decision.recommendation.alternative_candidate_ids]
    assert set(filter(None, refs)) <= {c.candidate_id for c in decision.candidates}
    assert decision.recommendation.generated_from_revision == decision.revision


@pytest.mark.parametrize("coverage", [None, {"complete":True,"budgetIndependent":True}])
def test_real_budget_tightening_and_expansion_results(database, coverage):
    provider = BudgetProvider(coverage)
    with database.session_factory() as db:
        service = _service(db, provider)
        first = _create(service)
        tightened = _say(service, first, "预算从 5000 降到 4000", "tighten")
        _assert_valid(tightened, 4000)
        assert len(provider.calls) == 1
        assert _trace(db,tightened)["metadata"]["executionMode"] == "rerank"
        pool = tightened.decision_state.domain_state["candidatePool"]
        assert any(c["attributes"]["price"] > 4000 for c in pool)
        expanded = _say(service, tightened, "预算从 4000 提高到 8000", "expand")
        _assert_valid(expanded, 8000)
        assert "premium" in {c.candidate_id for c in expanded.decision_state.candidates}
        assert expanded.decision_state.recommendation.primary_candidate_id == "premium"
        trace = _trace(db,expanded)
        assert trace["metadata"]["executionMode"] == ("rerank" if coverage else "refresh")
        assert len(provider.calls) == (1 if coverage else 2)
        assert trace["metadata"]["budgetChangeDirection"] == "relaxed"
        assert trace["metadata"]["oldBudget"] == 4000
        assert trace["metadata"]["newBudget"] == 8000
        pool_trace = trace["metadata"]["candidatePool"]
        assert pool_trace["candidateCountAfter"] == 3
        assert pool_trace["reused"] is bool(coverage)
        plan_node = next(node for node in trace["timeline"] if node["stage"] == "Execution Plan")
        assert "budget" in plan_node["output"]["changedFields"]
        assert plan_node["output"]["reason"]
        if not coverage:
            assert provider.calls[-1]["budget"] == 8000
            assert trace["metadata"]["candidatePool"]["refreshedCandidateCount"] == 3
        cancelled = _say(service, expanded, "取消预算", "cancel")
        _assert_valid(cancelled)
        assert cancelled.decision_state.domain_state["conversationFields"]["budget"]["value"] is None
        assert not [c for c in cancelled.decision_state.constraints if c.key == "price"]
        assert len(provider.calls) == (1 if coverage else 3)
        assert cancelled.decision_state.revision == first.decision_state.revision + 3


@pytest.mark.parametrize("covered", [False,True])
def test_first_budget_with_existing_pool(database, covered):
    provider = BudgetProvider({"complete":True,"budgetIndependent":True} if covered else None)
    with database.session_factory() as db:
        service = _service(db, provider)
        first = _create(service, None)
        result = _say(service, first, "预算 5000", "first-budget")
        _assert_valid(result, 5000)
        assert len(provider.calls) == (1 if covered else 2)
        assert _trace(db,result)["metadata"]["budgetChangeDirection"] == "first_set"


def test_manual_candidates_exclusions_evidence_and_replay_survive(database):
    provider = BudgetProvider()
    with database.session_factory() as db:
        service = _service(db, provider)
        first = _create(service)
        manual = _command(service, first, "add_candidate", {"candidate":{"candidateId":"manual:one","name":"Mine","attributes":{"price":3900,"performance":60}}}, "manual")
        excluded = _command(service, manual, "exclude_candidate", {"candidateId":"balanced"}, "exclude")
        expanded = _say(service, excluded, "预算 8000", "expand")
        _assert_valid(expanded,8000)
        assert "manual:one" in {c.candidate_id for c in expanded.decision_state.candidates}
        assert "balanced" in expanded.decision_state.excluded_candidates
        assert "balanced" not in {c.candidate_id for c in expanded.decision_state.candidates}
        before = expanded.decision_state
        tighter = _say(service, expanded, "预算 4000", "tighten")
        _assert_valid(tighter,4000)
        assert tighter.decision_state.search_runs == before.search_runs
        assert tighter.decision_state.sources == before.sources
        assert {e.evidence_id:e.retrieved_at for e in tighter.decision_state.evidence}.items() <= {e.evidence_id:e.retrieved_at for e in before.evidence}.items()
        assert tighter.decision_state.domain_state["manualCandidates"] == before.domain_state["manualCandidates"]
        replay = _say(service, expanded, "预算 4000", "tighten")
        assert replay.trace_id == tighter.trace_id
        assert len(provider.calls) == 2


@pytest.mark.parametrize("stage", ["search","rank","explain","validate","save"])
def test_budget_failure_rolls_back_complete_state_and_can_retry(database, monkeypatch, stage):
    provider = BudgetProvider()
    with database.session_factory() as db:
        service = _service(db,provider)
        first = _create(service)
        stored_before = service.repository.get(first.decision_state.decision_id).model_dump(mode="json")
        with monkeypatch.context() as patch:
            def fail(*args, **kwargs):
                raise RuntimeError("budget interrupted")
            profile = service.registry.get("shopping")
            if stage == "search":
                patch.setattr(provider,"search",fail)
            elif stage == "rank":
                patch.setattr(profile.ranking,"rank",fail)
            elif stage == "explain":
                patch.setattr(profile,"explain",fail)
            elif stage == "validate":
                patch.setattr("choice_agent.agents.stages.validate_recommendation",fail)
            else:
                original = service.repository.save
                def fail_after_save(decision):
                    original(decision)
                    fail()
                patch.setattr(service.repository,"save",fail_after_save)
            with pytest.raises(RuntimeError, match="budget interrupted"):
                _say(service,first,"预算 8000","retry")
        stored = service.repository.get(first.decision_state.decision_id)
        assert stored.model_dump(mode="json") == stored_before
        rows = db.scalars(select(TraceRecord).where(TraceRecord.session_id == stored.session_id)).all()
        traces = [r.trace_json if isinstance(r.trace_json,dict) else json.loads(r.trace_json) for r in rows]
        assert any(t["metadata"]["commitStatus"] == "rolled_back" for t in traces)
        result = _say(service,first,"预算 8000","retry")
        _assert_valid(result,8000)
        calls = len(provider.calls)
        assert _say(service,first,"预算 8000","retry").trace_id == result.trace_id
        assert len(provider.calls) == calls


@pytest.mark.parametrize("new_budget", [4000,8000])
def test_travel_budget_dependent_search_refreshes_even_when_tightening(database, new_budget):
    provider = BudgetProvider()
    with database.session_factory() as db:
        service = _service(db,provider,"travel")
        first = _create(service,domain="travel")
        result = _say(service,first,f"预算 {new_budget}","travel-budget")
        _assert_valid(result,new_budget,"budget")
        assert len(provider.calls) == 2
        assert _trace(db,result)["metadata"]["executionMode"] == "refresh"


def test_fixed_fixture_coverage_is_real_and_respects_travel_departure(database):
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        first = service.create(1,GenericDecisionRequest(message="买电脑，预算 8000",domain="shopping",context={"searchMode":"fixture"}))
        expanded = _say(service,first,"预算 12000","fixture-expand")
        _assert_valid(expanded,12000)
        assert _trace(db,expanded)["metadata"]["executionMode"] == "rerank"
        assert expanded.decision_state.search_runs == first.decision_state.search_runs
        assert "creator-16" in {c.candidate_id for c in expanded.decision_state.candidates}
        travel = service.create(1,GenericDecisionRequest(message="从上海出发两天一夜，预算 1000",domain="travel",context={"searchMode":"fixture"}))
        result = _say(service,travel,"预算 1500","travel-fixture")
        _assert_valid(result,1500,"budget")
        assert _trace(db,result)["metadata"]["executionMode"] == "rerank"
        other = service.create(1,GenericDecisionRequest(message="从北京出发两天一夜，预算 1000",domain="travel",context={"searchMode":"fixture"}))
        assert "budgetCoverage" not in other.decision_state.domain_state["source"]
        result = _say(service,other,"预算 1500","travel-other")
        assert _trace(db,result)["metadata"]["executionMode"] == "refresh"
        assert not result.decision_state.candidates
        assert not result.decision_state.recommendation or result.decision_state.recommendation.primary_candidate_id is None

def test_web_request_uses_current_budget_for_expand_and_clear(database):
    requests = []
    url = "https://catalog.example/spec"

    def transport(request, timeout):
        prompt = json.loads(request.data)["input"]
        fields = json.loads(prompt.split("Confirmed/current fields (override original goal): ", 1)[1].splitlines()[0])
        constraints = json.loads(prompt.rsplit("Constraints: ", 1)[1])
        budget = fields["budget"]["value"]
        hard_limits = [c["value"] for c in constraints if c["kind"] == "hard" and c["key"] == "price"]
        assert hard_limits == ([budget] if budget is not None else [])
        requests.append(budget)
        candidates = []
        for key, price in [("basic", 3800), ("premium", 7600), ("deluxe", 11000)]:
            if budget is not None and price > budget:
                continue
            candidates.append({
                "id": key, "name": key.title(), "attributes": {"price": price},
                "evidence": [{"key": "price", "value": price, "sourceTitle": "Catalog", "sourceUrl": url}],
            })
        return {
            "id": f"search-{len(requests)}",
            "output_text": json.dumps({
                "candidates": candidates,
                "budgetCoverage": {"complete": True, "budgetIndependent": True},
            }),
            "output": [{"type": "web_search_call", "action": {"sources": [
                {"type": "url", "url": url, "title": "Catalog"},
            ]}}],
        }

    provider = OpenAIWebSearchProvider("test-key", "https://provider.example/v1", "test", transport=transport)
    with database.session_factory() as db:
        service = _service(db, provider)
        first = _create(service)
        _assert_valid(first, 5000)
        expanded = _command(service, first, "update_fields", {"fields": {"budget": 8000}}, "panel-expand")
        _assert_valid(expanded, 8000)
        assert "premium" in {c.candidate_id for c in expanded.decision_state.candidates}
        assert _trace(db, expanded)["metadata"]["executionMode"] == "refresh"
        cancelled = _say(service, expanded, "取消预算", "web-cancel")
        _assert_valid(cancelled)
        assert "deluxe" in {c.candidate_id for c in cancelled.decision_state.candidates}
        assert "budgetCoverage" not in cancelled.decision_state.domain_state["source"]
        assert requests == [5000, 8000, None]


def test_explicit_refresh_replaces_previous_coverage(database):
    provider = BudgetProvider({"complete": True, "budgetIndependent": True})
    with database.session_factory() as db:
        service = _service(db, provider)
        first = _create(service)
        assert first.decision_state.domain_state["source"]["budgetCoverage"]["complete"]
        provider.coverage = None
        refreshed = _say(service, first, "重新搜索", "force-refresh")
        _assert_valid(refreshed, 5000)
        assert _trace(db, refreshed)["metadata"]["executionMode"] == "refresh"
        assert "budgetCoverage" not in refreshed.decision_state.domain_state["source"]
        expanded = _say(service, refreshed, "预算 8000", "expand-after-refresh")
        _assert_valid(expanded, 8000)
        assert _trace(db, expanded)["metadata"]["executionMode"] == "refresh"
        assert len(provider.calls) == 3



def test_auto_search_fallback_does_not_prove_live_coverage(database):
    provider = BudgetProvider()
    provider.fail = True
    with database.session_factory() as db:
        service = _service(db, provider)
        first = service.create(1, GenericDecisionRequest(
            message="买电脑，预算 8000", domain="shopping", context={"searchMode": "auto"},
        ))
        assert first.decision_state.domain_state["source"]["mode"] == "fixture"
        assert "budgetCoverage" not in first.decision_state.domain_state["source"]
        provider.fail = False
        expanded = _say(service, first, "预算 12000", "expand-after-fallback")
        _assert_valid(expanded, 12000)
        assert _trace(db, expanded)["metadata"]["executionMode"] == "refresh"
        assert [call["budget"] for call in provider.calls] == [12000]
