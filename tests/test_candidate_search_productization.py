import asyncio
import json
from types import SimpleNamespace

from choice_agent.api.decision_stream import stream_create_decision
from choice_agent.api.routes import search_capabilities
from choice_agent.config import Settings
from choice_agent.decision.ranking import AttributeCriterionEvaluator, GenericRankingEngine
from choice_agent.providers.model import DisabledProvider
from choice_agent.schemas import Candidate, Constraint, Criterion, DecisionState, GenericDecisionRequest, MissingValuePolicy


class FakeRequest:
    def __init__(self, database):
        self.app = SimpleNamespace(state=SimpleNamespace(database=database))

    async def is_disconnected(self):
        return False


async def _collect_stream(response):
    events = []
    async for chunk in response.body_iterator:
        text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        for line in text.splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


def _stream_events(database, body, settings=None):
    response = stream_create_decision(
        FakeRequest(database),
        1,
        body,
        settings or Settings(database_url="sqlite:///:memory:"),
        DisabledProvider(),
    )
    return asyncio.run(_collect_stream(response))


def test_search_capabilities_hide_provider_details():
    payload = search_capabilities(Settings(search_api_key="secret")).model_dump(by_alias=True)
    assert payload == {
        "supportedDomains": ["shopping", "travel"],
        "webSearchConfigured": True,
        "defaultSearchMode": "fixture",
    }
    assert "secret" not in json.dumps(payload)
    assert "base" not in json.dumps(payload).lower()


def test_search_capabilities_use_runtime_search_settings():
    runtime_settings = Settings(search_provider="openai", search_api_key="browser-secret")
    payload = search_capabilities(
        Settings(search_provider="fixture", search_api_key=""),
        (runtime_settings, DisabledProvider()),
    ).model_dump(by_alias=True)

    assert payload == {
        "supportedDomains": ["shopping", "travel"],
        "webSearchConfigured": True,
        "defaultSearchMode": "web",
    }
    assert "browser-secret" not in json.dumps(payload)


def test_stream_create_emits_progress_and_final_for_fixture(database):
    events = _stream_events(database, GenericDecisionRequest(
        message="预算 7000 的轻便通勤电脑",
        domain="shopping",
        context={"searchMode": "fixture"},
        request_id="stream-fixture",
    ))
    assert [event["type"] for event in events][-1] == "final"
    messages = [event.get("message") for event in events if event["type"] == "progress"]
    assert "正在理解你的需求" in messages
    assert "正在寻找候选" in messages
    assert any(str(message).startswith("找到 ") for message in messages)
    assert any(str(message).startswith("正在比较剩余 ") for message in messages)
    final = events[-1]["response"]
    assert final["decisionState"]["domain"] == "shopping"
    assert final["decisionState"]["context"]["searchMode"] == "fixture"


def test_stream_web_without_key_returns_error_event(database):
    events = _stream_events(database, GenericDecisionRequest(
        message="预算 7000 的轻便通勤电脑",
        domain="shopping",
        context={"searchMode": "web"},
        request_id="stream-web-missing-key",
    ))
    assert events[-1]["type"] == "error"
    assert events[-1]["error"]["code"] == "search_provider_failed"
    assert "API Key" in events[-1]["error"]["message"]


def test_ranking_counts_separate_hard_and_missing_exclusions():
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
    ranked = GenericRankingEngine().rank(decision, candidates, AttributeCriterionEvaluator())
    assert [item.candidate_id for item in ranked] == ["ok"]
    assert decision.domain_state["rankingCounts"] == {
        "considered": 4,
        "found": 4,
        "userExcluded": 1,
        "hardConstraintExcluded": 1,
        "missingDataExcluded": 1,
        "remaining": 1,
    }
    assert decision.candidate_state["missing"].reason == "缺少必要数据"
    assert decision.candidate_state["hard"].reason == "不满足硬约束"