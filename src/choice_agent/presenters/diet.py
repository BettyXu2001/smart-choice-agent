from __future__ import annotations

from choice_agent.agents.base import AgentContext
from choice_agent.schemas import ChatResponse


class DietPresenter:
    def clarify(self, context: AgentContext, trace_id: str) -> ChatResponse:
        question = context.data["clarify_question"]
        return ChatResponse(
            session_id=context.session_id,
            trace_id=trace_id,
            response_type="CLARIFY",
            speech_text=question,
            next_action=context.decision.next_action.value,
            clarify_question=question,
            missing_slots=context.data["missing_slots"],
            decision_state=context.decision,
        )

    def answer(self, context: AgentContext, trace_id: str) -> ChatResponse:
        return ChatResponse(
            session_id=context.session_id,
            trace_id=trace_id,
            response_type="ANSWER",
            speech_text=context.data["speech_text"],
            display_blocks=context.data.get("display_blocks", []),
            next_action=context.decision.next_action.value,
            decision_state=context.decision,
        )