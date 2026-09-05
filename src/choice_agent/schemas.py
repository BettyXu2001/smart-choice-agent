from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

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


class EvidenceVerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"


class CriterionDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    TARGET = "target"


class MissingValuePolicy(str, Enum):
    NEUTRAL = "neutral"
    WORST = "worst"
    EXCLUDE = "exclude"


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
    constraint_id: str | None = None
    label: str | None = None
    operator: str = "contains_any"
    value: Any = None
    unit: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)


class Criterion(ApiModel):
    key: str
    label: str
    weight: float = Field(default=1.0, ge=0)
    direction: CriterionDirection = CriterionDirection.HIGHER_IS_BETTER
    target: float | None = None
    unit: str | None = None
    missing_policy: MissingValuePolicy = MissingValuePolicy.NEUTRAL


class Evidence(ApiModel):
    key: str
    value: Any
    source_title: str
    source_url: str | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = Field(default=1.0, ge=0, le=1)
    evidence_id: str | None = None
    candidate_id: str | None = None
    criterion_key: str | None = None
    claim: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    freshness: str | None = None
    verification_status: EvidenceVerificationStatus = EvidenceVerificationStatus.UNVERIFIED


class ScoreContribution(ApiModel):
    criterion_key: str
    raw_value: Any = None
    normalized_score: float = Field(ge=0, le=100)
    weight: float = Field(default=1.0, ge=0)
    weighted_score: float = 0
    explanation: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class Candidate(ApiModel):
    candidate_id: str
    name: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    score: float = 0
    eliminated: bool = False
    elimination_reasons: list[str] = Field(default_factory=list)
    summary: str = ""
    origin: str = "unknown"
    score_breakdown: list[ScoreContribution] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


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


class RecommendationPoint(ApiModel):
    text: str
    candidate_id: str | None = None
    criterion_key: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class Recommendation(ApiModel):
    primary_candidate_id: str | None = None
    alternative_candidate_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    tradeoffs: list[str] = Field(default_factory=list)
    reasons: list[RecommendationPoint] = Field(default_factory=list)
    tradeoff_details: list[RecommendationPoint] = Field(default_factory=list)
    generated_from_revision: int | None = None
    ranking_method: str = "weighted_sum"


class DecisionMessage(ApiModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SourceDocument(ApiModel):
    source_id: str
    title: str
    url: str | None = None
    publisher: str | None = None
    kind: Literal["web", "database", "fixture", "manual"] = "fixture"
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)


class SearchRun(ApiModel):
    run_id: str
    provider: str
    mode: str
    query: str
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EditEvent(ApiModel):
    command_id: str
    command_type: str
    revision_before: int
    revision_after: int
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CompositionItem(ApiModel):
    slot: str
    candidate_id: str | None = None
    label: str = ""


class CompositionResult(ApiModel):
    strategy: str
    items: list[CompositionItem] = Field(default_factory=list)
    summary: str = ""


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
    owner_user_id: int | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    messages: list[DecisionMessage] = Field(default_factory=list)
    sources: list[SourceDocument] = Field(default_factory=list)
    search_runs: list[SearchRun] = Field(default_factory=list)
    edit_events: list[EditEvent] = Field(default_factory=list)
    schema_version: int = 2
    intent_key: str | None = None
    composition: CompositionResult | None = None



class SearchCapabilitiesResponse(ApiModel):
    supported_domains: list[str] = Field(default_factory=list)
    web_search_configured: bool = False
    default_search_mode: str = "fixture"


class CandidateSearchProgressCounts(ApiModel):
    found: int = 0
    user_excluded: int = 0
    hard_constraint_excluded: int = 0
    missing_data_excluded: int = 0
    remaining: int = 0


class DecisionProgressError(ApiModel):
    code: str
    message: str


class DecisionProgressEvent(ApiModel):
    request_id: str
    command_id: str | None = None
    sequence: int
    type: Literal["progress", "final", "error"]
    stage: str | None = None
    message: str | None = None
    counts: CandidateSearchProgressCounts | None = None
    source_mode: str | None = None
    warning: str | None = None
    response: dict[str, Any] | None = None
    error: DecisionProgressError | None = None

class GenericDecisionRequest(ApiModel):
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    message: str
    domain: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class GenericDecisionMessageRequest(ApiModel):
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    message: str
    expected_revision: int | None = Field(default=None, ge=0)
    context: dict[str, Any] = Field(default_factory=dict)


class DecisionCommandRequest(ApiModel):
    command_id: str
    type: Literal[
        "update_fields",
        "confirm_fields",
        "update_candidate",
        "answer_question",
        "set_constraint",
        "remove_constraint",
        "set_criterion_weight",
        "add_candidate",
        "exclude_candidate",
        "restore_candidate",
        "refresh_candidates",
        "generate_recommendation",
    ]
    expected_revision: int = Field(ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class GenericDecisionResponse(ApiModel):
    decision_state: DecisionState
    trace_id: str
    speech_text: str
    display_blocks: list[dict[str, Any]] = Field(default_factory=list)

class DietFieldState(ApiModel):
    source: Literal["conversation", "panel", "model", "legacy"] = "legacy"
    confirmed: bool = False
    updated_revision: int = 0
    cleared: bool = False


class DietPanelCommand(ApiModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    command_id: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=0)
    type: Literal["update_fields", "confirm_fields", "set_source"]
    payload: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(ApiModel):
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
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


class AssistanceCandidateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    text: str = Field(min_length=1, max_length=1000)
    quote: str = Field(min_length=1, max_length=1000)
    concern: bool = False


class AssistanceFieldUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    value: Any = None
    quote: str = Field(min_length=1, max_length=1000)


class AssistanceInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal["update", "compare", "explain", "what_if", "clarify"] = "compare"
    fields: dict[str, Any] = Field(default_factory=dict)
    explicit_fields: list[AssistanceFieldUpdate] = Field(default_factory=list, max_length=8)
    candidate_updates: list[AssistanceCandidateUpdate] = Field(default_factory=list, max_length=8)
    question: str | None = Field(default=None, max_length=500)


class AssistanceReason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    source_id: str
    quote: str
    text: str = Field(min_length=1, max_length=1000)


class AssistanceExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary_candidate_id: str | None = None
    summary: str = Field(min_length=1, max_length=1500)
    reasons: list[AssistanceReason] = Field(min_length=1, max_length=6)
    tradeoffs: list[AssistanceReason] = Field(default_factory=list, max_length=4)
    question: str | None = Field(default=None, max_length=500)
