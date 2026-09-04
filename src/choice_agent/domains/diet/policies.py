from __future__ import annotations

from typing import Any

from choice_agent.agents.base import AgentContext
from choice_agent.agents.diet import CriticAgent, RiskAgent


class DietCandidateCriticPolicy:
    def evaluate(self, context: AgentContext) -> dict[str, Any]:
        return CriticAgent().execute(context)


class DietHealthRiskPolicy:
    def evaluate(self, context: AgentContext) -> dict[str, Any]:
        return RiskAgent().execute(context)