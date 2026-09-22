"""Grounded turn updates and bounded decision assistance, with optional model reasoning."""
import json
import re
from hashlib import sha256
from uuid import uuid4

from choice_agent.decision.conversation import fields, patch_fields
from choice_agent.decision.evidence import sync_decision_evidence, source_kind_for_origin
from choice_agent.schemas import (
    AssistanceInterpretation, AssistanceExplanation, Evidence, Recommendation, RecommendationPoint,
    DecisionStatus, DecisionNextAction,
)
from choice_agent.decision.state_machine import transition_decision


def state(decision):
    return decision.domain_state.setdefault("assistance", {"facts": [], "changes": []})


def hypothetical(text):
    return bool(re.search(r"如果|假如|假设|要是", text))


_NUMBERS = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _number(value):
    return float(value) if re.fullmatch(r"\d+(?:\.\d+)?", value) else float(_NUMBERS[value])


def commute_measure(text):
    if "通勤" not in text:
        return None
    match = re.search(r"(?P<basis>每天|每日|单程|来回|往返)?[^，。；]{0,10}(?P<value>\d+(?:\.\d+)?|一|两|二|三|四|五|六|七|八|九|十)\s*(?P<unit>小时|分钟)", text)
    if not match:
        return None
    minutes = int(_number(match.group("value")) * (60 if match.group("unit") == "小时" else 1))
    basis_text = match.group("basis") or "每天"
    return {"minutes": minutes, "basis": "one_way" if basis_text == "单程" else "daily"}


def _apply_fact_attributes(decision, candidate_id, kind, measure):
    if kind != "commute" or not measure:
        return
    for collection in [decision.domain_state.get("manualCandidates", []), decision.domain_state.get("candidatePool", [])]:
        for item in collection:
            if item.get("candidateId") == candidate_id:
                item.setdefault("attributes", {})["commute_minutes"] = measure["minutes"]
                item.setdefault("attributes", {})["commute_basis"] = measure["basis"]
    for candidate in decision.candidates:
        if candidate.candidate_id == candidate_id:
            candidate.attributes["commute_minutes"] = measure["minutes"]
            candidate.attributes["commute_basis"] = measure["basis"]


def matched_candidates(decision, text):
    compact = text.replace(" ", "")
    pool = decision.domain_state.get("manualCandidates") or decision.domain_state.get("candidatePool", [])
    matches = []
    for candidate in pool:
        name = candidate["name"].replace(" ", "")
        alias = re.match(r"[A-Za-z]+", name)
        if name in compact or (alias and re.search(r"(?<![A-Za-z0-9])"+re.escape(alias[0])+r"(?![A-Za-z0-9])", text)):
            matches.append(candidate)
    return matches


def add_fact(decision, candidate_id, text, concern=False, source="conversation"):
    info = state(decision)
    kind = "commute" if "通勤" in text else "salary" if any(w in text for w in ["薪资", "薪酬", "工资"]) else "description"
    existing = info.setdefault("facts", [])
    existing[:] = [f for f in existing if not (f["candidateId"] == candidate_id and (f["kind"] == kind if kind != "description" else f["text"] == text))]
    measure = commute_measure(text) if kind == "commute" else None
    fact = {"id":"fact:"+uuid4().hex,"candidateId":candidate_id,"text":text,"quote":text,"kind":kind,"concern":concern,"source":source,"confirmed":True,"revision":decision.revision+1}
    if measure:
        fact["value"] = measure["minutes"]
        fact["unit"] = "分钟"
        fact["basis"] = measure["basis"]
    existing.append(fact)
    _apply_fact_attributes(decision, candidate_id, kind, measure)
    info["changes"].append("补充候选信息："+text)


_TRAVEL_PRIORITY_WORDS = [
    "轻松", "放松", "不累", "不想太累", "人少", "安静", "自然", "风景", "省钱", "预算", "便宜", "交通近", "路程短",
]


def _travel_days(text):
    match = re.search(r"(\d+(?:\.\d+)?|一|两|二|三|四|五|六|七|八|九|十)\s*(?:天|日)", text)
    if not match:
        return None
    value = _number(match.group(1))
    return int(value) if value == int(value) else None


def _travel_priority(text):
    found = [word for word in _TRAVEL_PRIORITY_WORDS if word in text]
    if not found:
        return None
    if any(word in found for word in ["轻松", "放松", "不累", "不想太累"]):
        return "轻松"
    return "、".join(dict.fromkeys(found))


