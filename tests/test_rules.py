from choice_agent.domains.diet.rules import (
    clarify,
    classify_intent,
    hard_exclusions,
    risk_reasons,
)
from choice_agent.schemas import ClarifyAction, Intent, SlotBundle


def test_intent_rules_cover_adjust_plan_and_risk():
    assert classify_intent("换一个", True)[0] == Intent.MEAL_ADJUST
    assert classify_intent("帮我规划三餐", False)[0] == Intent.MEAL_PLAN
    assert classify_intent("糖尿病怎么吃能治好", False)[0] == Intent.HEALTH_RISK


def test_adjust_without_history_falls_back_to_recommendation():
    assert classify_intent("换一个", False)[0] == Intent.MEAL_RECOMMENDATION


def test_clarification_matches_legacy_required_slots():
    action, _, missing = clarify(SlotBundle())
    assert action == ClarifyAction.ASK
    assert missing == ["mealTime", "healthGoal"]
    action, _, missing = clarify(SlotBundle(meal_time=["晚餐"], taste=["清淡"]))
    assert action == ClarifyAction.READY
    assert missing == []


def test_hard_exclusions_and_risk_rules():
    options = {"taste": ["麻辣", "清淡"]}
    assert hard_exclusions("我不能吃麻辣", options) == ["麻辣"]
    assert risk_reasons("我想绝食减肥")

