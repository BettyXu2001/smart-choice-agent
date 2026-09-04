from __future__ import annotations

from choice_agent.decision.ranking import AttributeCriterionEvaluator
from choice_agent.domains.base import DomainMetadata
from choice_agent.domains.comparison import ComparisonProfile
from choice_agent.providers.candidates import FixtureCandidateProvider
from choice_agent.schemas import Constraint, ConstraintKind, Criterion, CriterionDirection


class ShoppingProfile(ComparisonProfile):
    metadata = DomainMetadata(
        key="shopping",
        label="购物决策",
        description="比较商品能力、价格和使用成本；fixture 不代表实时价格或库存。",
        complete=True,
    )
    criteria = [
        Criterion(key="price", label="价格", weight=1.2, direction=CriterionDirection.LOWER_IS_BETTER, unit="元"),
        Criterion(key="performance", label="性能", weight=1.1),
        Criterion(key="portability", label="便携性", weight=0.9),
        Criterion(key="battery", label="续航", weight=1.0),
        Criterion(key="durability", label="耐用性", weight=1.0),
        Criterion(key="support", label="售后", weight=0.8),
    ]
    clarification_question = "你要购买哪类商品？预算范围和最看重的用途是什么？"

    def __init__(self, web_provider=None):
        super().__init__(
            ShoppingFixtureProvider("shopping", SHOPPING_FIXTURES),
            AttributeCriterionEvaluator({
                "price": (0, 15000), "performance": (0, 100), "portability": (0, 100),
                "battery": (0, 100), "durability": (0, 100), "support": (0, 100),
            }),
            web_provider,
        )

    def needs_clarification(self, context) -> bool:
        return context.decision.domain_state.get("conversationFields", {}).get("category", {}).get("value") is None

    def matches(self, message: str) -> bool:
        return any(word in message.lower() for word in [
            "买", "购买", "选电脑", "手机", "耳机", "家电", "笔记本", "shopping", "laptop", "phone"
        ])

    def constraints(self, message: str, current: list[Constraint]) -> list[Constraint]:
        constraints = [item for item in current if item.source != "inferred"]
        if any(word in message for word in ["便宜", "预算", "性价比"]):
            constraints.append(Constraint(key="price", kind=ConstraintKind.SOFT, values=["预算友好"], source="inferred"))
        if any(word in message for word in ["轻", "便携", "出差"]):
            constraints.append(Constraint(key="portability", kind=ConstraintKind.SOFT, values=["便携"], source="inferred"))
        if any(word in message for word in ["性能", "游戏", "剪辑"]):
            constraints.append(Constraint(key="performance", kind=ConstraintKind.SOFT, values=["高性能"], source="inferred"))
        return constraints or [Constraint(key="fit", kind=ConstraintKind.SOFT, values=["综合匹配"], source="inferred")]


SHOPPING_FIXTURES = [
    {"id": "portable-13", "name": "轻薄本 13", "summary": "便携和续航突出，适合移动办公。", "attributes": {"price": 6999, "performance": 72, "portability": 94, "battery": 90, "durability": 76, "support": 82}},
    {"id": "balanced-14", "name": "均衡本 14", "summary": "性能、价格和便携性较均衡。", "attributes": {"price": 7599, "performance": 84, "portability": 80, "battery": 78, "durability": 84, "support": 80}},
    {"id": "creator-16", "name": "创作本 16", "summary": "性能强，重量和续航存在取舍。", "attributes": {"price": 10999, "performance": 96, "portability": 52, "battery": 62, "durability": 88, "support": 78}},
]

def shopping_category(message: str) -> str | None:
    text = message.lower()
    categories = {
        "headphones": ["耳机", "headphone"],
        "phone": ["手机", "phone"],
        "appliance": ["家电", "冰箱", "洗衣机", "空调"],
        "laptop": ["电脑", "笔记本", "laptop", "computer"],
    }
    return next((key for key, words in categories.items() if any(word in text for word in words)), None)


class ShoppingFixtureProvider(FixtureCandidateProvider):
    def search(self, context):
        category = context.decision.domain_state.get("conversationFields", {}).get("category", {}).get("value")
        if category is None:
            raise ValueError("请先指定商品类别")
        if category == "laptop":
            return super().search(context)
        labels = {"phone": "手机", "headphones": "耳机", "appliance": "家电"}
        prices = {"phone": [1999, 3499, 5999], "headphones": [199, 699, 1499], "appliance": [1999, 3999, 6999]}
        fixtures = [
            {
                "id": f"{category}-{index}",
                "name": f"{labels[category]}方案 {index + 1}",
                "summary": "离线模拟方案，不代表具体在售商品。",
                "attributes": {
                    "price": price, "performance": 60 + index * 15,
                    "durability": 65 + index * 10, "support": 70 + index * 8,
                },
            }
            for index, price in enumerate(prices[category])
        ]
        return FixtureCandidateProvider(f"shopping:{category}", fixtures).search(context)
