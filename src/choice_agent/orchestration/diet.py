from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from choice_agent.agents.base import AgentContext, AgentRuntime
from choice_agent.agents.diet import (
    AdjustmentAgent, CandidateAgent, ClarificationAgent, CriticAgent,
    ExplanationAgent, IntentAgent, PlanningAgent, RiskAgent, UnderstandingAgent,
)
from choice_agent.config import Settings
from choice_agent.db_models import SessionRecord
from choice_agent.decision.engine import DecisionEngine
from choice_agent.providers.model import ModelProvider
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import (
    ChatRequest, ChatResponse, ClarifyAction, DecisionState, Intent,
    SessionPhase, SlotBundle, SourceMode,
)
from choice_agent.services.trace import TraceScope


class DietOrchestrator:
    def __init__(self, db: Session, settings: Settings, provider: ModelProvider):
        self.db = db
        self.settings = settings
        self.repository = DietRepository(db)
        self.engine = DecisionEngine()
        self.provider = provider

    def _session(self, user_id: int, request: ChatRequest) -> SessionRecord:
        if request.session_id:
            row = self.repository.get_session(request.session_id, user_id)
            if row is None:
                raise ValueError("会话不存在或无权访问")
            return row
        return self.repository.create_session(user_id, request.source_mode)

    def chat(self, user_id: int, request: ChatRequest) -> ChatResponse:
        if not request.message.strip():
            raise ValueError("message 不能为空")
        session = self._session(user_id, request)
        session.source_mode = request.source_mode.value
        trace_id = uuid4().hex
        decision = DecisionState(decision_id=uuid4().hex, session_id=session.id)
        recent = [
            {"role": row.role, "content": row.content}
            for row in self.repository.recent_messages(session.id, 6)
        ]

        with TraceScope(self.db, trace_id, session.id, user_id) as trace:
            trace.event("REQUEST_RECEIVED", "HTTP", request, {"sessionId": session.id})
            self.repository.add_message(session.id, "user", request.message, None, trace_id)
            context = AgentContext(
                session_id=session.id,
                trace_id=trace_id,
                user_id=user_id,
                message=request.message,
                decision=decision,
                data={
                    "source_mode": request.source_mode.value,
                    "current_slots": session.slots or {},
                    "last_recommendations": session.last_recommendations or [],
                    "slot_options": self.repository.slot_options(),
                    "recent_messages": recent,
                    "exclude_ids": [],
                },
            )
            runtime = AgentRuntime(trace)
            runtime.run(IntentAgent(self.provider, self.settings.light_model), context)
            runtime.run(UnderstandingAgent(), context)

            if decision.intent == Intent.HEALTH_RISK:
                context.data["speech_text"] = ""
                runtime.run(RiskAgent(), context)
                return self._finish_text(session, context, trace_id, SessionPhase.RECOMMEND)

            if decision.intent == Intent.OTHER:
                context.data["speech_text"] = (
                    "我现在主要帮你做饮食选择。你可以告诉我餐次、口味、场景或健康目标。"
                )
                context.data["display_blocks"] = []
                return self._finish_text(session, context, trace_id, SessionPhase.START)

            if decision.intent == Intent.MEAL_ADJUST:
                runtime.run(AdjustmentAgent(), context)

            if decision.intent not in {Intent.MEAL_ADJUST, Intent.MEAL_PLAN}:
                result = runtime.run(ClarificationAgent(), context)
                if result["action"] == ClarifyAction.ASK.value:
                    return self._finish_clarify(session, context, trace_id)

            if decision.intent == Intent.MEAL_PLAN:
                runtime.run(PlanningAgent(self.repository, self.engine), context)
                phase = SessionPhase.PLAN
            else:
                runtime.run(CandidateAgent(self.repository, self.engine), context)
                phase = SessionPhase.RECOMMEND

            critic = runtime.run(CriticAgent(), context)
            if not critic["passed"]:
                raise RuntimeError("候选审查失败：" + "；".join(critic["issues"]))
            runtime.run(ExplanationAgent(self.provider, self.settings.main_model), context)
            runtime.run(RiskAgent(), context)
            return self._finish_answer(session, context, trace_id, phase)

    def _save_state(self, session: SessionRecord, context: AgentContext, phase: SessionPhase) -> None:
        session.phase = phase.value
        session.current_intent = context.decision.intent.value if context.decision.intent else None
        slots: SlotBundle = context.data.get("slots", SlotBundle())
        session.slots = slots.model_dump(by_alias=True)
        ids = [block.id for block in context.data.get("display_blocks", [])]
        session.last_recommendations = list(
            dict.fromkeys([*(session.last_recommendations or []), *ids])
        )
        context.decision.revision = session.revision + 1
        self.repository.save_session(session)
        self.repository.save_decision(
            context.decision.decision_id,
            session.id,
            context.decision.model_dump(mode="json", by_alias=True),
        )

    def _finish_clarify(
        self, session: SessionRecord, context: AgentContext, trace_id: str
    ) -> ChatResponse:
        question = context.data["clarify_question"]
        self._save_state(session, context, SessionPhase.CLARIFY)
        self.repository.add_message(
            session.id, "assistant", question, Intent.CLARIFY_NEEDED.value, trace_id
        )
        return ChatResponse(
            session_id=session.id,
            trace_id=trace_id,
            response_type="CLARIFY",
            speech_text=question,
            next_action="ASK_CLARIFY",
            clarify_question=question,
            missing_slots=context.data["missing_slots"],
            decision_state=context.decision,
        )

    def _finish_answer(
        self,
        session: SessionRecord,
        context: AgentContext,
        trace_id: str,
        phase: SessionPhase,
    ) -> ChatResponse:
        self._save_state(session, context, phase)
        speech = context.data["speech_text"]
        self.repository.add_message(
            session.id, "assistant", speech, context.decision.intent.value, trace_id
        )
        return ChatResponse(
            session_id=session.id,
            trace_id=trace_id,
            response_type="ANSWER",
            speech_text=speech,
            display_blocks=context.data.get("display_blocks", []),
            decision_state=context.decision,
        )

    def _finish_text(
        self,
        session: SessionRecord,
        context: AgentContext,
        trace_id: str,
        phase: SessionPhase,
    ) -> ChatResponse:
        context.data.setdefault("display_blocks", [])
        return self._finish_answer(session, context, trace_id, phase)
