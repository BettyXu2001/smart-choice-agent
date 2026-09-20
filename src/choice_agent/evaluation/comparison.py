from __future__ import annotations

from collections import defaultdict
from typing import Any

from choice_agent.evaluation.metrics import METRIC_BY_ID, summarize_results


class EvaluationComparisonError(ValueError):
    pass


_RESULT_KEY_FIELDS = ("caseId", "caseRevision", "repetition")
_STATUS_SEVERITY = {"passed": 0, "not_evaluated": 1, "failed": 2, "error": 3}
_STATUS_QUALITY = {"error": 0, "failed": 1, "not_evaluated": 2, "passed": 3}
_FAILURE_STATUSES = {"failed", "error"}


def compare_runs(
    baseline_run: dict[str, Any],
    candidate_run: dict[str, Any],
    baseline_results: list[dict[str, Any]],
    candidate_results: list[dict[str, Any]],
    *,
    case_titles: dict[str, str] | None = None,
) -> dict[str, Any]:
    _validate_runs(baseline_run, candidate_run)
    baseline_index = {_result_key(item): item for item in baseline_results}
    candidate_index = {_result_key(item): item for item in candidate_results}
    if baseline_index.keys() != candidate_index.keys():
        missing_candidate = sorted(baseline_index.keys() - candidate_index.keys())
        missing_baseline = sorted(candidate_index.keys() - baseline_index.keys())
        raise EvaluationComparisonError(
            "Run 的 Case/revision/repetition 集合不一致"
            f"；candidate 缺少 {_format_keys(missing_candidate)}"
            f"；baseline 缺少 {_format_keys(missing_baseline)}"
        )
    if not baseline_index:
        raise EvaluationComparisonError("Run 没有可比较的 Case Result")

    baseline_summary = summarize_results(list(baseline_index.values()))
    candidate_summary = summarize_results(list(candidate_index.values()))
    baseline_groups = _group_by_case(baseline_index.values())
    candidate_groups = _group_by_case(candidate_index.values())
    titles = case_titles or {}
    case_diffs = []
    for case_key in sorted(baseline_groups):
        baseline_group = baseline_groups[case_key]
        candidate_group = candidate_groups[case_key]
        baseline_case = _case_outcome(baseline_group)
        candidate_case = _case_outcome(candidate_group)
        classification = classify_case_diff(baseline_case, candidate_case)
        case_id, case_revision = case_key
        case_diffs.append(
            {
                "caseId": case_id,
                "caseRevision": case_revision,
                "title": titles.get(case_id),
                "classification": classification,
                "scoreDelta": _delta(candidate_case["score"], baseline_case["score"]),
                "baseline": baseline_case,
                "candidate": candidate_case,
            }
        )

    diff_counts = {key: 0 for key in ("improved", "regressed", "unchanged", "new_failure", "fixed")}
    for item in case_diffs:
        diff_counts[item["classification"]] += 1
    return {
        "baselineRun": _run_view(baseline_run, baseline_summary),
        "candidateRun": _run_view(candidate_run, candidate_summary),
        "aggregateDelta": _aggregate_delta(baseline_summary, candidate_summary),
        "caseDiffCounts": diff_counts,
        "caseDiffs": case_diffs,
    }


def classify_case_diff(baseline: dict[str, Any], candidate: dict[str, Any]) -> str:
    baseline_status = baseline["status"]
    candidate_status = candidate["status"]
    if baseline_status in _FAILURE_STATUSES and candidate_status == "passed":
        return "fixed"
    if baseline_status == "passed" and candidate_status in _FAILURE_STATUSES:
        return "new_failure"

    baseline_score = baseline.get("score")
    candidate_score = candidate.get("score")
    if baseline_score is not None and candidate_score is not None:
        if candidate_score > baseline_score:
            return "improved"
        if candidate_score < baseline_score:
            return "regressed"
    baseline_quality = _STATUS_QUALITY.get(baseline_status, -1)
    candidate_quality = _STATUS_QUALITY.get(candidate_status, -1)
    if candidate_quality > baseline_quality:
        return "improved"
    if candidate_quality < baseline_quality:
        return "regressed"
    return "unchanged"


