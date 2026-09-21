from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from choice_agent.config import Settings
from choice_agent.database import Database
from choice_agent.domains.diet.seed import seed_legacy_data
from choice_agent.domains.diet.profile import DietProfile
from choice_agent.domains.generic import GenericProfile
from choice_agent.domains.registry import DomainRegistry
from choice_agent.domains.shopping import ShoppingProfile
from choice_agent.domains.travel import TravelProfile
from choice_agent.db_models import TraceRecord
from choice_agent.evaluation.deterministic import evaluate_auto_assertion
from choice_agent.evaluation.metrics import METRIC_BY_ID, aggregate_metric, trace_observation_metrics
from choice_agent.evaluation.schemas import (
    CURRENT_PROMPT_VERSION,
    CURRENT_RULE_VERSION,
    EvaluationCaseData,
    EvaluationRunConfiguration,
)
from choice_agent.orchestration.diet import DietOrchestrator
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.providers.model import DisabledProvider, ModelProvider
from choice_agent.providers.search import SearchProviderError
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

    def run_case(
        self,
        owner_id: int,
        case_snapshot: dict[str, Any],
        run_configuration: EvaluationRunConfiguration | None = None,
    ) -> EvaluationRunOutput:
        case_data = EvaluationCaseData.model_validate(case_snapshot.get("caseData") or case_snapshot.get("case_data") or {})
        configuration = run_configuration or self._default_run_configuration()
        try:
            outputs, trace_snapshot = self._execute_case(owner_id, case_data, case_snapshot, configuration)
            outputs.setdefault("execution", {"status": "success", "errorType": None, "errorMessage": None})
            outputs["traceSnapshot"] = trace_snapshot
            assertions = [self._evaluate_assertion(assertion.model_dump(mode="json", by_alias=True), outputs) for assertion in case_data.assertions]
            metrics = {
                metric_id: aggregate_metric(assertions, metric_id)
                for metric_id in METRIC_BY_ID
            }
            metrics.update(trace_observation_metrics(trace_snapshot))
            status = deterministic_gate_status(assertions)

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

    def _execute_case(
        self,
        owner_id: int,
        case_data: EvaluationCaseData,
        case_snapshot: dict[str, Any],
        run_configuration: EvaluationRunConfiguration,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if case_data.fixture_actual is not None:
            return {"mode": "fixture_actual", **case_data.fixture_actual}, {}
        messages = [message.strip() for message in case_data.messages if message.strip()]
        if not messages:
            messages = [str(case_snapshot.get("originalQuestion") or case_snapshot.get("original_question") or "").strip()]
        messages = [message for message in messages if message]
        if not messages:
            raise ValueError("Case 缺少可执行用户问题")
        self._validate_fault_setup(case_data)
        execution_settings = replace(
            self.settings,
            main_model=run_configuration.model,
            light_model=run_configuration.model,
        )
        execution_provider = self.provider if run_configuration.provider == "configured" else DisabledProvider()
        database = Database(Settings(database_url="sqlite:///:memory:"))
        database.create_all()
        with database.session_factory() as isolated_db:
            seed_legacy_data(isolated_db)
            isolated = EvaluationRunner(
                isolated_db,
                settings=self._settings_for(case_data, execution_settings),
                provider=self._provider_for(case_data, execution_provider),
            )
            try:
                outputs = isolated._run_diet(owner_id, messages) if case_data.domain == "diet" else isolated._run_generic(owner_id, case_data.domain, messages, case_data)
                trace_snapshot = isolated._trace_snapshot(owner_id, isolated._trace_ids(outputs))
                return outputs, trace_snapshot
            except Exception as error:
                trace_snapshot = isolated._latest_trace_snapshot(owner_id)
                if self._expects_execution_error(case_data):
                    return {
                        "mode": "orchestrator",
                        "execution": {
                            "status": "error",
                            "errorType": type(error).__name__,
                            "errorMessage": f"{type(error).__name__}: {error}",
                        },
                    }, trace_snapshot
                raise

    @staticmethod
    def _validate_fault_setup(case_data: EvaluationCaseData) -> None:
        setup = case_data.setup or {}
        mock_model = setup.get("mockModel")
        if mock_model not in {None, "timeout", "invalid_json", "unknown_candidate", "false_quote", "invented_number"}:
            raise ValueError(f"不支持的 mockModel：{mock_model}")
        mock_search = setup.get("mockSearch")
        if mock_search not in {None, "missing_key", "transport_error", "invalid_response"}:
            raise ValueError(f"不支持的 mockSearch：{mock_search}")
        mock_agent = setup.get("mockAgent")
        if mock_agent not in {None, "CandidateAgent"}:
            raise ValueError(f"不支持的 mockAgent：{mock_agent}")
        expected = setup.get("expectedExecutionStatus")
        if expected not in {None, "error"}:
            raise ValueError(f"不支持的 expectedExecutionStatus：{expected}")
        if expected == "error" and not (
            mock_search == "invalid_response" or mock_agent == "CandidateAgent"
        ):
            raise ValueError("expectedExecutionStatus=error 仅允许受控失败注入")

    @staticmethod
    def _expects_execution_error(case_data: EvaluationCaseData) -> bool:
        return (case_data.setup or {}).get("expectedExecutionStatus") == "error"

    def _default_run_configuration(self) -> EvaluationRunConfiguration:
        provider = "configured" if self.provider.enabled else "disabled"
        return EvaluationRunConfiguration(
            model=self.settings.main_model,
            provider=provider,
            prompt_version=CURRENT_PROMPT_VERSION,
            rule_version=CURRENT_RULE_VERSION,
            run_label="candidate",
        )

    def _settings_for(self, case_data: EvaluationCaseData, base_settings: Settings | None = None) -> Settings:
        settings = base_settings or self.settings
        setup = case_data.setup or {}
        if setup.get("mockSearch") == "missing_key":
            return replace(settings, search_api_key="", search_provider="fixture")
        return settings

    def _provider_for(self, case_data: EvaluationCaseData, base_provider: ModelProvider | None = None) -> ModelProvider:
        mock = (case_data.setup or {}).get("mockModel")
        if mock:
            return FaultInjectionModel(str(mock))
        return base_provider or self.provider

    def _registry_for(self, db: Session, case_data: EvaluationCaseData) -> DomainRegistry | None:
        setup = case_data.setup or {}
        mock = setup.get("mockSearch")
        if setup.get("mockAgent") == "CandidateAgent":
            mock = "agent_failure"
        if mock not in {"transport_error", "invalid_response"}:
            if mock != "agent_failure":
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
        if (setup.get("mockSearch") or setup.get("mockAgent")) and "searchMode" not in dict(setup.get("context") or {}):
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

    @staticmethod
    def _trace_ids(outputs: dict[str, Any]) -> list[str]:
        values = [turn.get("traceId") for turn in outputs.get("turns", []) if isinstance(turn, dict)]
        values.append(outputs.get("traceId"))
        return list(dict.fromkeys(str(value) for value in values if value))

    def _trace_snapshot(self, owner_id: int, trace_ids: list[str]) -> dict[str, Any]:
        if not trace_ids:
            return {}
        repository = DietRepository(self.db)
        rows = [row for trace_id in trace_ids if (row := repository.trace(owner_id, trace_id)) is not None]
        if not rows:
            return {}
        snapshots = [self._trace_row(row) for row in rows]
        latest = dict(snapshots[-1])
        latest["relatedTraces"] = snapshots
        latest["observability"] = self._case_observability(rows)
        return latest

    def _latest_trace_snapshot(self, owner_id: int) -> dict[str, Any]:
        row = self.db.scalar(
            select(TraceRecord)
            .where(TraceRecord.user_id == owner_id)
            .order_by(desc(TraceRecord.id))
            .limit(1)
        )
        return self._trace_snapshot(owner_id, [row.trace_id]) if row is not None else {}

    @staticmethod
    def _trace_row(row) -> dict[str, Any]:
        return {
            "traceId": row.trace_id,
            "sessionId": row.session_id,
            "status": row.status,
            "durationMs": row.duration_ms,
            "eventCount": row.event_count,
            "errorMessage": row.error_message,
            "traceJson": row.trace_json,
        }

    @staticmethod
    def _case_observability(trace_rows) -> dict[str, Any]:
        provider_nodes = []
        for row in trace_rows:
            if isinstance(row.trace_json, dict):
                trace = row.trace_json
            elif isinstance(row.trace_json, str):
                try:
                    trace = json.loads(row.trace_json)
                except json.JSONDecodeError:
                    trace = {}
            else:
                trace = {}
            for node in trace.get("timeline", []):
                output = node.get("output") if isinstance(node, dict) else None
                if node.get("kind") in {"model", "search", "provider"} and isinstance(output, dict) and output.get("provider"):
                    provider_nodes.append(output)
        token_values = [
            item["totalTokens"] for item in provider_nodes
            if isinstance(item.get("totalTokens"), int) and not isinstance(item.get("totalTokens"), bool)
        ]
        costs = [
            float(item["estimatedCost"]) for item in provider_nodes
            if isinstance(item.get("estimatedCost"), (int, float)) and not isinstance(item.get("estimatedCost"), bool)
        ]
        unreported = sum(1 for item in provider_nodes if not isinstance(item.get("totalTokens"), int) or isinstance(item.get("totalTokens"), bool))
        unknown_price = sum(
            1 for item in provider_nodes
            if isinstance(item.get("totalTokens"), int)
            and not isinstance(item.get("totalTokens"), bool)
            and not isinstance(item.get("estimatedCost"), (int, float))
        )
        return {
            "latencyMs": sum(row.duration_ms or 0 for row in trace_rows),
            "traceCount": len(trace_rows),
            "providerCallCount": len(provider_nodes),
            "totalTokens": sum(token_values) if token_values else None,
            "estimatedCost": round(sum(costs), 12) if provider_nodes and not unreported and not unknown_price else None,
            "knownEstimatedCost": round(sum(costs), 12) if costs else None,
            "unreportedUsageCallCount": unreported,
            "unknownPriceCallCount": unknown_price,
        }

    def _evaluate_assertion(self, assertion: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
        metric_id = assertion.get("metricId") or assertion.get("metric_id")
        if metric_id not in METRIC_BY_ID:
            raise ValueError(f"未知指标：{metric_id}")
        operator = assertion.get("operator", "equals")
        expected = assertion.get("expected")
        reason = None
        if operator == "manual":
            actual = None
            passed = None
            evaluation_method = "manual"
        elif operator == "auto":
            result = evaluate_auto_assertion(metric_id, expected, outputs)
            actual = result.actual
            passed = result.passed
            reason = result.reason
            evaluation_method = result.evaluation_method
        elif operator in {"changed", "unchanged"}:
            before_found, before = _path_lookup(outputs, assertion.get("beforePath") or assertion.get("before_path"))
            after_found, after = _path_lookup(outputs, assertion.get("actualPath") or assertion.get("actual_path") or assertion.get("path"))
            actual = {"before": before, "after": after}
            if not before_found or not after_found:
                passed = None
                reason = "断言路径不存在"
                evaluation_method = "not_evaluated"
            else:
                passed = before != after if operator == "changed" else before == after
                evaluation_method = "deterministic"
        else:
            found, actual = _path_lookup(outputs, assertion.get("path") or assertion.get("actualPath") or assertion.get("actual_path"))
            if not found:
                passed = None
                reason = "断言路径不存在"
                evaluation_method = "not_evaluated"
            elif operator == "equals":
                passed = actual == expected
                evaluation_method = "deterministic"
            elif operator == "not_equals":
                passed = actual != expected
                evaluation_method = "deterministic"
            elif operator == "contains":
                passed = _contains(actual, expected)
                evaluation_method = "deterministic"
            elif operator == "not_contains":
                passed = not _contains(actual, expected)
                evaluation_method = "deterministic"
            elif operator == "includes_all":
                passed = all(_contains(actual, item) for item in _as_list(expected))
                evaluation_method = "deterministic"
            elif operator == "excludes_all":
                passed = all(not _contains(actual, item) for item in _as_list(expected))
                evaluation_method = "deterministic"
            elif operator == "non_empty":
                passed = bool(actual)
                evaluation_method = "deterministic"
            elif operator == "empty":
                passed = not bool(actual)
                evaluation_method = "deterministic"
            else:
                raise ValueError(f"未知断言操作：{operator}")
        return {
            "metricId": metric_id,
            "path": assertion.get("path"),
            "operator": operator,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "eligible": evaluation_method != "not_evaluated",
            "required": assertion.get("required", True),
            "note": assertion.get("note"),
            "evaluationMethod": evaluation_method,
            "missingReason": reason,
        }

def deterministic_gate_status(assertions: list[dict[str, Any]]) -> str:
    required = [item for item in assertions if item.get("required", True)]
    if not required:
        return "not_evaluated"
    if any(
        item.get("evaluationMethod") == "deterministic" and item.get("passed") is False
        for item in required
    ):
        return "failed"
    if any(
        item.get("evaluationMethod") != "deterministic" or item.get("passed") is None
        for item in required
    ):
        return "not_evaluated"
    return "passed"


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
        if self.failure == "invalid_json":
            raise json.JSONDecodeError("simulated invalid JSON", "{", 1)
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
            raise SearchProviderError("Web Search 未返回结构化候选")
        if self.failure == "agent_failure":
            raise RuntimeError("CandidateAgent execution failed: simulated")
        raise SearchProviderError("Web Search 传输失败：simulated")


def _path_lookup(value: Any, path: str | None) -> tuple[bool, Any]:
    if not path:
        return True, value
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.lstrip("-").isdigit():
            index = int(part)
            if -len(current) <= index < len(current):
                current = current[index]
            else:
                return False, None
        else:
            return False, None
    return True, current


def _path_get(value: Any, path: str | None) -> Any:
    return _path_lookup(value, path)[1]


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
