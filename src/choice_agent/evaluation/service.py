from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from choice_agent.config import Settings
from choice_agent.evaluation.comparison import EvaluationComparisonError, compare_runs as build_run_comparison
from choice_agent.evaluation.deterministic import evaluate_repetition_stability
from choice_agent.evaluation.fixtures import CORE_DATASET, starter_cases, starter_dataset_specs
from choice_agent.evaluation.metrics import EVALUATOR_VERSION, aggregate_metric, metric_definitions_json, summarize_results
from choice_agent.evaluation.runner import EvaluationRunner, deterministic_gate_status
from choice_agent.evaluation.schemas import (
    EvaluationCaseCreate,
    EvaluationCaseUpdate,
    EvaluationDatasetCreate,
    EvaluationReviewUpdate,
    CURRENT_PROMPT_VERSION,
    CURRENT_RULE_VERSION,
    EvaluationRunConfiguration,
    EvaluationRunCreate,
)
from choice_agent.providers.model import DisabledProvider, ModelProvider
from choice_agent.repositories.evaluation_repository import EvaluationConflictError, EvaluationRepository


class EvaluationConfigurationError(ValueError):
    pass


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
        completed = [run for run in runs if run["status"] in {"completed", "partial"}]
        latest = completed[0] if completed else None
        candidate = next(
            (run for run in completed if run["runConfiguration"].get("runLabel") == "candidate"),
            None,
        )
        baseline = next(
            (run for run in completed if run["runConfiguration"].get("runLabel") == "baseline"),
            None,
        )
        comparison = None
        comparison_error = None
        if baseline and candidate:
            try:
                full_comparison = self.compare_runs(owner_id, baseline["id"], candidate["id"])
                comparison = {
                    "baselineRunId": baseline["id"],
                    "candidateRunId": candidate["id"],
                    "scoreDelta": full_comparison["aggregateDelta"]["overallScore"],
                    "comparable": True,
                    "caseDiffCounts": full_comparison["caseDiffCounts"],
                    "baselineSummary": full_comparison["baselineRun"]["summary"],
                    "candidateSummary": full_comparison["candidateRun"]["summary"],
                }
            except EvaluationComparisonError as error:
                comparison_error = str(error)
        return {
            "evaluatorVersion": EVALUATOR_VERSION,
            "metricDefinitions": metric_definitions_json(),
            "latestRun": latest,
            "previousRun": baseline,
            "comparison": comparison,
            "comparisonError": comparison_error,
            "runs": runs,
            "cases": cases,
            "datasets": datasets,
            "taxonomy": ["理解错误", "约束处理错误", "候选获取错误", "Evidence 错误", "排序错误", "解释不一致", "多轮状态丢失", "Fallback 异常"],
            "lifecycle": ["open", "diagnosed", "fix_pending", "awaiting_regression", "verified", "reopened"],
        }

    def ensure_starter_cases(self, owner_id: int) -> None:
        rows = self.repository.list_cases(owner_id, limit=500)
        by_seed = {_seed_id(self.case_response(row)): row for row in rows if _seed_id(self.case_response(row))}
        for item in starter_cases():
            payload = item.model_dump(mode="json", by_alias=True)
            seed_id = _seed_id(payload)
            if seed_id and seed_id in by_seed:
                continue
            row = self.repository.add_case(owner_id, _case_payload(item))
            if seed_id:
                by_seed[seed_id] = row
        self._ensure_starter_datasets(owner_id)

    def _ensure_starter_datasets(self, owner_id: int) -> None:
        existing = {(row.name, row.version) for row in self.repository.list_datasets(owner_id, 100)}
        cases = [self.case_response(row) for row in self.repository.list_cases(owner_id, limit=500)]
        for spec in starter_dataset_specs():
            key = (spec["name"], spec["version"])
            if key in existing:
                continue
            snapshots = [case for case in cases if _seed_dataset(case) == spec["name"] and _seed_version(case) == spec["version"]]
            snapshots.sort(key=lambda case: _seed_id(case) or case["id"])
            if not snapshots:
                continue
            payload = {
                "name": spec["name"],
                "version": spec["version"],
                "description": spec.get("description"),
                "case_snapshots": snapshots,
                "dataset_hash": _hash_json({"name": spec["name"], "version": spec["version"], "cases": snapshots}),
            }
            try:
                self.repository.add_dataset(owner_id, payload)
            except EvaluationConflictError:
                continue

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
        run_configuration = self._effective_run_configuration(body)
        if run_configuration.provider == "configured" and (
            self.provider is None or not self.provider.enabled
        ):
            raise EvaluationConfigurationError("configured provider 未启用")
        request_id = body.request_id or uuid4().hex
        fingerprint_payload = body.model_dump(
            mode="json",
            by_alias=True,
            exclude={"request_id", "run_configuration", "model_name"},
        )
        fingerprint_payload["runConfiguration"] = run_configuration.model_dump(mode="json", by_alias=True)
        fingerprint = _hash_json(fingerprint_payload)
        existing = self.repository.run_by_request(owner_id, request_id)
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise EvaluationConflictError("requestId 已用于不同评估配置")
            return self.run_response(existing, include_results=True)
        dataset = self.repository.get_dataset(owner_id, body.dataset_id) if body.dataset_id else self._default_dataset(owner_id)
        if body.dataset_id and dataset is None:
            raise KeyError("Dataset 不存在或无权限访问")
        snapshots = dataset.case_snapshots if dataset else [self.case_response(row) for row in self.repository.list_cases(owner_id, limit=body.limit)]
        snapshots = snapshots[: body.limit]
        stored_config = {
            **body.config,
            "limit": body.limit,
            "repeat": body.repeat,
            "runConfiguration": run_configuration.model_dump(mode="json", by_alias=True),
        }
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
                "model_name": run_configuration.model,
                "config_json": stored_config,
                "status": "running",
                "summary_json": {},
            },
        )
        result_rows = []
        runner = EvaluationRunner(self.db, settings=self.settings, provider=self.provider)
        for snapshot in snapshots:
            for repetition in range(1, body.repeat + 1):
                output = runner.run_case(owner_id, snapshot, run_configuration)
                result_rows.append(self.repository.add_result(
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
                ))
        self._finalize_repetition_metrics(result_rows)
        result_payloads = [self.result_response(result) for result in result_rows]
        summary = summarize_results(result_payloads)
        status = "completed" if not summary["caseCounts"]["error"] else "partial"
        run = self.repository.update_run(run, status=status, summary_json=summary, finished_at=datetime.now())
        self._sync_case_regression_status(owner_id, run, result_payloads)
        return self.run_response(run, include_results=True)

    def _default_dataset(self, owner_id: int):
        return next(
            (
                row for row in self.repository.list_datasets(owner_id, 100)
                if row.name == CORE_DATASET["name"] and row.version == CORE_DATASET["version"]
            ),
            None,
        )

    def compare_runs(self, owner_id: int, baseline_run_id: str, candidate_run_id: str) -> dict[str, Any]:
        baseline_row = self.repository.get_run(owner_id, baseline_run_id)
        candidate_row = self.repository.get_run(owner_id, candidate_run_id)
        if baseline_row is None or candidate_row is None:
            raise KeyError("Run 不存在或无权限访问")
        baseline_run = self.run_response(baseline_row)
        candidate_run = self.run_response(candidate_row)
        baseline_results = [self.result_response(item) for item in self.repository.list_results(baseline_row.id)]
        candidate_results = [self.result_response(item) for item in self.repository.list_results(candidate_row.id)]
        case_ids = {item["caseId"] for item in baseline_results + candidate_results}
        case_titles = {}
        if baseline_row.dataset_id:
            dataset = self.repository.get_dataset(owner_id, baseline_row.dataset_id)
            if dataset is not None:
                case_titles.update(
                    {
                        snapshot["id"]: snapshot.get("title") or snapshot["id"]
                        for snapshot in dataset.case_snapshots or []
                        if snapshot.get("id") in case_ids
                    }
                )
        for case_id in case_ids - case_titles.keys():
            row = self.repository.get_case(owner_id, case_id)
            if row is not None:
                case_titles[case_id] = row.title
        return build_run_comparison(
            baseline_run,
            candidate_run,
            baseline_results,
            candidate_results,
            case_titles=case_titles,
        )

    def update_review(self, owner_id: int, result_id: str, body: EvaluationReviewUpdate) -> dict[str, Any]:
        row = self.repository.get_result(result_id)
        if row is None:
            raise KeyError("Result 不存在")
        run = self.repository.get_run(owner_id, row.run_id)
        if run is None:
            raise KeyError("Result 不存在或无权限访问")
        reviews = dict(body.reviews)
        reviews["_evaluation"] = {
            "outputFingerprint": _hash_json(row.outputs_json or {}),
            "reviewedAt": datetime.now().isoformat(),
        }
        row = self.repository.update_result_reviews(row, reviews)
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
        run_configuration = self._run_configuration_from_row(row)
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
            "runConfiguration": run_configuration,
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
        reviews = row.reviews_json or {}
        metadata = reviews.get("_evaluation") if isinstance(reviews, dict) else None
        review_stale = bool(
            isinstance(metadata, dict)
            and metadata.get("outputFingerprint")
            and metadata.get("outputFingerprint") != _hash_json(row.outputs_json or {})
        )
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
            "reviews": reviews,
            "reviewStale": review_stale,
            "metrics": row.metrics_json or {},
            "errorMessage": row.error_message,
            "createdAt": row.created_at.isoformat(),
            "updatedAt": row.updated_at.isoformat(),
        }

    def _finalize_repetition_metrics(self, rows: list[Any]) -> None:
        groups: dict[tuple[str, int], list[Any]] = {}
        for row in rows:
            groups.setdefault((row.case_id, row.case_revision), []).append(row)
        for peers in groups.values():
            result = evaluate_repetition_stability([row.outputs_json or {} for row in peers])
            for row in peers:
                assertions = list(row.assertions_json or [])
                changed = False
                for assertion in assertions:
                    metric_id = assertion.get("metricId") or assertion.get("metric_id")
                    if metric_id != "recommendation_stability" or assertion.get("operator") != "auto":
                        continue
                    assertion.update({
                        "actual": result.actual,
                        "passed": result.passed,
                        "eligible": result.passed is not None,
                        "evaluationMethod": result.evaluation_method,
                        "missingReason": result.reason,
                    })
                    changed = True
                if not changed:
                    continue
                metrics = dict(row.metrics_json or {})
                metrics["recommendation_stability"] = aggregate_metric(assertions, "recommendation_stability")
                self.repository.update_result_evaluation(
                    row,
                    status=deterministic_gate_status(assertions),
                    assertions=assertions,
                    metrics=metrics,
                )
    def _sync_case_regression_status(self, owner_id: int, run, results: list[dict[str, Any]]) -> None:
        for result in results:
            row = self.repository.get_case(owner_id, result["caseId"])
            if row is None or not row.fix_version or row.revision != result["caseRevision"]:
                continue
            if result["status"] == "passed" and row.status == "awaiting_regression":
                self.repository.update_case(row, row.revision, {"status": "verified"})
            elif result["status"] == "failed" and row.status == "verified":
                self.repository.update_case(row, row.revision, {"status": "reopened"})

    def _effective_run_configuration(self, body: EvaluationRunCreate) -> EvaluationRunConfiguration:
        if body.run_configuration is not None:
            return body.run_configuration
        provider = "configured" if self.provider is not None and self.provider.enabled else "disabled"
        return EvaluationRunConfiguration(
            model=body.model_name or self.settings.main_model,
            provider=provider,
            prompt_version=CURRENT_PROMPT_VERSION,
            rule_version=CURRENT_RULE_VERSION,
            run_label="candidate",
        )

    @staticmethod
    def _run_configuration_from_row(row) -> dict[str, Any]:
        config = row.config_json or {}
        stored = config.get("runConfiguration")
        if isinstance(stored, dict):
            return stored
        return {
            "model": row.model_name or "unknown",
            "provider": "legacy",
            "promptVersion": "legacy-unversioned",
            "ruleVersion": "legacy-unversioned",
            "runLabel": "candidate",
        }


def _case_payload(body: EvaluationCaseCreate) -> dict[str, Any]:
    data = body.model_dump(mode="json", by_alias=False)
    data["case_data"] = data.pop("case_data")
    return data


def _hash_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _seed_id(case: dict[str, Any]) -> str | None:
    value = case.get("caseData") or case.get("case_data") or {}
    setup = value.get("setup") or {}
    seed_id = setup.get("seedId") or setup.get("seed_id")
    return str(seed_id) if seed_id else None


def _seed_dataset(case: dict[str, Any]) -> str | None:
    value = case.get("caseData") or case.get("case_data") or {}
    setup = value.get("setup") or {}
    dataset = setup.get("seedDataset") or setup.get("seed_dataset")
    return str(dataset) if dataset else None


def _seed_version(case: dict[str, Any]) -> str | None:
    value = case.get("caseData") or case.get("case_data") or {}
    setup = value.get("setup") or {}
    version = setup.get("seedVersion") or setup.get("seed_version")
    return str(version) if version else None
