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
from choice_agent.decision.selector import SelectionCandidate, select_candidates
from choice_agent.decision.state_machine import transition_decision
from choice_agent.domains.base import DomainMetadata
from choice_agent.domains.diet.composition import DietMealPlanCompositionStrategy
from choice_agent.domains.diet.evaluator import DietCriterionEvaluator
from choice_agent.domains.diet.policies import DietCandidateCriticPolicy, DietHealthRiskPolicy
from choice_agent.domains.diet.rules import classify_intent
from choice_agent.domains.diet.web import (
    DietDisplayCandidate,
    DietWebCandidateProvider,
    normalize_diet_attributes,
    web_display_id,
)
from choice_agent.domains.profile import DomainCapabilities, DomainProfile
from choice_agent.providers.candidates import CandidateProvider, CandidateSearchResult, CompositeCandidateProvider, DietMealProvider
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


_REALTIME_KEYWORDS = (
    "附近", "周边", "附近餐厅", "外卖", "配送", "美团", "饿了么",
    "营业", "开门", "排队", "距离", "现在", "实时", "今天有什么店",
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

    def __init__(
        self,
        repository: DietRepository,
        settings: Settings,
        provider: ModelProvider,
        web_provider: CandidateProvider | None = None,
    ):
        self.repository = repository
        self.settings = settings
        self.provider = provider
        self.web_provider = web_provider
        self.target_candidate_count = 3

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
        result, meta = self._hybrid_recall(context)
        return self._apply_recall_result(context, result, meta, reused_candidate_pool=False)

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
        records = {str(meal.id): meal for meal in self.repository.list_meals(source, context.user_id)}
        context.data["meal_records_by_id"] = records
        current = CandidateSearchResult(
            candidates=pool,
            sources=context.decision.sources,
            evidence=context.decision.evidence,
            warnings=list(context.decision.domain_state.get("source", {}).get("warnings", [])),
        )
        ranked = self._rank_preview(context, current)
        if len(ranked) < self.target_candidate_count and self._web_enabled():
            try:
                web = self._web_search(context, "rerank_insufficient")
                if web.candidates:
                    merged = CompositeCandidateProvider.merge([current, web])
                    meta = {
                        "mode": "hybrid",
                        "label": "餐食库 + 实时 Web Search",
                        "realTime": True,
                        "recallReason": "rerank_web_supplement",
                        "warnings": [*current.warnings, *web.warnings],
                    }
                    return self._apply_recall_result(context, merged, meta, reused_candidate_pool=True)
            except RuntimeError as error:
                current.warnings.append(f"Web Search 失败，已保留餐食库候选：{error}")
                if context.trace:
                    context.trace.fallback(
                        stage="Fallback",
                        reason=f"Diet Web Search 失败，复用当前候选池：{type(error).__name__}: {error}",
                        from_path="diet_web_search",
                        to_path="diet_candidate_pool",
                        details={"error": str(error)},
                    )
        meta = {
            "mode": context.decision.domain_state.get("source", {}).get("mode", "database"),
            "label": context.decision.domain_state.get("source", {}).get("label", "餐食库"),
            "realTime": context.decision.domain_state.get("source", {}).get("realTime", False),
            "recallReason": "reused_candidate_pool",
            "warnings": current.warnings,
        }
        return self._apply_recall_result(context, current, meta, reused_candidate_pool=True)

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

    def _hybrid_recall(self, context: AgentContext) -> tuple[CandidateSearchResult, dict[str, Any]]:
        realtime = self._needs_realtime(context)
        db_result = self._database_search(context)
        if realtime and self._web_enabled():
            try:
                web_result = self._web_search(context, "realtime_web_first")
                if web_result.candidates:
                    return CompositeCandidateProvider.merge([web_result, db_result]), {
                        "mode": "hybrid",
                        "label": "实时 Web Search + 餐食库",
                        "realTime": True,
                        "recallReason": "realtime_web_first",
                        "warnings": [*web_result.warnings, *db_result.warnings],
                    }
            except RuntimeError as error:
                db_result.warnings.append(f"Web Search 失败，已回退餐食库：{error}")
                if context.trace:
                    context.trace.fallback(
                        stage="Fallback",
                        reason=f"Diet Web Search 失败，已回退餐食库：{type(error).__name__}: {error}",
                        from_path="diet_web_search",
                        to_path="diet_database",
                        details={"error": str(error), "realtime": True},
                    )
                return db_result, self._source_meta("database", "web_failed_db_fallback", db_result.warnings)
        preview = self._rank_preview(context, db_result)
        if len(preview) >= self.target_candidate_count or not self._web_enabled():
            return db_result, self._source_meta("database", "db_sufficient", db_result.warnings)
        try:
            web_result = self._web_search(context, "db_insufficient_web_supplement")
            if web_result.candidates:
                return CompositeCandidateProvider.merge([db_result, web_result]), {
                    "mode": "hybrid",
                    "label": "餐食库 + 实时 Web Search",
                    "realTime": False,
                    "recallReason": "db_insufficient_web_supplement",
                    "warnings": [*db_result.warnings, *web_result.warnings],
                }
        except RuntimeError as error:
            db_result.warnings.append(f"Web Search 失败，已保留餐食库候选：{error}")
            if context.trace:
                context.trace.fallback(
                    stage="Fallback",
                    reason=f"Diet Web Search 失败，已保留餐食库候选：{type(error).__name__}: {error}",
                    from_path="diet_web_search",
                    to_path="diet_database",
                    details={"error": str(error), "realtime": False},
                )
        return db_result, self._source_meta("database", "web_failed_db_fallback", db_result.warnings)

    def _database_search(self, context: AgentContext) -> CandidateSearchResult:
        return DietMealProvider(self.repository).search(context)

    def _web_search(self, context: AgentContext, reason: str) -> CandidateSearchResult:
        if not self._web_enabled():
            return CandidateSearchResult(warnings=["Web Search 未配置，已使用餐食库候选"])
        context.data["diet_web_recall_reason"] = reason
        result = DietWebCandidateProvider(self.web_provider).search(context)
        if result.run:
            result.run.mode = "web"
        return result

    def _web_enabled(self) -> bool:
        return bool(self.web_provider and getattr(self.web_provider, "enabled", True))

    def _needs_realtime(self, context: AgentContext) -> bool:
        text = f"{context.message} {context.decision.user_goal}"
        return any(keyword in text for keyword in _REALTIME_KEYWORDS)

    def _source_meta(self, mode: str, reason: str, warnings: list[str]) -> dict[str, Any]:
        labels = {"database": "餐食库", "web": "实时 Web Search", "hybrid": "餐食库 + 实时 Web Search"}
        return {"mode": mode, "label": labels.get(mode, "餐食库"), "realTime": mode == "web", "recallReason": reason, "warnings": warnings}

    def _rank_preview(self, context: AgentContext, result: CandidateSearchResult) -> list[Candidate]:
        candidates, _, _ = EvidenceValidator().validate(result.candidates, result.sources)
        ranked = GenericRankingEngine().rank(
            context.decision,
            candidates,
            DietCriterionEvaluator(),
            tie_breaker=self._tie_breaker,
        )
        if not context.data["slots"].is_empty():
            ranked = [candidate for candidate in ranked if candidate.score > 0]
        return ranked[:10]

    def _apply_recall_result(
        self,
        context: AgentContext,
        result: CandidateSearchResult,
        meta: dict[str, Any],
        reused_candidate_pool: bool,
    ) -> dict[str, Any]:
        candidates, evidence, validation_warnings = EvidenceValidator().validate(result.candidates, result.sources)
        warnings = list(dict.fromkeys([*result.warnings, *validation_warnings, *meta.get("warnings", [])]))
        if context.trace:
            context.trace.node(
                "Candidate Retrieval",
                "operation",
                "success",
                f"检索到 {len(result.candidates)} 个餐食候选",
                input_payload={"sourceMode": context.data["source_mode"], "recallReason": meta.get("recallReason")},
                output_payload={
                    "candidateCount": len(result.candidates),
                    "candidates": [{"id": item.candidate_id, "name": item.name, "origin": item.origin} for item in result.candidates],
                    "warnings": warnings,
                    "sourceMode": meta.get("mode"),
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
                    "warnings": validation_warnings,
                },
                refs={"sourceIds": [item.source_id for item in result.sources]},
            )
        decision = context.decision
        decision.sources = result.sources
        if result.run:
            decision.search_runs.append(result.run)
        decision.domain_state["source"] = {
            "mode": meta.get("mode", "database"),
            "label": meta.get("label", "餐食库"),
            "realTime": bool(meta.get("realTime")),
            "warnings": warnings,
            "recallReason": meta.get("recallReason"),
        }
        ranking_diagnostics: dict[str, Any] = {}
        ranked = GenericRankingEngine().rank(
            decision,
            candidates,
            DietCriterionEvaluator(),
            tie_breaker=self._tie_breaker,
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
                    attributes={"sourceMode": meta.get("mode", "database")},
                )
                for candidate in ranked
            ],
            context.data.get("selection_strategy", "ranked"),
            context.data.get("recent_recommendation_ids", []),
            context.data.get("avoid_recent_count", 0),
        )
        by_id = {candidate.candidate_id: candidate for candidate in ranked}
        ranked_candidates = [by_id[item_id] for item_id in selection.ordered_ids]
        records = context.data.get("meal_records_by_id", {})
        ranked_meals: list[RankedMeal] = []
        display_candidates: list[DietDisplayCandidate] = []
        display_map: dict[str, str] = {}
        for candidate in ranked_candidates:
            record = records.get(candidate.candidate_id)
            if record is not None:
                matched = {
                    field: [value for value in getattr(slots, field) if value in candidate.attributes.get(field, [])]
                    for field in SLOT_FIELDS
                }
                ranked_meals.append(RankedMeal(meal=record, score=candidate.score, matched=matched))
                display_id = int(candidate.candidate_id)
                source_type = SourceMode(record.source_type)
            else:
                display_id = web_display_id(candidate.candidate_id)
                source_type = SourceMode.PUBLIC
            display_candidates.append(DietDisplayCandidate(candidate=candidate, display_id=display_id, source_type=source_type))
            display_map[str(display_id)] = candidate.candidate_id
        context.data["ranked"] = ranked_meals
        context.data["diet_display_candidates"] = display_candidates
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
        decision.domain_state["displayCandidateMap"] = display_map
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
                f"{'复用候选池' if reused_candidate_pool else '完成'} {counts.get('remaining', before_selection_count)} 个餐食排序",
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
                output_payload={"orderedIds": selection.ordered_ids, "insights": selection.insights.as_dict()},
            )
        transition_decision(decision, DecisionStatus.COMPARING, DecisionNextAction.COMPARE_CANDIDATES)
        return {
            "sourceMode": SourceMode(context.data["source_mode"]).value,
            "candidateCount": len(display_candidates),
            "candidates": [
                {"id": item.candidate.candidate_id, "name": item.name, "score": item.score}
                for item in display_candidates
            ],
            "reusedCandidatePool": reused_candidate_pool,
        }

    def _tie_breaker(self, candidate: Candidate):
        if candidate.candidate_id.isdigit():
            return (0, int(candidate.candidate_id))
        return (1, candidate.name, candidate.candidate_id)