from __future__ import annotations

from choice_agent.decision.ranking import AttributeCriterionEvaluator
from choice_agent.domains.base import DomainMetadata
from choice_agent.domains.comparison import ComparisonProfile
from choice_agent.providers.candidates import FixtureCandidateProvider
from choice_agent.schemas import Constraint, ConstraintKind, Criterion, CriterionDirection


class TravelProfile(ComparisonProfile):
    metadata = DomainMetadata(
        key="travel",
        label="旅行决策",
        description="比较短途目的地；fixture 模式不冒充实时信息。",
        complete=True,
    )
    criteria = [
        Criterion(key="travel_hours", label="交通时间", weight=1.0, direction=CriterionDirection.LOWER_IS_BETTER, unit="小时"),
        Criterion(key="budget", label="预算压力", weight=1.0, direction=CriterionDirection.LOWER_IS_BETTER, unit="元"),
        Criterion(key="relaxation", label="放松程度", weight=1.2),
        Criterion(key="crowd_level", label="人流压力", weight=1.1, direction=CriterionDirection.LOWER_IS_BETTER),
        Criterion(key="nature", label="自然景观", weight=0.9),
    ]
    clarification_question = "你想从哪里出发、计划几天、最在意预算还是轻松程度？"

    def __init__(self, web_provider=None):
        super().__init__(
            FixtureCandidateProvider("travel", TRAVEL_FIXTURES),
            AttributeCriterionEvaluator({
                "travel_hours": (0, 4), "budget": (0, 2000),
                "relaxation": (0, 100), "crowd_level": (0, 100), "nature": (0, 100),
            }),
            web_provider,
        )

    def needs_clarification(self, context) -> bool:
        fields = context.decision.domain_state.get("conversationFields", {})
        return not fields.get("departure", {}).get("value") or not fields.get("days", {}).get("value")

    def matches(self, message: str) -> bool:
        return any(word in message.lower() for word in [
            "旅行", "旅游", "周末", "出发", "目的地", "两天一夜", "travel", "trip"
        ])

    def constraints(self, message: str, current: list[Constraint]) -> list[Constraint]:
        constraints = [item for item in current if item.source != "inferred"]
        if any(word in message for word in ["不想太累", "轻松", "放松"]):
            constraints.append(Constraint(key="relaxation", kind=ConstraintKind.SOFT, values=["轻松"], source="inferred"))
        if any(word in message for word in ["人少", "不要太挤", "避开人流"]):
            constraints.append(Constraint(key="crowd_level", kind=ConstraintKind.SOFT, values=["人少"], source="inferred"))
        if any(word in message for word in ["预算", "便宜", "省钱"]):
            constraints.append(Constraint(key="budget", kind=ConstraintKind.SOFT, values=["预算友好"], source="inferred"))
        return constraints or [Constraint(key="fit", kind=ConstraintKind.SOFT, values=["综合匹配"], source="inferred")]


TRAVEL_FIXTURES = [
    {"id": "moganshan", "name": "莫干山", "summary": "自然景观强，适合慢节奏；周末热门民宿区可能偏贵。", "attributes": {"travel_hours": 2.5, "budget": 1450, "relaxation": 88, "crowd_level": 48, "nature": 92}},
    {"id": "shaoxing", "name": "绍兴", "summary": "交通近、预算稳定，适合轻松城市漫游。", "attributes": {"travel_hours": 1.5, "budget": 950, "relaxation": 78, "crowd_level": 42, "nature": 58}},
    {"id": "ningbo-dongqian", "name": "宁波东钱湖", "summary": "湖景开阔，适合轻度骑行和散步。", "attributes": {"travel_hours": 2.8, "budget": 1280, "relaxation": 84, "crowd_level": 30, "nature": 84}},
    {"id": "suzhou", "name": "苏州", "summary": "距离最近，但核心区域周末人流较高。", "attributes": {"travel_hours": 0.6, "budget": 900, "relaxation": 68, "crowd_level": 72, "nature": 64}},
]


TravelDomain = TravelProfile