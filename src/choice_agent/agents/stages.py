from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from choice_agent.agents.base import AgentContext, AgentRuntime, BaseAgent
from choice_agent.domains.profile import DomainProfile, StageHandler


class ProfileStage(BaseAgent):
    def __init__(self, name: str, handler: StageHandler):
        self.name = name
        self.handler = handler

    def execute(self, context: AgentContext) -> dict[str, Any]:
        return self.handler(context)


@dataclass(frozen=True)
class StageRunResult:
    outcome: str
    phase: str


class StageRunner:
    """The single decision-stage scheduler, extracted from the Diet pipeline."""

    def run(self, profile: DomainProfile, context: AgentContext, runtime: AgentRuntime) -> StageRunResult:
        runtime.run(ProfileStage("IntentAgent", profile.intent), context)
        context.emit_progress("understanding_requirements", "正在理解你的需求")
        runtime.run(ProfileStage("UnderstandingAgent", profile.understand), context)

        if profile.should_run_pre_safety(context):
            runtime.run(ProfileStage("RiskAgent", profile.pre_safety), context)
            return StageRunResult("answer", profile.phase(context))
        if profile.should_stop_after_understanding(context):
            return StageRunResult("answer", profile.phase(context))
        if profile.should_adjust(context):
            runtime.run(ProfileStage("AdjustmentAgent", profile.adjust), context)
        if profile.should_clarify(context):
            result = runtime.run(ProfileStage("ClarificationAgent", profile.clarify), context)
            if profile.is_clarifying(result, context):
                return StageRunResult("clarify", "CLARIFY")
        if profile.should_compose(context):
            runtime.run(ProfileStage("PlanningAgent", profile.compose), context)
        else:
            runtime.run(ProfileStage("CandidateAgent", profile.source_and_rank), context)

        critic = runtime.run(ProfileStage("CriticAgent", profile.critic), context)
        if not critic.get("passed", False):
            raise RuntimeError("候选审查失败：" + "；".join(critic.get("issues", [])))
        runtime.run(ProfileStage("ExplanationAgent", profile.explain), context)
        if profile.capabilities.post_safety:
            runtime.run(ProfileStage("RiskAgent", profile.post_safety), context)
        return StageRunResult("answer", profile.phase(context))
    def recompute(
        self,
        profile: DomainProfile,
        context: AgentContext,
        runtime: AgentRuntime,
        refresh_candidates: bool,
    ) -> StageRunResult:
        if profile.should_run_pre_safety(context):
            runtime.run(ProfileStage("RiskAgent", profile.pre_safety), context)
            return StageRunResult("answer", profile.phase(context))
        handler = profile.source_and_rank if refresh_candidates else profile.rerank
        stage_name = "CandidateAgent" if refresh_candidates else "RankAgent"
        if profile.should_compose(context):
            handler, stage_name = profile.compose, "PlanningAgent"
        runtime.run(ProfileStage(stage_name, handler), context)
        critic = runtime.run(ProfileStage("CriticAgent", profile.critic), context)
        if not critic.get("passed", False):
            raise RuntimeError("候选审查失败：" + "；".join(critic.get("issues", [])))
        runtime.run(ProfileStage("ExplanationAgent", profile.explain), context)
        if profile.capabilities.post_safety:
            runtime.run(ProfileStage("RiskAgent", profile.post_safety), context)
        return StageRunResult("answer", profile.phase(context))
