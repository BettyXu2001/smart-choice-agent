from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from choice_agent.db_models import (
    DecisionRecord,
    FeedbackRecord,
    MealRecord,
    MessageRecord,
    SessionRecord,
    SlotOptionRecord,
    TraceRecord,
)
from choice_agent.schemas import FeedbackRequest, MealRequest, SourceMode, TraceLabelRequest


class DietRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_session(self, user_id: int, source_mode: SourceMode = SourceMode.PUBLIC) -> SessionRecord:
        row = SessionRecord(id=uuid4().hex, user_id=user_id, source_mode=source_mode.value, slots={})
        self.db.add(row)
        self.db.commit()
        return row

    def get_session(self, session_id: str, user_id: int) -> SessionRecord | None:
        return self.db.scalar(
            select(SessionRecord).where(
                SessionRecord.id == session_id, SessionRecord.user_id == user_id
            )
        )

    def save_session(self, row: SessionRecord) -> None:
        row.updated_at = datetime.now()
        row.revision += 1
        self.db.add(row)
        self.db.commit()

    def add_message(
        self, session_id: str, role: str, content: str, intent: str | None, trace_id: str
    ) -> None:
        self.db.add(
            MessageRecord(
                session_id=session_id,
                role=role,
                content=content,
                intent=intent,
                agent_trace_id=trace_id,
            )
        )
        self.db.commit()

    def recent_messages(self, session_id: str, limit: int = 10) -> list[MessageRecord]:
        rows = self.db.scalars(
            select(MessageRecord)
            .where(MessageRecord.session_id == session_id)
            .order_by(desc(MessageRecord.created_at))
            .limit(limit)
        ).all()
        return list(reversed(rows))

    def list_meals(self, source: SourceMode, user_id: int | None = None) -> list[MealRecord]:
        query = select(MealRecord).where(MealRecord.source_type == source.value)
        if source == SourceMode.PERSONAL:
            query = query.where(MealRecord.owner_user_id == user_id)
        return list(self.db.scalars(query.order_by(MealRecord.id)).all())

    def create_meal(self, user_id: int, request: MealRequest) -> MealRecord:
        row = MealRecord(
            source_type=SourceMode.PERSONAL.value,
            owner_user_id=user_id,
            name=request.name.strip(),
            **request.slots().model_dump(),
        )
        self.db.add(row)
        self.db.commit()
        return row

    def update_meal(self, user_id: int, meal_id: int, request: MealRequest) -> MealRecord | None:
        row = self.db.scalar(
            select(MealRecord).where(
                MealRecord.id == meal_id,
                MealRecord.source_type == SourceMode.PERSONAL.value,
                MealRecord.owner_user_id == user_id,
            )
        )
        if row is None:
            return None
        row.name = request.name.strip()
        for key, value in request.slots().model_dump().items():
            setattr(row, key, value)
        self.db.commit()
        return row

    def delete_meal(self, user_id: int, meal_id: int) -> bool:
        row = self.db.scalar(
            select(MealRecord).where(
                MealRecord.id == meal_id,
                MealRecord.source_type == SourceMode.PERSONAL.value,
                MealRecord.owner_user_id == user_id,
            )
        )
        if row is None:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def slot_options(self) -> dict[str, list[str]]:
        rows = self.db.scalars(
            select(SlotOptionRecord)
            .where(SlotOptionRecord.enabled == 1)
            .order_by(SlotOptionRecord.slot_name, SlotOptionRecord.sort_order)
        ).all()
        result: dict[str, list[str]] = {}
        for row in rows:
            result.setdefault(row.slot_name, []).append(row.option_value)
        return result

    def save_feedback(self, user_id: int, request: FeedbackRequest) -> None:
        self.db.add(
            FeedbackRecord(
                user_id=user_id,
                session_id=request.session_id,
                item_id=request.item_id,
                action=request.action,
                rating=request.rating,
                reason=request.reason,
            )
        )
        self.db.commit()

    def feedbacks(
        self,
        user_id: int,
        session_ids: list[str],
        start_at: datetime,
        end_at: datetime,
    ) -> list[FeedbackRecord]:
        if not session_ids:
            return []
        return list(
            self.db.scalars(
                select(FeedbackRecord)
                .where(
                    FeedbackRecord.user_id == user_id,
                    FeedbackRecord.session_id.in_(session_ids),
                    FeedbackRecord.created_at >= start_at,
                    FeedbackRecord.created_at < end_at,
                )
                .order_by(FeedbackRecord.created_at)
            ).all()
        )

    def save_trace(self, row: TraceRecord) -> None:
        self.db.add(row)
        self.db.commit()

    def trace(self, user_id: int, trace_id: str) -> TraceRecord | None:
        return self.db.scalar(
            select(TraceRecord).where(
                TraceRecord.user_id == user_id, TraceRecord.trace_id == trace_id
            )
        )

    def session_traces(self, user_id: int, session_id: str, limit: int) -> list[TraceRecord]:
        return list(
            self.db.scalars(
                select(TraceRecord)
                .where(TraceRecord.user_id == user_id, TraceRecord.session_id == session_id)
                .order_by(desc(TraceRecord.created_at))
                .limit(max(1, min(1000, limit)))
            ).all()
        )

    def traces(
        self,
        user_id: int,
        start_at: datetime,
        end_at: datetime,
        only_unlabeled: bool,
        limit: int,
    ) -> list[TraceRecord]:
        filters = [
            TraceRecord.user_id == user_id,
            TraceRecord.created_at >= start_at,
            TraceRecord.created_at < end_at,
        ]
        if only_unlabeled:
            filters.append(TraceRecord.labeled_at.is_(None))
        return list(
            self.db.scalars(
                select(TraceRecord)
                .where(and_(*filters))
                .order_by(desc(TraceRecord.created_at))
                .limit(max(1, min(1000, limit)))
            ).all()
        )

    def label_trace(
        self, user_id: int, trace_id: str, request: TraceLabelRequest
    ) -> TraceRecord | None:
        row = self.trace(user_id, trace_id)
        if row is None:
            return None
        row.expected_intent = request.expected_intent.value if request.expected_intent else None
        row.expected_slots = (
            request.expected_slots.model_dump(by_alias=True) if request.expected_slots else None
        )
        row.expected_clarify_action = (
            request.expected_clarify_action.value if request.expected_clarify_action else None
        )
        row.label_note = request.label_note
        row.labeled_by = user_id
        row.labeled_at = datetime.now()
        self.db.commit()
        return row

    def save_decision(self, decision_id: str, session_id: str, state: dict) -> None:
        row = self.db.get(DecisionRecord, decision_id)
        if row is None:
            row = DecisionRecord(
                id=decision_id,
                session_id=session_id,
                domain=state.get("domain", "diet"),
                status=state.get("status", "draft"),
                revision=state.get("revision", 0),
                state_json=state,
            )
        else:
            row.status = state.get("status", row.status)
            row.revision = state.get("revision", row.revision)
            row.state_json = state
        self.db.add(row)
        self.db.commit()
