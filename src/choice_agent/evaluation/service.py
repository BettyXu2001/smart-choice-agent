from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from choice_agent.config import Settings
from choice_agent.evaluation.fixtures import starter_cases
from choice_agent.evaluation.metrics import EVALUATOR_VERSION, METRIC_BY_ID, metric_definitions_json, summarize_results
from choice_agent.evaluation.runner import EvaluationRunner
from choice_agent.evaluation.schemas import (
    EvaluationCaseCreate,
    EvaluationCaseUpdate,
    EvaluationDatasetCreate,
    EvaluationReviewUpdate,
    EvaluationRunCreate,
)
from choice_agent.providers.model import ModelProvider
from choice_agent.repositories.evaluation_repository import EvaluationConflictError, EvaluationRepository


class EvaluationService:
    def __init__(self, db: Session, *, settings: Settings | None = None, provider: ModelProvider | None = None):
        self.db = db
        self.settings = settings or Settings()
        self.provider = provider
        self.repository = EvaluationRepository(db)

    def dashboard(self, owner_id: int) -> dict[str, Any]:
        self.ensure_starter_cases(owner_id)
        runs = [self.run_response(row) for row in self.repository.list_runs(owner_id, 20)]
        cases = [self.case_response(row) for row in self.repository.list_cases(owner_id, limit=100)]
        datasets = [self.dataset_response(row) for row in self.repository.list_datasets(owner_id, 50)]
        latest = next((run for run in runs if run["status"] in {"completed", "partial"}), None)
        previous = next((run for run in runs if latest and run["id"] != latest["id"] and self._comparable(run, latest)), None)
        return {
            "evaluatorVersion": EVALUATOR_VERSION,
            "metricDefinitions": metric_definitions_json(),
            "latestRun": latest,
            "previousRun": previous,
            "comparison": self._comparison(latest, previous),
            "runs": runs,
            "cases": cases,
            "datasets": datasets,
            "taxonomy": ["理解错误", "约束处理错误", "候选获取错误", "Evidence 错误", "排序错误", "解释不一致", "多轮状态丢失", "Fallback 异常"],
            "lifecycle": ["open", "diagnosed", "fix_pending", "awaiting_regression", "verified", "reopened"],
        }

    def ensure_starter_cases(self, owner_id: int) -> None:
        if self.repository.list_cases(owner_id, limit=1):
            return
        for item in starter_cases():
            self.create_case(owner_id, item)

    def create_case(self, owner_id: int, body: EvaluationCaseCreate) -> dict[str, Any]:
        return self.case_response(self.repository.add_case(owner_id, _case_payload(body)))

    def update_case(self, owner_id: int, case_id: str, body: EvaluationCaseUpdate) -> dict[str, Any]:
        row = self.repository.get_case(owner_id, case_id)
        if row is None:
            raise KeyError("Case 不存在或无权限访问")
        changes = {key: value for key, value in body.model_dump(mode="json", by_alias=False, exclude={"revision"}, exclude_none=True).items()}
        if "case_data" in changes:
            changes["case_data"] = changes["case_data"]
        if changes.get("status") == "verified" and row.status != "verified":
            raise EvaluationConflictError("Case 只能由通过的回归运行自动标记为 verified")
        updated = self.repository.update_case(row, body.revision, changes)
        return self.case_response(updated)

    def create_dataset(self, owner_id: int, body: EvaluationDatasetCreate) -> dict[str, Any]:
        snapshots = []
        for case_id in body.case_ids:
            row = self.repository.get_case(owner_id, case_id)
            if row is None:
                raise KeyError("Case 不存在或无权限访问")
            snapshots.append(self.case_response(row))
        payload = {
            "name": body.name,
            "version": body.version,
            "description": body.description,
            "case_snapshots": snapshots,
            "dataset_hash": _hash_json({"name": body.name, "version": body.version, "cases": snapshots}),
        }
        return self.dataset_response(self.repository.add_dataset(owner_id, payload))

    def create_run(self, owner_id: int, body: EvaluationRunCreate) -> dict[str, Any]:
        self.ensure_starter_cases(owner_id)
        request_id = body.request_id or uuid4().hex
        fingerprint = _hash_json(body.model_dump(mode="json", by_alias=True, exclude={"request_id"}))
        existing = self.repository.run_by_request(owner_id, request_id)
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise EvaluationConflictError("requestId 已用于不同评估配置")
            return self.run_response(existing, include_results=True)
        dataset = self.repository.get_dataset(owner_id, body.dataset_id) if body.dataset_id else None
        if body.dataset_id and dataset is None:
            raise KeyError("Dataset 不存在或无权限访问")
        snapshots = dataset.case_snapshots if dataset else [self.case_response(row) for row in self.repository.list_cases(owner_id, limit=body.limit)]
        snapshots = snapshots[: body.limit]
        run = self.repository.add_run(
            owner_id,
            {
                "request_id": request_id,
                "fingerprint": fingerprint,
                "version_label": body.version_label,
                "build_commit": "unknown",
                "evaluator_version": EVALUATOR_VERSION,
                "dataset_id": dataset.id if dataset else None,
                "dataset_name": dataset.name if dataset else "Bad Case Center",
                "dataset_version": dataset.version if dataset else "adhoc",
                "dataset_hash": dataset.dataset_hash if dataset else _hash_json(snapshots),
                "mode": body.mode,
                "model_name": body.model_name,
                "config_json": {**body.config, "limit": body.limit, "repeat": body.repeat},
                "status": "running",
                "summary_json": {},
            },
        )
        result_payloads = []
        runner = EvaluationRunner(self.db, settings=self.settings, provider=self.provider)
        for snapshot in snapshots:
            for repetition in range(1, body.repeat + 1):
                output = runner.run_case(owner_id, snapshot)
                result = self.repository.add_result(
                    {
                        "run_id": run.id,
                        "case_id": snapshot["id"],
                        "case_revision": snapshot["revision"],
                        "repetition": repetition,
                        "status": output.status,
                        "outputs_json": output.outputs,
                        "trace_snapshot": output.trace_snapshot,
                        "assertions_json": output.assertions,
                        "reviews_json": {},
                        "metrics_json": output.metrics,
                        "error_message": output.error_message,
                    }
                )
                result_payloads.append(self.result_response(result))
        summary = summarize_results(result_payloads)
        status = "completed" if not summary["caseCounts"]["error"] else "partial"
        run = self.repository.update_run(run, status=status, summary_json=summary, finished_at=datetime.now())
        self._sync_case_regression_status(owner_id, run, result_payloads)
        return self.run_response(run, include_results=True)

    def update_review(self, owner_id: int, result_id: str, body: EvaluationReviewUpdate) -> dict[str, Any]:
        row = self.repository.get_result(result_id)
        if row is None:
            raise KeyError("Result 不存在")
        run = self.repository.get_run(owner_id, row.run_id)
        if run is None:
            raise KeyError("Result 不存在或无权限访问")
        row = self.repository.update_result_reviews(row, body.reviews)
        results = [self.result_response(item) for item in self.repository.list_results(run.id)]
        self.repository.update_run(run, summary_json=summarize_results(results))
        return self.result_response(row)

    def case_response(self, row) -> dict[str, Any]:
        return {
            "id": row.id,
            "ownerUserId": row.owner_user_id,
            "revision": row.revision,
            "title": row.title,
            "originalQuestion": row.original_question,
            "expectedBehavior": row.expected_behavior,
            "actualBehavior": row.actual_behavior,
            "errorType": row.error_type,
            "diagnosis": row.diagnosis,
            "modules": row.modules or [],
            "fixPlan": row.fix_plan,
            "fixVersion": row.fix_version,
            "status": row.status,
            "caseData": row.case_data or {},
            "sourceRunId": row.source_run_id,
            "sourceTraceId": row.source_trace_id,
            "auditEvents": row.audit_events or [],
            "createdAt": row.created_at.isoformat(),
            "updatedAt": row.updated_at.isoformat(),
        }

    def dataset_response(self, row) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "version": row.version,
            "datasetHash": row.dataset_hash,
            "description": row.description,
            "caseSnapshots": row.case_snapshots or [],
            "caseCount": len(row.case_snapshots or []),
            "createdAt": row.created_at.isoformat(),
            "updatedAt": row.updated_at.isoformat(),
        }

    def run_response(self, row, *, include_results: bool = False) -> dict[str, Any]:
        response = {
            "id": row.id,
            "requestId": row.request_id,
            "fingerprint": row.fingerprint,
            "versionLabel": row.version_label,
            "buildCommit": row.build_commit,
            "evaluatorVersion": row.evaluator_version,
            "datasetId": row.dataset_id,
            "datasetName": row.dataset_name,
            "datasetVersion": row.dataset_version,
            "datasetHash": row.dataset_hash,
            "mode": row.mode,
            "modelName": row.model_name,
            "config": row.config_json or {},
            "status": row.status,
            "summary": row.summary_json or {},
            "errorMessage": row.error_message,
            "startedAt": row.started_at.isoformat(),
            "finishedAt": row.finished_at.isoformat() if row.finished_at else None,
            "createdAt": row.created_at.isoformat(),
            "updatedAt": row.updated_at.isoformat(),
        }
        if include_results:
            response["results"] = [self.result_response(item) for item in self.repository.list_results(row.id)]
        return response

    def result_response(self, row) -> dict[str, Any]:
        return {
            "id": row.id,
            "runId": row.run_id,
            "caseId": row.case_id,
            "caseRevision": row.case_revision,
            "repetition": row.repetition,
            "status": row.status,
            "outputs": row.outputs_json or {},
            "traceSnapshot": row.trace_snapshot or {},
            "assertions": row.assertions_json or [],
            "reviews": row.reviews_json or {},
            "metrics": row.metrics_json or {},
            "errorMessage": row.error_message,
            "createdAt": row.created_at.isoformat(),
            "updatedAt": row.updated_at.isoformat(),
        }

    def _sync_case_regression_status(self, owner_id: int, run, results: list[dict[str, Any]]) -> None:
        for result in results:
            row = self.repository.get_case(owner_id, result["caseId"])
            if row is None or not row.fix_version or row.revision != result["caseRevision"]:
                continue
            if result["status"] == "passed" and row.status == "awaiting_regression":
                self.repository.update_case(row, row.revision, {"status": "verified"})
            elif result["status"] == "failed" and row.status == "verified":
                self.repository.update_case(row, row.revision, {"status": "reopened"})

    @staticmethod
    def _comparable(left: dict[str, Any], right: dict[str, Any]) -> bool:
        keys = ["datasetHash", "evaluatorVersion", "mode", "modelName"]
        return all(left.get(key) == right.get(key) for key in keys)

    @staticmethod
    def _comparison(latest: dict[str, Any] | None, previous: dict[str, Any] | None) -> dict[str, Any] | None:
        if not latest or not previous:
            return None
        latest_score = latest.get("summary", {}).get("overallScore")
        previous_score = previous.get("summary", {}).get("overallScore")
        if latest_score is None or previous_score is None:
            return None
        return {
            "baselineRunId": previous["id"],
            "scoreDelta": round(latest_score - previous_score, 2),
            "comparable": True,
        }


def _case_payload(body: EvaluationCaseCreate) -> dict[str, Any]:
    data = body.model_dump(mode="json", by_alias=False)
    data["case_data"] = data.pop("case_data")
    return data


def _hash_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
