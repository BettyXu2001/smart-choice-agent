from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from choice_agent.agents.base import AgentContext, AgentRuntime, BaseAgent
from choice_agent.decision.execution import ExecutionMode, plan_execution
from choice_agent.decision.validation import validate_recommendation
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


MAX_CRITIC_RECOVERY_ATTEMPTS = 1


class StageRunner:
    """Plan and execute the minimum safe decision-stage path for each turn."""

    def run(self, profile: DomainProfile, context: AgentContext, runtime: AgentRuntime) -> StageRunResult:
        executed: list[str] = []
        if not context.data.get("skip_interpretation"):
            runtime.run(ProfileStage("IntentAgent", profile.intent), context)
            executed.append("intent")
            context.emit_progress("understanding_requirements", "正在理解你的需求")
            runtime.run(ProfileStage("UnderstandingAgent", profile.understand), context)
            executed.append("understanding")

            if profile.should_run_pre_safety(context):
                runtime.run(ProfileStage("RiskAgent", profile.pre_safety), context)
                executed.append("pre_safety")
                self._record_terminal_path(context, "pre_safety", executed)
                return StageRunResult("answer", profile.phase(context))
            if profile.should_stop_after_understanding(context):
                self._skip(context, "Candidate Retrieval", "理解阶段已给出答复，后续候选检索跳过")
                return StageRunResult("answer", profile.phase(context))
            if profile.should_adjust(context):
                runtime.run(ProfileStage("AdjustmentAgent", profile.adjust), context)
                executed.append("adjustment")
            if profile.should_clarify(context):
                result = runtime.run(ProfileStage("ClarificationAgent", profile.clarify), context)
                executed.append("clarification")
                if profile.is_clarifying(result, context):
                    self._skip(context, "Candidate Retrieval", "需要先补充关键信息，候选检索跳过")
                    self._record_terminal_path(context, "blocking_clarification", executed)
                    return StageRunResult("clarify", "CLARIFY")
            else:
                self._skip(context, "Constraint Update", "当前轮次无需澄清")

        if context.data.get("skip_interpretation") and profile.should_run_pre_safety(context):
            runtime.run(ProfileStage("RiskAgent", profile.pre_safety), context)
            executed.append("pre_safety")
            self._record_terminal_path(context, "pre_safety", executed)
            return StageRunResult("answer", profile.phase(context))

        if context.data.get("requires_command_clarification") and profile.key != "diet":
            if profile.should_clarify(context):
                result = runtime.run(ProfileStage("ClarificationAgent", profile.clarify), context)
                executed.append("clarification")
                if profile.is_clarifying(result, context):
                    self._skip(context, "Candidate Retrieval", "需要先补充关键信息，候选检索跳过")
                    self._record_terminal_path(context, "blocking_clarification", executed)
                    return StageRunResult("clarify", "CLARIFY")

        plan = plan_execution(
            profile,
            context.decision,
            context.data.get("execution_baseline"),
            context.data,
        )
        self._record_plan(context, plan)
        context.emit_progress("execution_planned", f"按 {plan.mode.value} 路径执行", executionMode=plan.mode.value, plannedPath=list(plan.planned_path))

        if plan.mode in {ExecutionMode.FULL, ExecutionMode.REFRESH}:
            handler, stage_name, step = profile.source_and_rank, "CandidateAgent", "candidate_refresh"
            if profile.should_compose(context):
                handler, stage_name, step = profile.compose, "PlanningAgent", "composition"
            runtime.run(ProfileStage(stage_name, handler), context)
            executed.append(step)
            self._critic(profile, context, runtime, executed)
        elif plan.mode == ExecutionMode.RERANK:
            handler, stage_name, step = profile.rerank, "RankAgent", "rerank"
            if profile.should_compose(context):
                handler, stage_name, step = profile.compose, "PlanningAgent", "composition"
            runtime.run(ProfileStage(stage_name, handler), context)
            executed.append(step)
            self._critic(profile, context, runtime, executed)
        else:
            self._skip(context, "Candidate Retrieval", plan.reason)
            self._skip(context, "Ranking", plan.reason)
            self._skip(context, "CriticAgent", plan.reason)

        status_before = context.decision.status
        next_action_before = context.decision.next_action
        context.emit_progress("explaining_recommendation", "正在整理结论与依据", executionMode=plan.mode.value)
        runtime.run(ProfileStage("ExplanationAgent", profile.explain), context)
        executed.append("what_if" if plan.mode == ExecutionMode.WHAT_IF else "explanation")
        if plan.mode == ExecutionMode.WHAT_IF:
            context.decision.status = status_before
            context.decision.next_action = next_action_before

        context.emit_progress("validating_recommendation", "正在校验推荐一致性", executionMode=plan.mode.value)
        self._validate(context, executed)
        if profile.capabilities.post_safety:
            runtime.run(ProfileStage("RiskAgent", profile.post_safety), context)
            executed.append("safety")
        if context.trace:
            context.trace.metadata["executedPath"] = executed
            context.trace.turn_summary["executedPath"] = executed
            pool_summary = context.trace.metadata.get("candidatePool", {})
            pool_summary.update({
                "candidateCount": len(context.decision.domain_state.get("candidatePool", [])),
                "evidenceCount": len(context.decision.evidence),
                "searchRunCount": len(context.decision.search_runs),
            })
            context.trace.metadata["candidatePool"] = pool_summary
        context.emit_progress("recommendation_ready", "决策结果已就绪", executionMode=plan.mode.value, status=context.decision.status.value)
        return StageRunResult("answer", profile.phase(context))

    def recompute(
        self,
        profile: DomainProfile,
        context: AgentContext,
        runtime: AgentRuntime,
        refresh_candidates: bool,
    ) -> StageRunResult:
        context.data["skip_interpretation"] = True
        context.data["requested_execution_mode"] = (
            ExecutionMode.REFRESH if refresh_candidates else ExecutionMode.RERANK
        )
        return self.run(profile, context, runtime)

    @staticmethod
    def _record_terminal_path(context: AgentContext, mode: str, executed: list[str]) -> None:
        if not context.trace:
            return
        context.trace.metadata.update({
            "executionMode": mode,
            "plannedPath": list(executed),
            "executedPath": list(executed),
            "skipReasons": {"candidate_refresh": "阻塞性澄清尚未完成" if mode == "blocking_clarification" else "风险预检查已终止后续执行"},
        })
        context.trace.turn_summary.update({
            "executionMode": mode,
            "plannedPath": list(executed),
            "executedPath": list(executed),
        })

    @staticmethod
    def _critic(profile, context, runtime, executed: list[str]) -> None:
        critic = runtime.run(ProfileStage("CriticAgent", profile.critic), context)
        executed.append("critic")
        if critic.get("passed", False):
            return

        attempts = int(context.data.get("critic_recovery_attempts", 0))
        issues = list(critic.get("issues", []))
        issue_codes = list(critic.get("issueCodes", []))
        if attempts >= MAX_CRITIC_RECOVERY_ATTEMPTS:
            raise RuntimeError("候选审查恢复失败（已重试 1 次）：" + "；".join(issues))

        context.data["critic_recovery_attempts"] = attempts + 1
        action = StageRunner._recover_critic_failure(
            profile, context, runtime, executed, issue_codes
        )
        retry = runtime.run(ProfileStage("CriticAgent", profile.critic), context)
        executed.append("critic_retry")
        recovered = bool(retry.get("passed", False))
        context.data["critic_recovery"] = {
            "attempts": attempts + 1,
            "action": action,
            "issues": issues,
            "issueCodes": issue_codes,
            "recovered": recovered,
        }
        if context.trace:
            context.trace.node(
                "Critic Recovery",
                "operation",
                "success" if recovered else "failed",
                "候选审查定向恢复成功" if recovered else "候选审查定向恢复后仍失败",
                input_payload={"issues": issues, "issueCodes": issue_codes, "maxAttempts": MAX_CRITIC_RECOVERY_ATTEMPTS},
                output_payload={"action": action, "retry": retry},
            )
        if not recovered:
            retry_issues = list(retry.get("issues", [])) or issues
            raise RuntimeError("候选审查恢复失败（已重试 1 次）：" + "；".join(retry_issues))

    @staticmethod
    def _recover_critic_failure(profile, context, runtime, executed: list[str], issue_codes: list[str]) -> str:
        known_local = {"duplicate_candidate", "score_out_of_range", "excluded_candidate"}
        pool = context.decision.domain_state.get("candidatePool", [])
        if "duplicate_candidate" in issue_codes:
            deduped_pool = []
            seen_pool = set()
            for item in pool:
                candidate_id = str(item.get("candidateId") or item.get("candidate_id") or item.get("id") or "")
                if candidate_id and candidate_id in seen_pool:
                    continue
                if candidate_id:
                    seen_pool.add(candidate_id)
                deduped_pool.append(item)
            context.decision.domain_state["candidatePool"] = deduped_pool
            deduped_candidates = []
            seen_candidates = set()
            for item in context.decision.candidates:
                if item.candidate_id in seen_candidates:
                    continue
                seen_candidates.add(item.candidate_id)
                deduped_candidates.append(item)
            context.decision.candidates = deduped_candidates

        if profile.should_compose(context):
            action = "compose"
            runtime.run(ProfileStage("PlanningAgent", profile.compose), context)
            executed.append("critic_recovery_compose")
        elif pool and (not issue_codes or set(issue_codes).issubset(known_local)):
            action = "rerank"
            runtime.run(ProfileStage("RankAgent", profile.rerank), context)
            executed.append("critic_recovery_rerank")
        else:
            action = "refresh"
            runtime.run(ProfileStage("CandidateAgent", profile.source_and_rank), context)
            executed.append("critic_recovery_refresh")

        if context.trace:
            context.trace.fallback(
                stage="Critic Recovery",
                reason="Critic 首次审查失败，执行一次定向恢复",
                from_path="critic_failed",
                to_path=action,
                details={"issueCodes": issue_codes, "attempt": 1, "maxAttempts": MAX_CRITIC_RECOVERY_ATTEMPTS},
            )
        return action

    @staticmethod
    def _validate(context: AgentContext, executed: list[str]) -> None:
        before = context.trace.snapshot(context.decision) if context.trace else None
        node_id = context.trace.start_node(
            "Final Validation", "operation", "校验正式推荐不变量"
        ) if context.trace else None
        try:
            result = validate_recommendation(context.decision)
        except Exception as error:
            if context.trace and node_id:
                context.trace.finish_node(node_id, "failed", error=str(error))
            raise
        if context.trace and node_id:
            context.trace.finish_node(
                node_id,
                "success",
                output_payload=result,
                changes=context.trace.diff(before, context.decision) if before else [],
            )
        executed.append("validation")

    @staticmethod
    def _record_plan(context: AgentContext, plan) -> None:
        context.data["execution_plan"] = plan
        if not context.trace:
            return
        pool = context.decision.domain_state.get("candidatePool", [])
        source = context.decision.domain_state.get("source", {})
        pool_summary = {
            "candidateCount": len(pool),
            "reused": plan.mode in {ExecutionMode.RERANK, ExecutionMode.EXPLAIN_ONLY, ExecutionMode.WHAT_IF},
            "sourceMode": source.get("mode"),
            "evidenceCount": len(context.decision.evidence),
            "searchRunCount": len(context.decision.search_runs),
        }
        context.trace.metadata.update({
            "executionMode": plan.mode.value,
            "plannedPath": list(plan.planned_path),
            "skipReasons": plan.skip_reasons,
            "candidatePool": pool_summary,
        })
        context.trace.turn_summary.update({
            "executionMode": plan.mode.value,
            "planReason": plan.reason,
            "plannedPath": list(plan.planned_path),
        })
        context.trace.node(
            "Execution Plan",
            "operation",
            "success",
            plan.reason,
            output_payload={
                "mode": plan.mode.value,
                "plannedPath": list(plan.planned_path),
                "skipReasons": plan.skip_reasons,
            },
        )

    @staticmethod
    def _skip(context: AgentContext, stage: str, reason: str) -> None:
        if context.trace:
            context.trace.node(
                stage,
                "operation",
                "skipped",
                reason,
                input_payload={"domain": context.decision.domain},
                output_payload={"status": context.decision.status.value},
            )
