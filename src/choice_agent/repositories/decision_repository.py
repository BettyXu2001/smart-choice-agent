from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from choice_agent.db_models import DecisionRecord
from choice_agent.schemas import DecisionState


class DecisionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, decision_id: str) -> DecisionState | None:
        row = self.db.get(DecisionRecord, decision_id)
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
        else:
            row.session_id = decision.session_id
            row.domain = decision.domain
            row.status = decision.status.value
            row.revision = decision.revision
            row.state_json = state
            row.updated_at = datetime.now()
        self.db.add(row)
        self.db.commit()