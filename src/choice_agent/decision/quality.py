from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from choice_agent.schemas import Candidate, DecisionQualityAssessment, DecisionState, SensitiveCriterion


@dataclass(frozen=True)
class ScoreScenario:
    criterion_key: str
    description: str
    factor: float = 1.0
    missing_candidate_id: str | None = None
    missing_score: float | None = None


def _score(candidate: Candidate, scenario: ScoreScenario | None = None) -> float | None:
    total_weight = 0.0
    total_score = 0.0
    for contribution in candidate.score_breakdown:
        weight = contribution.weight
        normalized = contribution.normalized_score
        if scenario and contribution.criterion_key == scenario.criterion_key:
            weight *= scenario.factor
            if (
                contribution.raw_value is None
                and scenario.missing_candidate_id == candidate.candidate_id
                and scenario.missing_score is not None
            ):
                normalized = scenario.missing_score
        if weight <= 0:
            continue
        total_weight += weight
        total_score += normalized * weight
    return total_score / total_weight / 100 if total_weight > 0 else None


def ranked_candidate_id(candidates: list[Candidate], scenario: ScoreScenario | None = None) -> str | None:
    scored = [
        (score, -index, candidate.candidate_id)
        for index, candidate in enumerate(candidates)
        if (score := _score(candidate, scenario)) is not None
    ]
    return max(scored)[2] if scored else None


def scenario_scores(candidates: list[Candidate], scenario: ScoreScenario) -> dict[str, float]:
    return {
        candidate.candidate_id: score
        for candidate in candidates
        if (score := _score(candidate, scenario)) is not None
    }


def sensitivity_scenarios(decision: DecisionState) -> Iterable[ScoreScenario]:
    criterion_keys: set[str] = set()
    for criterion in decision.criteria:
        if criterion.weight <= 0:
            continue
        criterion_keys.add(criterion.key)
        yield ScoreScenario(criterion.key, "权重降低为一半", factor=0.5)
        yield ScoreScenario(criterion.key, "权重提高为一点五倍", factor=1.5)
    for candidate in decision.candidates[:2]:
        for contribution in candidate.score_breakdown:
            if contribution.raw_value is not None or contribution.criterion_key not in criterion_keys:
                continue
            yield ScoreScenario(
                contribution.criterion_key, "缺失值按最低边界计算",
                missing_candidate_id=candidate.candidate_id, missing_score=0,
            )
            yield ScoreScenario(
                contribution.criterion_key, "缺失值按最高边界计算",
                missing_candidate_id=candidate.candidate_id, missing_score=100,
            )


def assess_decision_quality(decision: DecisionState) -> DecisionQualityAssessment:
    candidates = decision.candidates[:2]
    if (
        len(candidates) < 2
        or any(not item.score_breakdown for item in candidates)
        or not any(
            contribution.raw_value is not None
            for candidate in candidates
            for contribution in candidate.score_breakdown
        )
    ):
        return DecisionQualityAssessment(
            status="insufficient_data",
            warnings=["至少需要两个带评分拆解的候选才能评估结论稳健度。"],
        )

    completeness: list[float] = []
    for candidate in candidates:
        total = sum(item.weight for item in candidate.score_breakdown if item.weight > 0)
        present = sum(
            item.weight for item in candidate.score_breakdown
            if item.weight > 0 and item.raw_value is not None
        )
        completeness.append(present / total if total else 0.0)

    labels = {item.key: item.label for item in decision.criteria}
    baseline_id = candidates[0].candidate_id
    scenarios = list(sensitivity_scenarios(decision))
    stable_count = 0
    sensitive: list[SensitiveCriterion] = []
    seen_sensitive: set[tuple[str, str | None]] = set()
    for scenario in scenarios:
        winner = ranked_candidate_id(candidates, scenario)
        if winner == baseline_id:
            stable_count += 1
            continue
        key = (scenario.criterion_key, winner)
        if key in seen_sensitive:
            continue
        seen_sensitive.add(key)
        sensitive.append(SensitiveCriterion(
            criterion_key=scenario.criterion_key,
            label=labels.get(scenario.criterion_key, scenario.criterion_key),
            scenario=scenario.description,
            changed_to_candidate_id=winner,
        ))

    robustness = stable_count / len(scenarios) if scenarios else None
    level = (
        "unavailable" if robustness is None else
        "high" if robustness >= 0.8 else
        "medium" if robustness >= 0.5 else "low"
    )
    warnings: list[str] = []
    if any(item.origin == "web" for item in candidates):
        warnings.append("网页来源链接已校验，但内容未经过独立事实核实。")
    if any(item.origin in {"fixture", "demo"} for item in candidates):
        warnings.append("包含演示数据，不能代表实时情况。")
    if any(item.origin == "manual" for item in candidates):
        warnings.append("包含用户提供的数据，尚未经外部核实。")
    if any(value < 1 for value in completeness):
        warnings.append("前两名仍有评分维度缺少数据。")

    return DecisionQualityAssessment(
        status="available",
        data_completeness=round(sum(completeness) / len(completeness), 4),
        score_margin=round(max(0.0, candidates[0].score - candidates[1].score), 4),
        robustness=round(robustness, 4) if robustness is not None else None,
        robustness_level=level,
        sensitive_criteria=sensitive,
        warnings=warnings,
        scenario_count=len(scenarios),
    )