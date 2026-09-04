from __future__ import annotations

from abc import abstractmethod
from typing import Any

from choice_agent.agents.base import AgentContext
from choice_agent.decision.evidence import EvidenceValidator
from choice_agent.decision.ranking import CriterionEvaluator, GenericRankingEngine
from choice_agent.decision.state_machine import transition_decision
from choice_agent.domains.profile import DomainProfile
from choice_agent.providers.candidates import CandidateProvider, CompositeCandidateProvider, ManualCandidateProvider
from choice_agent.schemas import (
    Assumption, Candidate, Constraint, Criterion, DecisionNextAction, DecisionStatus,
    Recommendation, RecommendationPoint, UnansweredQuestion,
)


class ComparisonProfile(DomainProfile):
    criteria: list[Criterion]
    clarification_question = "还需要一些信息才能开始比较。"

    def __init__(
        self,
        provider: CandidateProvider,
        evaluator: CriterionEvaluator,
        web_provider: CandidateProvider | None = None,
    ):
        self.candidate_provider = provider
        self.web_provider = web_provider
        self.evaluator = evaluator
        self.ranking = GenericRankingEngine()
        self.evidence_validator = EvidenceValidator()

    def intent(self, context: AgentContext) -> dict[str, Any]:
        from choice_agent.agents.conversation import interpret
        result = interpret(context, context.data.get("model_provider"), context.data.get("model_name"))
        context.decision.intent_key = result["intent"]
        return result

    def understand(self, context: AgentContext) -> dict[str, Any]:
        decision = context.decision
        decision.domain = self.key
        if not decision.user_goal:
            decision.user_goal = context.message
        decision.criteria = self._merge_criteria(decision.criteria)
        from choice_agent.decision.conversation import sync_dependencies
        sync_dependencies(decision, self.criteria)
        decision.assumptions = [
            Assumption(key="provider", value=self.candidate_provider.name, confidence=1.0)
        ]
        decision.domain_state["intent"] = decision.intent_key
        return {
            "goal": decision.user_goal,
            "constraints": [item.model_dump(by_alias=True) for item in decision.constraints],
            "criteria": [item.model_dump(by_alias=True) for item in decision.criteria],
        }

    def clarify(self, context: AgentContext) -> dict[str, Any]:
        if context.data.get("conversation_question") or self.needs_clarification(context):
            question = context.data.get("conversation_question") or self.clarification_question
            context.decision.clarifying_questions = [question]
            context.decision.unanswered_questions = [
                UnansweredQuestion(key=f"{self.key}_context", question=question, asked_by="ClarificationAgent")
            ]
            transition_decision(context.decision, DecisionStatus.CLARIFYING, DecisionNextAction.ASK_CLARIFY)
            context.data["speech_text"] = question
            context.data["display_blocks"] = []
            context.decision.recommendation = None
            return {"action": "ASK", "questionToAsk": question}
        context.decision.clarifying_questions = []
        context.decision.unanswered_questions = []
        context.decision.next_action = DecisionNextAction.SEARCH_CANDIDATES
        return {"action": "READY", "questionToAsk": None}

    def source_and_rank(self, context: AgentContext) -> dict[str, Any]:
        if context.data.get("is_hypothetical"):
            return self.rerank(context)
        result = self._search(context)
        manual = ManualCandidateProvider().search(context)
        result = CompositeCandidateProvider.merge([result, manual])
        candidates, evidence, validation_warnings = self.evidence_validator.validate(
            result.candidates, result.sources
        )
        if result.run:
            context.decision.search_runs.append(result.run)
        context.decision.sources = result.sources
        context.decision.evidence = evidence
        context.decision.domain_state["candidatePool"] = [
            item.model_dump(mode="json", by_alias=True) for item in candidates
        ]
        context.decision.domain_state["source"] = {
            "mode": result.run.mode if result.run else "manual",
            "label": result.sources[0].title if result.sources else "手工候选",
            "realTime": bool(result.run and result.run.mode == "web"),
            "warnings": [*result.warnings, *validation_warnings],
        }
        context.decision.candidates = self.ranking.rank(context.decision, candidates, self.evaluator)
        transition_decision(context.decision, DecisionStatus.COMPARING, DecisionNextAction.COMPARE_CANDIDATES)
        return {
            "provider": self.candidate_provider.name,
            "candidateCount": len(context.decision.candidates),
            "candidates": [
                {"id": item.candidate_id, "name": item.name, "score": item.score}
                for item in context.decision.candidates
            ],
        }

    def rerank(self, context: AgentContext) -> dict[str, Any]:
        pool = [
            Candidate.model_validate(item)
            for item in context.decision.domain_state.get("candidatePool", [])
        ]
        context.decision.candidates = self.ranking.rank(
            context.decision, pool, self.evaluator
        )
        transition_decision(
            context.decision, DecisionStatus.COMPARING, DecisionNextAction.COMPARE_CANDIDATES
        )
        return {
            "candidateCount": len(context.decision.candidates),
            "reusedCandidatePool": True,
        }

    def critic(self, context: AgentContext) -> dict[str, Any]:
        candidates = context.decision.candidates
        ids = [item.candidate_id for item in candidates]
        issues: list[str] = []
        if len(ids) != len(set(ids)):
            issues.append("候选项存在重复")
        if any(item.score < 0 or item.score > 1 for item in candidates):
            issues.append("候选评分超出范围")
        return {"passed": not issues, "issues": issues}

    def explain(self, context: AgentContext) -> dict[str, Any]:
        from choice_agent.decision.assistance import explain
        return explain(context, self)

    def display_blocks(self, context: AgentContext) -> list[dict[str, Any]]:
        if context.decision.status == DecisionStatus.CLARIFYING: return []
        return [
            {
                "id": candidate.candidate_id,
                "name": candidate.name,
                "score": candidate.score,
                "summary": candidate.summary,
                "facts": [f for f in context.decision.domain_state.get("assistance", {}).get("facts", []) if f["candidateId"] == candidate.candidate_id],
                "attributes": candidate.attributes,
                "scoreBreakdown": [item.model_dump(by_alias=True) for item in candidate.score_breakdown],
                "evidence": [item.model_dump(mode="json", by_alias=True) for item in candidate.evidence],
            }
            for candidate in context.decision.candidates
        ]

    def _search(self, context: AgentContext):
        mode = str(context.decision.context.get("searchMode", "fixture")).lower()
        if mode == "web":
            if self.web_provider is None:
                raise RuntimeError("当前领域未配置 Web Search")
            return self.web_provider.search(context)
        if mode == "auto" and self.web_provider is not None and getattr(self.web_provider, "enabled", False):
            try:
                return self.web_provider.search(context)
            except RuntimeError as error:
                result = self.candidate_provider.search(context)
                result.warnings.append(f"Web Search 失败，已回退 fixture：{error}")
                return result
        return self.candidate_provider.search(context)

    def _merge_criteria(self, current: list[Criterion]) -> list[Criterion]:
        weights = {item.key: item.weight for item in current}
        return [item.model_copy(update={"weight": weights.get(item.key, item.weight)}) for item in self.criteria]

    def needs_clarification(self, context: AgentContext) -> bool:
        return max(len(context.message.strip()), len(context.decision.user_goal.strip())) < 6

    @abstractmethod
    def constraints(self, message: str, current: list[Constraint]) -> list[Constraint]:
        raise NotImplementedError