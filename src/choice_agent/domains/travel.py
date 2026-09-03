from __future__ import annotations

from datetime import datetime
from typing import Any

from choice_agent.decision.state_machine import transition_decision
from choice_agent.domains.base import DomainMetadata, DomainPlugin
from choice_agent.schemas import (
    Assumption,
    Candidate,
    CandidateState,
    Constraint,
    ConstraintKind,
    Criterion,
    DecisionNextAction,
    DecisionState,
    DecisionStatus,
    Evidence,
    Recommendation,
    UnansweredQuestion,
)


class TravelDomain(DomainPlugin):
    metadata = DomainMetadata(
        key="travel",
        label="旅行决策",
        description="使用本地 fixture 比较短途目的地，验证通用决策链路。",
        complete=False,
    )

    criteria = [
        Criterion(key="travel_hours", label="交通时间", weight=1.0),
        Criterion(key="budget", label="预算压力", weight=1.0),
        Criterion(key="relaxation", label="放松程度", weight=1.2),
        Criterion(key="crowd_level", label="人流压力", weight=1.1),
        Criterion(key="nature", label="自然景观", weight=0.9),
    ]

    def matches(self, message: str) -> bool:
        return any(word in message.lower() for word in [
            "旅行", "旅游", "周末", "出发", "目的地", "两天一夜", "travel", "trip"
        ])

    def understand(self, decision: DecisionState, message: str) -> None:
        decision.domain = self.key
        decision.user_goal = message
        decision.criteria = list(self.criteria)
        decision.constraints = self._constraints(message)
        decision.assumptions = [
            Assumption(
                key="provider",
                value="travel_fixture",
                confidence=1.0,
                source="system",
            )
        ]
        decision.domain_state["source"] = {
            "mode": "fixture",
            "label": "本地演示数据",
            "realTime": False,
        }
        decision.domain_state["intent"] = "compare_travel_options"

    def clarify(self, decision: DecisionState, message: str) -> bool:
        if len(message.strip()) < 6:
            question = "你想从哪里出发、计划几天、最在意预算还是轻松程度？"
            decision.clarifying_questions = [question]
            decision.unanswered_questions = [
                UnansweredQuestion(key="travel_context", question=question, asked_by="TravelDomain")
            ]
            transition_decision(
                decision, DecisionStatus.CLARIFYING, DecisionNextAction.ASK_CLARIFY
            )
            return True
        decision.clarifying_questions = []
        decision.unanswered_questions = []
        transition_decision(
            decision, DecisionStatus.SEARCHING, DecisionNextAction.SEARCH_CANDIDATES
        )
        return False

    def candidates(self, decision: DecisionState, message: str) -> list[Candidate]:
        return [self._candidate(item) for item in _TRAVEL_FIXTURES]

    def rank(self, decision: DecisionState, candidates: list[Candidate]) -> list[Candidate]:
        ranked = []
        for candidate in candidates:
            score = self._score(decision, candidate)
            ranked.append(candidate.model_copy(update={"score": score}))
        ranked.sort(key=lambda item: (-item.score, item.name))
        return ranked

    def explain(self, decision: DecisionState, ranked: list[Candidate]) -> Recommendation:
        if not ranked:
            return Recommendation(summary="暂时没有可比较的旅行候选。")
        primary = ranked[0]
        alternatives = ranked[1:3]
        tradeoffs = [
            f"{primary.name}综合匹配最高，但仍需要你自行核实实时价格、天气和营业状态。"
        ]
        for item in alternatives:
            tradeoffs.append(f"{item.name}可以作为备选，当前综合分 {item.score:.2f}。")
        return Recommendation(
            primary_candidate_id=primary.candidate_id,
            alternative_candidate_ids=[item.candidate_id for item in alternatives],
            summary=f"优先考虑 {primary.name}。它在你当前目标下的综合匹配度最高。",
            tradeoffs=tradeoffs,
        )

    def display_blocks(self, decision: DecisionState) -> list[dict[str, Any]]:
        return [
            {
                "id": candidate.candidate_id,
                "name": candidate.name,
                "score": candidate.score,
                "summary": candidate.attributes.get("summary", ""),
                "attributes": candidate.attributes,
                "evidence": [item.model_dump(mode="json", by_alias=True) for item in candidate.evidence],
            }
            for candidate in decision.candidates
        ]

    def _constraints(self, message: str) -> list[Constraint]:
        constraints: list[Constraint] = []
        if any(word in message for word in ["不想太累", "轻松", "放松"]):
            constraints.append(Constraint(key="relaxation", kind=ConstraintKind.SOFT, values=["轻松"]))
        if any(word in message for word in ["人少", "不要太挤", "避开人流"]):
            constraints.append(Constraint(key="crowd_level", kind=ConstraintKind.SOFT, values=["人少"]))
        if any(word in message for word in ["预算", "便宜", "省钱"]):
            constraints.append(Constraint(key="budget", kind=ConstraintKind.SOFT, values=["预算友好"]))
        if not constraints:
            constraints.append(Constraint(key="fit", kind=ConstraintKind.SOFT, values=["综合匹配"]))
        return constraints

    def _candidate(self, item: dict[str, Any]) -> Candidate:
        evidence = [
            Evidence(
                key=key,
                value=value,
                source_title="Choice Agent travel fixture",
                source_url="https://example.com/choice-agent-demo",
                retrieved_at=datetime.utcnow(),
                confidence=0.72,
            )
            for key, value in item["attributes"].items()
        ]
        return Candidate(
            candidate_id=item["id"],
            name=item["name"],
            attributes={**item["attributes"], "summary": item["summary"]},
            evidence=evidence,
        )

    def _score(self, decision: DecisionState, candidate: Candidate) -> float:
        attrs = candidate.attributes
        score = 0.0
        weight_total = 0.0
        for criterion in decision.criteria:
            weight = max(0.0, criterion.weight)
            if weight == 0:
                continue
            value = attrs.get(criterion.key)
            if isinstance(value, (int, float)):
                normalized = float(value) / 100 if value > 5 else float(value)
                if criterion.key in {"travel_hours", "budget", "crowd_level"}:
                    normalized = 1 - min(1.0, normalized / (3 if criterion.key == "travel_hours" else 100)) if criterion.key == "travel_hours" else 1 - min(1.0, normalized)
                score += max(0.0, min(1.0, normalized)) * weight
                weight_total += weight
        return round(score / weight_total, 4) if weight_total else 0.0


