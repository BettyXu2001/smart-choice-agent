import pytest

from choice_agent.decision.state_machine import (
    DecisionRevisionError,
    DecisionStateTransitionError,
    assert_expected_revision,
    transition_decision,
)
from choice_agent.schemas import DecisionNextAction, DecisionState, DecisionStatus


def test_decision_state_defaults_are_backward_compatible():
    state = DecisionState(decision_id="d1", session_id="s1")
    assert state.candidate_state == {}
    assert state.unanswered_questions == []
    assert state.assumptions == []
    assert state.trace_refs == []
    assert state.next_action == DecisionNextAction.WAIT_USER


def test_transition_decision_accepts_current_workflow_steps():
    state = DecisionState(decision_id="d1", session_id="s1")
    transition_decision(state, DecisionStatus.CLARIFYING, DecisionNextAction.ASK_CLARIFY)
    assert state.status == DecisionStatus.CLARIFYING
    assert state.next_action == DecisionNextAction.ASK_CLARIFY

    transition_decision(state, DecisionStatus.COMPARING, DecisionNextAction.COMPARE_CANDIDATES)
    transition_decision(state, DecisionStatus.DECIDED, DecisionNextAction.WAIT_USER)
    assert state.status == DecisionStatus.DECIDED
    assert state.next_action == DecisionNextAction.WAIT_USER


def test_transition_decision_rejects_illegal_backwards_transition():
    state = DecisionState(
        decision_id="d1", session_id="s1", status=DecisionStatus.SEARCHING
    )
    with pytest.raises(DecisionStateTransitionError):
        transition_decision(state, DecisionStatus.CLARIFYING)


def test_expected_revision_check_allows_optional_and_matching_revision():
    assert_expected_revision(3, None)
    assert_expected_revision(3, 3)
    with pytest.raises(DecisionRevisionError):
        assert_expected_revision(3, 2)
