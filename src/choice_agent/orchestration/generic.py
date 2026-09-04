from __future__ import annotations

from uuid import uuid4, uuid5, NAMESPACE_URL
import hashlib
import json
from sqlalchemy.exc import IntegrityError
from choice_agent.decision.conversation import public_decision

from sqlalchemy.orm import Session

from choice_agent.agents.base import AgentContext
from choice_agent.config import Settings
from choice_agent.decision.commands import apply_command
from choice_agent.decision.selector import normalize_avoid_recent_count, normalize_strategy
from choice_agent.decision.state_machine import assert_expected_revision, DecisionRevisionError
from choice_agent.domains.diet.profile import DietProfile
from choice_agent.domains.generic import GenericProfile
from choice_agent.domains.registry import DomainRegistry
from choice_agent.domains.shopping import ShoppingProfile
from choice_agent.domains.travel import TravelProfile
from choice_agent.orchestration.unified import UnifiedDecisionOrchestrator
from choice_agent.providers.model import DisabledProvider, ModelProvider
from choice_agent.providers.search import OpenAIWebSearchProvider
from choice_agent.repositories.decision_repository import DecisionRepository
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import (
    DecisionCommandRequest, DecisionMessage, DecisionState, EditEvent, GenericDecisionMessageRequest,
    GenericDecisionRequest, GenericDecisionResponse, SlotBundle, SourceMode, TraceReference,
)
from choice_agent.services.trace import TraceScope


_PROTECTED_CONTEXT_KEYS = {
    "decisionId",
    "decision_id",
    "domain",
    "messages",
    "ownerUserId",
    "owner_user_id",
    "revision",
    "sessionId",
    "session_id",
    "status",
}

