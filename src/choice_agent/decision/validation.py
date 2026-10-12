from __future__ import annotations

from choice_agent.decision.ranking import GenericRankingEngine


class RecommendationInvariantError(RuntimeError):
    pass


def validate_recommendation(decision) -> dict[str, int | bool]:
    recommendation = decision.recommendation
    if recommendation is None:
        return {"valid": True, "candidateReferences": 0, "evidenceReferences": 0}
    active = {item.candidate_id: item for item in decision.candidates}
    excluded = set(decision.excluded_candidates)
    references = [
        recommendation.primary_candidate_id,
        *recommendation.alternative_candidate_ids,
        *[item.candidate_id for item in recommendation.reasons],
        *[item.candidate_id for item in recommendation.tradeoff_details],
    ]
    references = [item for item in references if item]
    unknown = sorted(set(references).difference(active))
    if unknown:
        raise RecommendationInvariantError(f"推荐引用了非活动候选：{', '.join(unknown)}")
    blocked = sorted(set(references).intersection(excluded))
    if blocked:
        raise RecommendationInvariantError(f"推荐引用了已排除候选：{', '.join(blocked)}")
    eliminated = sorted({candidate_id for candidate_id in references if decision.candidate_state.get(candidate_id) and decision.candidate_state[candidate_id].status != "active"})
    if eliminated:
        raise RecommendationInvariantError(f"推荐引用了已淘汰候选：{', '.join(eliminated)}")
    if recommendation.primary_candidate_id:
        failure = GenericRankingEngine().hard_constraint_failure(decision, active[recommendation.primary_candidate_id])
        if failure:
            raise RecommendationInvariantError("主推荐不满足硬约束")
    known_evidence = {item.evidence_id for item in decision.evidence if item.evidence_id}
    known_evidence.update(item.source_id for item in decision.sources if item.source_id)
    evidence_refs = [evidence_id for point in [*recommendation.reasons, *recommendation.tradeoff_details] for evidence_id in point.evidence_ids]
    invalid_evidence = sorted(set(evidence_refs).difference(known_evidence))
    if invalid_evidence:
        raise RecommendationInvariantError(f"推荐引用了未知证据：{', '.join(invalid_evidence)}")
    return {"valid": True, "candidateReferences": len(references), "evidenceReferences": len(evidence_refs)}
