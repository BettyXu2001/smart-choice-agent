from __future__ import annotations

from choice_agent.decision.ranking import AttributeCriterionEvaluator
from choice_agent.domains.base import DomainMetadata
from choice_agent.domains.comparison import ComparisonProfile
from choice_agent.providers.candidates import ManualCandidateProvider
from choice_agent.schemas import Criterion, CriterionDirection


class GenericProfile(ComparisonProfile):
    metadata = DomainMetadata(
        key="generic",
        label="通用决策",
        description="以用户提供的候选和评分进行比较，不生成虚构事实。",
        complete=True,
    )
    criteria = [
        Criterion(key="fit", label="目标匹配 (0-100)"),
        Criterion(key="cost", label="成本 (0-100)", direction=CriterionDirection.LOWER_IS_BETTER),
        Criterion(key="risk", label="风险 (0-100)", direction=CriterionDirection.LOWER_IS_BETTER),
    ]
    clarification_question = "你在比较哪些选择？可以直接写“候选：A：优点和顾虑；B：优点和顾虑”，不需要打分。"

    def __init__(self):
        super().__init__(ManualCandidateProvider(), AttributeCriterionEvaluator())

    def matches(self, message: str) -> bool:
        return True

    def constraints(self, message, current):
        return current

    def needs_clarification(self, context) -> bool:
        manual = context.decision.domain_state.get("manualCandidates", [])
        return len(manual) < 2

    def explain(self, context):
        if len(context.decision.domain_state.get("manualCandidates", [])) < 2:
            context.decision.recommendation = None
            return self.clarify(context)
        return super().explain(context)
