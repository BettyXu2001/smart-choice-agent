from __future__ import annotations

from typing import Any

from choice_agent.schemas import DecisionState


def decision_projection(decision: DecisionState) -> dict[str, Any]:
    """Return only business state needed for regression comparisons."""
    recommendation = decision.recommendation.model_dump(mode="json", by_alias=True) if decision.recommendation else None
    return {
        "decisionId": decision.decision_id,
        "domain": decision.domain,
        "revision": decision.revision,
        "constraints": [item.model_dump(mode="json", by_alias=True) for item in decision.constraints],
        "criteria": [item.model_dump(mode="json", by_alias=True) for item in decision.criteria],
        "candidates": [item.model_dump(mode="json", by_alias=True) for item in decision.candidates],
        "excludedCandidates": list(decision.excluded_candidates),
        "recommendation": recommendation,
        "status": decision.status.value,
    }
