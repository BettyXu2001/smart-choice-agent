from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any


EVALUATOR_VERSION = "evaluation-v3"


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    category: str
    label: str
    direction: str = "higher_is_better"
    unit: str = "%"
    scored: bool = True
    description: str = ""


METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition("intent_accuracy", "需求理解", "Intent 识别准确率", description="匹配金标签操作意图的轮次占比。"),
    MetricDefinition("domain_routing_accuracy", "需求理解", "领域路由准确率", description="未显式注入领域时，系统选择正确业务领域的请求占比。"),
    MetricDefinition("clarification_decision_accuracy", "需求理解", "澄清决策准确率", description="需要追问时追问且信息充分时不多问的请求占比。"),
    MetricDefinition("constraint_extraction_accuracy", "需求理解", "约束抽取准确率", description="字段、值、硬软属性和候选归属正确的约束占比。"),
    MetricDefinition("correction_update_accuracy", "需求理解", "用户纠正后的状态更新准确率", description="纠正后新值生效、旧值移除且归属正确的轮次占比。"),
    MetricDefinition("hard_constraint_satisfaction", "决策质量", "硬约束满足率", description="推荐满足全部硬约束的可判定请求占比。"),
    MetricDefinition("soft_preference_satisfaction", "决策质量", "软偏好满足率", description="首选候选的评分明细覆盖用户强调偏好并达到预期匹配度的请求占比。"),
    MetricDefinition("safety_constraint_violation_rate", "决策质量", "安全约束违规率", direction="lower_is_better", description="可判定安全场景中未正确触发风险控制或仍给出禁止结果的比例。"),
    MetricDefinition("exclusion_correctness", "决策质量", "排除候选正确率", description="排除集合匹配预期的轮次占比。"),
    MetricDefinition("recommendation_stability", "决策质量", "推荐稳定性", description="相同输入和固定来源下推荐保持稳定的重复配对占比。"),
    MetricDefinition("sensitivity_to_condition_change", "决策质量", "条件变化后的结论敏感性", description="条件变化后结论按预期改变或维持的配对占比。"),
    MetricDefinition("reason_recommendation_consistency", "解释质量", "推荐与理由一致率", description="推荐候选与理由、语义审阅断言一致的回答占比。"),
    MetricDefinition("evidence_reference_validity", "解释质量", "Evidence 引用有效率", description="引用存在、归属正确并能回到来源原文的引用占比。"),
    MetricDefinition("unsupported_fact_rate", "解释质量", "无依据事实生成率", direction="lower_is_better", description="人工审阅 claim 中无来源支持的比例。"),
    MetricDefinition("excluded_candidate_recommend_rate", "解释质量", "已排除候选误推荐率", direction="lower_is_better", description="有排除记录时仍推荐已排除候选的比例。"),
    MetricDefinition("multi_turn_state_retention", "多轮交互", "多轮状态保持率", description="无合法编辑时事实、排除集合和正式推荐保持正确的断言占比。"),
    MetricDefinition("correction_coverage", "多轮交互", "用户纠正覆盖率", description="被更新流程处理的纠正目标占比。"),
    MetricDefinition("what_if_isolation", "多轮交互", "What-if 不污染正式状态成功率", description="假设轮次前后正式业务投影不变的占比。"),
    MetricDefinition("llm_fallback_success", "工程可靠性", "LLM 调用失败 Fallback 成功率", description="模型调用失败后仍返回有效降级结果并通过状态断言的请求占比。"),
    MetricDefinition("search_fallback_success", "工程可靠性", "Search 调用失败 Fallback 成功率", description="搜索调用失败后仍返回有效降级结果且来源变化可观察的请求占比。"),
    MetricDefinition("fallback_activation_rate", "工程可靠性", "Fallback 激活率", direction="lower_is_better", scored=False, description="有可观测 Trace 的请求中实际进入任一 Fallback 的比例；单独展示，不进入总分。"),
    MetricDefinition("agent_execution_failure_rate", "工程可靠性", "Agent 执行失败率", direction="lower_is_better", description="失败 AgentRun 占全部 AgentRun 比例。"),
    MetricDefinition("average_response_time_ms", "工程可靠性", "平均响应时间", direction="lower_is_better", unit="ms", scored=False, description="有耗时请求的 durationMs 均值；单独展示，不进入总分。"),
)

