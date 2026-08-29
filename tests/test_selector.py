from choice_agent.decision.selector import (
    SelectionCandidate,
    normalize_avoid_recent_count,
    normalize_strategy,
    select_candidates,
)
from choice_agent.schemas import SelectionStrategy


def candidates():
    return [
        SelectionCandidate(candidate_id="a", name="A", score=0.1),
        SelectionCandidate(candidate_id="b", name="B", score=0.4),
        SelectionCandidate(candidate_id="c", name="C", score=0.5),
    ]


def test_ranked_strategy_keeps_existing_order():
    result = select_candidates(candidates(), "ranked")
    assert result.selected_id == "a"
    assert result.ordered_ids == ["a", "b", "c"]
    assert result.insights.selected_probability == 1
    assert "按匹配度排序" in result.insights.tags


def test_random_strategy_can_be_deterministic():
    result = select_candidates(candidates(), "random", random_fn=lambda: 0.5)
    assert result.selected_id == "b"
    assert result.ordered_ids == ["b", "a", "c"]
    assert result.insights.selected_probability == 1 / 3


def test_weighted_strategy_uses_scores_as_weights():
    assert select_candidates(candidates(), "weighted", random_fn=lambda: 0).selected_id == "a"
    result = select_candidates(candidates(), "weighted", random_fn=lambda: 0.99)
    assert result.selected_id == "c"
    assert result.insights.selected_probability == 0.5


def test_weighted_strategy_falls_back_to_random_when_scores_are_zero():
    zero_score_candidates = [
        SelectionCandidate(candidate_id="a", name="A", score=0),
        SelectionCandidate(candidate_id="b", name="B", score=0),
    ]
    result = select_candidates(zero_score_candidates, "weighted", random_fn=lambda: 0.75)
    assert result.selected_id == "b"
    assert result.insights.selected_probability == 1 / 2


def test_least_recent_prefers_candidates_not_seen_in_session_history():
    result = select_candidates(
        candidates(), "least_recent", recent_ids=["b", "a"], random_fn=lambda: 0
    )
    assert result.selected_id == "c"
    assert result.ordered_ids == ["c", "a", "b"]
    assert result.insights.selected_probability == 1


def test_avoid_recent_count_filters_recent_candidates():
    result = select_candidates(candidates(), "ranked", recent_ids=["a", "b"], avoid_recent_count=1)
    assert result.selected_id == "a"
    assert result.ordered_ids == ["a", "c"]
    assert result.insights.candidate_count == 3
    assert result.insights.eligible_count == 2
    assert result.insights.recent_excluded_count == 1


def test_empty_candidate_list_returns_empty_result():
    result = select_candidates([], "weighted")
    assert result.selected_id is None
    assert result.ordered_ids == []
    assert result.insights.candidate_count == 0
    assert result.insights.eligible_count == 0


def test_invalid_strategy_and_avoid_recent_count_are_normalized_safely():
    assert normalize_strategy("unknown") == SelectionStrategy.RANKED
    assert normalize_strategy("least-recent") == SelectionStrategy.LEAST_RECENT
    assert normalize_avoid_recent_count(-3) == 0
    assert normalize_avoid_recent_count("abc") == 0
    assert normalize_avoid_recent_count(99) == 20