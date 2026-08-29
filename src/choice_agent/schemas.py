from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class SourceMode(str, Enum):
    PERSONAL = "PERSONAL"
    PUBLIC = "PUBLIC"


class Intent(str, Enum):
    MEAL_RECOMMENDATION = "MEAL_RECOMMENDATION"
    CLARIFY_NEEDED = "CLARIFY_NEEDED"
    MEAL_ADJUST = "MEAL_ADJUST"
    MEAL_PLAN = "MEAL_PLAN"
    HEALTH_RISK = "HEALTH_RISK"
    OTHER = "OTHER"


class SessionPhase(str, Enum):
    START = "START"
    CLARIFY = "CLARIFY"
    RECOMMEND = "RECOMMEND"
    PLAN = "PLAN"


class ClarifyAction(str, Enum):
    ASK = "ASK"
    READY = "READY"


class DecisionStatus(str, Enum):
    DRAFT = "draft"
    CLARIFYING = "clarifying"
    SEARCHING = "searching"
    COMPARING = "comparing"
    DECIDED = "decided"


class ConstraintKind(str, Enum):
    HARD = "hard"
    SOFT = "soft"


class DecisionNextAction(str, Enum):
    ASK_CLARIFY = "ASK_CLARIFY"
    SEARCH_CANDIDATES = "SEARCH_CANDIDATES"
    COMPARE_CANDIDATES = "COMPARE_CANDIDATES"
    SHOW_RECOMMENDATION = "SHOW_RECOMMENDATION"
    WAIT_USER = "WAIT_USER"


class SelectionStrategy(str, Enum):
    RANKED = "ranked"
    RANDOM = "random"
    WEIGHTED = "weighted"
    LEAST_RECENT = "least_recent"


class SlotBundle(ApiModel):
    meal_time: list[str] = Field(default_factory=list)
    mood: list[str] = Field(default_factory=list)
    scene: list[str] = Field(default_factory=list)
    health_goal: list[str] = Field(default_factory=list)
    cuisine: list[str] = Field(default_factory=list)
    taste: list[str] = Field(default_factory=list)
    convenience: list[str] = Field(default_factory=list)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple, set)):
            return []
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    def merged_with(self, newer: "SlotBundle") -> "SlotBundle":
        values = {}
        for name in type(self).model_fields:
            values[name] = list(dict.fromkeys([*getattr(self, name), *getattr(newer, name)]))
        return SlotBundle(**values)

    def is_empty(self) -> bool:
        return all(not getattr(self, name) for name in type(self).model_fields)


class Constraint(ApiModel):
    key: str
    kind: ConstraintKind
    values: list[str] = Field(default_factory=list)
    source: str = "user"


class Criterion(ApiModel):
    key: str
    label: str
    weight: float = Field(default=1.0, ge=0)


class Evidence(ApiModel):
    key: str
    value: Any
    source_title: str
    source_url: str | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = Field(default=1.0, ge=0, le=1)


class Candidate(ApiModel):
    candidate_id: str
    name: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    score: float = 0
    eliminated: bool = False
    elimination_reasons: list[str] = Field(default_factory=list)


class CandidateState(ApiModel):
    status: str = "active"
    reason: str | None = None
    updated_by: str | None = None


class UnansweredQuestion(ApiModel):
    key: str
    question: str
    required: bool = True
    asked_by: str | None = None


class Assumption(ApiModel):
    key: str
    value: Any
    confidence: float = Field(default=0.5, ge=0, le=1)
    source: str = "system"


class TraceReference(ApiModel):
    trace_id: str
    event_type: str | None = None
    agent_name: str | None = None


class Recommendation(ApiModel):
    primary_candidate_id: str | None = None
    alternative_candidate_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    tradeoffs: list[str] = Field(default_factory=list)


class AgentRun(ApiModel):
    agent_name: str
    model_name: str | None = None
    status: str = "SUCCESS"
    latency_ms: int = 0
    input_payload: Any = None
    output_payload: Any = None
    error_message: str | None = None


class DecisionState(ApiModel):
    decision_id: str
    session_id: str
    domain: str = "diet"
    intent: Intent | None = None
    user_goal: str = ""
    constraints: list[Constraint] = Field(default_factory=list)
    criteria: list[Criterion] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    candidate_state: dict[str, CandidateState] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list)
    unanswered_questions: list[UnansweredQuestion] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    recommendation: Recommendation | None = None
    next_action: DecisionNextAction = DecisionNextAction.WAIT_USER
    risk_flags: list[str] = Field(default_factory=list)
    excluded_candidates: list[str] = Field(default_factory=list)
    agent_runs: list[AgentRun] = Field(default_factory=list)
    trace_refs: list[TraceReference] = Field(default_factory=list)
    revision: int = 0
    status: DecisionStatus = DecisionStatus.DRAFT
    domain_state: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(ApiModel):
    session_id: str | None = None
    message: str
    source_mode: SourceMode = SourceMode.PUBLIC
    context: dict[str, Any] = Field(default_factory=dict)
    expected_revision: int | None = Field(default=None, ge=0)


class MealRequest(ApiModel):
    name: str
    meal_time: list[str] = Field(default_factory=list)
    mood: list[str] = Field(default_factory=list)
    scene: list[str] = Field(default_factory=list)
    health_goal: list[str] = Field(default_factory=list)
    cuisine: list[str] = Field(default_factory=list)
    taste: list[str] = Field(default_factory=list)
    convenience: list[str] = Field(default_factory=list)

    def slots(self) -> SlotBundle:
        data = self.model_dump(exclude={"name"})
        return SlotBundle(**data)


class MealResponse(ApiModel):
    id: int
    source_type: SourceMode
    name: str
    meal_time: list[str] = Field(default_factory=list)
    mood: list[str] = Field(default_factory=list)
    scene: list[str] = Field(default_factory=list)
    health_goal: list[str] = Field(default_factory=list)
    cuisine: list[str] = Field(default_factory=list)
    taste: list[str] = Field(default_factory=list)
    convenience: list[str] = Field(default_factory=list)
    match_score: float = 0
    reason: str | None = None


class ChatResponse(ApiModel):
    session_id: str
    trace_id: str
    response_type: str
    speech_text: str
    display_blocks: list[MealResponse] = Field(default_factory=list)
    next_action: str = "WAIT_USER"
    clarify_question: str | None = None
    missing_slots: list[str] = Field(default_factory=list)
    decision_state: DecisionState | None = None


class FeedbackRequest(ApiModel):
    session_id: str
    item_id: int | None = None
    action: str
    rating: int | None = Field(default=None, ge=1, le=5)
    reason: str | None = None


class TraceLabelRequest(ApiModel):
    expected_intent: Intent | None = None
    expected_slots: SlotBundle | None = None
    expected_clarify_action: ClarifyAction | None = None
    label_note: str | None = None


class EvaluationRequest(ApiModel):
    start_at: datetime
    end_at: datetime
    include_llm_judge: bool = False
    limit: int = Field(default=200, ge=1, le=1000)
