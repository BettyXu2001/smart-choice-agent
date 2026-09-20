from choice_agent.decision.clarification import select_decision_question
from choice_agent.decision.quality import assess_decision_quality
from choice_agent.schemas import Candidate, Criterion, DecisionState, ScoreContribution


def contribution(key, value, score, weight=1.0):
    return ScoreContribution(
        criterion_key=key,
        raw_value=value,
        normalized_score=score,
        weight=weight,
        weighted_score=score * weight,
    )


def decision_with(candidates):
    return DecisionState(
        decision_id="quality",
        session_id="quality-session",
        domain="generic",
        criteria=[
            Criterion(key="fit", label="目标匹配"),
            Criterion(key="cost", label="成本"),
        ],
        candidates=candidates,
    )


def test_quality_assessment_reports_complete_stable_decision():
    decision = decision_with([
        Candidate(
            candidate_id="a", name="A", score=0.8, origin="manual",
            score_breakdown=[contribution("fit", 90, 90), contribution("cost", 70, 70)],
        ),
        Candidate(
            candidate_id="b", name="B", score=0.55, origin="manual",
            score_breakdown=[contribution("fit", 60, 60), contribution("cost", 50, 50)],
        ),
    ])

    assessment = assess_decision_quality(decision)

    assert assessment.status == "available"
    assert assessment.data_completeness == 1
    assert assessment.score_margin == 0.25
    assert assessment.robustness_level == "high"
    assert not assessment.sensitive_criteria


def test_quality_assessment_finds_weight_sensitive_criterion():
    decision = decision_with([
        Candidate(
            candidate_id="a", name="A", score=0.65,
            score_breakdown=[contribution("fit", 90, 90), contribution("cost", 40, 40)],
        ),
        Candidate(
            candidate_id="b", name="B", score=0.625,
            score_breakdown=[contribution("fit", 60, 60), contribution("cost", 65, 65)],
        ),
    ])

    decision.quality_assessment = assess_decision_quality(decision)
    question = select_decision_question(decision)

    assert decision.quality_assessment.robustness < 1
    assert {item.criterion_key for item in decision.quality_assessment.sensitive_criteria}
    assert question is not None
    assert question.expected_impact == "may_change_recommendation"


def test_missing_value_question_only_when_boundary_can_change_winner():
    decision = decision_with([
        Candidate(
            candidate_id="a", name="A", score=0.65,
            score_breakdown=[contribution("fit", 80, 80), contribution("cost", None, 50)],
        ),
        Candidate(
            candidate_id="b", name="B", score=0.64,
            score_breakdown=[contribution("fit", 68, 68), contribution("cost", 60, 60)],
        ),
    ])

    decision.quality_assessment = assess_decision_quality(decision)
    question = select_decision_question(decision)

    assert decision.quality_assessment.data_completeness == 0.75
    assert question is not None
    assert question.candidate_id == "a"
    assert question.criterion_key == "cost"
    assert "可能改变" in question.question


def test_qualitative_candidates_do_not_get_fake_robustness_or_question():
    decision = decision_with([
        Candidate(
            candidate_id="a", name="A", score=0.5,
            score_breakdown=[contribution("fit", None, 50), contribution("cost", None, 50)],
        ),
        Candidate(
            candidate_id="b", name="B", score=0.5,
            score_breakdown=[contribution("fit", None, 50), contribution("cost", None, 50)],
        ),
    ])

    decision.quality_assessment = assess_decision_quality(decision)

    assert decision.quality_assessment.status == "insufficient_data"
    assert decision.quality_assessment.robustness is None
    assert select_decision_question(decision) is None