def _travel_departure(text, previous_question, current):
    explicit_patterns = [
        r"从(?P<place>[\u4e00-\u9fa5A-Za-z]{2,12})出发",
        r"出发地(?:是|在)?(?P<place>[\u4e00-\u9fa5A-Za-z]{2,12})",
        r"(?P<place>[\u4e00-\u9fa5A-Za-z]{2,12})出发",
    ]
    for pattern in explicit_patterns:
        explicit = re.search(pattern, text)
        if explicit:
            place = explicit.group("place").strip("，,。；;、 ")
            if place:
                return place
    if current.get("departure", {}).get("value"):
        return None
    if not previous_question or not any(word in previous_question for word in ["出发", "哪里", "哪儿", "几天", "计划玩"]):
        return None
    for part in re.split(r"[\s,，、；;。]+", text):
        part = part.strip()
        if not re.fullmatch(r"[\u4e00-\u9fa5A-Za-z]{2,12}", part):
            continue
        if any(word in part for word in [*_TRAVEL_PRIORITY_WORDS, "天", "小时", "预算", "人均"]):
            continue
        return part
    return None


def _travel_patch(text, previous_question, current):
    patch = {}
    days = _travel_days(text)
    if days is not None:
        patch["days"] = days
    priority = _travel_priority(text)
    if priority:
        patch["priority"] = priority
    departure = _travel_departure(text, previous_question, current)
    if departure:
        patch["departure"] = departure
    return patch

def prepare_turn(context):
    d, text = context.decision, context.message.strip()
    info = state(d)
    info["changes"] = []
    info.pop("unhandled", None)
    info.pop("warning", None)
    context.data["is_hypothetical"] = hypothetical(text)
    context.data["turn_intent"] = "what_if" if hypothetical(text) else "explain" if any(w in text for w in ["为什么", "为何", "理由"]) else "compare"
    if hypothetical(text): return
    patch = {}
    previous_question=info.get("currentAnalysis",{}).get("question") or info.get("analysis",{}).get("question") or info.get("lastQuestion","")
    if previous_question and "这项顾虑" in previous_question:
        pending=[f for f in info.get("facts",[]) if f.get("concern")]
        if len(pending)==1 and re.search(r"不能妥协|不能交换|硬条件|必须排除",text):
            fact=pending[0]
            d.excluded_candidates=sorted(set([*d.excluded_candidates,fact["candidateId"]]))
            fact.update(concern=False,resolution="excluded",resolvedRevision=d.revision+1)
            info["changes"].append("按你的确认排除了有顾虑的候选")
        elif len(pending)==1 and re.search(r"可以交换|可以接受|可以妥协",text):
            pending[0].update(concern=False,resolution="accepted",resolvedRevision=d.revision+1)
            info["changes"].append("你确认这项顾虑可以接受，已恢复比较")
    if d.domain == "generic":
        if previous_question and "编程基础" in previous_question:
            if text.strip("。！ ") in {"有","有的","会","是的"}: patch["background"]="已有编程基础"
            elif text.strip("。！ ") in {"没有","不会","没有的"}: patch["background"]="零编程基础"
        short_priority=re.fullmatch(r"(稳定|成长|成长方向|成本|日常成本|系统框架|动手实践|实践)(?:更重要|优先|最重要)?[。！]*",text)
        if short_priority: patch["priority"]=short_priority[1]
        if re.search(r"零(?:编程)?基础|没有(?:编程)?基础|不会编程", text): patch["background"] = "零编程基础"
        elif re.search(r"(?:有|已有|会|掌握|学过).{0,8}(?:Python|python|编程).{0,4}(?:基础)?", text): patch["background"] = "已有 Python / 编程基础"
        hours = re.search(r"每周(?:只有|最多|能用|可用|有|投入|学习|大约|时间|是|为|\s)*(\d+(?:\.\d+)?|一|两|二|三|四|五|六|七|八|九|十)\s*(?:个)?小时", text)
        if hours:
            value=hours[1]
            patch["weeklyHours"] = float(value) if re.fullmatch(r"\d+(?:\.\d+)?",value) else {"一":1,"两":2,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}[value]
    if d.domain == "travel":
        patch.update(_travel_patch(text, previous_question, fields(d)))
    if patch:
        patch_fields(d,patch,source="conversation")
        info["changes"].extend(f"{fields(d)[k]['label']}：{v}" for k,v in patch.items())
    matches = matched_candidates(d,text)
    question = context.data["turn_intent"] == "explain" or bool(re.search(r"？|吗$|多少|是否|怎么样|能不能|是不是", text))
    fact_cue = any(w in text for w in ["通勤", "薪资", "薪酬", "工资", "加班", "远程", "补充", "改成", "纠正", "担心", "不能接受", "不太能接受"])
    if len(matches) == 1:
        info["focusCandidateId"] = matches[0]["candidateId"]
    elif not matches and any(w in text for w in ["它", "那家", "这个选项"]):
        focus=info.get("focusCandidateId")
        pool=d.domain_state.get("candidatePool",[])
        matches=[c for c in pool if c["candidateId"]==focus]
        if not matches and fact_cue:
            context.data["fact_question"]="你说的是哪个候选？告诉我名称后，我再更新它的信息。"
            context.data["blocking_question"]=context.data["fact_question"]
    if fact_cue and not question:
        if len(matches)==1:
            concern = any(w in text for w in ["不能接受", "无法接受", "不太能接受", "不接受", "担心", "顾虑"])
            add_fact(d,matches[0]["candidateId"],text,concern)
        elif len(matches)>1:
            context.data["fact_question"]="请分别说明每个候选要补充的信息，以免我把条件记错。"
            context.data["blocking_question"]=context.data["fact_question"]


