from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy.orm import Session

from choice_agent.config import Settings
from choice_agent.database import Database
from choice_agent.domains.diet.seed import seed_legacy_data
from choice_agent.domains.diet.profile import DietProfile
from choice_agent.domains.generic import GenericProfile
from choice_agent.domains.registry import DomainRegistry
from choice_agent.domains.shopping import ShoppingProfile
from choice_agent.domains.travel import TravelProfile
from choice_agent.evaluation.metrics import METRIC_BY_ID, aggregate_metric
from choice_agent.evaluation.schemas import EvaluationCaseData
from choice_agent.orchestration.diet import DietOrchestrator
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.providers.model import DisabledProvider, ModelProvider
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import ChatRequest, DecisionCommandRequest, GenericDecisionMessageRequest, GenericDecisionRequest, SourceMode


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
        database = Database(Settings(database_url="sqlite:///:memory:"))
        database.create_all()
        with database.session_factory() as isolated_db:
            seed_legacy_data(isolated_db)
            isolated = EvaluationRunner(
                isolated_db,
                settings=self._settings_for(case_data),
                provider=self._provider_for(case_data),
            )
            outputs = isolated._run_diet(owner_id, messages) if case_data.domain == "diet" else isolated._run_generic(owner_id, case_data.domain, messages, case_data)
            trace_snapshot = isolated._trace_snapshot(owner_id, outputs.get("traceId"))
            return outputs, trace_snapshot
    def _settings_for(self, case_data: EvaluationCaseData) -> Settings:
        setup = case_data.setup or {}
        if setup.get("mockSearch") == "missing_key":
            return replace(self.settings, search_api_key="", search_provider="fixture")
        return self.settings

    def _provider_for(self, case_data: EvaluationCaseData) -> ModelProvider:
        mock = (case_data.setup or {}).get("mockModel")
        if mock:
            return FaultInjectionModel(str(mock))
        return self.provider

    def _registry_for(self, db: Session, case_data: EvaluationCaseData) -> DomainRegistry | None:
        mock = (case_data.setup or {}).get("mockSearch")
        if mock not in {"transport_error", "invalid_response"}:
            return None
        search = FaultInjectionSearchProvider(str(mock))
        diet_repository = DietRepository(db, commit=False)
        return DomainRegistry([
            DietProfile(diet_repository, self.settings, self.provider),
            TravelProfile(search),
            ShoppingProfile(search),
            GenericProfile(),
        ])

    def _run_diet(self, owner_id: int, messages: list[str]) -> dict[str, Any]:
        orchestrator = DietOrchestrator(self.db, self.settings, self.provider)
        response = None
        session_id = None
        turns = []
        for message in messages:
            response = orchestrator.chat(
                owner_id,
                ChatRequest(session_id=session_id, message=message, source_mode=SourceMode.PUBLIC),
            )
            session_id = response.session_id
            turns.append(self._diet_turn(message, response))
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
            "turns": turns,
        }

    def _run_generic(self, owner_id: int, domain: str, messages: list[str], case_data: EvaluationCaseData) -> dict[str, Any]:
        setup = case_data.setup or {}
        context = {"searchMode": "fixture", **dict(setup.get("context") or {})}
        if setup.get("mockSearch"):
            context["searchMode"] = "web"
        orchestrator = GenericDecisionOrchestrator(
            self.db,
            registry=self._registry_for(self.db, case_data),
            settings=self.settings,
            provider=self.provider,
        )
        response = orchestrator.create(owner_id, GenericDecisionRequest(message=messages[0], domain=domain, context=context))
        turns = [self._generic_turn(messages[0], response)]
        for message in messages[1:]:
            response = orchestrator.message(
                owner_id,
                response.decision_state.decision_id,
                GenericDecisionMessageRequest(message=message, expected_revision=response.decision_state.revision, context=context),
            )
            turns.append(self._generic_turn(message, response))
        for raw_command in case_data.commands:
            if response.decision_state.domain == "diet":
                raise ValueError("Evaluation Runner 暂不支持 diet command case")
            payload = dict(raw_command)
            payload.setdefault("commandId", payload.get("command_id") or f"eval-command-{len(turns) + 1}")
            payload.setdefault("expectedRevision", response.decision_state.revision)
            payload.setdefault("context", context)
            command = DecisionCommandRequest.model_validate(payload)
            response = orchestrator.command(owner_id, response.decision_state.decision_id, command)
            turns.append(self._generic_turn(command.type, response))
        return {
            "mode": "orchestrator",
            "domain": response.decision_state.domain,
            "traceId": response.trace_id,
            "speechText": response.speech_text,
            "displayBlocks": response.display_blocks,
            "decisionState": response.decision_state.model_dump(mode="json", by_alias=True),
            "turns": turns,
        }

    def _generic_turn(self, message: str, response) -> dict[str, Any]:
        return {
            "message": message,
            "traceId": response.trace_id,
            "speechText": response.speech_text,
            "displayBlocks": response.display_blocks,
            "decisionState": response.decision_state.model_dump(mode="json", by_alias=True),
        }

    def _diet_turn(self, message: str, response) -> dict[str, Any]:
        return {
            "message": message,
            "traceId": response.trace_id,
            "speechText": response.speech_text,
            "displayBlocks": [item.model_dump(mode="json", by_alias=True) for item in response.display_blocks],
            "decisionState": response.decision_state.model_dump(mode="json", by_alias=True) if response.decision_state else {},
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


class FaultInjectionModel:
    enabled = True

    def __init__(self, failure: str):
        self.failure = failure

    def complete_json(self, **kwargs):
        data = json.loads(kwargs["user_prompt"])
        if "source_catalog" not in data:
            return {"fields": {}, "question": None, "intent": "compare", "candidate_updates": []}
        allowed = data.get("allowed_primary_ids") or []
        source_catalog = data.get("source_catalog") or {}
        primary = allowed[0] if allowed else None
        source_id, source = next(iter(source_catalog.items()))
        value = {
            "primary_candidate_id": primary,
            "summary": "结合已有依据，先考虑当前候选。",
            "reasons": [{"candidate_id": source["candidateId"], "source_id": source_id, "quote": source["text"], "text": "这项已有信息是当前建议的依据。"}],
            "tradeoffs": [],
            "question": None,
        }
        if self.failure == "timeout":
            raise TimeoutError("simulated")
        if self.failure == "unknown_candidate":
            value["primary_candidate_id"] = "not-a-candidate"
        elif self.failure == "false_quote":
            value["reasons"][0]["quote"] = "编造资料"
        elif self.failure == "invented_number":
            value["summary"] = "这个选择保证带来 999999 收益"
        return value


class FaultInjectionSearchProvider:
    name = "fault_injection_web_search"
    enabled = True

    def __init__(self, failure: str):
        self.failure = failure

    def search(self, context):
        if self.failure == "invalid_response":
            raise ValueError("Web Search 未返回结构化候选")
        raise RuntimeError("Web Search 传输失败：simulated")


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
        return any(_contains(key, expected) or _contains(value, expected) for key, value in actual.items())
    if isinstance(actual, list):
        return any(_contains(item, expected) for item in actual)
    if actual is None:
        return False
    return str(expected) in str(actual)
