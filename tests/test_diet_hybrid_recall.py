import pytest

from choice_agent.config import Settings
from choice_agent.orchestration.diet import DietOrchestrator
from choice_agent.providers.model import DisabledProvider
from choice_agent.providers.search import SearchProviderError
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import (
    Candidate,
    ChatRequest,
    Evidence,
    MealRequest,
    SearchRun,
    SourceDocument,
    SourceMode,
)
from choice_agent.providers.candidates import CandidateSearchResult


class FakeDietWebProvider:
    enabled = True
    name = "fake_diet_web"

    def __init__(self, candidates=None, fail=False):
        self.calls = []
        self.candidates = candidates or [_web_candidate("nearby-porridge", "附近清淡粥店")]
        self.fail = fail

    def search(self, context):
        self.calls.append(context.message)
        if self.fail:
            raise SearchProviderError("simulated web failure")
        source = SourceDocument(
            source_id="web:1",
            title="附近餐厅",
            url="https://example.com/restaurant",
            kind="web",
        )
        return CandidateSearchResult(
            candidates=self.candidates,
            sources=[source],
            evidence=[item for candidate in self.candidates for item in candidate.evidence],
            run=SearchRun(run_id="web-run", provider="fake", mode="web", query=context.message),
        )


def _web_candidate(candidate_id, name):
    return Candidate(
        candidate_id=candidate_id,
        name=name,
        origin="web",
        summary="实时搜索候选",
        attributes={
            "mealTime": ["晚餐"],
            "taste": ["清淡"],
            "convenience": ["快速"],
        },
        evidence=[
            Evidence(
                key="taste",
                value=["清淡"],
                criterion_key="taste",
                source_title="附近餐厅",
                source_url="https://example.com/restaurant",
                claim="主打清淡粥品",
            )
        ],
    )


def _service(db, provider):
    service = DietOrchestrator(db, Settings(search_api_key="test-key"), DisabledProvider())
    service.web_provider = provider
    return service


def _one_personal_meal(db):
    repository = DietRepository(db)
    return repository.create_meal(1, MealRequest(
        name="个人清淡晚餐",
        meal_time=["晚餐"],
        taste=["清淡"],
    ))


def test_diet_uses_database_only_when_candidates_are_sufficient(database):
    with database.session_factory() as db:
        provider = FakeDietWebProvider(fail=True)
        result = _service(db, provider).chat(1, ChatRequest(message="晚餐想吃清淡一点"))

        assert result.display_blocks
        assert provider.calls == []
        assert result.decision_state.domain_state["source"]["mode"] == "database"


def test_diet_supplements_with_web_when_database_candidates_are_insufficient(database):
    with database.session_factory() as db:
        _one_personal_meal(db)
        provider = FakeDietWebProvider()
        result = _service(db, provider).chat(1, ChatRequest(
            message="晚餐想吃清淡一点",
            source_mode=SourceMode.PERSONAL,
        ))

        assert provider.calls
        assert result.decision_state.domain_state["source"]["mode"] == "hybrid"
        assert any(candidate.origin == "web" for candidate in result.decision_state.candidates)
        web_candidate = next(candidate for candidate in result.decision_state.candidates if candidate.origin == "web")
        assert set(web_candidate.attributes) >= {
            "meal_time", "mood", "scene", "health_goal", "cuisine", "taste", "convenience",
        }
        assert result.decision_state.domain_state["displayCandidateMap"]


def test_diet_realtime_request_uses_web_first(database):
    with database.session_factory() as db:
        provider = FakeDietWebProvider()
        result = _service(db, provider).chat(1, ChatRequest(message="附近外卖晚餐想吃清淡一点"))

        assert provider.calls
        assert result.decision_state.domain_state["source"]["recallReason"] == "realtime_web_first"
        assert any(candidate.origin == "web" for candidate in result.decision_state.candidates)


def test_diet_web_failure_falls_back_to_database(database):
    with database.session_factory() as db:
        _one_personal_meal(db)
        provider = FakeDietWebProvider(fail=True)
        result = _service(db, provider).chat(1, ChatRequest(
            message="晚餐想吃清淡一点",
            source_mode=SourceMode.PERSONAL,
        ))

        assert provider.calls
        assert result.display_blocks
        assert all(candidate.origin != "web" for candidate in result.decision_state.candidates)
        assert "Web Search 失败" in "；".join(result.decision_state.domain_state["source"]["warnings"])