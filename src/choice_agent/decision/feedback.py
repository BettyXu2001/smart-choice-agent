from __future__ import annotations

import re
from typing import Any, Literal

FeedbackType = Literal[
    "candidate_dislike",
    "batch_reject",
    "preference_update",
    "recommendation_misaligned",
    "refresh_request",
]


def classify_feedback(message: str, *, has_candidates: bool = False) -> FeedbackType | None:
    text = message.strip().lower()
    if not text:
        return None
    if any(token in text for token in ("换一批", "再找一批", "都不喜欢", "都不太想吃", "都不想吃", "这些都不想吃", "整批不满意", "这批不行", "这一批不行", "没有一个合适", "都不合适", "全部不合适")):
        return "batch_reject"
    if any(token in text for token in ("刷新候选", "刷新一下", "重新搜索", "重新检索", "重新找")):
        return "refresh_request"
    if any(token in text for token in ("推荐偏离", "偏离目标", "不符合目标", "方向不对", "推荐错了", "不是我要的")):
        return "recommendation_misaligned"
    if has_candidates and re.search(r"(?:不喜欢|不想要|不合适|排除|不要).+", text):
        return "candidate_dislike"
    if re.search(r"更看重|最看重|改成|调整为|优先|偏好|预算|用途|出发|天数|清淡|口味", text):
        return "preference_update"
    return None


def constraint_audit(decision) -> dict[str, Any]:
    pool = list(decision.domain_state.get("candidatePool", []))
    hard = [item for item in decision.constraints if getattr(item.kind, "value", item.kind) == "hard"]
    primary_id = decision.recommendation.primary_candidate_id if decision.recommendation else None
    primary = next((item for item in pool if item.get("candidateId") == primary_id), None)
    violations = _violations(primary, hard) if primary else ["recommended_candidate_missing"]
    viable = [
        item.get("candidateId") for item in pool
        if item.get("candidateId") not in set(decision.excluded_candidates) and not _violations(item, hard)
    ]
    mode = "rerank" if violations and viable else "refresh"
    return {
        "checkedConstraintIds": [item.constraint_id or item.key for item in hard],
        "recommendationCandidateId": primary_id,
        "violations": violations,
        "viableCandidateIds": viable,
        "executionMode": mode,
    }


def _violations(candidate: dict[str, Any] | None, constraints) -> list[str]:
    if candidate is None:
        return ["candidate_missing"]
    attributes = candidate.get("attributes", {})
    result: list[str] = []
    for constraint in constraints:
        value = attributes.get(constraint.key)
        expected = constraint.value if constraint.value is not None else constraint.values
        if not _matches(value, constraint.operator, expected):
            result.append(constraint.constraint_id or constraint.key)
    return result


def _matches(actual: Any, operator: str, expected: Any) -> bool:
    if operator in {"lt", "lte", "gt", "gte"}:
        if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
            return False
        return {"lt": actual < expected, "lte": actual <= expected, "gt": actual > expected, "gte": actual >= expected}[operator]
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    actual_values = set(actual if isinstance(actual, list) else [actual])
    expected_values = set(expected if isinstance(expected, list) else [expected])
    if operator == "contains_all":
        return expected_values <= actual_values
    if operator == "not_contains":
        return not bool(actual_values & expected_values)
    return bool(actual_values & expected_values)