def model_context(context):
    d=context.decision
    return {"message":context.message,"domain":d.domain,"fields":fields(d),
            "recent_messages":[{"role":m.role,"content":m.content[:2000]} for m in d.messages[-8:]],
            "previous_question":state(d).get("currentAnalysis",{}).get("question") or state(d).get("analysis",{}).get("question") or state(d).get("lastQuestion") or (d.clarifying_questions[0] if d.clarifying_questions else None),
            "candidates":[{"candidateId":c["candidateId"],"name":c["name"],"summary":c.get("summary","")[:1000],"origin":c.get("origin")} for c in (d.domain_state.get("manualCandidates") or d.domain_state.get("candidatePool",[]))[:12]],
            "facts":state(d).get("facts",[])[-24:],"rule_intent":context.data.get("turn_intent")}


def explicit_patch(context, updates):
    """Accept quoted corrections only when their field and value are locally checkable."""
    current=fields(context.decision)
    aliases={"budget":["预算"],"days":["天"],"maxTransitHours":["交通","车程","路程"],"weeklyHours":["每周"],"priority":["看重","在意","优先"],"category":["买","商品","换成","改成"],"departure":["出发","从"],"background":["基础","编程"],"usage":["用途","用来","用于"],"target":["目标"]}
    patch={}
    for update in updates:
        if update.key not in current or update.quote not in context.message: raise ValueError("纠正缺少本轮字段原文")
        if not any(word in update.quote for word in aliases.get(update.key,[])): raise ValueError("纠正字段含义不明确")
        if update.value is None:
            if not any(w in update.quote for w in ["清空","取消","不限","不限制"]): raise ValueError("没有明确清空意图")
        elif current[update.key]["type"]=="number":
            amounts=[float(n)*{"":1,"千":1000,"万":10000,"k":1000}[unit.lower()] for n,unit in re.findall(r"(\d+(?:\.\d+)?)\s*([千万kK]?)",update.quote)]
            if isinstance(update.value,bool) or update.value not in amounts: raise ValueError("纠正数值缺少依据")
        else:
            value=str(update.value)
            categories={"laptop":["电脑","笔记本"],"phone":["手机"],"headphones":["耳机"],"appliance":["家电"]}
            if update.key=="category":
                if not any(w in update.quote for w in categories.get(value,[value])): raise ValueError("商品类别缺少依据")
            elif value not in update.quote: raise ValueError("纠正文本缺少依据")
        patch[update.key]=update.value
    return patch


def model_understand(context):
    d=context.decision
    provider=context.data.get("model_provider")
    if not provider or not provider.enabled or context.data.get("is_hypothetical"): return
    from choice_agent.prompts.conversation import SYSTEM_PROMPT
    try:
        user_prompt=json.dumps(model_context(context),ensure_ascii=False)
        raw=(
            context.trace.model_call(
                "Intent Understanding",
                context.data.get("model_name"),
                SYSTEM_PROMPT,
                user_prompt,
                lambda: provider.complete_json(system_prompt=SYSTEM_PROMPT,user_prompt=user_prompt,model=context.data.get("model_name")),
                provider=provider,
            )
            if context.trace
            else provider.complete_json(system_prompt=SYSTEM_PROMPT,user_prompt=user_prompt,model=context.data.get("model_name"))
        )
        parsed=AssistanceInterpretation.model_validate(raw)
        if parsed.intent=="what_if":
            # A model cannot retroactively undo deterministic changes; ambiguous intent is clarified.
            context.data["fact_question"]="你想暂时比较一个假设，还是修改当前条件？"
            context.data["blocking_question"]=context.data["fact_question"]
            return
        known={c["candidateId"] for c in model_context(context)["candidates"]}
        for update in parsed.candidate_updates:
            if update.candidate_id not in known or update.quote not in context.message or update.text!=update.quote:
                raise ValueError("候选更新缺少本轮原文依据")
            if context.data.get("turn_intent")=="explain" or "？" in update.quote: raise ValueError("不能把问题当成事实")
            if update.concern and not any(w in update.quote for w in ["不能接受","无法接受","不太能接受","不接受","担心","顾虑"]): raise ValueError("顾虑缺少原文依据")
        # Validate the whole model patch on a copy before accepting any suggestion.
        shadow=d.model_copy(deep=True)
        patch_fields(shadow,parsed.fields,source="model",confirmed=False)
        corrections=explicit_patch(context,parsed.explicit_fields)
        if corrections: patch_fields(shadow,corrections,source="conversation",confirmed=True)
        if parsed.fields or corrections:
            d.domain_state=shadow.domain_state
            if "target" in corrections: d.user_goal=shadow.user_goal
        state(d)["changes"].extend(f"{fields(d)[k]['label']}：{v}" for k,v in corrections.items())
        for update in parsed.candidate_updates:
            if not any(f["candidateId"]==update.candidate_id and f["text"]==update.text for f in state(d).get("facts",[])):
                add_fact(d,update.candidate_id,update.text,update.concern,source="conversation")
        if parsed.question: context.data["fact_question"]=parsed.question
        context.data["model_understood"]=True
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        warning=f"模型理解不可用，保留已确认条件：{type(error).__name__}"
        d.domain_state["interpretationWarning"]=warning
        state(d)["warning"]=warning
        if context.trace:
            context.trace.fallback(
                stage="Fallback",
                reason=f"模型理解不可用，保留已确认条件：{type(error).__name__}: {error}",
                from_path="model_understanding",
                to_path="confirmed_rules",
                details={"agent": "ConversationInterpretation", "warning": warning},
            )


