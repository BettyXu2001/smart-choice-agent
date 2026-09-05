"""Turn interpretation: deterministic explicit edits, optional model suggestions."""
import re
from choice_agent.decision.conversation import fields, patch_fields, PRIORITIES

_NUMBERS = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _number(value):
    return float(value) if re.fullmatch(r"\d+(?:\.\d+)?", value) else float(_NUMBERS[value])


def _duration_minutes(match):
    amount = _number(match.group("value"))
    unit = match.group("unit") or "分钟"
    return int(amount * 60) if unit == "小时" else int(amount)


def _commute_limit(text):
    if "通勤" not in text:
        return None
    match = re.search(r"(?P<basis>每天|每日|单程|来回|往返)?[^，。；]{0,8}(?:最多|不超过|不超|上限|只能接受|接受)[^，。；]{0,8}(?P<value>\d+(?:\.\d+)?|一|两|二|三|四|五|六|七|八|九|十)\s*(?P<unit>小时|分钟)", text)
    if not match:
        return None
    basis_text = match.group("basis") or "每天"
    basis = "one_way" if basis_text == "单程" else "daily"
    return {"minutes": _duration_minutes(match), "basis": basis}


def interpret(context, provider=None, model=None):
    d, text = context.decision, context.message.strip()
    from choice_agent.decision.assistance import prepare_turn, model_understand, state
    prepare_turn(context)
    if context.data.get("is_hypothetical"):
        return {"intent":"what_if","confidence":1.0}
    current = fields(d)
    patch = {}
    question = d.domain_state.get("sceneResolution", {}).get("question") if len(d.messages) == 1 else None
    if d.domain == "generic" and not current["target"].get("value") and not current["target"].get("cleared"):
        patch["target"] = d.user_goal.split("\n")[0]
    if "category" in current:
        from choice_agent.domains.shopping import shopping_category
        category = shopping_category(text)
        if category: patch["category"] = category
    commute_limit = _commute_limit(text)
    if commute_limit and "maxCommuteMinutes" in current:
        patch["maxCommuteMinutes"] = commute_limit["minutes"]
        if "commuteBasis" in current:
            patch["commuteBasis"] = commute_limit["basis"]
    budget = re.search(r"(?:总预算|预算|不超过|不超|最多|上限)[是为改到成不超过：:\s]*(\d+(?:\.\d+)?)\s*(万|千|k)?", text, re.I)
    if not budget and "budget" in current and current["budget"].get("value") is not None:
        budget = re.search(r"^(?:改到|改成|调整到)\s*(\d+(?:\.\d+)?)\s*(万|千|k)?(?:元)?[。！!\s]*$", text, re.I)
    if budget and "budget" in current and not ("小时" in text and "预算" not in text and "元" not in text):
        if d.domain == "travel" and ("人均" in text or "每人" in text):
            question = "这里按整次行程的总预算比较。请告诉我总预算是多少元？"
        else: patch["budget"] = float(budget[1]) * {None:1,"万":10000,"千":1000,"k":1000}.get((budget[2] or '').lower() or None,1)
    for key, words in [("budget", "预算"), ("priority", "偏好|优先|更看重"), ("departure", "出发地"), ("days", "天数"), ("maxTransitHours", "交通时间"), ("maxCommuteMinutes", "通勤")]:
        if key in current and re.search(r"(?:清空|取消|不限|不限制)(?:.{0,3})(?:"+words+r")|(?:"+words+r")(?:不限|不限制|清空)", text): patch[key] = None
    if d.domain == "travel":
        departure = re.search(r"从([\u4e00-\u9fffA-Za-z]{2,12}?)(?:出发|去)", text)
        if departure: patch["departure"] = departure[1]
        days = re.search(r"(\d+|一|两|二|三|四|五|六|七)天", text)
        if days: patch["days"] = int(days[1]) if days[1].isdigit() else {"一":1,"两":2,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7}[days[1]]
        transit = re.search(r"(?:交通|路程|车程)[^，。；]{0,8}?(\d+(?:\.\d+)?)\s*小时", text)
        if transit: patch["maxTransitHours"] = float(transit[1])
    usage = re.search(r"(?:用于|用来|用途是|主要用来)([^，。；]+)", text)
    if usage and "usage" in current: patch["usage"] = usage[1]
    priority = re.search(r"(?:更看重|最看重|最在意|优先考虑|优先|更在意|更想)([^，。；]+)",text)
    if priority: patch["priority"] = priority[1]
    elif d.domain != "generic" and not current.get("priority", {}).get("cleared"):
        words = [w for values in PRIORITIES.values() for w in values if w in text and not any(n+w in text for n in ["不", "不要", "不看重"])]
        if words and "priority" not in patch: patch["priority"] = "、".join(dict.fromkeys(words))
    if patch:
        patch_fields(d, patch, source="conversation")
        state(d)["changes"].extend(f"{current[k]['label']}：{v if v is not None else '已清空'}" for k,v in patch.items())
    operation = "update_fields" if patch else "compare"
    # Only the current turn supplies operations; the original goal is never re-parsed.
    from choice_agent.decision.commands import apply_command
    from choice_agent.schemas import DecisionCommandRequest
    candidates = d.domain_state.get("candidatePool", [])
    for verb, kind in [("排除", "exclude_candidate"), ("恢复", "restore_candidate")]:
        if verb in text:
            matches = [c for c in candidates if c["name"] in text or c["candidateId"] in text]
            if len(matches) == 1:
                apply_command(d, DecisionCommandRequest(command_id="turn",type=kind,expected_revision=d.revision,payload={"candidateId": matches[0]["candidateId"]}))
                operation = kind
            else: question = "请告诉我你要" + verb + "的候选名称。"
    if d.domain == "generic":
        # Named choices with descriptions, e.g. 候选：A：离家近；B：成长快.
        raw = re.sub(r"^(?:添加)?候选[：:]", "", text)
        spaced = re.findall(r"(?:^|[，,；;])\s*([A-Za-z][A-Za-z0-9_-]*)\s+([^，,；;]+)", text)
        if len(spaced) >= 2:
            raw = "；".join(name+"："+description for name,description in spaced)
        if len(spaced) >= 2 or "候选" in text or re.search(r"[^：:；;]+[：:][^；;]+[；;]", text):
            for piece in re.split(r"[；;\n]",raw):
                match = re.fullmatch(r"\s*([^：:]{1,60})[：:]\s*(.+)", piece)
                if match:
                    name, summary = match.groups()
                    existing = next((c for c in d.domain_state.get("manualCandidates",[]) if c["name"] == name),None)
                    payload = {"candidate": {"name":name,"summary":summary,"attributes":{}}}
                    if existing: payload["candidate"]["candidateId"] = existing["candidateId"]
                    apply_command(d, DecisionCommandRequest(command_id="turn",type="add_candidate",expected_revision=d.revision,payload=payload))
                    operation = "add_candidate"
    if "换一批" in text or "刷新" in text: operation = "refresh"
    if not context.data.get("simulation"):
        model_understand(context)
    understood = bool(patch or state(d).get("changes") or operation != "compare" or context.data.get("turn_intent") == "explain")
    context.data["unhandled_turn"] = not understood and not any(w in text for w in ["比较", "帮我选", "选哪个", "推荐", "继续", "谢谢"])
    context.data["conversation_question"] = question or context.data.get("fact_question")
    return {"intent":operation,"confidence":1.0 if patch else 0.7}