from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from choice_agent.db_models import DecisionRecord
from choice_agent.schemas import DecisionState
from choice_agent.decision.state_machine import DecisionRevisionError


class DecisionRepository:
    def __init__(self, db: Session, *, commit: bool = True):
        self.db = db
        self.commit = commit

    def get(self, decision_id: str) -> DecisionState | None:
        row = self.db.get(DecisionRecord, decision_id)
        if row is None:
            return None
        return DecisionState.model_validate(row.state_json)

    def visible_to_user(self, decision: DecisionState, user_id: int) -> bool:
        owner = decision.owner_user_id
        if owner is None and user_id == 1:
            decision.owner_user_id = 1
            return True
        return owner == user_id

    def get_for_user(self, decision_id: str, user_id: int) -> DecisionState | None:
        decision = self.get(decision_id)
        if decision is None:
            return None
        if not self.visible_to_user(decision, user_id):
            return None
        return decision

    def list_for_user(self, user_id: int, limit: int = 50) -> list[tuple[DecisionRecord, DecisionState]]:
        bounded_limit = max(1, min(limit, 100))
        rows = self.db.scalars(
            select(DecisionRecord)
            .order_by(desc(DecisionRecord.updated_at), desc(DecisionRecord.created_at))
            .limit(bounded_limit * 3)
        ).all()
        visible: list[tuple[DecisionRecord, DecisionState]] = []
        for row in rows:
            decision = DecisionState.model_validate(row.state_json)
            if self.visible_to_user(decision, user_id):
                visible.append((row, decision))
                if len(visible) >= bounded_limit:
                    break
        return visible

    def latest_for_session(self, session_id: str) -> DecisionState | None:
        row = self.db.scalar(
            select(DecisionRecord)
            .where(DecisionRecord.session_id == session_id)
            .order_by(desc(DecisionRecord.updated_at), desc(DecisionRecord.created_at))
            .limit(1)
        )
        if row is None:
            return None
        return DecisionState.model_validate(row.state_json)

    def save(self, decision: DecisionState) -> None:
        state = decision.model_dump(mode="json", by_alias=True)
        row = self.db.get(DecisionRecord, decision.decision_id)
        if row is None:
            row = DecisionRecord(
                id=decision.decision_id,
                session_id=decision.session_id,
                domain=decision.domain,
                status=decision.status.value,
                revision=decision.revision,
                state_json=state,
            )
            self.db.add(row)
        else:
            result = self.db.execute(
                update(DecisionRecord)
                .where(
                    DecisionRecord.id == decision.decision_id,
                    DecisionRecord.revision == decision.revision - 1,
                )
                .values(
                    session_id=decision.session_id,
                    domain=decision.domain,
                    status=decision.status.value,
                    revision=decision.revision,
                    state_json=state,
                    updated_at=datetime.now(),
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                self.db.rollback()
                raise DecisionRevisionError("Decision 已被其他请求更新，请刷新后重试")
        if self.commit:
            self.db.commit()
        else:
            self.db.flush()
