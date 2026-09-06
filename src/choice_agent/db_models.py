from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from choice_agent.database import Base


def utcnow() -> datetime:
    return datetime.now()


class SessionRecord(Base):
    __tablename__ = "diet_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    phase: Mapped[str] = mapped_column(String(64), default="START")
    source_mode: Mapped[str] = mapped_column(String(32), default="PUBLIC")
    current_intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    slots: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_recommendations: Mapped[list[int]] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class MessageRecord(Base):
    __tablename__ = "diet_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("diet_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MealRecord(Base):
    __tablename__ = "meal_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    owner_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    meal_time: Mapped[list[str]] = mapped_column(JSON, default=list)
    mood: Mapped[list[str]] = mapped_column(JSON, default=list)
    scene: Mapped[list[str]] = mapped_column(JSON, default=list)
    health_goal: Mapped[list[str]] = mapped_column(JSON, default=list)
    cuisine: Mapped[list[str]] = mapped_column(JSON, default=list)
    taste: Mapped[list[str]] = mapped_column(JSON, default=list)
    convenience: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class SlotOptionRecord(Base):
    __tablename__ = "diet_slot_option"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_name: Mapped[str] = mapped_column(String(64), index=True)
    option_value: Mapped[str] = mapped_column(String(64))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class FeedbackRecord(Base):
    __tablename__ = "recommend_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TraceRecord(Base):
    __tablename__ = "diet_request_trace"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(32))
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    expected_intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_slots: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    expected_clarify_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    labeled_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    labeled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    label_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class DecisionRecord(Base):
    __tablename__ = "decision_state"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    domain: Mapped[str] = mapped_column(String(64), default="diet")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class UserProfileRecord(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AgentRunRecord(Base):
    __tablename__ = "agent_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    decision_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_name: Mapped[str] = mapped_column(String(128))
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_payload: Mapped[dict[str, Any] | str | None] = mapped_column(JSON, nullable=True)
    output_payload: Mapped[dict[str, Any] | str | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EvidenceRecord(Base):
    __tablename__ = "decision_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(String(64), index=True)
    candidate_id: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(String(128))
    value_json: Mapped[Any] = mapped_column(JSON)
    source_title: Mapped[str] = mapped_column(String(256))
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EvaluationCaseRecord(Base):
    __tablename__ = "evaluation_case"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(Integer, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(256))
    original_question: Mapped[str] = mapped_column(Text)
    expected_behavior: Mapped[str] = mapped_column(Text)
    actual_behavior: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str] = mapped_column(String(64), index=True)
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    modules: Mapped[list[str]] = mapped_column(JSON, default=list)
    fix_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    case_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    audit_events: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class EvaluationDatasetRecord(Base):
    __tablename__ = "evaluation_dataset"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "name", "version", name="uq_evaluation_dataset_owner_name_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[str] = mapped_column(String(64))
    dataset_hash: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    case_snapshots: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class EvaluationRunRecord(Base):
    __tablename__ = "evaluation_run"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "request_id", name="uq_evaluation_run_owner_request"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(Integer, index=True)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    version_label: Mapped[str] = mapped_column(String(128), index=True)
    build_commit: Mapped[str] = mapped_column(String(128), default="unknown")
    evaluator_version: Mapped[str] = mapped_column(String(32), default="evaluation-v1")
    dataset_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    dataset_name: Mapped[str] = mapped_column(String(128), default="未命名数据集")
    dataset_version: Mapped[str] = mapped_column(String(64), default="adhoc")
    dataset_hash: Mapped[str] = mapped_column(String(64), default="")
    mode: Mapped[str] = mapped_column(String(32), default="fixture")
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class EvaluationResultRecord(Base):
    __tablename__ = "evaluation_result"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id", "case_revision", "repetition", name="uq_evaluation_result_run_case_rep"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("evaluation_run.id"), index=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    case_revision: Mapped[int] = mapped_column(Integer, default=1)
    repetition: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="passed", index=True)
    outputs_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    trace_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    assertions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    reviews_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
