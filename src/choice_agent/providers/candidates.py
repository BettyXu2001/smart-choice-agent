from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from choice_agent.agents.base import AgentContext
from choice_agent.decision.engine import SLOT_FIELDS
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import Candidate, Evidence, SearchRun, SourceDocument, SourceMode


@dataclass
class CandidateSearchResult:
    candidates: list[Candidate] = field(default_factory=list)
    sources: list[SourceDocument] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    run: SearchRun | None = None
    warnings: list[str] = field(default_factory=list)


class CandidateProvider(Protocol):
    name: str

    def search(self, context: AgentContext) -> CandidateSearchResult:
        ...


class DietMealProvider:
    name = "diet_database"

    def __init__(self, repository: DietRepository):
        self.repository = repository

    def search(self, context: AgentContext) -> CandidateSearchResult:
        source_mode = SourceMode(context.data["source_mode"])
        meals = self.repository.list_meals(source_mode, context.user_id)
        context.data["meal_records_by_id"] = {str(meal.id): meal for meal in meals}
        source_id = f"diet:{source_mode.value.lower()}"
        source = SourceDocument(
            source_id=source_id,
            title="个人餐食库" if source_mode == SourceMode.PERSONAL else "公共餐食库",
            kind="database",
        )
        candidates: list[Candidate] = []
        evidence: list[Evidence] = []
        for meal in meals:
            attributes = {field: list(getattr(meal, field) or []) for field in SLOT_FIELDS}
            items = [
                Evidence(
                    key=key,
                    value=value,
                    candidate_id=str(meal.id),
                    criterion_key=key,
                    source_title=source.title,
                    publisher="Choice Agent",
                    confidence=1.0,
                    verification_status="verified",
                )
                for key, value in attributes.items()
                if value
            ]
            evidence.extend(items)
            candidates.append(
                Candidate(
                    candidate_id=str(meal.id),
                    name=meal.name,
                    attributes=attributes,
                    evidence=items,
                    origin="database",
                )
            )
        run = SearchRun(
            run_id=uuid4().hex,
            provider=self.name,
            mode="database",
            query=context.message,
            source_ids=[source_id],
        )
        return CandidateSearchResult(candidates, [source], evidence, run)


class FixtureCandidateProvider:
    name = "fixture"

    def __init__(self, domain: str, fixtures: list[dict[str, Any]]):
        self.domain = domain
        self.fixtures = fixtures

    def search(self, context: AgentContext) -> CandidateSearchResult:
        source_id = f"fixture:{self.domain}"
        source = SourceDocument(
            source_id=source_id,
            title=f"Choice Agent {self.domain} fixture",
            kind="fixture",
        )
        candidates: list[Candidate] = []
        evidence: list[Evidence] = []
        for item in self.fixtures:
            items = [
                Evidence(
                    key=key,
                    value=value,
                    candidate_id=str(item["id"]),
                    criterion_key=key,
                    source_title=source.title,
                    publisher="Choice Agent",
                    confidence=1.0,
                    verification_status="verified",
                )
                for key, value in item.get("attributes", {}).items()
            ]
            evidence.extend(items)
            candidates.append(
                Candidate(
                    candidate_id=str(item["id"]),
                    name=str(item["name"]),
                    summary=str(item.get("summary", "")),
                    attributes=dict(item.get("attributes", {})),
                    evidence=items,
                    origin="fixture",
                )
            )
        run = SearchRun(
            run_id=uuid4().hex,
            provider=f"fixture:{self.domain}",
            mode="fixture",
            query=context.message,
            source_ids=[source_id],
        )
        return CandidateSearchResult(candidates, [source], evidence, run)


class ManualCandidateProvider:
    name = "manual"

    def search(self, context: AgentContext) -> CandidateSearchResult:
        candidates = [
            Candidate.model_validate(item)
            for item in context.decision.domain_state.get("manualCandidates", [])
        ]
        return CandidateSearchResult(candidates=candidates)


class CompositeCandidateProvider:
    name = "composite"

    def __init__(self, providers: list[CandidateProvider]):
        self.providers = providers

    def search(self, context: AgentContext) -> CandidateSearchResult:
        return self.merge([provider.search(context) for provider in self.providers])

    @staticmethod
    def merge(results: list[CandidateSearchResult]) -> CandidateSearchResult:
        merged = CandidateSearchResult()
        by_id: dict[str, Candidate] = {}
        for result in results:
            for candidate in result.candidates:
                by_id.setdefault(candidate.candidate_id, candidate)
            merged.sources.extend(result.sources)
            merged.evidence.extend(result.evidence)
            if result.run and merged.run is None:
                merged.run = result.run
            merged.warnings.extend(result.warnings)
        merged.candidates = list(by_id.values())
        return merged