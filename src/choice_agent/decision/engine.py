from __future__ import annotations

from dataclasses import dataclass

from choice_agent.db_models import MealRecord
from choice_agent.schemas import Candidate, Criterion, Evidence, SlotBundle


SLOT_FIELDS = (
    "meal_time", "mood", "scene", "health_goal", "cuisine", "taste", "convenience"
)


@dataclass(frozen=True)
class RankedMeal:
    meal: MealRecord
    score: float
    matched: dict[str, list[str]]
    eliminated: bool = False
    elimination_reasons: tuple[str, ...] = ()


class DecisionEngine:
    criteria = [
        Criterion(key="meal_time", label="餐次匹配", weight=1),
        Criterion(key="mood", label="心情匹配", weight=1),
        Criterion(key="scene", label="场景匹配", weight=1),
        Criterion(key="health_goal", label="健康目标", weight=1),
        Criterion(key="cuisine", label="菜系偏好", weight=1),
        Criterion(key="taste", label="口味偏好", weight=1),
        Criterion(key="convenience", label="便利程度", weight=1),
    ]

    def rank(
        self,
        meals: list[MealRecord],
        query: SlotBundle,
        excluded_ids: list[int] | None = None,
        hard_exclusions: list[str] | None = None,
    ) -> list[RankedMeal]:
        excluded = set(excluded_ids or [])
        banned = set(hard_exclusions or [])
        ranked: list[RankedMeal] = []
        for meal in meals:
            if meal.id in excluded:
                continue
            all_values = {value for field in SLOT_FIELDS for value in (getattr(meal, field) or [])}
            blocked = sorted(all_values & banned)
            if blocked:
                continue
            matched: dict[str, list[str]] = {}
            total = 0.0
            has_query = False
            for field in SLOT_FIELDS:
                requested = getattr(query, field)
                available = set(getattr(meal, field) or [])
                if requested:
                    has_query = True
                    hits = [value for value in requested if value in available]
                    matched[field] = hits
                    total += len(hits) / len(requested)
            if has_query and not any(matched.values()):
                continue
            ranked.append(RankedMeal(meal=meal, score=max(0.0, min(1.0, total / 7)), matched=matched))
        return sorted(ranked, key=lambda item: (-item.score, item.meal.id))[:10]

    def candidate(self, ranked: RankedMeal) -> Candidate:
        attributes = {field: list(getattr(ranked.meal, field) or []) for field in SLOT_FIELDS}
        evidence = [
            Evidence(
                key=field,
                value=values,
                source_title=(
                    "个人餐食库" if ranked.meal.source_type == "PERSONAL" else "公共餐食库"
                ),
                confidence=1.0,
            )
            for field, values in attributes.items()
            if values
        ]
        return Candidate(
            candidate_id=str(ranked.meal.id),
            name=ranked.meal.name,
            attributes=attributes,
            evidence=evidence,
            score=ranked.score,
            eliminated=ranked.eliminated,
            elimination_reasons=list(ranked.elimination_reasons),
        )
