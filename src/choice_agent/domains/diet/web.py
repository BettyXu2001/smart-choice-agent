from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from choice_agent.agents.base import AgentContext
from choice_agent.decision.engine import SLOT_FIELDS
from choice_agent.providers.candidates import CandidateProvider, CandidateSearchResult
from choice_agent.providers.search import OpenAIWebSearchProvider
from choice_agent.schemas import Candidate, Evidence, MealResponse, SourceMode


DIET_SEARCH_INSTRUCTION = (
    "Research real meal, restaurant, delivery, or dish options for this diet decision. "
    "Return strict JSON with a candidates array. Each candidate needs id, name, summary, "
    "attributes, and evidence. Attributes must use Diet snake_case fields only: "
    "meal_time, mood, scene, health_goal, cuisine, taste, convenience. Every attribute "
    "value must be an array of short strings. For nearby restaurants, delivery, opening "
    "hours, distance, queues, price, or other realtime needs, prefer current web sources. "
    "Each evidence item needs key, value, claim, sourceTitle, and sourceUrl. Use only URLs "
    "returned by web search."
)

_FIELD_ALIASES = {
    "mealTime": "meal_time",
    "meal_time": "meal_time",
    "mood": "mood",
    "scene": "scene",
    "healthGoal": "health_goal",
    "health_goal": "health_goal",
    "cuisine": "cuisine",
    "taste": "taste",
    "convenience": "convenience",
}


@dataclass(frozen=True)
class DietDisplayCandidate:
    candidate: Candidate
    display_id: int
    source_type: SourceMode

    @property
    def name(self) -> str:
        return self.candidate.name

    @property
    def score(self) -> float:
        return self.candidate.score

    @property
    def attributes(self) -> dict[str, list[str]]:
        return normalize_diet_attributes(self.candidate.attributes)


def normalize_diet_attributes(attributes: dict[str, Any]) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {field: [] for field in SLOT_FIELDS}
    for raw_key, raw_value in (attributes or {}).items():
        key = _FIELD_ALIASES.get(str(raw_key), str(raw_key))
        if key not in normalized:
            continue
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        normalized[key] = list(dict.fromkeys(
            str(item).strip() for item in values if str(item).strip()
        ))
    return normalized


def normalize_evidence_key(key: str | None) -> str | None:
    if key is None:
        return None
    return _FIELD_ALIASES.get(str(key), str(key))


def web_display_id(candidate_id: str) -> int:
    digest = sha256(candidate_id.encode("utf-8")).hexdigest()[:12]
    return -1 * (int(digest, 16) % 1_000_000_000 + 1)


def meal_response_from_display(item: DietDisplayCandidate, reason: str) -> MealResponse:
    attributes = item.attributes
    return MealResponse(
        id=item.display_id,
        source_type=item.source_type,
        name=item.name,
        meal_time=attributes["meal_time"],
        mood=attributes["mood"],
        scene=attributes["scene"],
        health_goal=attributes["health_goal"],
        cuisine=attributes["cuisine"],
        taste=attributes["taste"],
        convenience=attributes["convenience"],
        match_score=item.score,
        reason=reason,
    )


class DietWebCandidateProvider:
    name = "diet_web_search"

    def __init__(self, provider: CandidateProvider):
        self.provider = provider

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.provider, "enabled", True))

    def search(self, context: AgentContext) -> CandidateSearchResult:
        result = self.provider.search(context)
        normalized_candidates = [self._candidate(candidate) for candidate in result.candidates]
        return CandidateSearchResult(
            candidates=normalized_candidates,
            sources=result.sources,
            evidence=[item for candidate in normalized_candidates for item in candidate.evidence],
            run=result.run,
            warnings=result.warnings,
        )

    def _candidate(self, candidate: Candidate) -> Candidate:
        candidate_id = candidate.candidate_id
        if not candidate_id.startswith("web:"):
            candidate_id = f"web:{candidate_id}"
        attributes = normalize_diet_attributes(candidate.attributes)
        evidence: list[Evidence] = []
        for item in candidate.evidence:
            key = normalize_evidence_key(item.key) or item.key
            criterion_key = normalize_evidence_key(item.criterion_key or item.key) or key
            evidence.append(
                item.model_copy(update={
                    "key": key,
                    "criterion_key": criterion_key,
                    "candidate_id": candidate_id,
                    "value": _normalize_evidence_value(item.value),
                })
            )
        return candidate.model_copy(update={
            "candidate_id": candidate_id,
            "attributes": attributes,
            "evidence": evidence,
            "origin": "web",
        })


def _normalize_evidence_value(value: Any) -> Any:
    if isinstance(value, list):
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))
    if isinstance(value, str):
        return value.strip()
    return value


def diet_web_provider_from_openai(provider: OpenAIWebSearchProvider) -> DietWebCandidateProvider:
    provider.instruction = DIET_SEARCH_INSTRUCTION
    return DietWebCandidateProvider(provider)