class GenericDecisionOrchestrator:
    """Generic API facade using the same lifecycle that powers Diet."""

    def __init__(
        self,
        db: Session,
        registry: DomainRegistry | None = None,
        settings: Settings | None = None,
        provider: ModelProvider | None = None,
    ):
        self.db = db
        self.settings = settings or Settings()
        self.provider = provider or DisabledProvider()
        self.repository = DecisionRepository(db, commit=False)
        self.diet_repository = DietRepository(db, commit=False)
        web_provider = OpenAIWebSearchProvider(
            api_key=self.settings.search_api_key,
            base_url=self.settings.search_base_url,
            model=self.settings.search_model,
            timeout_seconds=self.settings.search_timeout_seconds,
            max_queries=self.settings.search_max_queries,
        )
        self.registry = registry or DomainRegistry([
            DietProfile(self.diet_repository, self.settings, self.provider),
            TravelProfile(web_provider), ShoppingProfile(web_provider), GenericProfile(),
        ])
        self.unified = UnifiedDecisionOrchestrator()

    def create(self, user_id: int, request: GenericDecisionRequest) -> GenericDecisionResponse:
        message = request.message.strip()
        if not message:
            raise ValueError("message 不能为空")
        profile = self.registry.resolve(message, request.domain)
        decision_id = uuid5(NAMESPACE_URL, f"choice-agent:create:{user_id}:{request.request_id}").hex if request.request_id else uuid4().hex
        receipt = self._receipt("create", request)
        existing = self.repository.get_for_user(decision_id, user_id)
        if existing:
            replay = self._replay(existing, receipt)
            if replay: return replay
            raise ValueError("requestId 已用于不同请求")
        session_id = (
            self.diet_repository.create_session(
                user_id, SourceMode(request.context.get("sourceMode", SourceMode.PUBLIC.value))
            ).id if profile.key == "diet" else uuid4().hex
        )
        decision = DecisionState(
            decision_id=decision_id,
            session_id=session_id,
            domain=profile.key,
            owner_user_id=user_id,
            user_goal=message,
            context=self._safe_context(request.context, defaults=True),
            messages=[DecisionMessage(role="user", content=message)],
        )
        decision.domain_state["pendingReceipt"] = receipt
        resolution = self.registry.identify(message, request.domain)
        decision.domain_state["sceneResolution"] = resolution
        try:
            return self._run(user_id, profile, decision, message, None)
        except (IntegrityError, DecisionRevisionError):
            self.db.rollback()
            existing = self.repository.get_for_user(decision_id, user_id)
            replay = self._replay(existing, receipt) if existing else None
            if replay: return replay
            raise

    def message(
        self, user_id: int, decision_id: str, request: GenericDecisionMessageRequest
    ) -> GenericDecisionResponse:
        message = request.message.strip()
        if not message:
            raise ValueError("message 不能为空")
        decision = self.repository.get_for_user(decision_id, user_id)
        if decision is None:
            raise KeyError("Decision 不存在或无权访问")
        receipt = self._receipt("message", request)
        replay = self._replay(decision, receipt)
        if replay: return replay
        assert_expected_revision(decision.revision, request.expected_revision)
        decision.domain_state["pendingReceipt"] = receipt
        profile = self.registry.get(decision.domain)
        decision.context = {**decision.context, **self._safe_context(request.context)}
        decision.messages.append(DecisionMessage(role="user", content=message))
        decision.domain_state.setdefault("messages", []).append(
            {"role": "user", "content": message}
        )
        decision.agent_runs = []
        return self._run(user_id, profile, decision, message, request.expected_revision)

    def command(
        self, user_id: int, decision_id: str, request: DecisionCommandRequest
    ) -> GenericDecisionResponse:
        decision = self.repository.get_for_user(decision_id, user_id)
        if decision is None:
            raise KeyError("Decision 不存在或无权访问")
        receipt = self._receipt("command", request)
        replay = self._replay(decision, receipt)
        if replay: return replay
        profile = self.registry.get(decision.domain)
        # Compatibility for commands written before receipts existed.
        existing = next((e for e in decision.edit_events if e.command_id == request.command_id), None)
        if existing:
            if existing.command_type != request.type or existing.payload != request.payload: raise ValueError("commandId 已用于不同操作")
            return GenericDecisionResponse(decision_state=public_decision(decision),trace_id=f"command:{request.command_id}", speech_text=decision.messages[-1].content,display_blocks=decision.domain_state.get("displayBlocks",[]))
        decision.domain_state["pendingReceipt"] = receipt
        assert_expected_revision(decision.revision, request.expected_revision)
        decision.context = {**decision.context, **self._safe_context(request.context)}
        before = decision.revision
        mutation = apply_command(decision, request)
        message = mutation.message or decision.user_goal
        if not mutation.message and decision.domain != "diet":
            labels = {"update_fields":"更新条件", "confirm_fields":"确认条件", "update_candidate":"修改候选说明", "add_candidate":"添加候选", "exclude_candidate":"排除候选", "restore_candidate":"恢复候选", "set_criterion_weight":"调整比较偏好", "set_constraint":"添加限制", "remove_constraint":"移除限制", "refresh_candidates":"刷新候选", "generate_recommendation":"重新比较"}
            description = labels.get(request.type, "更新选择")
            if request.type == "update_fields":
                current = decision.domain_state.get("conversationFields", {})
                description += "：" + "、".join(f"{current[k]['label']}设为{v if v is not None else '不限 / 清空'}" for k,v in request.payload.get("fields",{}).items())
            decision.messages.append(DecisionMessage(role="user",content=description))
        if mutation.message:
            decision.messages.append(DecisionMessage(role="user", content=mutation.message))
            decision.domain_state.setdefault("messages", []).append(
                {"role": "user", "content": mutation.message}
            )
        decision.agent_runs = []
        trace_id = uuid4().hex
        decision.trace_refs.append(TraceReference(trace_id=trace_id, event_type="COMMAND"))
        with TraceScope(self.db, trace_id, decision.session_id, user_id) as trace:
            try:
                trace.event(
                    "COMMAND_RECEIVED", "UNIFIED_DECISION", request,
                    {"domain": profile.key, "mode": mutation.mode},
                )
                context = AgentContext(
                    session_id=decision.session_id,
                    trace_id=trace_id,
                    user_id=user_id,
                    message=message,
                    decision=decision,
                    data=self._stage_data(decision),
                )
                if mutation.mode == "full":
                    self.unified.run(profile, context, trace)
                elif decision.domain != "diet" and (profile.needs_clarification(context)):
                    profile.clarify(context)
                else:
                    self.unified.recompute(
                        profile, context, trace,
                        refresh_candidates=mutation.mode == "refresh",
                    )
                speech = context.data.get("clarify_question") or context.data.get(
                    "speech_text",
                    decision.recommendation.summary if decision.recommendation else "需要更多信息。",
                )
                decision.messages.append(DecisionMessage(role="assistant", content=speech))
                decision.revision = before + 1
                decision.edit_events.append(
                    EditEvent(
                        command_id=request.command_id,
                        command_type=request.type,
                        revision_before=before,
                        revision_after=decision.revision,
                        payload=request.payload,
                    )
                )
                self._persist(decision, context, profile)
                blocks = profile.display_blocks(context)
            except Exception:
                self.db.rollback()
                raise

        return GenericDecisionResponse(
            decision_state=public_decision(decision),
            trace_id=trace_id,
            speech_text=speech,
            display_blocks=blocks,
        )

    def _run(self, user_id, profile, decision, message, expected_revision):
        trace_id = uuid4().hex
        decision.trace_refs.append(TraceReference(trace_id=trace_id, event_type="REQUEST"))
        with TraceScope(self.db, trace_id, decision.session_id, user_id) as trace:
            try:
                trace.event(
                    "REQUEST_RECEIVED",
                    "UNIFIED_DECISION",
                    {"message": message, "expectedRevision": expected_revision, "context": decision.context},
                    {"domain": profile.key},
                )
                context = AgentContext(
                    session_id=decision.session_id,
                    trace_id=trace_id,
                    user_id=user_id,
                    message=message,
                    decision=decision,
                    data=self._stage_data(decision),
                )
                resolution = self.registry.identify(message)
                selected = next((key for key, label in {"diet":"饮食","shopping":"购物","travel":"旅行","generic":"通用"}.items() if f"按{label}继续" in message), None)
                different = selected or (resolution["domain"] if resolution["domain"] != "generic" else None)
                if len(decision.messages) > 1 and decision.domain != "diet" and different and different != decision.domain:
                    decision.domain_state["suggestedDomain"] = {"domain":different,"message":message,"explicit": bool(selected)}
                    context.data["speech_text"] = "这像是一个新的决策场景。可以点击侧栏的新建入口继续，当前选择会保留。"
                else:
                    decision.domain_state.pop("suggestedDomain", None)
                    self.unified.run(profile, context, trace)
                speech = context.data.get("clarify_question") or context.data.get("speech_text", "需要更多信息。")
                decision.messages.append(DecisionMessage(role="assistant", content=speech))
                decision.revision += 1
                self._persist(decision, context, profile)
                blocks = profile.display_blocks(context)
            except Exception:
                self.db.rollback()
                raise

        return GenericDecisionResponse(
            decision_state=public_decision(decision), trace_id=trace_id,
            speech_text=speech, display_blocks=blocks,
        )

    def _persist(self, decision, context, profile):
        if decision.recommendation:
            decision.recommendation.generated_from_revision = decision.revision
        if decision.domain == "diet":
            session = self.diet_repository.get_session(decision.session_id, context.user_id)
            if session is not None:
                session.revision = decision.revision
                session.slots = decision.domain_state.get("slots", {})
                session.source_mode = context.data["source_mode"]
                session.current_intent = decision.intent.value if decision.intent else None
                session.phase = "CLARIFY" if decision.status.value == "clarifying" else profile.phase(context)
                ids = [int(item.candidate_id) for item in decision.candidates if item.candidate_id.isdigit()]
                session.last_recommendations = list(dict.fromkeys([*(session.last_recommendations or []), *ids]))
        blocks = profile.display_blocks(context)
        decision.domain_state["displayBlocks"] = blocks
        decision.domain_state.setdefault("conversationTurns", []).append({"revision":decision.revision,"traceId":context.trace_id,"displayBlocks":blocks,"speechText":decision.messages[-1].content,"analysis":decision.domain_state.get("assistance",{}).get("analysis")})
        pending = decision.domain_state.pop("pendingReceipt", None)
        if pending:
            snapshot = public_decision(decision)
            snapshot.domain_state.pop("conversationTurns", None)
            response = GenericDecisionResponse(decision_state=snapshot, trace_id=context.trace_id, speech_text=decision.messages[-1].content,display_blocks=blocks)
            decision.domain_state.setdefault("conversationReceipts", {})[pending["id"]] = {"fingerprint":pending["fingerprint"],"response":response.model_dump(mode="json",by_alias=True)}
        self.repository.save(decision)
        self.db.commit()

    def _stage_data(self, decision: DecisionState) -> dict:
        context = decision.context
        if decision.domain != "diet":
            return {"model_provider":self.provider,"model_name":self.settings.light_model,"main_model_name":self.settings.main_model,
                    "recent_messages":[m.model_dump(mode="json") for m in decision.messages[-8:]]}
        return {
            "source_mode": str(context.get("sourceMode", SourceMode.PUBLIC.value)),
            "current_slots": decision.domain_state.get("slots", {}),
            "slots": SlotBundle.model_validate(decision.domain_state.get("slots", {})),
            "last_recommendations": [int(item.candidate_id) if item.candidate_id.isdigit() else item.candidate_id for item in decision.candidates[:3]],
            "slot_options": self.diet_repository.slot_options(),
            "recent_messages": [item.model_dump(mode="json") for item in decision.messages[-6:]],
            "exclude_ids": [],
            "selection_strategy": normalize_strategy(context.get("selectionStrategy")),
            "avoid_recent_count": normalize_avoid_recent_count(context.get("avoidRecentCount")),
            "recent_recommendation_ids": [item.candidate_id for item in decision.candidates[:3]],
        }

    def _safe_context(self, context: dict, defaults: bool = False) -> dict:
        result = {
            key: value for key, value in context.items()
            if key not in _PROTECTED_CONTEXT_KEYS
        }
        default_mode = self.settings.search_provider
        if default_mode == "openai":
            default_mode = "web"
        if defaults:
            result.setdefault("searchMode", default_mode if default_mode in {"fixture", "web", "auto"} else "fixture")
        return result

    @staticmethod
    def _receipt(kind, request):
        identifier = getattr(request, "request_id", None) or getattr(request, "command_id", None)
        if not identifier: return None
        body = request.model_dump(mode="json", exclude={"expected_revision"})
        fingerprint = hashlib.sha256(json.dumps({"kind":kind,"body":body},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        return {"id": kind + ":" + identifier, "fingerprint": fingerprint}

    @staticmethod
    def _replay(decision, receipt):
        if not receipt: return None
        existing = decision.domain_state.get("conversationReceipts",{}).get(receipt["id"])
        if not existing: return None
        if existing["fingerprint"] != receipt["fingerprint"]: raise ValueError("requestId / commandId 已用于不同内容")
        return GenericDecisionResponse.model_validate(existing["response"])
