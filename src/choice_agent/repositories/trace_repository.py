from __future__ import annotations

from sqlalchemy.orm import Session

from choice_agent.db_models import TraceRecord


class TraceRepository:
    def __init__(self, db: Session):
        self.db = db

    def save(self, row: TraceRecord) -> None:
        self.db.add(row)
        self.db.commit()