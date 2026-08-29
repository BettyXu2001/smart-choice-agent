from choice_agent.db_models import MealRecord
from choice_agent.decision.engine import DecisionEngine
from choice_agent.schemas import SlotBundle


def meal(meal_id, name, **slots):
    defaults = {
        "meal_time": [], "mood": [], "scene": [], "health_goal": [],
        "cuisine": [], "taste": [], "convenience": [],
    }
    defaults.update(slots)
    return MealRecord(id=meal_id, name=name, source_type="PUBLIC", **defaults)


def test_rank_is_stable_and_compatible_with_seven_dimension_score():
    engine = DecisionEngine()
    meals = [
        meal(2, "B", meal_time=["晚餐"], taste=["清淡"]),
        meal(1, "A", meal_time=["晚餐"], taste=["清淡"]),
    ]
    ranked = engine.rank(meals, SlotBundle(meal_time=["晚餐"], taste=["清淡"]))
    assert [item.meal.id for item in ranked] == [1, 2]
    assert ranked[0].score == 2 / 7


def test_rank_applies_history_and_hard_exclusions():
    engine = DecisionEngine()
    meals = [
        meal(1, "麻辣", meal_time=["晚餐"], taste=["麻辣"]),
        meal(2, "清淡", meal_time=["晚餐"], taste=["清淡"]),
    ]
    ranked = engine.rank(
        meals,
        SlotBundle(meal_time=["晚餐"]),
        excluded_ids=[2],
        hard_exclusions=["麻辣"],
    )
    assert ranked == []
