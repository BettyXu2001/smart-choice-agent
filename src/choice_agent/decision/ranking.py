from __future__ import annotations

from math import isfinite
from typing import Any, Callable, Protocol

from choice_agent.schemas import (
    Candidate,
    CandidateState,
    Criterion,
    CriterionDirection,
    DecisionState,
    MissingValuePolicy,
    ScoreContribution,
)


class CriterionEvaluator(Protocol):
    def evaluate(
        self, criterion: Criterion, candidate: Candidate, decision: DecisionState
    ) -> ScoreContribution | None:
        ...


class AttributeCriterionEvaluator:
    def __init__(self, ranges: dict[str, tuple[float, float]] | None = None):
        self.ranges = ranges or {}

    def evaluate(
        self, criterion: Criterion, candidate: Candidate, decision: DecisionState
    ) -> ScoreContribution | None:
        value = candidate.attributes.get(criterion.key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            return None
        if candidate.origin == "web" and not any(
            item.verification_status.value == "verified"
            and (item.criterion_key or item.key) == criterion.key
            and item.value == value
            for item in candidate.evidence
        ):
            return None
        low, high = self.ranges.get(criterion.key, (0.0, 100.0))
        span = max(0.0001, high - low)
        normalized = max(0.0, min(100.0, (float(value) - low) / span * 100))
        if criterion.direction == CriterionDirection.LOWER_IS_BETTER:
            normalized = 100 - normalized
        elif criterion.direction == CriterionDirection.TARGET and criterion.target is not None:
            distance = abs(float(value) - criterion.target)
            normalized = max(0.0, 100 - distance / span * 100)
        return ScoreContribution(
            criterion_key=criterion.key,
            raw_value=value,
            normalized_score=round(normalized, 4),
            weight=criterion.weight,
            weighted_score=round(normalized * criterion.weight, 4),
            explanation=f"{criterion.label}标准化得分 {normalized:.1f}",
            evidence_ids=[
                item.evidence_id for item in candidate.evidence
                if item.evidence_id
                and item.verification_status.value == "verified"
                and (item.criterion_key or item.key) == criterion.key
            ],
        )


class GenericRankingEngine:
    def rank(
        self,
        decision: DecisionState,
        candidates: list[Candidate],
        evaluator: CriterionEvaluator,
        tie_breaker: Callable[[Candidate], Any] | None = None,
    ) -> list[Candidate]:
        excluded = set(decision.excluded_candidates)
        ranked: list[Candidate] = []
        for candidate in candidates:
            if candidate.candidate_id in excluded:
                decision.candidate_state[candidate.candidate_id] = CandidateState(
                    status="excluded", reason="用户排除", updated_by="RankStage"
                )
                continue
            contributions: list[ScoreContribution] = []
            eliminate = False
            for criterion in decision.criteria:
                contribution = evaluator.evaluate(criterion, candidate, decision)
                if contribution is None:
                    if criterion.missing_policy == MissingValuePolicy.EXCLUDE:
                        eliminate = True
                        break
                    missing_score = 0 if criterion.missing_policy == MissingValuePolicy.WORST else 50
                    contribution = ScoreContribution(
                        criterion_key=criterion.key,
                        normalized_score=missing_score,
                        weight=criterion.weight,
                        weighted_score=missing_score * criterion.weight,
                        explanation="缺少数据，按最低分处理" if missing_score == 0 else "缺少数据，按中性分处理",
                    )
                if contribution is not None:
                    contributions.append(contribution)
            if eliminate or self._violates_hard_constraint(decision, candidate):
                decision.candidate_state[candidate.candidate_id] = CandidateState(
                    status="eliminated", reason="不满足硬约束", updated_by="RankStage"
                )
                continue
            total_weight = sum(item.weight for item in contributions)
            score = sum(item.weighted_score for item in contributions) / total_weight if total_weight else 0
            ranked.append(candidate.model_copy(update={"score": round(score / 100, 4), "score_breakdown": contributions}))
            decision.candidate_state[candidate.candidate_id] = CandidateState(
                status="active", updated_by="RankStage"
            )
        stable_key = tie_breaker or (lambda item: (item.name, item.candidate_id))
        ranked.sort(key=lambda item: (-item.score, stable_key(item)))
        return ranked

    def _violates_hard_constraint(self, decision: DecisionState, candidate: Candidate) -> bool:
        flattened = {
            str(value)
            for raw in candidate.attributes.values()
            for value in (raw if isinstance(raw, list) else [raw])
        }
        for constraint in decision.constraints:
            if constraint.kind.value != "hard":
                continue
            # Older Diet states encoded a cross-attribute deny list under this key.
            if constraint.key == "diet_exclusion":
                if flattened.intersection(constraint.values):
                    return True
                continue
            actual = candidate.attributes.get(constraint.key)
            expected = constraint.value if constraint.value is not None else constraint.values
            if actual is None:
                if constraint.key == "commute_minutes":
                    continue
                return True
            values = actual if isinstance(actual, list) else [actual]
            wanted = expected if isinstance(expected, list) else [expected]
            operator = constraint.operator
            if operator == "contains_any":
                passed = any(value in values for value in wanted)
            elif operator == "contains_all":
                passed = all(value in values for value in wanted)
            elif operator == "not_contains":
                passed = all(value not in values for value in wanted)
            elif operator == "eq":
                passed = actual == expected
            elif operator == "ne":
                passed = actual != expected
            elif operator in {"lt", "lte", "gt", "gte"}:
                if isinstance(actual, bool) or isinstance(expected, bool):
                    return True
                if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
                    return True
                if not isfinite(actual) or not isfinite(expected):
                    return True
                passed = {"lt": actual < expected, "lte": actual <= expected,
                          "gt": actual > expected, "gte": actual >= expected}[operator]
            else:
                raise ValueError(f"不支持的约束 operator：{operator}")
            if not passed:
                return True
        return False