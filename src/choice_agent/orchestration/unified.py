from __future__ import annotations

from choice_agent.agents.base import AgentContext, AgentRuntime
from choice_agent.agents.stages import StageRunResult, StageRunner
from choice_agent.domains.profile import DomainProfile
from choice_agent.services.trace import TraceScope


class UnifiedDecisionOrchestrator:
    """Runs the lifecycle extracted from the original complete Diet workflow."""

    def __init__(self, runner: StageRunner | None = None):
        self.runner = runner or StageRunner()

    def run(
        self,
        profile: DomainProfile,
        context: AgentContext,
        trace: TraceScope,
    ) -> StageRunResult:
        return self.runner.run(profile, context, AgentRuntime(trace))
    def recompute(
        self,
        profile: DomainProfile,
        context: AgentContext,
        trace: TraceScope,
        refresh_candidates: bool = False,
    ) -> StageRunResult:
        return self.runner.recompute(
            profile, context, AgentRuntime(trace), refresh_candidates
        )