def candidate_text(decision,candidate):
    return "；".join([candidate.summary or "说明待补充",*[f["text"] for f in state(decision).get("facts",[]) if f["candidateId"]==candidate.candidate_id]])


def _stable_evidence_id(*parts):
    raw = "|".join("" if part is None else str(part) for part in parts)
    return "ev:" + sha256(raw.encode("utf-8")).hexdigest()[:24]


def _source_label(source_kind):
    return {
        "user": "用户输入",
        "web": "搜索结果",
        "system": "系统推断",
        "fixture": "演示数据",
        "database": "数据库记录",
    }.get(source_kind or "unknown", "来源不明")


def _note(source_kind, citation_status=None):
    if source_kind == "web":
        return "来源链接已校验，内容未独立核实" if citation_status == "matched" else "搜索来源未完全校验，内容需核实"
    if source_kind == "user":
        return "用户输入，未外部核实"
    if source_kind == "fixture":
        return "演示数据，不代表真实情况"
    if source_kind == "database":
        return "项目数据库记录"
    if source_kind == "system":
        return "系统推断，需查看其支撑依据"
    return "来源不明，待核实"


def _register_evidence(decision, item):
    if not item.evidence_id:
        item = item.model_copy(update={"evidence_id": _stable_evidence_id(item.candidate_id, item.key, item.value, item.source_title, item.source_url)})
    existing = {e.evidence_id: e for e in decision.evidence if e.evidence_id}
    existing[item.evidence_id] = item
    decision.evidence = list(existing.values())
    return item


def _candidate_evidence(decision, candidate, key, value, text, statement_kind=None):
    for item in candidate.evidence:
        if (item.criterion_key or item.key) == key and (value is None or item.value == value) and item.evidence_id:
            return _register_evidence(decision, item)
    source_kind = source_kind_for_origin(candidate.origin)
    if candidate.candidate_id in decision.domain_state.get("demoCandidateIds", []):
        source_kind = "fixture"
    if source_kind == "fixture" and not decision.context.get("demoMode") and candidate.origin != "fixture":
        source_kind = "unknown"
    statement_kind = statement_kind or ("subjective_judgment" if source_kind == "user" else "reported_fact")
    item = Evidence(
        evidence_id=_stable_evidence_id(candidate.candidate_id, key, value if value is not None else text, source_kind),
        candidate_id=candidate.candidate_id,
        criterion_key=key,
        key=key,
        value=value if value is not None else text,
        source_title=_source_label(source_kind),
        claim=text,
        source_quote=text,
        source_kind=source_kind,
        statement_kind=statement_kind,
        citation_status="not_applicable",
        claim_status="not_applicable" if source_kind in {"fixture", "database"} else "unverified",
        verification_note=_note(source_kind),
        recorded_revision=decision.revision,
    )
    return _register_evidence(decision, item)


