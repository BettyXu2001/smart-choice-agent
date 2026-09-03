from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from choice_agent.agents.base import AgentContext, AgentRuntime, BaseAgent
from choice_agent.decision.state_machine import assert_expected_revision, transition_decision
from choice_agent.domains.base import DomainPlugin, DomainRunResult
from choice_agent.domains.registry import DomainRegistry
from choice_agent.repositories.decision_repository import DecisionRepository
from choice_agent.schemas import (
    CandidateState,
    DecisionNextAction,
    DecisionState,
    DecisionStatus,
    GenericDecisionMessageRequest,
    GenericDecisionRequest,
    GenericDecisionResponse,
    TraceReference,
)
from choice_agent.services.trace import TraceScope


class DomainPipelineAgent(BaseAgent):
    def __init__(self, plugin: DomainPlugin):
        self.plugin = plugin
        self.name = f"{plugin.label}PipelineAgent"

    def execute(self, context: AgentContext) -> dict:
        decision = context.decision
        message = context.message
        self.plugin.understand(decision, message)
        if self.plugin.clarify(decision, message):
            return {"domain": self.plugin.key, "status": decision.status.value, "candidateCount": 0}
        ranked = self.plugin.rank(decision, self.plugin.candidates(decision, message))
        decision.candidates = ranked
        decision.candidate_state = {
            candidate.candidate_id: CandidateState(status="active", updated_by=self.name)
            for candidate in ranked
        }
        decision.evidence = [evidence for candidate in ranked for evidence in candidate.evidence]
        decision.recommendation = self.plugin.explain(decision, ranked)
        transition_decision(decision, DecisionStatus.DECIDED, DecisionNextAction.WAIT_USER)
        return {
            "domain": self.plugin.key,
            "status": decision.status.value,
            "candidateCount": len(ranked),
            "primaryCandidateId": decision.recommendation.primary_candidate_id if decision.recommendation else None,
        }


class GenericDecisionOrchestrator:
    def __init__(self, db: Session, registry: DomainRegistry | None = None):
        self.db = db
        self.registry = registry or DomainRegistry()
        self.repository = DecisionRepository(db)

    def create(self, user_id: int, request: GenericDecisionRequest) -> GenericDecisionResponse:
        if not request.message.strip():
            raise ValueError("message 不能为空")
        plugin = self.registry.resolve(request.message, request.domain)
        decision = DecisionState(
            decision_id=uuid4().hex,
            session_id=uuid4().hex,
            domain=plugin.key,
            user_goal=request.message.strip(),
        )
        return self._run(user_id, plugin, decision, request.message.strip(), None)

    def message(
        self, user_id: int, decision_id: str, request: GenericDecisionMessageRequest
    ) -> GenericDecisionResponse:
        if not request.message.strip():
            raise ValueError("message 不能为空")
        decision = self.repository.get(decision_id)
        if decision is None:
            raise KeyError("Decision 不存在")
        assert_expected_revision(decision.revision, request.expected_revision)
        plugin = self.registry.get(decision.domain)
        decision.user_goal = request.message.strip()
        decision.domain_state.setdefault("messages", []).append({"role": "user", "content": request.message.strip()})
        return self._run(user_id, plugin, decision, request.message.strip(), request.expected_revision)

    def _run(
        self,
        user_id: int,
        plugin: DomainPlugin,
        decision: DecisionState,
        message: str,
        expected_revision: int | None,
    ) -> GenericDecisionResponse:
        trace_id = uuid4().hex
        decision.trace_refs = [*decision.trace_refs, TraceReference(trace_id=trace_id, event_type="REQUEST")]
        with TraceScope(self.db, trace_id, decision.session_id, user_id) as trace:
            trace.event(
                "REQUEST_RECEIVED",
                "GENERIC_DECISION",
                {"message": message, "expectedRevision": expected_revision},
                {"domain": plugin.key},
            )
            runtime = AgentRuntime(trace)
            context = AgentContext(
                session_id=decision.session_id,
                trace_id=trace_id,
                user_id=user_id,
                message=message,
                decision=decision,
                data={"domain": plugin.key},
            )
            runtime.run(DomainPipelineAgent(plugin), context)
            decision.revision += 1
            self.repository.save(decision)
            result = DomainRunResult(
                speech_text=decision.recommendation.summary if decision.recommendation else "需要更多信息。",
                display_blocks=plugin.display_blocks(decision),
            )
        return GenericDecisionResponse(
            decision_state=decision,
            trace_id=trace_id,
            speech_text=result.speech_text,
            display_blocks=result.display_blocks,
        )