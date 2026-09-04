from __future__ import annotations

from choice_agent.schemas import DecisionNextAction, DecisionState, DecisionStatus


class DecisionStateTransitionError(ValueError):
    pass


class DecisionRevisionError(ValueError):
    pass


_ALLOWED_TRANSITIONS: dict[DecisionStatus, set[DecisionStatus]] = {
    DecisionStatus.DRAFT: {
        DecisionStatus.CLARIFYING,
        DecisionStatus.SEARCHING,
        DecisionStatus.COMPARING,
        DecisionStatus.DECIDED,
    },
    DecisionStatus.CLARIFYING: {
        DecisionStatus.CLARIFYING,
        DecisionStatus.SEARCHING,
        DecisionStatus.COMPARING,
        DecisionStatus.DECIDED,
    },
    DecisionStatus.SEARCHING: {DecisionStatus.COMPARING, DecisionStatus.DECIDED},
    DecisionStatus.COMPARING: {DecisionStatus.CLARIFYING, DecisionStatus.COMPARING, DecisionStatus.DECIDED},
    DecisionStatus.DECIDED: {
        DecisionStatus.CLARIFYING,
        DecisionStatus.SEARCHING,
        DecisionStatus.COMPARING,
        DecisionStatus.DECIDED,
    },
}


def transition_decision(
    decision: DecisionState,
    target: DecisionStatus,
    next_action: DecisionNextAction | None = None,
) -> DecisionState:
    if decision.status != target and target not in _ALLOWED_TRANSITIONS[decision.status]:
        raise DecisionStateTransitionError(
            f"Illegal decision status transition: {decision.status.value} -> {target.value}"
        )
    decision.status = target
    if next_action is not None:
        decision.next_action = next_action
    return decision


def assert_expected_revision(actual_revision: int, expected_revision: int | None) -> None:
    if expected_revision is None:
        return
    if expected_revision != actual_revision:
        raise DecisionRevisionError(
            f"Decision revision mismatch: expected {expected_revision}, actual {actual_revision}"
        )