def catalog(decision):
    sync_decision_evidence(decision)
    result={}
    for c in decision.candidates:
        trusted_summary=c.origin!="web"
        if trusted_summary:
            text = c.summary or "说明待补充"
            item = _candidate_evidence(decision, c, "summary", text, text)
            result[item.evidence_id]={"candidateId":c.candidate_id,"text":text,"source":item.source_kind,"evidence":item.model_dump(mode="json", by_alias=True)}
            result[f"candidate:{c.candidate_id}:summary"] = result[item.evidence_id]
        for key,value in c.attributes.items():
            if isinstance(value,(int,float)) and (c.origin!="web" or any(p.criterion_key==key and p.raw_value is not None and p.evidence_ids for p in c.score_breakdown)):
                text=f"{key}：{value}"
                item = _candidate_evidence(decision, c, key, value, text)
                result[item.evidence_id]={"candidateId":c.candidate_id,"text":text,"source":item.source_kind,"evidence":item.model_dump(mode="json", by_alias=True)}
                result[f"candidate:{c.candidate_id}:{key}"] = result[item.evidence_id]
    valid={c.candidate_id for c in decision.candidates}
    for f in state(decision).get("facts",[]):
        if f["candidateId"] in valid:
            item = Evidence(
                evidence_id=f["id"],
                candidate_id=f["candidateId"],
                criterion_key=f.get("kind"),
                key=f.get("kind") or "fact",
                value=f.get("value", f["text"]),
                source_title="用户输入" if f.get("source") == "conversation" else _source_label(source_kind_for_origin(f.get("source"))),
                claim=f["text"],
                source_quote=f.get("quote") or f["text"],
                source_kind="user" if f.get("source") == "conversation" else source_kind_for_origin(f.get("source")),
                statement_kind="reported_fact",
                citation_status="not_applicable",
                claim_status="unverified",
                verification_note="用户输入，未外部核实",
                recorded_revision=f.get("revision"),
            )
            item = _register_evidence(decision, item)
            result[item.evidence_id]={"candidateId":f["candidateId"],"text":f["text"],"source":item.source_kind,"evidence":item.model_dump(mode="json", by_alias=True)}
    return result


def point(c, text, key="summary"):
    source_id = f"candidate:{c.candidate_id}:{key}"
    return {"candidateId":c.candidate_id,"text":text,"sourceId":source_id,"evidenceIds":[source_id]}


def _resolve_refs(item, sources):
    ids = []
    for source_id in item.get("evidenceIds") or [item.get("sourceId")]:
        source = sources.get(source_id)
        evidence = source.get("evidence") if source else None
        evidence_id = evidence.get("evidenceId") if isinstance(evidence, dict) else source_id
        if source and evidence_id and evidence_id not in ids:
            ids.append(evidence_id)
    if not ids:
        return None
    resolved = dict(item)
    resolved["evidenceIds"] = ids
    resolved["sourceId"] = ids[0]
    return resolved


def _reason_refs(reason):
    refs = [{"source_id": item.source_id, "quote": item.quote} for item in reason.citations]
    if not refs:
        refs = [{"source_id": reason.source_id, "quote": reason.quote}]
    elif reason.source_id != refs[0]["source_id"] or reason.quote != refs[0]["quote"]:
        raise ValueError("解释引用表示不一致")
    return refs


