from __future__ import annotations

from abc import abstractmethod
from typing import Any

from choice_agent.agents.base import AgentContext
from choice_agent.decision.evidence import EvidenceValidator, sync_decision_evidence
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
        retained_assumptions = [item for item in decision.assumptions if item.key != "provider"]
        decision.assumptions = [
            *retained_assumptions,
            Assumption(key="provider", value=self.candidate_provider.name, confidence=1.0),
        ]
        decision.domain_state["intent"] = decision.intent_key
        return {
            "goal": decision.user_goal,
            "constraints": [item.model_dump(by_alias=True) for item in decision.constraints],
            "criteria": [item.model_dump(by_alias=True) for item in decision.criteria],
        }

    def clarification_prompt(self, context: AgentContext) -> str:
        return self.clarification_question

    def clarify(self, context: AgentContext) -> dict[str, Any]:
        blocking_question = context.data.get("blocking_question")
        if blocking_question or self.needs_clarification(context):
            question = blocking_question or self.clarification_prompt(context)
            context.decision.clarifying_questions = [question]
            context.decision.unanswered_questions = [
                UnansweredQuestion(key=f"{self.key}_context", question=question, asked_by="ClarificationAgent")
            ]
            transition_decision(context.decision, DecisionStatus.CLARIFYING, DecisionNextAction.ASK_CLARIFY)
            context.data["speech_text"] = question
            context.data["display_blocks"] = []
            context.decision.recommendation = None
            from choice_agent.decision.assistance import state
            info = state(context.decision)
            info.pop("analysis", None)
            info.pop("currentAnalysis", None)
            info["lastQuestion"] = question
            return {"action": "ASK", "questionToAsk": question}
        context.decision.clarifying_questions = []
        context.decision.unanswered_questions = []
        context.decision.next_action = DecisionNextAction.SEARCH_CANDIDATES
        return {"action": "READY", "questionToAsk": None}

    def source_and_rank(self, context: AgentContext) -> dict[str, Any]:
        if context.data.get("is_hypothetical"):
            return self.rerank(context)
        mode = str(context.decision.context.get("searchMode", "fixture")).lower()
        source_mode = "web" if mode == "web" else "fixture"
        context.emit_progress("searching_candidates", "正在寻找候选", sourceMode=source_mode)
        result = self._search(context)
        manual = ManualCandidateProvider().search(context)
        result = CompositeCandidateProvider.merge([result, manual])
        merged_count = len(result.candidates)
        run_mode = result.run.mode if result.run else "manual"
        if context.trace:
            context.trace.node(
                "Candidate Retrieval",
                "operation",
                "success",
                f"检索到 {merged_count} 个候选",
                input_payload={"mode": mode, "sourceMode": source_mode, "provider": self.candidate_provider.name},
                output_payload={
                    "runMode": run_mode,
                    "candidateCount": merged_count,
                    "candidates": [{"id": item.candidate_id, "name": item.name, "origin": item.origin} for item in result.candidates],
                    "warnings": result.warnings,
                },
                refs={"searchRunId": result.run.run_id if result.run else None},
            )
        context.emit_progress("candidates_found", f"找到 {merged_count} 个候选", counts={"found": merged_count}, sourceMode=run_mode)
        context.emit_progress("validating_evidence", "正在校验证据来源", sourceMode=run_mode)
        candidates, evidence, validation_warnings = self.evidence_validator.validate(
            result.candidates, result.sources
        )
        if context.trace:
            context.trace.node(
                "Evidence",
                "operation",
                "success",
                f"加入 {len(evidence)} 条 Evidence",
                input_payload={"sourceCount": len(result.sources), "candidateCount": len(result.candidates)},
                output_payload={
                    "evidence": [item.model_dump(mode="json", by_alias=True) for item in evidence],
                    "warnings": validation_warnings,
                },
                refs={"sourceIds": [item.source_id for item in result.sources]},
            )
        if result.run:
            context.decision.search_runs.append(result.run)
        context.decision.sources = result.sources
        context.decision.evidence = evidence
        context.decision.domain_state["candidatePool"] = [
            item.model_dump(mode="json", by_alias=True) for item in candidates
        ]
        context.decision.domain_state["source"] = {
            "mode": run_mode,
            "label": self._source_label(run_mode, result.sources),
            "realTime": bool(result.run and result.run.mode == "web"),
            "warnings": [*result.warnings, *validation_warnings],
        }
        ranking_diagnostics: dict[str, Any] = {}
        context.decision.candidates = self.ranking.rank(
            context.decision, candidates, self.evaluator, diagnostics=ranking_diagnostics
        )
        sync_decision_evidence(context.decision)
        self._update_decision_quality(context.decision)
        counts = context.decision.domain_state.get("rankingCounts", {})
        if context.trace:
            context.trace.node(
                "Hard Filter",
                "operation",
                "success",
                f"硬约束排除 {counts.get('hardConstraintExcluded', 0)} 个候选",
                input_payload={"constraints": [item.model_dump(mode="json", by_alias=True) for item in context.decision.constraints]},
                output_payload={
                    "counts": counts,
                    "eliminated": ranking_diagnostics.get("eliminated", []),
                },
            )
            context.trace.node(
                "Ranking",
                "operation",
                "success",
                f"完成 {counts.get('remaining', len(context.decision.candidates))} 个候选排序",
                input_payload={"criteria": [item.model_dump(mode="json", by_alias=True) for item in context.decision.criteria]},
                output_payload={"ranked": ranking_diagnostics.get("ranked", [])},
            )
        context.emit_progress("constraints_applied", f"基于硬约束排除 {counts.get('hardConstraintExcluded', 0)} 个", counts=counts, sourceMode=run_mode)
        context.emit_progress("ranking_candidates", f"正在比较剩余 {counts.get('remaining', len(context.decision.candidates))} 个", counts=counts, sourceMode=run_mode)
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
        context.emit_progress("ranking_candidates", f"正在比较剩余 {len(pool)} 个", sourceMode=context.decision.domain_state.get("source", {}).get("mode"))
        ranking_diagnostics: dict[str, Any] = {}
        context.decision.candidates = self.ranking.rank(
            context.decision, pool, self.evaluator, diagnostics=ranking_diagnostics
        )
        sync_decision_evidence(context.decision)
        self._update_decision_quality(context.decision)
        counts = context.decision.domain_state.get("rankingCounts", {})
        if context.trace:
            context.trace.node(
                "Hard Filter",
                "operation",
                "success",
                f"硬约束排除 {counts.get('hardConstraintExcluded', 0)} 个候选",
                input_payload={"constraints": [item.model_dump(mode="json", by_alias=True) for item in context.decision.constraints]},
                output_payload={"counts": counts, "eliminated": ranking_diagnostics.get("eliminated", [])},
            )
            context.trace.node(
                "Ranking",
                "operation",
                "success",
                f"复用候选池完成 {counts.get('remaining', len(context.decision.candidates))} 个候选排序",
                input_payload={"criteria": [item.model_dump(mode="json", by_alias=True) for item in context.decision.criteria]},
                output_payload={"ranked": ranking_diagnostics.get("ranked", [])},
            )
        context.emit_progress("comparison_ready", f"完成比较，保留 {counts.get('remaining', len(context.decision.candidates))} 个候选", counts=counts, sourceMode=context.decision.domain_state.get("source", {}).get("mode"))
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

    @staticmethod
    def _update_decision_quality(decision) -> None:
        from choice_agent.decision.assistance import state
        from choice_agent.decision.clarification import select_decision_question
        from choice_agent.decision.quality import assess_decision_quality

        decision.quality_assessment = assess_decision_quality(decision)
        info = state(decision)
        question = select_decision_question(decision)
        if question:
            info["decisionQuestion"] = question.model_dump(mode="json", by_alias=True)
        else:
            info.pop("decisionQuestion", None)

    @staticmethod
    def _source_label(mode: str, sources: list[Any]) -> str:
        if mode == "web":
            return "实时 Web Search"
        if mode == "manual":
            return "手工候选"
        if mode == "database":
            return "本地数据库候选"
        return "演示候选数据"

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
                if context.trace:
                    context.trace.fallback(
                        stage="Fallback",
                        reason=f"Web Search 失败，已回退 fixture 候选：{type(error).__name__}: {error}",
                        from_path=f"web_search:{getattr(self.web_provider, 'name', 'web')}",
                        to_path=f"fixture_search:{self.candidate_provider.name}",
                        details={"mode": mode, "error": str(error)},
                    )
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
