from __future__ import annotations

from typing import Any

from choice_agent.agents.base import AgentContext
from choice_agent.agents.diet import (
    AdjustmentAgent,
    ClarificationAgent,
    ExplanationAgent,
    IntentAgent,
    UnderstandingAgent,
)
from choice_agent.config import Settings
from choice_agent.decision.engine import RankedMeal, SLOT_FIELDS
from choice_agent.decision.evidence import EvidenceValidator
from choice_agent.decision.ranking import GenericRankingEngine
from choice_agent.domains.diet.evaluator import DietCriterionEvaluator
from choice_agent.decision.selector import SelectionCandidate, select_candidates
from choice_agent.decision.state_machine import transition_decision
from choice_agent.domains.base import DomainMetadata
from choice_agent.domains.diet.composition import DietMealPlanCompositionStrategy
from choice_agent.domains.diet.policies import DietCandidateCriticPolicy, DietHealthRiskPolicy
from choice_agent.domains.diet.rules import classify_intent
from choice_agent.domains.profile import DomainCapabilities, DomainProfile
from choice_agent.providers.candidates import DietMealProvider
from choice_agent.providers.model import ModelProvider
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import (
    Candidate,
    CandidateState,
    ClarifyAction,
    DecisionNextAction,
    DecisionStatus,
    Intent,
    SourceMode,
)