def rule_analysis(context, decision):
    info=state(decision);current=fields(decision);candidates=decision.candidates
    priority=str(current.get("priority",{}).get("value") or "")
    result={"primaryCandidateId":None,"reasons":[],"tradeoffs":[],"question":None,"hypothetical":bool(context.data.get("is_hypothetical")),"mode":"rules","changes":info.get("changes",[])}
    if not candidates:
        result.update(summary="当前没有满足条件的候选，先保留你的限制。",question="你想补充其他候选，还是调整哪一项限制？")
        return result
    measured=any(any(p.raw_value is not None and p.weight>0 for p in c.score_breakdown) for c in candidates)
    chosen=None
    if measured:
        chosen=candidates[0]
        if not any(p.raw_value is not None and p.weight>0 for p in chosen.score_breakdown):
            result.update(summary="排序靠前的候选缺少可核验或用户提供的有效数值，暂不把缺失值当成优势。",question="可以补充它在关键比较维度上的信息吗？")
            return result
        active={c.key:c for c in decision.criteria}
        for score in sorted(chosen.score_breakdown,key=lambda p:p.weight,reverse=True):
            if score.raw_value is None or score.weight<=0: continue
            criterion=active.get(score.criterion_key)
            if not criterion: continue
            peers=[c for c in candidates[1:] if isinstance(c.attributes.get(criterion.key),(int,float))]
            text=f"{chosen.name}的{criterion.label}为 {score.raw_value}{criterion.unit or ''}"
            item = point(chosen,text,criterion.key)
            if peers:
                text+=f"；{peers[0].name}为 {peers[0].attributes[criterion.key]}{criterion.unit or ''}"
                item.update(text=text,evidenceIds=[item["sourceId"],f"candidate:{peers[0].candidate_id}:{criterion.key}"])
            result["reasons"].append(item)
            if len(result["reasons"])>=2: break
        for other in candidates[1:]:
            advantages=[]
            for criterion in decision.criteria:
                a,b=chosen.attributes.get(criterion.key),other.attributes.get(criterion.key)
                if not isinstance(a,(int,float)) or not isinstance(b,(int,float)): continue
                lower=criterion.direction.value=="lower_is_better"
                if (b<a if lower else b>a): advantages.append(criterion.label)
            if advantages: result["tradeoffs"].append(point(other,f"{other.name}在{'、'.join(advantages[:2])}上更有优势；当前排序综合考虑了其他偏好。"))
    else:
        for c in candidates: c.score_breakdown=[]
        decision.domain_state["qualitative"]=True
        background=current.get("background",{}).get("value") or ""
        # Bounded textual dimensions: these are evidence matches, never candidate scores.
        if "稳定" in priority:
            positive=["薪酬稳定","平台成熟","稳定性高","稳定"]
            negative=["业务阶段较早","早期","不稳定"]
        elif any(w in priority for w in ["成长","方向","匹配"]):
            positive=["成长空间更大","成长空间大","方向更匹配","方向匹配"]
            negative=["传统产品","不匹配"]
        elif any(w in priority for w in ["实践","实战"]) and "已有" in background:
            positive=["实践反馈快","项目实战","实践"]
            negative=["实践少"]
        elif "框架" in priority or "零" in background or 0 < (current.get("weeklyHours",{}).get("value") or 100) <= 3:
            positive=["路径完整","上手稳定","系统框架"]
            negative=["自行补齐","需要自行组织"]
        else: positive=[];negative=[]
        supported=[c for c in candidates if any(w in c.summary for w in positive) and not any(w in c.summary for w in negative)]
        if len(supported)==1: chosen=supported[0]
        if not chosen and len(candidates)==1: chosen=candidates[0]
        if chosen and len(candidates)==1:
            result["reasons"].append(point(chosen,f"排除其他选项后只剩 {chosen.name}；它的已知取舍需要继续核对。"))
        elif chosen:
            result["reasons"].append(point(chosen,f"{chosen.name}的已有说明是：{chosen.summary}。这与{'你的基础和可用时间' if background or current.get('weeklyHours',{}).get('value') else '你表达的优先项'}更吻合。"))
        for c in candidates:
            if c!=chosen: result["tradeoffs"].append(point(c,f"{c.name}：{candidate_text(decision,c)}"))
        if not chosen:
            if "学习" in decision.user_goal:
                result["question"]="你目前有编程基础吗？" if any(w in priority for w in ["实践","实战"]) and not background else "你更希望先获得系统框架，还是通过动手项目学习？"
            elif len(candidates)==1:
                result["question"]=f"排除其他选项后只剩 {candidates[0].name}。它的已知取舍可以接受吗，还是需要补充其他候选？"
            else:
                result["question"]="稳定、成长方向和日常成本中，哪一项最不能妥协？"
    concerns=[f for f in info.get("facts",[]) if f.get("concern") and any(c.candidate_id==f["candidateId"] for c in candidates)]
    if chosen and any(f["candidateId"]==chosen.candidate_id for f in concerns):
        name=chosen.name
        result["summary"]=f"{name}仍有上述优势，但你新增的顾虑改变了取舍，暂时不把它作为确定选择。"
        for f in concerns:
            if f["candidateId"]==chosen.candidate_id: result["tradeoffs"].insert(0,{"candidateId":f["candidateId"],"text":f["text"],"sourceId":f["id"]})
        result["question"]="这项顾虑是不能妥协的条件，还是可以用其他优势交换？"
        chosen=None
    else:
        result["summary"]=(f"按照{'你当前的优先项' if priority else '已有条件'}，目前更倾向 {chosen.name}。" if chosen else "现有信息还不足以锁定一个选择；先看这些差异。")
    result["primaryCandidateId"]=chosen.candidate_id if chosen else None
    if context.data.get("turn_intent")=="explain":
        focus=matched_candidates(decision,context.message)
        if len(focus)==1:
            c=next((c for c in candidates if c.candidate_id==focus[0]["candidateId"]),None)
            if c:
                result["summary"]=f"关于你问的 {c.name}：{candidate_text(decision,c)}。"+result["summary"]
                if chosen and c!=chosen: result["summary"]+=f"当前更倾向 {chosen.name}，是因为优先满足{priority or '当前比较条件'}；如果优先级改变，结论也可能改变。"
    if result["hypothetical"]: result["summary"]="仅看这个假设，"+result["summary"]+"当前已保存的条件和选择没有改变。"
    if decision.context.get("demoMode") or any(c.origin=="fixture" for c in candidates): result["summary"]+="以上依据演示数据，不代表真实情况。"
    return result


