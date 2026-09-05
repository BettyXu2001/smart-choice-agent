"""Validated, revisioned conversation fields and their scoring dependencies."""
from math import isfinite
from copy import deepcopy
from choice_agent.schemas import Constraint

FIELD_DEFINITIONS = {
    "shopping": {"category": ("商品类别", "text", "", "更换候选类别"), "budget": ("预算上限", "number", "元", "价格硬筛选"), "usage": ("主要用途", "text", "", "搜索参考；模拟数据未验证用途"), "priority": ("更看重", "text", "", "对应指标权重提高至默认的两倍")},
    "travel": {"departure": ("出发地", "text", "", "搜索参考；模拟行程未核验"), "days": ("出行天数", "number", "天", "搜索参考；模拟行程未核验"), "budget": ("总预算上限", "number", "元", "模拟总费用硬筛选，实际费用待核验"), "maxTransitHours": ("交通时间上限", "number", "小时", "模拟交通时长硬筛选，实际路线待核验"), "priority": ("更看重", "text", "", "对应指标权重提高至默认的两倍")},
    "generic": {"background": ("已有基础", "text", "", "路径适配参考"), "weeklyHours": ("每周可用时间", "number", "小时", "时间投入参考；不承诺完成时长"), "target": ("决策目标", "text", "", "比较目标"), "priority": ("更看重", "text", "", "定性比较参考；有评分时调整对应权重"), "maxCommuteMinutes": ("通勤上限", "number", "分钟", "通勤硬筛选；仅使用你提供的通勤时长"), "commuteBasis": ("通勤口径", "text", "", "daily 表示每日往返，one_way 表示单程")},
}
PRIORITIES = {"performance": ["性能", "游戏", "剪辑"], "portability": ["便携", "轻薄"], "battery": ["续航"], "durability": ["耐用"], "support": ["售后"], "price": ["价格", "性价比", "便宜"], "relaxation": ["轻松", "放松"], "crowd_level": ["人少", "安静"], "nature": ["自然", "风景"], "budget": ["省钱", "预算"], "travel_hours": ["交通", "路程"], "fit": ["匹配", "成长"], "cost": ["成本"], "risk": ["风险", "稳定"], "commute_minutes": ["通勤", "距离"]}
CATEGORY_NAMES = {"电脑": "laptop", "笔记本": "laptop", "手机": "phone", "耳机": "headphones", "家电": "appliance"}

def fields(decision):
    current = decision.domain_state.setdefault("conversationFields", {})
    for key, (label, kind, unit, impact) in FIELD_DEFINITIONS.get(decision.domain, {}).items():
        current.setdefault(key, {"key": key, "label": label, "type": kind, "unit": unit, "impact": impact, "editable": True, "value": None, "source": "legacy", "confirmed": False, "cleared": False})
    return current

def patch_fields(decision, patch, source="panel", confirmed=True):
    if not isinstance(patch, dict): raise ValueError("fields 必须为对象")
    current = deepcopy(fields(decision))
    for key, value in patch.items():
        if key not in current: raise ValueError(f"未知条件：{key}")
        item = current[key]
        if source == "model" and (item["confirmed"] or item.get("cleared")): continue
        if value is not None:
            if item["type"] == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0: raise ValueError(f"{item['label']}必须是正数")
                if key == "days" and value != int(value): raise ValueError("出行天数必须是整数")
            else:
                if not isinstance(value, str) or not value.strip() or len(value) > 2000: raise ValueError(f"{item['label']}需要非空文本")
                value = value.strip()
            if key == "category":
                value = CATEGORY_NAMES.get(value, value)
                if value not in set(CATEGORY_NAMES.values()): raise ValueError("当前支持电脑、手机、耳机、家电，可在通用场景比较其他类别")
        item.update(value=value, source=source, confirmed=confirmed, cleared=value is None, updatedRevision=decision.revision + 1)
    decision.domain_state["conversationFields"] = current
    if "category" in patch and decision.domain_state.get("activeCategory") != patch["category"]:
        decision.domain_state["activeCategory"] = patch["category"]
        decision.domain_state["candidatePool"] = []
        decision.domain_state["manualCandidates"] = []
        decision.excluded_candidates = []
    if "target" in patch and patch["target"]: decision.user_goal = patch["target"]
    decision.recommendation = None
    sync_dependencies(decision)

def sync_dependencies(decision, defaults=None):
    current = fields(decision)
    decision.constraints = [c for c in decision.constraints if c.source != "conversation_field"]
    for field, attribute in [("budget", "price" if decision.domain == "shopping" else "budget"), ("maxTransitHours", "travel_hours"), ("maxCommuteMinutes", "commute_minutes")]:
        item = current.get(field, {})
        if item.get("value") is not None and item.get("confirmed") and (field != "maxCommuteMinutes" or decision.domain == "generic"):
            decision.constraints.append(Constraint(key=attribute, constraint_id="field:"+field, kind="hard", operator="lte", value=item["value"], unit=item.get("unit"), source="conversation_field", label=item.get("label")))
    base = decision.domain_state.setdefault("baseCriterionWeights", {})
    if defaults:
        base.update({c.key:c.weight for c in defaults})
    priority = str(current.get("priority", {}).get("value") or "")
    manual = decision.domain_state.get("manualWeights", {})
    for criterion in decision.criteria:
        base.setdefault(criterion.key, criterion.weight)
        criterion.weight = manual.get(criterion.key, base[criterion.key] * (2 if any(w in priority for w in PRIORITIES.get(criterion.key, [])) else 1))

def public_decision(decision):
    result = decision.model_copy(deep=True)
    if result.domain != "diet": fields(result)
    result.domain_state.pop("conversationReceipts", None)
    result.domain_state.pop("dietReceipts", None)
    result.domain_state.pop("pendingReceipt", None)
    return result