_TRAVEL_FIXTURES = [
    {
        "id": "moganshan",
        "name": "莫干山",
        "summary": "自然景观强，适合放空和慢节奏，但周末热门民宿区可能偏贵。",
        "attributes": {"travel_hours": 2.5, "budget": 1450, "relaxation": 88, "crowd_level": 48, "nature": 92},
    },
    {
        "id": "shaoxing",
        "name": "绍兴",
        "summary": "交通近、预算稳定，城市漫游轻松，缺点是自然景观不如山野目的地。",
        "attributes": {"travel_hours": 1.5, "budget": 950, "relaxation": 78, "crowd_level": 42, "nature": 58},
    },
    {
        "id": "ningbo-dongqian",
        "name": "宁波东钱湖",
        "summary": "湖景开阔，适合轻度骑行和散步；交通略远，但比热门古镇更舒展。",
        "attributes": {"travel_hours": 2.8, "budget": 1280, "relaxation": 84, "crowd_level": 30, "nature": 84},
    },
    {
        "id": "suzhou",
        "name": "苏州",
        "summary": "距离最近、安排最稳，但核心园林和商业区周末人流压力较高。",
        "attributes": {"travel_hours": 0.6, "budget": 900, "relaxation": 68, "crowd_level": 72, "nature": 64},
    },
]