def explain(context, profile):
    d=context.decision;info=state(d)
    target=d
    if context.data.get("is_hypothetical"):
        target=d.model_copy(deep=True)
        from choice_agent.agents.base import AgentContext
        from choice_agent.agents.conversation import interpret
        simulated=AgentContext(session_id=context.session_id,trace_id=context.trace_id,user_id=context.user_id,message=re.sub(r"如果|假如|假设|要是","",context.message),decision=target,data={"simulation":True})
        interpret(simulated)
        target.criteria=profile._merge_criteria(target.criteria)
        from choice_agent.decision.conversation import sync_dependencies
        sync_dependencies(target,profile.criteria)
        from choice_agent.schemas import Candidate
        pool=[Candidate.model_validate(c) for c in target.domain_state.get("candidatePool",[])]
        target.candidates=profile.ranking.rank(target,pool,profile.evaluator)
    analysis=rule_analysis(context,target)
    if analysis["hypothetical"] and "当前已保存" not in analysis["summary"]:
        analysis["summary"]="假设分析："+analysis["summary"]+"当前已保存的条件和选择没有改变。"
    if analysis["hypothetical"] and "雨" in context.message:
        analysis.update(primaryCandidateId=None,summary="如果下雨，户外方案的适合程度需要重新确认。现有示例没有天气或室内备选资料，暂时不能据此改选。当前选择未改变。",question="遇到下雨，你愿意保留户外行程，还是更希望准备室内备选？")
    sources=catalog(target)
    analysis["reasons"]=[resolved for r in analysis["reasons"] if (resolved := _resolve_refs(r, sources))]
    analysis["tradeoffs"]=[resolved for r in analysis["tradeoffs"] if (resolved := _resolve_refs(r, sources))]
    provider=context.data.get("model_provider")
    analysis["mode"]="rules"
    if provider and provider.enabled and sources:
        from choice_agent.prompts.conversation import EXPLANATION_PROMPT
        measured=any(any(p.raw_value is not None for p in c.score_breakdown) for c in target.candidates)
        blocked={f["candidateId"] for f in state(target).get("facts",[]) if f.get("concern")}
        allowed=[c.candidate_id for c in target.candidates if c.candidate_id not in blocked and any(v["candidateId"]==c.candidate_id for v in sources.values())]
        if analysis["hypothetical"] and "雨" in context.message: allowed=[]
        if measured: allowed=[analysis["primaryCandidateId"]] if analysis["primaryCandidateId"] else []
        payload={**model_context(context),"fields":fields(target),"saved_fields":fields(d),"hypothetical":analysis["hypothetical"],"source_catalog":sources,"allowed_primary_ids":allowed,"rule_analysis":analysis}
        try:
            user_prompt=json.dumps(payload,ensure_ascii=False)
            model_name=context.data.get("main_model_name") or context.data.get("model_name")
            raw=(
                context.trace.model_call(
                    "Explanation",
                    model_name,
                    EXPLANATION_PROMPT,
                    user_prompt,
                    lambda: provider.complete_json(system_prompt=EXPLANATION_PROMPT,user_prompt=user_prompt,model=model_name),
                    provider=provider,
                )
                if context.trace
                else provider.complete_json(system_prompt=EXPLANATION_PROMPT,user_prompt=user_prompt,model=model_name)
            )
            parsed=AssistanceExplanation.model_validate(raw)
            if parsed.primary_candidate_id is not None and parsed.primary_candidate_id not in allowed: raise ValueError("推荐违反候选限制")
            for reason in [*parsed.reasons,*parsed.tradeoffs]:
                refs = _reason_refs(reason)
                for ref in refs:
                    source=sources.get(ref["source_id"])
                    if not source or source["text"]!=ref["quote"]: raise ValueError("解释引用无效")
                if not any(sources[ref["source_id"]]["candidateId"]==reason.candidate_id for ref in refs): raise ValueError("解释缺少本候选依据")
            if parsed.primary_candidate_id and not any(r.candidate_id==parsed.primary_candidate_id for r in parsed.reasons): raise ValueError("推荐缺少依据")
            response_text=" ".join([parsed.summary,*[r.text for r in [*parsed.reasons,*parsed.tradeoffs]]])
            used_source_ids={ref["source_id"] for reason in [*parsed.reasons,*parsed.tradeoffs] for ref in _reason_refs(reason)}
            known_text=json.dumps({"sources":{k:v for k,v in sources.items() if k in used_source_ids},"fields":fields(target)},ensure_ascii=False)
            if set(re.findall(r"\d+(?:\.\d+)?",response_text))-set(re.findall(r"\d+(?:\.\d+)?",known_text)): raise ValueError("解释含无依据数值")
            if any(w in response_text for w in ["保证成功","绝对安全","没有任何风险","稳赚"]): raise ValueError("解释包含无依据保证")
            analysis.update(primaryCandidateId=parsed.primary_candidate_id,summary=parsed.summary,
                reasons=[{"candidateId":r.candidate_id,"sourceId":_reason_refs(r)[0]["source_id"],"evidenceIds":[ref["source_id"] for ref in _reason_refs(r)],"text":r.text} for r in parsed.reasons],
                tradeoffs=[{"candidateId":r.candidate_id,"sourceId":_reason_refs(r)[0]["source_id"],"evidenceIds":[ref["source_id"] for ref in _reason_refs(r)],"text":r.text} for r in parsed.tradeoffs],question=parsed.question,mode="model")
            analysis["reasons"]=[resolved for r in analysis["reasons"] if (resolved := _resolve_refs(r, sources))]
            analysis["tradeoffs"]=[resolved for r in analysis["tradeoffs"] if (resolved := _resolve_refs(r, sources))]
            if analysis["hypothetical"]: analysis["summary"]="假设分析（未修改当前选择）："+analysis["summary"]
        except (ValueError,RuntimeError,OSError,KeyError,TypeError) as error:
            info["warning"]=f"模型解释不可用，已按现有事实继续比较：{type(error).__name__}"
            analysis["mode"]="rules_fallback"
            if context.trace:
                context.trace.fallback(
                    stage="Fallback",
                    reason=f"模型解释不可用，按已核对事实继续比较：{type(error).__name__}: {error}",
                    from_path="model_explanation",
                    to_path="rules_explanation",
                    details={"agent": "AssistanceExplanation", "warning": info["warning"], "mode": analysis["mode"]},
                )
    if not (d.context.get("demoMode") or any(c.origin=="fixture" for c in target.candidates)) and any(c.origin=="manual" for c in target.candidates):
        analysis["summary"]+="依据用户输入，尚未经外部核实。"
    elif analysis["mode"]=="model" and (d.context.get("demoMode") or any(c.origin=="fixture" for c in target.candidates)):
        analysis["summary"]+="以上依据演示数据，不代表真实情况。"
    analysis["sources"]=sources
    analysis["keyReasons"] = analysis.get("reasons", [])[:4]
    from choice_agent.decision.what_if import missing_info, official_change, scenarios
    speech=analysis["summary"]
    for key,label in [("reasons","依据"),("tradeoffs","取舍")]:
        lines=[r["text"] for r in analysis[key]][:2]
        if lines: speech+="\n"+label+"："+"；".join(lines)
    decision_question = info.get("decisionQuestion") if not analysis["hypothetical"] else None
    if isinstance(decision_question, dict):
        analysis["decisionQuestion"] = decision_question
        question = decision_question.get("question")
    elif analysis["hypothetical"]:
        question = analysis.get("question")
    elif not d.quality_assessment or d.quality_assessment.status == "insufficient_data" or not analysis.get("primaryCandidateId"):
        question = analysis.get("question")
    else:
        question = None
    if context.data.get("unhandled_turn") and analysis["mode"]!="model" and not info.get("changes"):
        question="这句话我还没整理成可比较的信息。你想修改哪个候选的哪一点，或最看重什么？"
    analysis["question"]=question
    analysis["missingInfo"] = missing_info(d, analysis)
    info["lastQuestion"]=question
    if question: speech+="\n"+question
    if analysis["hypothetical"]:
        analysis["notice"] = "这是一次假设比较，没有修改当前保存的正式条件。"
        info["whatIfAnalysis"] = analysis
        info["analysis"] = analysis
    else:
        change = official_change(d, context.data.get("official_baseline"), analysis)
        analysis["lastChange"] = change
        info["lastOfficialChange"] = change
        info["currentAnalysis"] = analysis
        info["analysis"] = analysis
        if isinstance(info.get("whatIfAnalysis"), dict):
            info["whatIfAnalysis"]["stale"] = True
        info["whatIfScenarios"] = scenarios(d, analysis)
        d.recommendation=Recommendation(primary_candidate_id=analysis["primaryCandidateId"],summary=analysis["summary"],ranking_method="grounded_qualitative" if d.domain_state.get("qualitative") else "weighted_sum",reasons=[RecommendationPoint(text=r["text"],candidate_id=r["candidateId"],evidence_ids=r.get("evidenceIds") or [r["sourceId"]]) for r in analysis["reasons"]],tradeoffs=[r["text"] for r in analysis["tradeoffs"]],tradeoff_details=[RecommendationPoint(text=r["text"],candidate_id=r["candidateId"],evidence_ids=r.get("evidenceIds") or [r["sourceId"]]) for r in analysis["tradeoffs"]],generated_from_revision=d.revision)
    context.data["speech_text"]=speech
    transition_decision(d,DecisionStatus.DECIDED,DecisionNextAction.WAIT_USER)
    context.data["display_blocks"]=profile.display_blocks(context)
    return {"speechText":speech,"recommendations":context.data["display_blocks"]}
