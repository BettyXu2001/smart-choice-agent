from __future__ import annotations

from choice_agent.agents.base import AgentContext
from choice_agent.decision.evidence import EvidenceValidator
from choice_agent.decision.engine import RankedMeal, SLOT_FIELDS
from choice_agent.decision.ranking import GenericRankingEngine
from choice_agent.domains.diet.evaluator import DietCriterionEvaluator
from choice_agent.decision.state_machine import transition_decision
from choice_agent.providers.candidates import DietMealProvider
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import (
    CandidateState, CompositionItem, CompositionResult, DecisionNextAction,
    DecisionStatus, SlotBundle,
)


class DietMealPlanCompositionStrategy:
    name = "diet_meal_plan"
    default_meal_times = ["早餐", "午餐", "晚餐"]

    def __init__(self, repository: DietRepository):
        self.provider = DietMealProvider(repository)
        self.ranking = GenericRankingEngine()
        self.evaluator = DietCriterionEvaluator()

    def execute(self, context: AgentContext) -> dict:
        slots: SlotBundle = context.data["slots"]
        requested = [value for value in slots.meal_time if value != "三餐"]
        meal_times = requested if len(requested) >= 2 else self.default_meal_times
        result = self.provider.search(context)
        candidates, evidence, warnings = EvidenceValidator().validate(
            result.candidates, result.sources
        )
        if result.run:
            context.decision.search_runs.append(result.run)
        context.decision.sources = result.sources
        context.decision.evidence = evidence
        context.decision.domain_state["source"] = {
            "mode": "database",
            "label": result.sources[0].title if result.sources else "餐食库",
            "realTime": False,
            "warnings": warnings,
        }
        original_slots = context.decision.domain_state.get("slots", {})
        original_excluded = list(context.decision.excluded_candidates)
        used: list[str] = []
        planned: list[tuple[str, RankedMeal | None]] = []
        selected_candidates = []
        records = context.data["meal_records_by_id"]
        for meal_time in meal_times:
            query = slots.model_copy(update={"meal_time": [meal_time]})
            context.decision.domain_state["slots"] = query.model_dump(by_alias=True)
            context.decision.excluded_candidates = list(dict.fromkeys([
                *original_excluded,
                *[str(item) for item in context.data.get("exclude_ids", [])],
                *used,
            ]))
            ranked = self.ranking.rank(context.decision, candidates, self.evaluator, tie_breaker=lambda item: int(item.candidate_id))
            ranked = [candidate for candidate in ranked if candidate.score > 0]
            selected = ranked[0] if ranked else None
            if selected:
                used.append(selected.candidate_id)
                selected_candidates.append(selected)
                meal = records[selected.candidate_id]
                matched = {
                    field: [
                        value for value in getattr(query, field)
                        if value in selected.attributes.get(field, [])
                    ]
                    for field in SLOT_FIELDS
                }
                planned.append((meal_time, RankedMeal(meal=meal, score=selected.score, matched=matched)))
            else:
                planned.append((meal_time, None))
        context.decision.domain_state["slots"] = original_slots
        context.decision.excluded_candidates = original_excluded
        context.data["planned"] = planned
        context.data["ranked"] = [item for _, item in planned if item is not None]
        context.decision.candidates = selected_candidates
        context.decision.candidate_state = {
            candidate.candidate_id: CandidateState(status="active", updated_by="PlanningAgent")
            for candidate in selected_candidates
        }
        context.decision.composition = CompositionResult(
            strategy=self.name,
            items=[
                CompositionItem(
                    slot=meal_time,
                    candidate_id=str(item.meal.id) if item else None,
                    label=item.meal.name if item else "暂时没有匹配项",
                )
                for meal_time, item in planned
            ],
        )
        transition_decision(
            context.decision, DecisionStatus.COMPARING, DecisionNextAction.COMPARE_CANDIDATES
        )
        return {
            "mealTimes": meal_times,
            "plannedMeals": [
                {"mealTime": meal_time, "mealId": item.meal.id if item else None}
                for meal_time, item in planned
            ],
        }