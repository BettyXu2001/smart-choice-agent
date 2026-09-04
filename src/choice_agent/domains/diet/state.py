from __future__ import annotations

import re

from choice_agent.domains.diet.rules import extract_slots, hard_exclusions
from choice_agent.schemas import Constraint, ConstraintKind, DietFieldState, SlotBundle

FIELDS = {field.alias or name: name for name, field in SlotBundle.model_fields.items()}
LABELS = {"mealTime": "餐次", "mood": "心情", "scene": "场景", "healthGoal": "健康目标",
          "cuisine": "菜系", "taste": "口味", "convenience": "便利程度", "exclusions": "排除条件"}


def metadata(decision):
    stored = decision.domain_state.setdefault("dietFieldState", {})
    for key in [*FIELDS, "exclusions"]:
        stored[key] = DietFieldState.model_validate(stored.get(key, {})).model_dump(by_alias=True)
    return stored


def values(decision):
    result = SlotBundle.model_validate(decision.domain_state.get("slots", {})).model_dump(by_alias=True)
    result["exclusions"] = list(dict.fromkeys(
        value for item in decision.constraints if item.key == "diet_exclusion" for value in item.values
    ))
    return result


def apply_fields(decision, patch, options, source="panel", validate=True):
    if not isinstance(patch, dict) or not patch or set(patch) - set(LABELS):
        raise ValueError("请选择有效的饮食条件")
    current = values(decision)
    states = metadata(decision)
    for key, items in patch.items():
        if (not isinstance(items, list) or len(items) > 30
                or any(not isinstance(v, str) or not v.strip() or len(v) > 100 for v in items)):
            raise ValueError("条件必须是非空文本组成的列表；清空请使用空列表")
        allowed = set(v for group in options.values() for v in group) if key == "exclusions" else set(options.get(key, []))
        # Existing legacy/model values remain removable or confirmable without inventing new options.
        if validate and any(v not in allowed and v not in current[key] for v in items):
            raise ValueError(f"{LABELS[key]}包含暂不支持的选项")
        current[key] = list(dict.fromkeys(items))
        states[key] = DietFieldState(source=source, confirmed=source in {"panel", "conversation"},
                                    updated_revision=decision.revision + 1, cleared=not items).model_dump(by_alias=True)
    decision.domain_state["slots"] = {k: v for k, v in current.items() if k in FIELDS}
    decision.constraints = [c for c in decision.constraints
                            if c.key != "diet_exclusion" and (c.key not in FIELDS.values() or c.kind == ConstraintKind.HARD)]
    decision.constraints.extend(Constraint(key=FIELDS[k], kind=ConstraintKind.SOFT, values=v,
                                          source=states[k]["source"])
                                for k, v in current.items() if k in FIELDS and v)
    if current["exclusions"]:
        decision.constraints.append(Constraint(key="diet_exclusion", kind=ConstraintKind.HARD,
                                               values=current["exclusions"], source=states["exclusions"]["source"]))
    return current


def understand_fields(context):
    decision = context.decision
    options = context.data["slot_options"]
    current = values(decision)
    # Compatibility sessions may predate persisted DecisionState.
    if not decision.domain_state.get("slots") and context.data.get("current_slots"):
        decision.domain_state["slots"] = context.data["current_slots"]
        current = values(decision)
    states = metadata(decision)
    message = context.message
    explicit = extract_slots(message, options).model_dump(by_alias=True)
    incoming = context.data["incoming_slots"].model_dump(by_alias=True)
    banned = hard_exclusions(message, options)
    patch = {}
    inferred = {}
    conflicts = []
    for key in FIELDS:
        label = LABELS[key]
        clear = bool(re.search(rf"(?:清空|取消|不限|不限制){label}|{label}(?:不限|随意|无所谓|不限制)", message))
        direct = [v for v in explicit[key] if v not in banned]
        for clause in re.split("[，。！？；,;]", message):
            parts = re.split("改成|改为|换成|换为", clause)
            if len(parts) > 1:
                replacement = extract_slots(parts[-1], options).model_dump(by_alias=True)[key]
                if replacement:
                    direct = [v for v in replacement if v not in banned]
        if clear:
            patch[key] = []
        elif direct:
            replace = key == "mealTime" or bool(re.search("改成|改为|换成|换为|只要|只想|不要.*要", message))
            patch[key] = direct if replace else list(dict.fromkeys([*current[key], *direct]))
        elif incoming[key] and not states[key]["confirmed"] and not states[key]["cleared"]:
            inferred[key] = list(dict.fromkeys([*current[key], *incoming[key]]))
        elif incoming[key] and states[key]["confirmed"] and current[key] and set(incoming[key]) - set(current[key]):
            conflicts.append(f"{label}仍按{'、'.join(current[key])}，还是调整为{'、'.join(incoming[key])}？")
    if banned:
        patch["exclusions"] = list(dict.fromkeys([*current["exclusions"], *banned]))
        for key in FIELDS:
            kept = [v for v in patch.get(key, current[key]) if v not in banned]
            if kept != patch.get(key, current[key]):
                patch[key] = kept
    if re.search("(?:清空|取消)排除条件|忌口不限", message):
        patch["exclusions"] = []
    if inferred:
        apply_fields(decision, inferred, options, source="model", validate=False)
    if patch:
        apply_fields(decision, patch, options, source="conversation", validate=False)
    if not inferred and not patch:
        # Rebuild compatibility constraints without changing any field provenance.
        saved = {k: dict(v) for k, v in states.items()}
        apply_fields(decision, current, options, source="legacy", validate=False)
        decision.domain_state["dietFieldState"] = saved
    unsupported = re.findall(r"(?:不吃|不能吃|过敏)[：:]?([^，。！？；\s]{1,12})", message)
    notes = decision.domain_state.setdefault("unverifiedRestrictions", [])
    for item in unsupported:
        if item not in banned and item not in notes:
            notes.append(item)
    context.data["field_conflicts"] = conflicts
    context.data["slots"] = SlotBundle.model_validate(decision.domain_state["slots"])
    context.data["hard_exclusions"] = values(decision)["exclusions"]
    return patch
