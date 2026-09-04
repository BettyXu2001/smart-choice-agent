from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from sqlalchemy.orm import Session

from choice_agent.agents.base import AgentContext, AgentRuntime
from choice_agent.agents.stages import ProfileStage
from choice_agent.config import Settings
from choice_agent.decision.selector import normalize_avoid_recent_count, normalize_strategy
from choice_agent.decision.state_machine import assert_expected_revision
from choice_agent.domains.diet.profile import DietProfile
from choice_agent.domains.diet.state import LABELS, apply_fields, metadata, values
from choice_agent.orchestration.unified import UnifiedDecisionOrchestrator
from choice_agent.presenters.diet import DietPresenter
from choice_agent.providers.model import ModelProvider
from choice_agent.repositories.decision_repository import DecisionRepository
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import (
    ChatRequest, ChatResponse, DecisionMessage, DecisionState, DietPanelCommand,
    EditEvent, Intent, MealResponse, SlotBundle, SourceMode, TraceReference,
)
from choice_agent.services.trace import TraceScope

_PROTECTED_CONTEXT_KEYS = {
    "decisionId", "decision_id", "domain", "messages", "ownerUserId", "owner_user_id",
    "revision", "sessionId", "session_id", "status",
}


class DietOrchestrator:
    """Diet conversation and panel share a single versioned write path."""

    def __init__(self, db: Session, settings: Settings, provider: ModelProvider):
        self.db = db
        self.settings = settings
        self.repository = DietRepository(db, commit=False)
        self.decisions = DecisionRepository(db, commit=False)
        self.provider = provider
        self.unified = UnifiedDecisionOrchestrator()
        self.presenter = DietPresenter()

    def _session(self, user_id, session_id):
        session = self.repository.get_session(session_id, user_id)
        if session is None:
            raise KeyError("会话不存在或无权访问")
        return session

    def _decision(self, session, user_id):
        decision = self.decisions.latest_for_session(session.id)
        if decision is None:
            decision = DecisionState(decision_id=uuid4().hex, session_id=session.id,
                                     domain="diet", owner_user_id=user_id,
                                     domain_state={"slots": session.slots or {}})
        if decision.owner_user_id not in (None, user_id):
            raise KeyError("会话不存在或无权访问")
        decision.owner_user_id = user_id
        return decision

    def state(self, user_id, session_id):
        session = self._session(user_id, session_id)
        decision = self.decisions.latest_for_session(session.id)
        if decision and decision.owner_user_id not in (None, user_id):
            raise KeyError("会话不存在或无权访问")
        if decision:
            metadata(decision)
            # Retry receipts are internal; do not send every old state to the browser.
            decision.domain_state.pop("dietReceipts", None)
            decision.domain_state.pop("conversationReceipts", None)
        return {"sessionId": session.id, "sourceMode": session.source_mode,
                "decisionState": decision.model_dump(mode="json", by_alias=True) if decision else None}

    def chat(self, user_id: int, request: ChatRequest) -> ChatResponse:
        if not request.message.strip():
            raise ValueError("message 不能为空")
        if request.request_id and not request.session_id:
            raise ValueError("使用 requestId 时请先创建会话")
        return self._execute(user_id, request.session_id, request, command=False)

    def command(self, user_id: int, session_id: str, request: DietPanelCommand) -> ChatResponse:
        return self._execute(user_id, session_id, request, command=True)

    def _context(self, decision, session, user_id, message, trace_id):
        return AgentContext(
            session_id=session.id, trace_id=trace_id, user_id=user_id,
            message=message, decision=decision,
            data={
                "source_mode": session.source_mode,
                "current_slots": decision.domain_state.get("slots", session.slots or {}),
                "slots": SlotBundle.model_validate(decision.domain_state.get("slots", session.slots or {})),
                "last_recommendations": session.last_recommendations or [],
                "slot_options": self.repository.slot_options(),
                "recent_messages": [{"role": row.role, "content": row.content}
                                    for row in self.repository.recent_messages(session.id, 6)],
                "exclude_ids": [],
                "selection_strategy": normalize_strategy(decision.context.get("selectionStrategy")),
                "avoid_recent_count": normalize_avoid_recent_count(decision.context.get("avoidRecentCount")),
                "recent_recommendation_ids": [str(item) for item in (session.last_recommendations or [])],
            },
        )

    def _panel_patch(self, decision, session, request):
        payload = request.payload
        options = self.repository.slot_options()
        if request.type == "set_source":
            if set(payload) != {"sourceMode"}:
                raise ValueError("set_source 仅接受 sourceMode")
            session.source_mode = SourceMode(payload["sourceMode"]).value
            return "已切换为" + ("个人餐食库" if session.source_mode == "PERSONAL" else "公共餐食库") + "。"
        if request.type == "confirm_fields":
            keys = payload.get("fields")
            if set(payload) != {"fields"} or not isinstance(keys, list) or not keys or any(not isinstance(k, str) or k not in LABELS for k in keys):
                raise ValueError("请选择需要确认的字段")
            patch = {k: values(decision)[k] for k in keys}
        else:
            if set(payload) != {"fields"}:
                raise ValueError("update_fields 仅接受 fields")
            patch = payload["fields"]
        previous = values(decision)
        apply_fields(decision, patch, options)
        verb = "确认" if request.type == "confirm_fields" else "修改"
        return "已" + verb + "：" + "；".join(
            f"{LABELS[k]}：{'、'.join(previous[k]) or '未设置'} → {'、'.join(v) or '不限'}"
            for k, v in patch.items()
        ) + "。"

    def _execute(self, user_id, session_id, request, command):
        session = self._session(user_id, session_id) if session_id else self.repository.create_session(user_id, request.source_mode)
        decision = self._decision(session, user_id)
        identifier = request.command_id if command else request.request_id
        request_data = request.model_dump(mode="json", by_alias=True)
        fingerprint = hashlib.sha256(json.dumps({"command": command, "request": request_data},
                                                sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        receipt = decision.domain_state.get("dietReceipts", {}).get(identifier) if identifier else None
        if receipt:
            if receipt["fingerprint"] != fingerprint:
                raise ValueError("请求 ID 已用于不同操作")
            return ChatResponse.model_validate(receipt["response"])
        try:
            assert_expected_revision(decision.revision, request.expected_revision)
        except Exception:
            self.db.rollback()
            raise
        trace_id = uuid4().hex
        before = decision.revision
        with TraceScope(self.db, trace_id, session.id, user_id) as trace:
            try:
                decision.agent_runs = []
                if command:
                    message = self._panel_patch(decision, session, request)
                else:
                    message = request.message.strip()
                    session.source_mode = request.source_mode.value
                    decision.context.update({k: v for k, v in request.context.items() if k not in _PROTECTED_CONTEXT_KEYS})
                decision.context["sourceMode"] = session.source_mode
                decision.messages.append(DecisionMessage(role="user", content=message))
                self.repository.add_message(session.id, "user", message, None, trace_id)
                decision.trace_refs.append(TraceReference(trace_id=trace_id, event_type="COMMAND" if command else "REQUEST"))
                trace.event("COMMAND_RECEIVED" if command else "REQUEST_RECEIVED", "HTTP", request, {"sessionId": session.id})
                context = self._context(decision, session, user_id, message, trace_id)
                profile = DietProfile(self.repository, self.settings, self.provider)
                clarify = False
                if command and request.type == "confirm_fields":
                    context.data["display_blocks"] = [MealResponse.model_validate(b) for b in decision.domain_state.get("displayBlocks", [])]
                    context.data["speech_text"] = message
                elif command:
                    if decision.intent is None or decision.intent == Intent.OTHER:
                        decision.intent = Intent.MEAL_RECOMMENDATION
                    if decision.risk_flags:
                        decision.intent = Intent.HEALTH_RISK
                    if not profile.should_run_pre_safety(context) and not profile.should_compose(context):
                        result = AgentRuntime(trace).run(ProfileStage("ClarificationAgent", profile.clarify), context)
                        clarify = profile.is_clarifying(result, context)
                    if not clarify:
                        self.unified.recompute(profile, context, trace, refresh_candidates=True)
                    context.data["speech_text"] = message + "\n" + context.data.get("speech_text", "")
                else:
                    result = self.unified.run(profile, context, trace)
                    clarify = result.outcome == "clarify"
                if clarify:
                    decision.candidates = []
                    decision.recommendation = None
                    decision.composition = None
                    context.data["display_blocks"] = []
                elif decision.intent != Intent.MEAL_PLAN:
                    decision.composition = None
                speech = context.data.get("clarify_question") if clarify else context.data.get("speech_text", "已更新。")
                if command and clarify:
                    speech = message + "\n" + speech
                    context.data["clarify_question"] = speech
                context.data["speech_text"] = speech
                decision.messages.append(DecisionMessage(role="assistant", content=speech))
                self.repository.add_message(session.id, "assistant", speech,
                                            Intent.CLARIFY_NEEDED.value if clarify else (decision.intent.value if decision.intent else None), trace_id)
                decision.revision = before + 1
                if decision.recommendation:
                    decision.recommendation.generated_from_revision = decision.revision
                if command:
                    decision.edit_events.append(EditEvent(command_id=identifier, command_type=request.type,
                                                         revision_before=before, revision_after=decision.revision,
                                                         payload=request.payload))
                session.phase = "CLARIFY" if clarify else profile.phase(context)
                session.current_intent = decision.intent.value if decision.intent else None
                session.slots = context.data["slots"].model_dump(by_alias=True)
                session.revision = decision.revision
                blocks = profile.display_blocks(context)
                decision.domain_state["displayBlocks"] = blocks
                session.last_recommendations = list(dict.fromkeys([*(session.last_recommendations or []), *[b["id"] for b in blocks]]))
                decision.domain_state.setdefault("dietTurns", []).append({
                    "requestId": identifier, "revision": decision.revision, "userText": message,
                    "speechText": speech, "displayBlocks": blocks, "traceId": trace_id,
                    "responseType": "CLARIFY" if clarify else "ANSWER",
                })
                response = self.presenter.clarify(context, trace_id) if clarify else self.presenter.answer(context, trace_id)
                # A receipt stores a bounded snapshot without embedding other receipts or history recursively.
                public_state = decision.model_copy(deep=True)
                public_state.domain_state.pop("dietReceipts", None)
                public_state.domain_state.pop("conversationReceipts", None)
                response.decision_state = public_state
                if identifier:
                    snapshot = response.model_dump(mode="json", by_alias=True)
                    snapshot["decisionState"]["domainState"].pop("dietTurns", None)
                    decision.domain_state.setdefault("dietReceipts", {})[identifier] = {
                        "fingerprint": fingerprint, "response": snapshot,
                    }
                self.decisions.save(decision)
                self.db.commit()
                return response
            except Exception:
                self.db.rollback()
                raise
