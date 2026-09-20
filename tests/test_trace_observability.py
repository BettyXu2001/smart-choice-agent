import json

from sqlalchemy import select

from choice_agent.db_models import TraceRecord
from choice_agent.decision.ranking import AttributeCriterionEvaluator, GenericRankingEngine
from choice_agent.domains.registry import DomainRegistry
from choice_agent.domains.travel import TravelProfile
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.providers.search import OpenAIWebSearchProvider
from choice_agent.providers.observability import ModelCompletion, ProviderCallMetadata
from choice_agent.services.trace import _redact
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


def test_trace_redaction_allows_only_numeric_token_counts():
    payload = _redact({
        "inputTokens": 10,
        "output_tokens": None,
        "totalTokens": "credential-like-value",
        "access_token": "secret",
        "token": "secret",
    })
    assert payload["inputTokens"] == 10
    assert payload["output_tokens"] is None
    assert payload["totalTokens"] == "[REDACTED]"
    assert payload["access_token"] == "[REDACTED]"
    assert payload["token"] == "[REDACTED]"


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
    assert trace["schemaVersion"] == 3
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
    failed_model = [node for node in trace["timeline"] if node["kind"] == "model" and node["status"] == "failed"]
    assert failed_model
    assert all(node["output"]["totalTokens"] is None for node in failed_model)
    fallback_runs = [event for event in trace["events"] if event.get("fallbackUsed")]
    assert fallback_runs
    assert all(event["retryCount"] == 0 for event in fallback_runs)
    assert all(event["fallbackReason"] for event in fallback_runs)


def test_trace_records_search_retries_and_auto_fallback_on_same_agent_run(database):
    attempts = []

    def failing_transport(request, timeout):
        attempts.append(timeout)
        raise TimeoutError("simulated search timeout")

    web = OpenAIWebSearchProvider(
        "key",
        "https://api.openai.com/v1",
        "search-model",
        transport=failing_transport,
    )
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(
            db,
            registry=DomainRegistry([TravelProfile(web)]),
        )
        result = service.create(1, GenericDecisionRequest(
            message="周末从上海出发两天一夜，不想太累",
            domain="travel",
            context={"searchMode": "auto"},
            request_id="trace-search-fallback",
        ))
        trace = _trace_json(db, result.trace_id)

    assert len(attempts) == 2
    failed_search = [
        node for node in trace["timeline"]
        if node["kind"] == "search" and node["status"] == "failed"
    ]
    assert len(failed_search) == 2
    fallback = next(node for node in trace["timeline"] if node["status"] == "fallback")
    assert fallback["output"]["fromPath"].startswith("web_search:")
    assert fallback["output"]["toPath"].startswith("fixture_search:")
    candidate_run = next(
        event for event in trace["events"]
        if event.get("agentName") == "CandidateAgent"
    )
    assert candidate_run["provider"] == "openai_web_search"
    assert candidate_run["retryCount"] == 1
    assert candidate_run["fallbackUsed"] is True
    assert candidate_run["totalTokens"] is None


def test_real_provider_usage_flows_into_agent_run_and_trace(database):
    class UsageModel:
        enabled = True
        name = "usage-provider"

        def complete_json(self, **kwargs):
            payload = json.loads(kwargs["user_prompt"])
            if "source_catalog" not in payload:
                value = {"fields": {}, "question": None, "intent": "compare", "candidate_updates": []}
            else:
                primary = payload["allowed_primary_ids"][0]
                source_id, source = next(iter(payload["source_catalog"].items()))
                value = {
                    "primary_candidate_id": primary,
                    "summary": "基于现有资料推荐。",
                    "reasons": [{
                        "candidate_id": source["candidateId"],
                        "source_id": source_id,
                        "quote": source["text"],
                        "text": "该资料支持当前建议。",
                    }],
                    "tradeoffs": [],
                    "question": None,
                }
            return ModelCompletion(value, ProviderCallMetadata(
                provider=self.name,
                model=kwargs["model"],
                prompt_version="sha256:test",
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                estimated_cost=0.0002,
            ))

    with database.session_factory() as db:
        result = GenericDecisionOrchestrator(db, provider=UsageModel()).create(
            1,
            GenericDecisionRequest(
                message="买电脑，预算 8000",
                domain="shopping",
                context={"searchMode": "fixture"},
                request_id="trace-real-usage",
            ),
        )
        trace = _trace_json(db, result.trace_id)

    model_runs = [event for event in trace["events"] if event.get("provider") == "usage-provider"]
    assert model_runs
    assert all(event["inputTokens"] == 10 for event in model_runs)
    assert all(event["outputTokens"] == 5 for event in model_runs)
    assert all(event["totalTokens"] == 15 for event in model_runs)
    assert all(event["estimatedCost"] == 0.0002 for event in model_runs)
    assert all(event["fallbackUsed"] is False for event in model_runs)


def test_search_response_usage_flows_into_candidate_agent_run(database):
    payload = {
        "id": "search-response",
        "model": "priced-search-model",
        "usage": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
        "output_text": json.dumps({
            "candidates": [{
                "id": "web-trip",
                "name": "Web Trip",
                "summary": "A sourced trip",
                "attributes": {"travel_hours": 1.5, "budget": 800, "relaxation": 80, "crowd_level": 30, "nature": 70},
                "evidence": [{
                    "key": "budget",
                    "value": 800,
                    "claim": "Budget is 800",
                    "sourceTitle": "Source",
                    "sourceUrl": "https://example.com/trip",
                }],
            }],
        }),
        "output": [{"content": [{
            "type": "output_text",
            "text": "",
            "annotations": [{
                "type": "url_citation",
                "url": "https://example.com/trip",
                "title": "Source",
            }],
        }]}],
    }
    web = OpenAIWebSearchProvider(
        "key",
        "https://api.openai.com/v1",
        "priced-search-model",
        transport=lambda request, timeout: payload,
        pricing={
            "priced-search-model": {"inputPer1MTokens": 1.0, "outputPer1MTokens": 2.0}
        },
    )
    with database.session_factory() as db:
        result = GenericDecisionOrchestrator(
            db,
            registry=DomainRegistry([TravelProfile(web)]),
        ).create(1, GenericDecisionRequest(
            message="周末从上海出发两天一夜，不想太累",
            domain="travel",
            context={"searchMode": "web"},
            request_id="trace-search-usage",
        ))
        trace = _trace_json(db, result.trace_id)

    candidate_run = next(event for event in trace["events"] if event.get("agentName") == "CandidateAgent")
    assert candidate_run["provider"] == "openai_web_search"
    assert candidate_run["modelName"] == "priced-search-model"
    assert candidate_run["inputTokens"] == 20
    assert candidate_run["outputTokens"] == 5
    assert candidate_run["totalTokens"] == 25
    assert candidate_run["estimatedCost"] == 0.00003
    assert candidate_run["promptVersion"].startswith("sha256:")


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
