from __future__ import annotations

from choice_agent.decision.engine import DecisionEngine
from choice_agent.domains.base import DomainMetadata, DomainPlugin
from choice_agent.domains.diet.rules import classify_intent
from choice_agent.schemas import Candidate, DecisionState, Recommendation


class DietDomain(DomainPlugin):
    metadata = DomainMetadata(
        key="diet",
        label="饮食决策",
        description="完整饮食推荐、澄清、计划、风险和评估领域。",
        complete=True,
    )

    def matches(self, message: str) -> bool:
        intent, _ = classify_intent(message, False)
        return intent.value != "OTHER"

    def understand(self, decision: DecisionState, message: str) -> None:
        decision.domain = self.key
        decision.user_goal = message
        decision.criteria = list(DecisionEngine.criteria)
        decision.domain_state["compatibility"] = {
            "api": "/api/v1/diet/chat",
            "orchestrator": "DietOrchestrator",
            "status": "complete_domain_compatibility_path",
        }

    def clarify(self, decision: DecisionState, message: str) -> bool:
        return False

    def candidates(self, decision: DecisionState, message: str) -> list[Candidate]:
        return []

    def rank(self, decision: DecisionState, candidates: list[Candidate]) -> list[Candidate]:
        return candidates

    def explain(self, decision: DecisionState, ranked: list[Candidate]) -> Recommendation:
        return Recommendation(
            summary="饮食领域当前通过完整兼容链路 /api/v1/diet/chat 运行。"
        )