METRIC_BY_ID = {item.metric_id: item for item in METRIC_DEFINITIONS}
QUALITY_METRIC_IDS = [item.metric_id for item in METRIC_DEFINITIONS if item.scored]
TRACE_OBSERVATION_METRIC_IDS = {"fallback_activation_rate", "agent_execution_failure_rate", "average_response_time_ms"}
DETERMINISTIC_TARGET_METRIC_IDS = (
    "intent_accuracy",
    "domain_routing_accuracy",
    "clarification_decision_accuracy",
    "constraint_extraction_accuracy",
    "correction_update_accuracy",
    "hard_constraint_satisfaction",
    "soft_preference_satisfaction",
    "safety_constraint_violation_rate",
    "exclusion_correctness",
    "recommendation_stability",
    "sensitivity_to_condition_change",
    "reason_recommendation_consistency",
    "evidence_reference_validity",
    "unsupported_fact_rate",
    "excluded_candidate_recommend_rate",
    "multi_turn_state_retention",
    "correction_coverage",
    "what_if_isolation",
    "llm_fallback_success",
    "agent_execution_failure_rate",
)


def metric_definitions_json() -> list[dict[str, Any]]:
    return [
        {
            "id": item.metric_id,
            "category": item.category,
            "label": item.label,
            "direction": item.direction,
            "unit": item.unit,
            "scored": item.scored,
            "description": item.description,
        }
        for item in METRIC_DEFINITIONS
    ]


def empty_metric(metric_id: str, missing_reason: str = "not_evaluated") -> dict[str, Any]:
    definition = METRIC_BY_ID[metric_id]
    return {
        "id": metric_id,
        "category": definition.category,
        "label": definition.label,
        "direction": definition.direction,
        "unit": definition.unit,
        "scored": definition.scored,
        "value": None,
        "numerator": 0,
        "denominator": 0,
        "eligibleCount": 0,
        "evaluatedCount": 0,
        "missingReason": missing_reason,
        "method": "assertion",
        "evaluationMethod": "not_evaluated",
        "failures": [],
    }


def aggregate_metric(assertions: list[dict[str, Any]], metric_id: str) -> dict[str, Any]:
    metric = empty_metric(metric_id)
    relevant = [item for item in assertions if item.get("metricId") == metric_id or item.get("metric_id") == metric_id]
    deterministic = [item for item in relevant if _assertion_method(item) == "deterministic" and item.get("eligible", True)]
    evaluated = [item for item in deterministic if item.get("passed") is not None]
    manual = [item for item in relevant if _assertion_method(item) == "manual"]
    metric["eligibleCount"] = len(deterministic)
    metric["evaluatedCount"] = len(evaluated)
    metric["denominator"] = len(evaluated)
    if not relevant:
        metric["missingReason"] = "not_applicable"
        return metric
    if not evaluated:
        metric["evaluationMethod"] = "manual" if manual else "not_evaluated"
        metric["missingReason"] = "manual_review" if manual else "not_evaluated"
        return metric
    if METRIC_BY_ID[metric_id].direction == "lower_is_better":
        numerator = sum(1 for item in evaluated if item.get("passed") is False)
    else:
        numerator = sum(1 for item in evaluated if item.get("passed") is True)
    metric["numerator"] = numerator
    metric["value"] = round(numerator / len(evaluated), 4)
    metric["missingReason"] = None
    metric["evaluationMethod"] = "deterministic"
    metric["failures"] = [item for item in evaluated if item.get("passed") is False]
    return metric


def _assertion_method(assertion: dict[str, Any]) -> str:
    method = assertion.get("evaluationMethod") or assertion.get("evaluation_method")
    if method in {"deterministic", "manual", "not_evaluated"}:
        return method
    return "manual" if assertion.get("operator") == "manual" else "deterministic"

