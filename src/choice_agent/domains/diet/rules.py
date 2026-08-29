from __future__ import annotations

import re

from choice_agent.schemas import ClarifyAction, Intent, SlotBundle


RISK_KEYWORDS = (
    "胃疼", "糖尿病", "孕妇", "未成年人", "儿童", "高血压", "治好", "治疗",
    "诊断", "处方", "极端节食", "绝食", "一天不吃", "只喝水",
)
PLAN_KEYWORDS = (
    "三餐", "早中晚", "早午晚", "一周饮食", "饮食规划", "规划一天",
    "规划今日", "一天的饮食", "今日饮食搭配", "规划三餐",
)
ADJUST_KEYWORDS = ("换一个", "换一批", "换点", "不要刚才", "还有别的", "重新推荐")
MEAL_KEYWORDS = ("吃什么", "推荐", "早餐", "午餐", "晚餐", "夜宵", "餐", "菜", "饭", "面")


def extract_slots(message: str, options: dict[str, list[str]]) -> SlotBundle:
    aliases = {
        "mealTime": "meal_time",
        "healthGoal": "health_goal",
        "mood": "mood",
        "scene": "scene",
        "cuisine": "cuisine",
        "taste": "taste",
        "convenience": "convenience",
    }
    values: dict[str, list[str]] = {name: [] for name in aliases.values()}
    for source_name, target_name in aliases.items():
        values[target_name] = [option for option in options.get(source_name, []) if option in message]

    simple_aliases = {
        "早上": ("meal_time", "早餐"),
        "中午": ("meal_time", "午餐"),
        "晚上": ("meal_time", "晚餐"),
        "宵夜": ("meal_time", "夜宵"),
        "减肥": ("health_goal", "减脂"),
        "方便": ("convenience", "快速"),
        "快点": ("convenience", "快速"),
        "不辣": ("taste", "清淡"),
    }
    for keyword, (field, value) in simple_aliases.items():
        if keyword in message and value not in values[field]:
            values[field].append(value)
    return SlotBundle(**values)


def classify_intent(message: str, has_history: bool) -> tuple[Intent, float]:
    text = message.strip()
    if any(keyword in text for keyword in RISK_KEYWORDS):
        return Intent.HEALTH_RISK, 1.0
    if any(keyword in text for keyword in ADJUST_KEYWORDS):
        return (Intent.MEAL_ADJUST if has_history else Intent.MEAL_RECOMMENDATION), 0.95
    if any(keyword in text for keyword in PLAN_KEYWORDS):
        return Intent.MEAL_PLAN, 0.95
    if any(keyword in text for keyword in MEAL_KEYWORDS):
        return Intent.MEAL_RECOMMENDATION, 0.85
    if len(text) <= 12 and has_history:
        return Intent.MEAL_RECOMMENDATION, 0.55
    return Intent.OTHER, 0.8


def missing_slots(slots: SlotBundle) -> list[str]:
    missing: list[str] = []
    if not slots.meal_time:
        missing.append("mealTime")
    strong_preference = slots.cuisine or slots.taste or slots.scene or slots.convenience
    if not slots.health_goal and not strong_preference:
        missing.append("healthGoal")
    return missing


def clarify(slots: SlotBundle) -> tuple[ClarifyAction, str | None, list[str]]:
    missing = missing_slots(slots)
    if not missing:
        return ClarifyAction.READY, None, []
    if "mealTime" in missing:
        question = "这顿主要是早餐、午餐还是晚餐？"
    elif "healthGoal" in missing:
        question = "这顿更想清淡点、顶饱点，还是按口味来？"
    else:
        question = "我再确认一下，你这顿最看重口味、健康目标还是方便快捷？"
    return ClarifyAction.ASK, question, missing


def hard_exclusions(message: str, options: dict[str, list[str]]) -> list[str]:
    exclusions: list[str] = []
    for values in options.values():
        for value in values:
            if re.search(rf"(不要|不能|不吃|忌|避开).{{0,4}}{re.escape(value)}", message):
                exclusions.append(value)
    return list(dict.fromkeys(exclusions))


def risk_reasons(message: str, response: str = "") -> list[str]:
    text = f"{message} {response}"
    rules = [
        (("治好", "治疗", "诊断", "药", "处方"), "涉及医疗诊断或治疗承诺"),
        (("绝食", "一天不吃", "只喝水", "极端节食"), "涉及极端节食建议"),
        (("保证", "一定能瘦", "最健康", "包瘦"), "涉及绝对化健康承诺"),
        (("孕妇", "糖尿病", "高血压", "未成年人", "儿童"), "涉及特殊人群或慢病风险"),
    ]
    return [reason for keywords, reason in rules if any(keyword in text for keyword in keywords)]


def conservative_message() -> str:
    return (
        "这个问题涉及健康或医疗风险，我不能替代医生做诊断或治疗建议。"
        "可以从日常饮食角度选择清淡、均衡、不过量的餐食；"
        "如果症状明显或有慢病、孕期等情况，建议咨询医生或营养师。"
    )
