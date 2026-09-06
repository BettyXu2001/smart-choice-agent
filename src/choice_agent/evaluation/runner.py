from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from sqlalchemy.orm import Session

from choice_agent.config import Settings
from choice_agent.database import Database
from choice_agent.domains.diet.seed import seed_legacy_data
from choice_agent.evaluation.metrics import METRIC_BY_ID, aggregate_metric
from choice_agent.evaluation.schemas import EvaluationCaseData
from choice_agent.orchestration.diet import DietOrchestrator
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.providers.model import DisabledProvider, ModelProvider
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import ChatRequest, GenericDecisionMessageRequest, GenericDecisionRequest, SourceMode


@dataclass
class EvaluationRunOutput:
    status: str
    outputs: dict[str, Any]
    trace_snapshot: dict[str, Any]
    assertions: list[dict[str, Any]]
    metrics: dict[str, Any]
    error_message: str | None = None


class EvaluationRunner:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        provider: ModelProvider | None = None,
    ):
        self.db = db
        self.settings = settings or Settings()
        self.provider = provider or DisabledProvider()

    def run_case(self, owner_id: int, case_snapshot: dict[str, Any]) -> EvaluationRunOutput:
        case_data = EvaluationCaseData.model_validate(case_snapshot.get("caseData") or case_snapshot.get("case_data") or {})
        try:
            outputs, trace_snapshot = self._execute_case(owner_id, case_data, case_snapshot)
            assertions = [self._evaluate_assertion(assertion.model_dump(mode="json", by_alias=True), outputs) for assertion in case_data.assertions]
            metrics = {
                metric_id: aggregate_metric(assertions, metric_id)
                for metric_id in METRIC_BY_ID
            }
            failed_required = [item for item in assertions if item.get("required", True) and item.get("passed") is False]
            status = "failed" if failed_required else "passed"
            if not assertions:
                status = "not_evaluated"
            return EvaluationRunOutput(status=status, outputs=outputs, trace_snapshot=trace_snapshot, assertions=assertions, metrics=metrics)
        except Exception as error:
            return EvaluationRunOutput(
                status="error",
                outputs={},
                trace_snapshot={},
                assertions=[],
                metrics={metric_id: aggregate_metric([], metric_id) for metric_id in METRIC_BY_ID},
                error_message=str(error),
            )

    def _execute_case(self, owner_id: int, case_data: EvaluationCaseData, case_snapshot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        if case_data.fixture_actual is not None:
            return {"mode": "fixture_actual", **case_data.fixture_actual}, {}
        messages = [message.strip() for message in case_data.messages if message.strip()]
        if not messages:
            messages = [str(case_snapshot.get("originalQuestion") or case_snapshot.get("original_question") or "").strip()]
        messages = [message for message in messages if message]
        if not messages:
            raise ValueError("Case 缺少可执行用户问题")
        with TemporaryDirectory(prefix="choice-agent-eval-") as folder:
            database = Database(Settings(database_url=f"sqlite:///{Path(folder) / 'evaluation.db'}"))
            database.create_all()
            with database.session_factory() as isolated_db:
                seed_legacy_data(isolated_db)
                isolated = EvaluationRunner(isolated_db, settings=self.settings, provider=self.provider)
                outputs = isolated._run_diet(owner_id, messages) if case_data.domain == "diet" else isolated._run_generic(owner_id, case_data.domain, messages)
                trace_snapshot = isolated._trace_snapshot(owner_id, outputs.get("traceId"))
                return outputs, trace_snapshot

    def _run_diet(self, owner_id: int, messages: list[str]) -> dict[str, Any]:
        orchestrator = DietOrchestrator(self.db, self.settings, self.provider)
        response = None
        session_id = None
        for message in messages:
            response = orchestrator.chat(
                owner_id,
                ChatRequest(session_id=session_id, message=message, source_mode=SourceMode.PUBLIC),
            )
            session_id = response.session_id
        if response is None:
            raise ValueError("Case 没有产生响应")
        state = response.decision_state.model_dump(mode="json", by_alias=True) if response.decision_state else {}
        return {
            "mode": "orchestrator",
            "domain": "diet",
            "traceId": response.trace_id,
            "speechText": response.speech_text,
            "displayBlocks": [item.model_dump(mode="json", by_alias=True) for item in response.display_blocks],
            "decisionState": state,
        }

    def _run_generic(self, owner_id: int, domain: str, messages: list[str]) -> dict[str, Any]:
        orchestrator = GenericDecisionOrchestrator(self.db, settings=self.settings, provider=self.provider)
        response = orchestrator.create(owner_id, GenericDecisionRequest(message=messages[0], domain=domain, context={"searchMode": "fixture"}))
        for message in messages[1:]:
            response = orchestrator.message(
                owner_id,
                response.decision_state.decision_id,
                GenericDecisionMessageRequest(message=message, expected_revision=response.decision_state.revision),
            )
        return {
            "mode": "orchestrator",
            "domain": response.decision_state.domain,
            "traceId": response.trace_id,
            "speechText": response.speech_text,
            "displayBlocks": response.display_blocks,
            "decisionState": response.decision_state.model_dump(mode="json", by_alias=True),
        }

    def _trace_snapshot(self, owner_id: int, trace_id: str | None) -> dict[str, Any]:
        if not trace_id:
            return {}
        row = DietRepository(self.db).trace(owner_id, trace_id)
        if row is None:
            return {}
        return {
            "traceId": row.trace_id,
            "sessionId": row.session_id,
            "status": row.status,
            "durationMs": row.duration_ms,
            "eventCount": row.event_count,
            "errorMessage": row.error_message,
            "traceJson": row.trace_json,
        }

    def _evaluate_assertion(self, assertion: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
        metric_id = assertion.get("metricId") or assertion.get("metric_id")
        if metric_id not in METRIC_BY_ID:
            raise ValueError(f"未知指标：{metric_id}")
        operator = assertion.get("operator", "equals")
        actual = _path_get(outputs, assertion.get("path") or assertion.get("actualPath") or assertion.get("actual_path"))
        expected = assertion.get("expected")
        if operator == "manual":
            passed = None
        elif operator == "equals":
            passed = actual == expected
        elif operator == "not_equals":
            passed = actual != expected
        elif operator == "contains":
            passed = _contains(actual, expected)
        elif operator == "not_contains":
            passed = not _contains(actual, expected)
        elif operator == "includes_all":
            passed = all(_contains(actual, item) for item in _as_list(expected))
        elif operator == "excludes_all":
            passed = all(not _contains(actual, item) for item in _as_list(expected))
        elif operator == "non_empty":
            passed = bool(actual)
        elif operator == "empty":
            passed = not bool(actual)
        elif operator in {"changed", "unchanged"}:
            before = _path_get(outputs, assertion.get("beforePath") or assertion.get("before_path"))
            after = _path_get(outputs, assertion.get("actualPath") or assertion.get("actual_path") or assertion.get("path"))
            passed = before != after if operator == "changed" else before == after
        else:
            raise ValueError(f"未知断言操作：{operator}")
        return {
            "metricId": metric_id,
            "path": assertion.get("path"),
            "operator": operator,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "eligible": True,
            "required": assertion.get("required", True),
            "note": assertion.get("note"),
        }


def _path_get(value: Any, path: str | None) -> Any:
    if not path:
        return value
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
    return current


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, dict):
        return expected in actual.values() or expected in actual.keys()
    if isinstance(actual, list):
        return expected in actual
    if actual is None:
        return False
    return str(expected) in str(actual)
