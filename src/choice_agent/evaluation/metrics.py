from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EVALUATOR_VERSION = "evaluation-v1"


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
    MetricDefinition("constraint_extraction_accuracy", "需求理解", "约束抽取准确率", description="字段、值、硬软属性和候选归属正确的约束占比。"),
    MetricDefinition("correction_update_accuracy", "需求理解", "用户纠正后的状态更新准确率", description="纠正后新值生效、旧值移除且归属正确的轮次占比。"),
    MetricDefinition("hard_constraint_satisfaction", "决策质量", "硬约束满足率", description="推荐满足全部硬约束的可判定请求占比。"),
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
    MetricDefinition("agent_execution_failure_rate", "工程可靠性", "Agent 执行失败率", direction="lower_is_better", description="失败 AgentRun 占全部 AgentRun 比例。"),
    MetricDefinition("average_response_time_ms", "工程可靠性", "平均响应时间", direction="lower_is_better", unit="ms", scored=False, description="有耗时请求的 durationMs 均值；单独展示，不进入总分。"),
)

METRIC_BY_ID = {item.metric_id: item for item in METRIC_DEFINITIONS}
QUALITY_METRIC_IDS = [item.metric_id for item in METRIC_DEFINITIONS if item.scored]


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
        "failures": [],
    }


def aggregate_metric(assertions: list[dict[str, Any]], metric_id: str) -> dict[str, Any]:
    metric = empty_metric(metric_id)
    relevant = [item for item in assertions if item.get("metricId") == metric_id or item.get("metric_id") == metric_id]
    eligible = [item for item in relevant if item.get("eligible", True)]
    evaluated = [item for item in eligible if item.get("passed") is not None]
    metric["eligibleCount"] = len(eligible)
    metric["evaluatedCount"] = len(evaluated)
    metric["denominator"] = len(evaluated)
    if not eligible:
        metric["missingReason"] = "not_applicable"
        return metric
    if not evaluated:
        metric["missingReason"] = "not_evaluated"
        return metric
    if METRIC_BY_ID[metric_id].direction == "lower_is_better":
        numerator = sum(1 for item in evaluated if item.get("passed") is False)
    else:
        numerator = sum(1 for item in evaluated if item.get("passed") is True)
    metric["numerator"] = numerator
    metric["value"] = round(numerator / len(evaluated), 4)
    metric["missingReason"] = None
    metric["failures"] = [item for item in evaluated if item.get("passed") is False]
    return metric


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, list[dict[str, Any]]] = {metric_id: [] for metric_id in METRIC_BY_ID}
    for result in results:
        for assertion in result.get("assertions", []):
            metric_id = assertion.get("metricId") or assertion.get("metric_id")
            if metric_id in merged:
                merged[metric_id].append(assertion)
    metrics = [aggregate_metric(assertions, metric_id) for metric_id, assertions in merged.items()]
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
    return {
        "overallScore": overall,
        "categoryScores": category_scores,
        "metrics": metrics,
        "coverage": {
            "evaluatedQualityMetrics": evaluated_quality,
            "qualityMetricCount": len(QUALITY_METRIC_IDS),
            "status": "full" if evaluated_quality == len(QUALITY_METRIC_IDS) else "partial" if evaluated_quality else "empty",
        },
        "caseCounts": {
            "total": len(results),
            "passed": sum(1 for result in results if result.get("status") == "passed"),
            "failed": failed_cases,
            "error": error_cases,
            "notEvaluated": sum(1 for result in results if result.get("status") == "not_evaluated"),
        },
    }