class DietProfile(DomainProfile):
    metadata = DomainMetadata(
        key="diet",
        label="饮食决策",
        description="完整饮食推荐、澄清、计划、风险和评估领域。",
        complete=True,
    )
    capabilities = DomainCapabilities(
        adjustment=True, composition=True, pre_safety=True, post_safety=True
    )

    def __init__(self, repository: DietRepository, settings: Settings, provider: ModelProvider):
        self.repository = repository
        self.settings = settings
        self.provider = provider

    def matches(self, message: str) -> bool:
        intent, _ = classify_intent(message, False)
        return intent != Intent.OTHER

    def intent(self, context: AgentContext) -> dict[str, Any]:
        result = IntentAgent(self.provider, self.settings.light_model).execute(context)
        context.decision.intent_key = context.decision.intent.value if context.decision.intent else None
        return result

    def understand(self, context: AgentContext) -> dict[str, Any]:
        original_goal = context.decision.user_goal
        previous_weights = {item.key: item.weight for item in context.decision.criteria}
        result = UnderstandingAgent().execute(context)
        for criterion in context.decision.criteria:
            criterion.weight = previous_weights.get(criterion.key, criterion.weight)
        if original_goal:
            context.decision.user_goal = original_goal
        if context.decision.intent == Intent.OTHER:
            context.data["speech_text"] = (
                "我现在主要帮你做饮食选择。你可以告诉我餐次、口味、场景或健康目标。"
            )
            context.data["display_blocks"] = []
            transition_decision(context.decision, DecisionStatus.DECIDED, DecisionNextAction.WAIT_USER)
        return result

    def clarify(self, context: AgentContext) -> dict[str, Any]:
        return ClarificationAgent().execute(context)

    def source_and_rank(self, context: AgentContext) -> dict[str, Any]:
        result = DietMealProvider(self.repository).search(context)
        candidates, evidence, warnings = EvidenceValidator().validate(
            result.candidates, result.sources
        )
        if context.trace:
            context.trace.node(
                "Candidate Retrieval",
                "operation",
                "success",
                f"从餐食库检索到 {len(result.candidates)} 个候选",
                input_payload={"sourceMode": context.data["source_mode"]},
                output_payload={
                    "candidateCount": len(result.candidates),
                    "candidates": [{"id": item.candidate_id, "name": item.name, "origin": item.origin} for item in result.candidates],
                    "warnings": result.warnings,
                },
                refs={"searchRunId": result.run.run_id if result.run else None},
            )
            context.trace.node(
                "Evidence",
                "operation",
                "success",
                f"加入 {len(evidence)} 条餐食 Evidence",
                input_payload={"sourceCount": len(result.sources), "candidateCount": len(result.candidates)},
                output_payload={
                    "evidence": [item.model_dump(mode="json", by_alias=True) for item in evidence],
                    "warnings": warnings,
                },
                refs={"sourceIds": [item.source_id for item in result.sources]},
            )
        decision = context.decision
        decision.sources = result.sources
        if result.run:
            decision.search_runs.append(result.run)
        decision.domain_state["source"] = {
            "mode": "database",
            "label": result.sources[0].title if result.sources else "餐食库",
            "realTime": False,
            "warnings": warnings,
        }
        ranking_diagnostics: dict[str, Any] = {}
        ranked = GenericRankingEngine().rank(
            decision, candidates, DietCriterionEvaluator(), tie_breaker=lambda item: int(item.candidate_id),
            diagnostics=ranking_diagnostics,
        )
        slots = context.data["slots"]
        before_selection_count = len(ranked)
        if not slots.is_empty():
            ranked = [candidate for candidate in ranked if candidate.score > 0]
        positive_count = len(ranked)
        ranked = ranked[:10]
        selection = select_candidates(
            [
                SelectionCandidate(
                    candidate_id=candidate.candidate_id,
                    name=candidate.name,
                    score=candidate.score,
                    attributes={"sourceMode": context.data["source_mode"]},
                )
                for candidate in ranked
            ],
            context.data.get("selection_strategy", "ranked"),
            context.data.get("recent_recommendation_ids", []),
            context.data.get("avoid_recent_count", 0),
        )
        by_id = {candidate.candidate_id: candidate for candidate in ranked}
        ranked_candidates = [by_id[item_id] for item_id in selection.ordered_ids]
        records = context.data["meal_records_by_id"]
        ranked_meals = [
            RankedMeal(
                meal=records[candidate.candidate_id],
                score=candidate.score,
                matched={
                    field: [
                        value for value in getattr(slots, field)
                        if value in candidate.attributes.get(field, [])
                    ]
                    for field in SLOT_FIELDS
                },
            )
            for candidate in ranked_candidates
        ]
        context.data["ranked"] = ranked_meals
        decision.domain_state["selection"] = selection.insights.as_dict()
        decision.candidates = ranked_candidates
        decision.candidate_state = {
            candidate.candidate_id: CandidateState(status="active", updated_by="CandidateAgent")
            for candidate in ranked_candidates
        }
        decision.evidence = evidence
        decision.domain_state["candidatePool"] = [
            item.model_dump(mode="json", by_alias=True) for item in candidates
        ]
        if context.trace:
            counts = decision.domain_state.get("rankingCounts", {})
            context.trace.node(
                "Hard Filter",
                "operation",
                "success",
                f"硬约束排除 {counts.get('hardConstraintExcluded', 0)} 个餐食",
                input_payload={"constraints": [item.model_dump(mode="json", by_alias=True) for item in decision.constraints]},
                output_payload={"counts": counts, "eliminated": ranking_diagnostics.get("eliminated", [])},
            )
            context.trace.node(
                "Ranking",
                "operation",
                "success",
                f"完成 {counts.get('remaining', before_selection_count)} 个餐食排序",
                input_payload={"criteria": [item.model_dump(mode="json", by_alias=True) for item in decision.criteria]},
                output_payload={"ranked": ranking_diagnostics.get("ranked", [])},
            )
            context.trace.node(
                "Selection",
                "operation",
                "success",
                f"按选择策略选出 {len(ranked_candidates)} 个餐食",
                input_payload={
                    "positiveScoreCount": positive_count,
                    "topLimit": 10,
                    "strategy": context.data.get("selection_strategy", "ranked"),
                    "recentRecommendationIds": context.data.get("recent_recommendation_ids", []),
                    "avoidRecentCount": context.data.get("avoid_recent_count", 0),
                },
                output_payload={
                    "orderedIds": selection.ordered_ids,
                    "insights": selection.insights.as_dict(),
                },
            )
        transition_decision(
            decision, DecisionStatus.COMPARING, DecisionNextAction.COMPARE_CANDIDATES
        )
        return {
            "sourceMode": SourceMode(context.data["source_mode"]).value,
            "candidateCount": len(ranked_meals),
            "candidates": [
                {"id": item.meal.id, "name": item.meal.name, "score": item.score}
                for item in ranked_meals
            ],
        }

    def rerank(self, context: AgentContext) -> dict[str, Any]:
        pool = [
            Candidate.model_validate(item)
            for item in context.decision.domain_state.get("candidatePool", [])
        ]
        if not pool:
            return self.source_and_rank(context)
        if self.repository is None:
            raise RuntimeError("Diet rerank 需要 DietRepository")
        source = SourceMode(context.data["source_mode"])
        records = {
            str(meal.id): meal
            for meal in self.repository.list_meals(source, context.user_id)
        }
        context.data["meal_records_by_id"] = records
        ranking_diagnostics: dict[str, Any] = {}
        ranked = GenericRankingEngine().rank(
            context.decision, pool, DietCriterionEvaluator(), tie_breaker=lambda item: int(item.candidate_id),
            diagnostics=ranking_diagnostics,
        )
        slots = context.data["slots"]
        before_selection_count = len(ranked)
        if not slots.is_empty():
            ranked = [candidate for candidate in ranked if candidate.score > 0]
        positive_count = len(ranked)
        ranked = [candidate for candidate in ranked if candidate.candidate_id in records][:10]
        selection = select_candidates(
            [
                SelectionCandidate(
                    candidate_id=candidate.candidate_id,
                    name=candidate.name,
                    score=candidate.score,
                    attributes={"sourceMode": source.value},
                )
                for candidate in ranked
            ],
            context.data.get("selection_strategy", "ranked"),
            context.data.get("recent_recommendation_ids", []),
            context.data.get("avoid_recent_count", 0),
        )
        by_id = {candidate.candidate_id: candidate for candidate in ranked}
        ranked_candidates = [by_id[item_id] for item_id in selection.ordered_ids]
        context.data["ranked"] = [
            RankedMeal(
                meal=records[candidate.candidate_id],
                score=candidate.score,
                matched={
                    field: [
                        value for value in getattr(slots, field)
                        if value in candidate.attributes.get(field, [])
                    ]
                    for field in SLOT_FIELDS
                },
            )
            for candidate in ranked_candidates
        ]
        context.decision.candidates = ranked_candidates
        context.decision.domain_state["selection"] = selection.insights.as_dict()
        if context.trace:
            counts = context.decision.domain_state.get("rankingCounts", {})
            context.trace.node(
                "Hard Filter",
                "operation",
                "success",
                f"硬约束排除 {counts.get('hardConstraintExcluded', 0)} 个餐食",
                input_payload={"constraints": [item.model_dump(mode="json", by_alias=True) for item in context.decision.constraints]},
                output_payload={"counts": counts, "eliminated": ranking_diagnostics.get("eliminated", [])},
            )
            context.trace.node(
                "Ranking",
                "operation",
                "success",
                f"复用候选池完成 {counts.get('remaining', before_selection_count)} 个餐食排序",
                input_payload={"criteria": [item.model_dump(mode="json", by_alias=True) for item in context.decision.criteria]},
                output_payload={"ranked": ranking_diagnostics.get("ranked", [])},
            )
            context.trace.node(
                "Selection",
                "operation",
                "success",
                f"按选择策略选出 {len(ranked_candidates)} 个餐食",
                input_payload={
                    "positiveScoreCount": positive_count,
                    "topLimit": 10,
                    "strategy": context.data.get("selection_strategy", "ranked"),
                    "recentRecommendationIds": context.data.get("recent_recommendation_ids", []),
                    "avoidRecentCount": context.data.get("avoid_recent_count", 0),
                },
                output_payload={"orderedIds": selection.ordered_ids, "insights": selection.insights.as_dict()},
            )
        transition_decision(
            context.decision, DecisionStatus.COMPARING, DecisionNextAction.COMPARE_CANDIDATES
        )
        return {"candidateCount": len(ranked_candidates), "reusedCandidatePool": True}

    def compose(self, context: AgentContext) -> dict[str, Any]:
        if self.repository is None:
            raise RuntimeError("DietMealPlanCompositionStrategy 需要 DietRepository")
        return DietMealPlanCompositionStrategy(self.repository).execute(context)

    def critic(self, context: AgentContext) -> dict[str, Any]:
        return DietCandidateCriticPolicy().evaluate(context)

    def explain(self, context: AgentContext) -> dict[str, Any]:
        return ExplanationAgent(self.provider, self.settings.main_model).execute(context)

    def pre_safety(self, context: AgentContext) -> dict[str, Any]:
        context.decision.candidates = []
        context.decision.recommendation = None
        context.decision.composition = None
        context.data["display_blocks"] = []
        context.data["speech_text"] = ""
        return DietHealthRiskPolicy().evaluate(context)

    def post_safety(self, context: AgentContext) -> dict[str, Any]:
        result = DietHealthRiskPolicy().evaluate(context)
        if not result.get("passed", True):
            context.decision.candidates = []
            context.decision.recommendation = None
            context.decision.composition = None
        return result

    def adjust(self, context: AgentContext) -> dict[str, Any]:
        return AdjustmentAgent().execute(context)

    def should_run_pre_safety(self, context: AgentContext) -> bool:
        return context.decision.intent == Intent.HEALTH_RISK

    def should_stop_after_understanding(self, context: AgentContext) -> bool:
        return context.decision.intent == Intent.OTHER

    def should_adjust(self, context: AgentContext) -> bool:
        return context.decision.intent == Intent.MEAL_ADJUST

    def should_clarify(self, context: AgentContext) -> bool:
        return bool(context.data.get("field_conflicts")) or context.decision.intent not in {Intent.MEAL_ADJUST, Intent.MEAL_PLAN}

    def is_clarifying(self, result: dict[str, Any], context: AgentContext) -> bool:
        return result.get("action") == ClarifyAction.ASK.value

    def should_compose(self, context: AgentContext) -> bool:
        return context.decision.intent == Intent.MEAL_PLAN

    def phase(self, context: AgentContext) -> str:
        if context.decision.intent == Intent.OTHER:
            return "START"
        if context.decision.intent == Intent.MEAL_PLAN:
            return "PLAN"
        return "RECOMMEND"

    def display_blocks(self, context: AgentContext) -> list[dict[str, Any]]:
        blocks = context.data.get("display_blocks", context.decision.domain_state.get("displayBlocks", []))
        return [item.model_dump(mode="json", by_alias=True) if hasattr(item, "model_dump") else item for item in blocks]
