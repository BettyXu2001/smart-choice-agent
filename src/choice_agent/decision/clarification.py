from __future__ import annotations

from choice_agent.decision.quality import ScoreScenario, ranked_candidate_id, scenario_scores
from choice_agent.schemas import DecisionQuestion, DecisionState


def select_decision_question(decision: DecisionState) -> DecisionQuestion | None:
    candidates = decision.candidates[:2]
    if (
        not decision.quality_assessment
        or decision.quality_assessment.status == "insufficient_data"
        or len(candidates) < 2
        or any(not item.score_breakdown for item in candidates)
    ):
        return None

    baseline_id = candidates[0].candidate_id
    baseline_margin = candidates[0].score - candidates[1].score
    labels = {item.key: item.label for item in decision.criteria}
    names = {item.candidate_id: item.name for item in candidates}
    best: tuple[float, DecisionQuestion] | None = None

    for candidate in candidates:
        for contribution in candidate.score_breakdown:
            if contribution.raw_value is not None:
                continue
            for boundary, description in ((0.0, "最低边界"), (100.0, "最高边界")):
                scenario = ScoreScenario(
                    contribution.criterion_key,
                    f"缺失值按{description}计算",
                    missing_candidate_id=candidate.candidate_id,
                    missing_score=boundary,
                )
                winner = ranked_candidate_id(candidates, scenario)
                if winner is None or winner == baseline_id:
                    continue
                scores = scenario_scores(candidates, scenario)
                changed_margin = abs(
                    scores.get(candidates[0].candidate_id, 0)
                    - scores.get(candidates[1].candidate_id, 0)
                )
                impact = abs(changed_margin - abs(baseline_margin))
                label = labels.get(contribution.criterion_key, contribution.criterion_key)
                question = DecisionQuestion(
                    key=f"missing:{candidate.candidate_id}:{contribution.criterion_key}",
                    question=(
                        f"{candidate.name} 的“{label}”目前缺少可比数据，"
                        f"这项信息可能改变 {candidates[0].name} 与 {candidates[1].name} 的排序。"
                        "你能补充吗？"
                    ),
                    reason=f"按{description}测试时，当前第一名会变为 {names.get(winner, winner)}。",
                    candidate_id=candidate.candidate_id,
                    criterion_key=contribution.criterion_key,
                )
                if best is None or impact > best[0]:
                    best = (impact, question)

    if best is not None:
        return best[1]

    assessment = decision.quality_assessment
    if assessment and assessment.sensitive_criteria:
        item = assessment.sensitive_criteria[0]
        return DecisionQuestion(
            key=f"weight:{item.criterion_key}",
            question=(
                f"你对“{item.label}”的重视程度可能改变 "
                f"{candidates[0].name} 与 {candidates[1].name} 的排序。"
                "这项对你有多重要？"
            ),
            reason=f"{item.scenario}时，当前第一名会发生变化。",
            criterion_key=item.criterion_key,
        )
    return None