def _validate_runs(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    if baseline.get("id") == candidate.get("id"):
        raise EvaluationComparisonError("Baseline 和 Candidate 必须是两个不同 Run")
    baseline_label = (baseline.get("runConfiguration") or {}).get("runLabel")
    candidate_label = (candidate.get("runConfiguration") or {}).get("runLabel")
    if baseline_label != "baseline" or candidate_label != "candidate":
        raise EvaluationComparisonError("Run 标签必须分别为 baseline 和 candidate")
    for label, run in (("Baseline", baseline), ("Candidate", candidate)):
        if run.get("status") not in {"completed", "partial"}:
            raise EvaluationComparisonError(f"{label} Run 尚未完成")
    for field, label in (
        ("datasetHash", "Regression Dataset"),
        ("evaluatorVersion", "Evaluator"),
        ("mode", "运行模式"),
    ):
        if baseline.get(field) != candidate.get(field):
            raise EvaluationComparisonError(f"{label} 不一致，不能比较")


def _result_key(result: dict[str, Any]) -> tuple[str, int, int]:
    try:
        return (
            str(result["caseId"]),
            int(result["caseRevision"]),
            int(result["repetition"]),
        )
    except KeyError as error:
        raise EvaluationComparisonError(f"Result 缺少比较键：{error.args[0]}") from error


def _format_keys(keys: list[tuple[str, int, int]]) -> str:
    if not keys:
        return "[]"
    preview = ", ".join(f"{case_id}@r{revision}#{repetition}" for case_id, revision, repetition in keys[:5])
    return f"[{preview}{', ...' if len(keys) > 5 else ''}]"


def _group_by_case(results) -> dict[tuple[str, int], list[dict[str, Any]]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[(result["caseId"], result["caseRevision"])].append(result)
    return dict(grouped)


def _case_outcome(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_results(results)
    status = max((item.get("status", "error") for item in results), key=lambda value: _STATUS_SEVERITY.get(value, 4))
    return {
        "status": status,
        "score": summary["overallScore"],
        "summary": summary,
        "resultIds": [item["id"] for item in sorted(results, key=lambda item: item["repetition"])],
    }


def _run_view(run: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run["id"],
        "status": run["status"],
        "datasetId": run.get("datasetId"),
        "datasetName": run.get("datasetName"),
        "datasetVersion": run.get("datasetVersion"),
        "datasetHash": run.get("datasetHash"),
        "evaluatorVersion": run.get("evaluatorVersion"),
        "mode": run.get("mode"),
        "runConfiguration": run.get("runConfiguration") or {},
        "summary": summary,
    }


def _aggregate_delta(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    baseline_categories = baseline.get("categoryScores") or {}
    candidate_categories = candidate.get("categoryScores") or {}
    category_names = sorted(set(baseline_categories) | set(candidate_categories))
    baseline_metrics = {item["id"]: item for item in baseline.get("metrics") or []}
    candidate_metrics = {item["id"]: item for item in candidate.get("metrics") or []}
    metrics = []
    for metric_id in METRIC_BY_ID:
        baseline_metric = baseline_metrics.get(metric_id, {})
        candidate_metric = candidate_metrics.get(metric_id, {})
        raw_delta = _delta(candidate_metric.get("value"), baseline_metric.get("value"), digits=4)
        quality_delta = raw_delta
        if raw_delta is not None and METRIC_BY_ID[metric_id].direction == "lower_is_better":
            quality_delta = round(-raw_delta, 4)
        metrics.append(
            {
                "metricId": metric_id,
                "rawDelta": raw_delta,
                "qualityDelta": quality_delta,
            }
        )
    return {
        "overallScore": _delta(candidate.get("overallScore"), baseline.get("overallScore")),
        "categoryScores": {
            category: _delta(candidate_categories.get(category), baseline_categories.get(category))
            for category in category_names
        },
        "metrics": metrics,
    }


def _delta(candidate: float | None, baseline: float | None, *, digits: int = 2) -> float | None:
    if candidate is None or baseline is None:
        return None
    return round(candidate - baseline, digits)
