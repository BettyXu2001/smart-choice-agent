from choice_agent.schemas import Candidate, Criterion, DecisionState, ScoreContribution, SlotBundle

class DietCriterionEvaluator:
    def evaluate(
        self, criterion: Criterion, candidate: Candidate, decision: DecisionState
    ) -> ScoreContribution | None:
        slots = SlotBundle.model_validate(decision.domain_state.get("slots", {}))
        requested = getattr(slots, criterion.key, [])
        if not requested:
            score = 0.0
        else:
            available = set(candidate.attributes.get(criterion.key, []))
            hits = [value for value in requested if value in available]
            score = len(hits) / len(requested) * 100
        return ScoreContribution(
            criterion_key=criterion.key,
            raw_value=candidate.attributes.get(criterion.key, []),
            normalized_score=round(score, 4),
            weight=criterion.weight,
            weighted_score=round(score * criterion.weight, 4),
            explanation=f"{criterion.label}匹配 {score:.1f}",
            evidence_ids=[
                item.evidence_id for item in candidate.evidence
                if item.evidence_id
                and item.verification_status.value == "verified"
                and (item.criterion_key or item.key) == criterion.key
            ],
        )
