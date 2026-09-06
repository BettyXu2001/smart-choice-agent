from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from choice_agent.db_models import (
    EvaluationCaseRecord,
    EvaluationDatasetRecord,
    EvaluationResultRecord,
    EvaluationRunRecord,
)


class EvaluationConflictError(ValueError):
    pass


class EvaluationRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_case(self, owner_id: int, data: dict[str, Any]) -> EvaluationCaseRecord:
        now = datetime.now().isoformat()
        row = EvaluationCaseRecord(
            id=uuid4().hex,
            owner_user_id=owner_id,
            revision=1,
            audit_events=[{"at": now, "event": "created", "status": data["status"]}],
            **data,
        )
        self.db.add(row)
        self.db.commit()
        return row

    def get_case(self, owner_id: int, case_id: str) -> EvaluationCaseRecord | None:
        return self.db.scalar(
            select(EvaluationCaseRecord).where(
                EvaluationCaseRecord.id == case_id,
                EvaluationCaseRecord.owner_user_id == owner_id,
            )
        )

    def list_cases(
        self,
        owner_id: int,
        *,
        status: str | None = None,
        error_type: str | None = None,
        module: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> list[EvaluationCaseRecord]:
        stmt = select(EvaluationCaseRecord).where(EvaluationCaseRecord.owner_user_id == owner_id)
        if status:
            stmt = stmt.where(EvaluationCaseRecord.status == status)
        if error_type:
            stmt = stmt.where(EvaluationCaseRecord.error_type == error_type)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(EvaluationCaseRecord.title.like(like) | EvaluationCaseRecord.original_question.like(like))
        rows = list(self.db.scalars(stmt.order_by(desc(EvaluationCaseRecord.updated_at)).limit(limit)))
        if module:
            rows = [row for row in rows if module in (row.modules or [])]
        return rows

    def update_case(self, row: EvaluationCaseRecord, expected_revision: int, changes: dict[str, Any]) -> EvaluationCaseRecord:
        if row.revision != expected_revision:
            raise EvaluationConflictError("Case 已被更新，请刷新后重试")
        old_status = row.status
        for key, value in changes.items():
            setattr(row, key, value)
        row.revision += 1
        row.updated_at = datetime.now()
        row.audit_events = [
            *(row.audit_events or []),
            {"at": row.updated_at.isoformat(), "event": "updated", "from": old_status, "to": row.status},
        ]
        self.db.commit()
        return row

    def add_dataset(self, owner_id: int, data: dict[str, Any]) -> EvaluationDatasetRecord:
        row = EvaluationDatasetRecord(id=uuid4().hex, owner_user_id=owner_id, **data)
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise EvaluationConflictError("同名同版本 Regression Dataset 已存在") from error
        return row

    def get_dataset(self, owner_id: int, dataset_id: str) -> EvaluationDatasetRecord | None:
        return self.db.scalar(
            select(EvaluationDatasetRecord).where(
                EvaluationDatasetRecord.id == dataset_id,
                EvaluationDatasetRecord.owner_user_id == owner_id,
            )
        )

    def list_datasets(self, owner_id: int, limit: int = 100) -> list[EvaluationDatasetRecord]:
        return list(
            self.db.scalars(
                select(EvaluationDatasetRecord)
                .where(EvaluationDatasetRecord.owner_user_id == owner_id)
                .order_by(desc(EvaluationDatasetRecord.created_at))
                .limit(limit)
            )
        )

    def add_run(self, owner_id: int, data: dict[str, Any]) -> EvaluationRunRecord:
        row = EvaluationRunRecord(id=uuid4().hex, owner_user_id=owner_id, **data)
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise EvaluationConflictError("requestId 已用于其他评估运行") from error
        return row

    def get_run(self, owner_id: int, run_id: str) -> EvaluationRunRecord | None:
        return self.db.scalar(
            select(EvaluationRunRecord).where(
                EvaluationRunRecord.id == run_id,
                EvaluationRunRecord.owner_user_id == owner_id,
            )
        )

    def run_by_request(self, owner_id: int, request_id: str) -> EvaluationRunRecord | None:
        return self.db.scalar(
            select(EvaluationRunRecord).where(
                EvaluationRunRecord.owner_user_id == owner_id,
                EvaluationRunRecord.request_id == request_id,
            )
        )

    def list_runs(self, owner_id: int, limit: int = 50) -> list[EvaluationRunRecord]:
        return list(
            self.db.scalars(
                select(EvaluationRunRecord)
                .where(EvaluationRunRecord.owner_user_id == owner_id)
                .order_by(desc(EvaluationRunRecord.created_at))
                .limit(limit)
            )
        )

    def update_run(self, row: EvaluationRunRecord, **changes: Any) -> EvaluationRunRecord:
        for key, value in changes.items():
            setattr(row, key, value)
        row.updated_at = datetime.now()
        self.db.commit()
        return row

    def add_result(self, data: dict[str, Any]) -> EvaluationResultRecord:
        row = EvaluationResultRecord(id=uuid4().hex, **data)
        self.db.add(row)
        self.db.commit()
        return row

    def list_results(self, run_id: str) -> list[EvaluationResultRecord]:
        return list(
            self.db.scalars(
                select(EvaluationResultRecord)
                .where(EvaluationResultRecord.run_id == run_id)
                .order_by(EvaluationResultRecord.created_at)
            )
        )

    def get_result(self, result_id: str) -> EvaluationResultRecord | None:
        return self.db.get(EvaluationResultRecord, result_id)

    def update_result_reviews(self, row: EvaluationResultRecord, reviews: dict[str, Any]) -> EvaluationResultRecord:
        row.reviews_json = reviews
        row.updated_at = datetime.now()
        self.db.commit()
        return row