def trace_observation_metrics(trace_snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fallback_metric = empty_metric("fallback_activation_rate", "not_applicable")
    agent_metric = empty_metric("agent_execution_failure_rate", "not_applicable")
    latency_metric = empty_metric("average_response_time_ms", "not_applicable")
    agent_events: list[dict[str, Any]] = []
    related = trace_snapshot.get("relatedTraces") if isinstance(trace_snapshot, dict) else None
    snapshots = related if isinstance(related, list) else [trace_snapshot] if trace_snapshot else []
    fallback_signals = []
    trace_documents = 0
    for snapshot in snapshots:
        trace = snapshot.get("traceJson") if isinstance(snapshot, dict) else None
        if not isinstance(trace, dict):
            continue
        trace_documents += 1
        fallback_signals.extend(
            {"kind": "timeline", "stage": node.get("stage"), "summary": node.get("summary")}
            for node in trace.get("timeline", [])
            if isinstance(node, dict) and str(node.get("kind", "")).lower() == "fallback"
        )
        fallback_signals.extend(
            {"kind": "event", "agentName": event.get("agentName") or event.get("agent_name")}
            for event in trace.get("events", [])
            if isinstance(event, dict) and event.get("fallbackUsed") is True
        )
        agent_events.extend(
            event for event in trace.get("events", [])
            if isinstance(event, dict) and event.get("eventType") == "AGENT_CALL"
        )
    if trace_documents:
        activated = bool(fallback_signals)
        fallback_metric.update({
            "value": 1.0 if activated else 0.0,
            "numerator": 1 if activated else 0,
            "denominator": 1,
            "eligibleCount": 1,
            "evaluatedCount": 1,
            "missingReason": None,
            "method": "trace_observation",
            "evaluationMethod": "deterministic",
            "failures": fallback_signals,
        })
    if agent_events:
        failures = sum(1 for event in agent_events if str(event.get("status", "")).upper() == "FAILED")
        agent_metric.update({
            "value": round(failures / len(agent_events), 4),
            "numerator": failures,
            "denominator": len(agent_events),
            "eligibleCount": len(agent_events),
            "evaluatedCount": len(agent_events),
            "missingReason": None,
            "method": "trace_observation",
            "evaluationMethod": "deterministic",
            "failures": [
                {
                    "agentName": event.get("agentName") or event.get("agent_name"),
                    "errorMessage": event.get("errorMessage") or event.get("error_message"),
                }
                for event in agent_events
                if str(event.get("status", "")).upper() == "FAILED"
            ],
        })
    observation = trace_snapshot.get("observability") if isinstance(trace_snapshot, dict) else None
    latency = observation.get("latencyMs") if isinstance(observation, dict) else None
    if isinstance(latency, (int, float)) and not isinstance(latency, bool):
        latency_metric.update({
            "value": round(float(latency), 2),
            "numerator": float(latency),
            "denominator": 1,
            "eligibleCount": 1,
            "evaluatedCount": 1,
            "missingReason": None,
            "method": "trace_observation",
            "evaluationMethod": "deterministic",
        })
    return {
        "fallback_activation_rate": fallback_metric,
        "agent_execution_failure_rate": agent_metric,
        "average_response_time_ms": latency_metric,
    }


def aggregate_result_observation(results: list[dict[str, Any]], metric_id: str) -> dict[str, Any]:
    metric = empty_metric(metric_id, "not_applicable")
    observations = []
    for result in results:
        metrics = result.get("metrics") or result.get("metrics_json") or {}
        observation = metrics.get(metric_id) if isinstance(metrics, dict) else None
        if isinstance(observation, dict) and observation.get("denominator", 0):
            observations.append(observation)
    if not observations:
        return metric
    numerator = sum(float(item.get("numerator") or 0) for item in observations)
    denominator = sum(int(item.get("denominator") or 0) for item in observations)
    metric.update({
        "value": round(numerator / denominator, 4 if metric_id in {"fallback_activation_rate", "agent_execution_failure_rate"} else 2),
        "numerator": numerator,
        "denominator": denominator,
        "eligibleCount": sum(int(item.get("eligibleCount") or 0) for item in observations),
        "evaluatedCount": sum(int(item.get("evaluatedCount") or 0) for item in observations),
        "missingReason": None,
        "method": "trace_observation",
        "evaluationMethod": "deterministic",
        "failures": [failure for item in observations for failure in item.get("failures", [])],
    })
    return metric


def summarize_results(
    results: list[dict[str, Any]],
    case_metadata: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    merged: dict[str, list[dict[str, Any]]] = {metric_id: [] for metric_id in METRIC_BY_ID}
    for result in results:
        for assertion in result.get("assertions", []):
            metric_id = assertion.get("metricId") or assertion.get("metric_id")
            if metric_id in merged:
                merged[metric_id].append(assertion)
    metrics = [
        aggregate_result_observation(results, metric_id)
        if metric_id in TRACE_OBSERVATION_METRIC_IDS
        else aggregate_metric(assertions, metric_id)
        for metric_id, assertions in merged.items()
    ]
    categories: dict[str, list[float]] = {}
    for metric in metrics:
        if not metric["scored"] or metric["value"] is None:
            continue
        value = metric["value"]
        if metric["direction"] == "lower_is_better":
            value = 1 - value
        categories.setdefault(metric["category"], []).append(value)
    category_scores = {
        category: round(sum(values) / len(values) * 100, 2)
        for category, values in categories.items()
        if values
    }
    overall = round(sum(category_scores.values()) / len(category_scores), 2) if category_scores else None
    failed_cases = sum(1 for result in results if result.get("status") == "failed")
    error_cases = sum(1 for result in results if result.get("status") == "error")
    evaluated_quality = sum(1 for metric in metrics if metric["scored"] and metric["value"] is not None)
    metric_by_id = {metric["id"]: metric for metric in metrics}
    deterministic_target = [
        metric_id for metric_id in DETERMINISTIC_TARGET_METRIC_IDS
        if metric_by_id[metric_id]["evaluationMethod"] == "deterministic" and metric_by_id[metric_id]["value"] is not None
    ]
    deterministic_catalog = [
        metric_id for metric_id in QUALITY_METRIC_IDS
        if metric_by_id[metric_id]["evaluationMethod"] == "deterministic" and metric_by_id[metric_id]["value"] is not None
    ]
    all_assertions = [assertion for result in results for assertion in result.get("assertions", [])]
    target_assertions = [
        assertion for assertion in all_assertions
        if (assertion.get("metricId") or assertion.get("metric_id")) in DETERMINISTIC_TARGET_METRIC_IDS
    ]
    deterministic_eligible = [assertion for assertion in target_assertions if _assertion_method(assertion) == "deterministic"]
    deterministic_evaluated = [assertion for assertion in deterministic_eligible if assertion.get("passed") is not None]
    manual_metric_ids = sorted({
        assertion.get("metricId") or assertion.get("metric_id")
        for assertion in target_assertions
        if _assertion_method(assertion) == "manual"
    })
    not_evaluated_metric_ids = [
        metric_id for metric_id in DETERMINISTIC_TARGET_METRIC_IDS
        if metric_by_id[metric_id]["value"] is None and metric_id not in manual_metric_ids
    ]
    case_counts = {
        "total": len(results),
        "passed": sum(1 for result in results if result.get("status") == "passed"),
        "failed": failed_cases,
        "error": error_cases,
        "notEvaluated": sum(1 for result in results if result.get("status") == "not_evaluated"),
    }
    summary = {
        "overallScore": overall,
        "categoryScores": category_scores,
        "metrics": metrics,
        "coverage": {
            "evaluatedQualityMetrics": evaluated_quality,
            "qualityMetricCount": len(QUALITY_METRIC_IDS),
            "status": "full" if evaluated_quality == len(QUALITY_METRIC_IDS) else "partial" if evaluated_quality else "empty",
            "deterministicEvaluatedMetricCount": len(deterministic_target),
            "deterministicMetricCount": len(DETERMINISTIC_TARGET_METRIC_IDS),
            "deterministicMetricRate": round(len(deterministic_target) / len(DETERMINISTIC_TARGET_METRIC_IDS), 4),
            "catalogDeterministicEvaluatedMetricCount": len(deterministic_catalog),
            "catalogQualityMetricCount": len(QUALITY_METRIC_IDS),
            "deterministicEvaluatedAssertionCount": len(deterministic_evaluated),
            "deterministicEligibleAssertionCount": len(deterministic_eligible),
            "deterministicAssertionRate": round(len(deterministic_evaluated) / len(deterministic_eligible), 4) if deterministic_eligible else 0.0,
            "manualReviewMetricIds": manual_metric_ids,
            "notEvaluatedMetricIds": not_evaluated_metric_ids,
        },
        "caseCounts": case_counts,
        "caseRates": _case_rates(case_counts),
        "performance": summarize_performance(results),
        "groups": {"byDomain": {}, "byCaseType": {}, "byTag": {}},
        "routingDiagnostics": routing_diagnostics(results),
    }
    if case_metadata:
        summary["groups"] = _group_summaries(results, case_metadata)
    return summary


def _case_rates(counts: dict[str, int]) -> dict[str, float | None]:
    total = counts["total"]
    if not total:
        return {"passRate": None, "failureRate": None, "errorRate": None, "notEvaluatedRate": None}
    return {
        "passRate": round(counts["passed"] / total, 4),
        "failureRate": round(counts["failed"] / total, 4),
        "errorRate": round(counts["error"] / total, 4),
        "notEvaluatedRate": round(counts["notEvaluated"] / total, 4),
    }


def _group_summaries(
    results: list[dict[str, Any]],
    case_metadata: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    dimensions: dict[str, dict[str, list[dict[str, Any]]]] = {
        "byDomain": {},
        "byCaseType": {},
        "byTag": {},
    }
    for result in results:
        metadata = case_metadata.get(str(result.get("caseId"))) or {}
        values = {
            "byDomain": [str(metadata.get("domain") or "unknown")],
            "byCaseType": [str(metadata.get("caseType") or "general")],
            "byTag": [str(tag) for tag in metadata.get("tags") or [] if str(tag)],
        }
        for dimension, keys in values.items():
            for key in dict.fromkeys(keys):
                dimensions[dimension].setdefault(key, []).append(result)
    output: dict[str, dict[str, Any]] = {}
    for dimension, groups in dimensions.items():
        output[dimension] = {}
        for key, grouped_results in sorted(groups.items()):
            grouped = summarize_results(grouped_results)
            output[dimension][key] = {
                name: value for name, value in grouped.items()
                if name not in {"groups", "performance", "routingDiagnostics"}
            }
    return output


def routing_diagnostics(results: list[dict[str, Any]]) -> dict[str, Any]:
    pairs: list[tuple[str, str]] = []
    for result in results:
        for assertion in result.get("assertions", []):
            if (assertion.get("metricId") or assertion.get("metric_id")) != "domain_routing_accuracy":
                continue
            if _assertion_method(assertion) != "deterministic" or assertion.get("passed") is None:
                continue
            expected = assertion.get("expected") or {}
            actual = assertion.get("actual") or {}
            expected_domain = expected.get("domain") if isinstance(expected, dict) else None
            actual_domain = actual.get("actualDomain") if isinstance(actual, dict) else None
            if expected_domain and actual_domain:
                pairs.append((str(expected_domain), str(actual_domain)))
    if not pairs:
        return {
            "sampleCount": 0,
            "accuracy": None,
            "macroPrecision": None,
            "macroRecall": None,
            "macroF1": None,
            "perDomain": {},
            "confusionMatrix": {},
        }
    labels = sorted({label for pair in pairs for label in pair})
    confusion = {
        expected: {actual: sum(1 for gold, predicted in pairs if gold == expected and predicted == actual) for actual in labels}
        for expected in labels
    }
    per_domain = {}
    for label in labels:
        true_positive = confusion[label][label]
        false_positive = sum(confusion[other][label] for other in labels if other != label)
        false_negative = sum(confusion[label][other] for other in labels if other != label)
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_domain[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": sum(confusion[label].values()),
        }
    return {
        "sampleCount": len(pairs),
        "accuracy": round(sum(1 for gold, predicted in pairs if gold == predicted) / len(pairs), 4),
        "macroPrecision": round(sum(item["precision"] for item in per_domain.values()) / len(per_domain), 4),
        "macroRecall": round(sum(item["recall"] for item in per_domain.values()) / len(per_domain), 4),
        "macroF1": round(sum(item["f1"] for item in per_domain.values()) / len(per_domain), 4),
        "perDomain": per_domain,
        "confusionMatrix": confusion,
    }


def summarize_performance(results: list[dict[str, Any]]) -> dict[str, Any]:
    observations = []
    for result in results:
        snapshot = result.get("traceSnapshot") or result.get("trace_snapshot") or {}
        observation = snapshot.get("observability") if isinstance(snapshot, dict) else None
        if isinstance(observation, dict):
            observations.append(observation)
    latencies = [
        float(item["latencyMs"])
        for item in observations
        if isinstance(item.get("latencyMs"), (int, float)) and not isinstance(item.get("latencyMs"), bool)
    ]
    token_values = [
        int(item["totalTokens"])
        for item in observations
        if isinstance(item.get("totalTokens"), int) and not isinstance(item.get("totalTokens"), bool)
    ]
    known_costs = [
        float(item["knownEstimatedCost"])
        for item in observations
        if isinstance(item.get("knownEstimatedCost"), (int, float)) and not isinstance(item.get("knownEstimatedCost"), bool)
    ]
    provider_call_count = sum(int(item.get("providerCallCount") or 0) for item in observations)
    unreported = sum(int(item.get("unreportedUsageCallCount") or 0) for item in observations)
    unknown_price = sum(int(item.get("unknownPriceCallCount") or 0) for item in observations)
    total_tokens = sum(token_values) if token_values else None
    ordered = sorted(latencies)
    p95 = ordered[max(0, ceil(len(ordered) * 0.95) - 1)] if ordered else None
    known_cost = round(sum(known_costs), 12) if known_costs else None
    estimated_total = known_cost if provider_call_count and not unreported and not unknown_price else None
    return {
        "caseCount": len(results),
        "latencySampleCount": len(latencies),
        "averageLatencyMs": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "p95LatencyMs": p95,
        "totalTokens": total_tokens,
        "averageTokensPerCase": round(total_tokens / len(token_values), 2) if token_values else None,
        "estimatedTotalCost": estimated_total,
        "knownEstimatedCost": known_cost,
        "tokenUsageCaseCount": len(token_values),
        "providerCallCount": provider_call_count,
        "unreportedUsageCallCount": unreported,
        "unknownPriceCallCount": unknown_price,
    }
