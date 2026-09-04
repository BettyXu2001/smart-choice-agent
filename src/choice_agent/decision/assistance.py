"""Grounded turn updates and bounded decision assistance, with optional model reasoning."""
from copy import deepcopy
import json
import re
from uuid import uuid4

from choice_agent.decision.conversation import fields, patch_fields
from choice_agent.schemas import (
    AssistanceInterpretation, AssistanceExplanation, Recommendation, RecommendationPoint,
    DecisionStatus, DecisionNextAction,
)
from choice_agent.decision.state_machine import transition_decision


def state(decision):
    return decision.domain_state.setdefault("assistance", {"facts": [], "changes": []})


def hypothetical(text):
    return bool(re.search(r"如果|假如|假设|要是", text))


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
    existing.append({"id":"fact:"+uuid4().hex,"candidateId":candidate_id,"text":text,"quote":text,"kind":kind,"concern":concern,"source":source,"confirmed":True,"revision":decision.revision+1})
    info["changes"].append("补充候选信息："+text)


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
    if d.domain == "generic":
        if re.search(r"零(?:编程)?基础|没有(?:编程)?基础|不会编程", text): patch["background"] = "零编程基础"
        elif re.search(r"(?:有|已有|会|掌握|学过).{0,8}(?:Python|python|编程).{0,4}(?:基础)?", text): patch["background"] = "已有 Python / 编程基础"
        hours = re.search(r"每周(?:只有|最多|能用|可用|有|投入|学习|大约|时间|是|为|\s)*(\d+(?:\.\d+)?|一|两|二|三|四|五|六|七|八|九|十)\s*(?:个)?小时", text)
        if hours:
            value=hours[1]
            patch["weeklyHours"] = float(value) if re.fullmatch(r"\d+(?:\.\d+)?",value) else {"一":1,"两":2,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}[value]
    if patch:
        patch_fields(d,patch,source="conversation")
        info["changes"].extend(f"{fields(d)[k]['label']}：{v}" for k,v in patch.items())
    matches = matched_candidates(d,text)
    question = context.data["turn_intent"] == "explain" or bool(re.search(r"？|吗$|多少|是否|怎么样|能不能|是不是", text))
    fact_cue = any(w in text for w in ["通勤", "薪资", "薪酬", "工资", "加班", "远程", "补充", "改成", "纠正"])
    if len(matches) == 1:
        info["focusCandidateId"] = matches[0]["candidateId"]
    elif not matches and any(w in text for w in ["它", "那家", "这个选项"]):
        focus=info.get("focusCandidateId")
        pool=d.domain_state.get("candidatePool",[])
        matches=[c for c in pool if c["candidateId"]==focus]
        if not matches and fact_cue: context.data["fact_question"]="你说的是哪个候选？告诉我名称后，我再更新它的信息。"
    if fact_cue and not question:
        if len(matches)==1:
            concern = any(w in text for w in ["不能接受", "无法接受", "不太能接受", "不接受", "担心", "顾虑"])
            add_fact(d,matches[0]["candidateId"],text,concern)
        elif len(matches)>1:
            context.data["fact_question"]="请分别说明每个候选要补充的信息，以免我把条件记错。"


def model_context(context):
    d=context.decision
    return {"message":context.message,"domain":d.domain,"fields":fields(d),
            "recent_messages":[{"role":m.role,"content":m.content[:2000]} for m in d.messages[-8:]],
            "previous_question":state(d).get("analysis",{}).get("question"),
            "candidates":[{"candidateId":c["candidateId"],"name":c["name"],"summary":c.get("summary","")[:1000],"origin":c.get("origin")} for c in (d.domain_state.get("manualCandidates") or d.domain_state.get("candidatePool",[]))[:12]],
            "facts":state(d).get("facts",[])[-24:],"rule_intent":context.data.get("turn_intent")}


def model_understand(context):
    d=context.decision
    provider=context.data.get("model_provider")
    if not provider or not provider.enabled or context.data.get("is_hypothetical"): return
    from choice_agent.prompts.conversation import SYSTEM_PROMPT
    try:
        parsed=AssistanceInterpretation.model_validate(provider.complete_json(system_prompt=SYSTEM_PROMPT,user_prompt=json.dumps(model_context(context),ensure_ascii=False),model=context.data.get("model_name")))
        if parsed.intent=="what_if":
            # A model cannot retroactively undo deterministic changes; ambiguous intent is clarified.
            context.data["fact_question"]="你想暂时比较一个假设，还是修改当前条件？"
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
        if parsed.fields: d.domain_state=shadow.domain_state
        for update in parsed.candidate_updates:
            if not any(f["candidateId"]==update.candidate_id and f["text"]==update.text for f in state(d).get("facts",[])):
                add_fact(d,update.candidate_id,update.text,update.concern,source="conversation")
        if parsed.question: context.data["fact_question"]=parsed.question
        context.data["model_understood"]=True
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        warning=f"模型理解不可用，保留已确认条件：{type(error).__name__}"
        d.domain_state["interpretationWarning"]=warning
        state(d)["warning"]=warning


def candidate_text(decision,candidate):
    return "；".join([candidate.summary or "说明待补充",*[f["text"] for f in state(decision).get("facts",[]) if f["candidateId"]==candidate.candidate_id]])


def catalog(decision):
    result={}
    for c in decision.candidates:
        result[f"candidate:{c.candidate_id}:summary"]={"candidateId":c.candidate_id,"text":c.summary or "说明待补充","source": "demo" if decision.context.get("demoMode") or c.origin=="fixture" else c.origin}
        for key,value in c.attributes.items():
            if isinstance(value,(int,float)):
                result[f"candidate:{c.candidate_id}:{key}"]={"candidateId":c.candidate_id,"text":f"{key}：{value}","source":c.origin}
    valid={c.candidate_id for c in decision.candidates}
    for f in state(decision).get("facts",[]):
        if f["candidateId"] in valid: result[f["id"]]={"candidateId":f["candidateId"],"text":f["text"],"source":f["source"]}
    return result


def point(c, text, key="summary"):
    return {"candidateId":c.candidate_id,"text":text,"sourceId":f"candidate:{c.candidate_id}:{key}"}


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
        active={c.key:c for c in decision.criteria}
        for score in sorted(chosen.score_breakdown,key=lambda p:p.weight,reverse=True):
            if score.raw_value is None or score.weight<=0: continue
            criterion=active.get(score.criterion_key)
            if not criterion: continue
            peers=[c for c in candidates[1:] if isinstance(c.attributes.get(criterion.key),(int,float))]
            text=f"{chosen.name}的{criterion.label}为 {score.raw_value}{criterion.unit or ''}"
            if peers: text+=f"；{peers[0].name}为 {peers[0].attributes[criterion.key]}{criterion.unit or ''}"
            result["reasons"].append(point(chosen,text,criterion.key))
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
        elif "零" in background or (current.get("weeklyHours",{}).get("value") or 100)>0 and (current.get("weeklyHours",{}).get("value") or 100)<=3:
            positive=["路径完整","上手稳定","系统框架"]
            negative=["自行补齐","需要自行组织"]
        else: positive=[];negative=[]
        supported=[c for c in candidates if any(w in c.summary for w in positive) and not any(w in c.summary for w in negative)]
        if len(supported)==1: chosen=supported[0]
        if chosen: result["reasons"].append(point(chosen,f"{chosen.name}的已有说明是：{chosen.summary}。这与{'你的基础和可用时间' if background or current.get('weeklyHours',{}).get('value') else '你表达的优先项'}更吻合。"))
        for c in candidates:
            if c!=chosen: result["tradeoffs"].append(point(c,f"{c.name}：{candidate_text(decision,c)}"))
        if not chosen:
            result["question"]="你更希望先获得系统框架，还是通过动手项目学习？" if "学习" in decision.user_goal else "稳定、成长方向和日常成本中，哪一项最不能妥协？"
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
    provider=context.data.get("model_provider")
    analysis["mode"]="rules"
    if provider and provider.enabled and sources:
        from choice_agent.prompts.conversation import EXPLANATION_PROMPT
        measured=any(any(p.raw_value is not None for p in c.score_breakdown) for c in target.candidates)
        blocked={f["candidateId"] for f in state(target).get("facts",[]) if f.get("concern")}
        allowed=[c.candidate_id for c in target.candidates if c.candidate_id not in blocked]
        if analysis["hypothetical"] and "雨" in context.message: allowed=[]
        if measured: allowed=[analysis["primaryCandidateId"]] if analysis["primaryCandidateId"] else []
        payload={**model_context(context),"source_catalog":sources,"allowed_primary_ids":allowed,"rule_analysis":analysis}
        try:
            parsed=AssistanceExplanation.model_validate(provider.complete_json(system_prompt=EXPLANATION_PROMPT,user_prompt=json.dumps(payload,ensure_ascii=False),model=context.data.get("main_model_name") or context.data.get("model_name")))
            if parsed.primary_candidate_id is not None and parsed.primary_candidate_id not in allowed: raise ValueError("推荐违反候选限制")
            for reason in [*parsed.reasons,*parsed.tradeoffs]:
                source=sources.get(reason.source_id)
                if not source or source["candidateId"]!=reason.candidate_id or source["text"]!=reason.quote: raise ValueError("解释引用无效")
            if parsed.primary_candidate_id and not any(r.candidate_id==parsed.primary_candidate_id for r in parsed.reasons): raise ValueError("推荐缺少依据")
            response_text=" ".join([parsed.summary,*[r.text for r in [*parsed.reasons,*parsed.tradeoffs]]])
            known_text=json.dumps({"sources":sources,"fields":fields(target)},ensure_ascii=False)
            if set(re.findall(r"\d+(?:\.\d+)?",response_text))-set(re.findall(r"\d+(?:\.\d+)?",known_text)): raise ValueError("解释含无依据数值")
            if any(w in response_text for w in ["保证成功","绝对安全","没有任何风险","稳赚"]): raise ValueError("解释包含无依据保证")
            analysis.update(primaryCandidateId=parsed.primary_candidate_id,summary=parsed.summary,
                reasons=[{"candidateId":r.candidate_id,"sourceId":r.source_id,"text":r.text} for r in parsed.reasons],
                tradeoffs=[{"candidateId":r.candidate_id,"sourceId":r.source_id,"text":r.text} for r in parsed.tradeoffs],question=parsed.question,mode="model")
            if analysis["hypothetical"]: analysis["summary"]="假设分析（未修改当前选择）："+analysis["summary"]
        except (ValueError,RuntimeError,OSError,KeyError,TypeError) as error:
            info["warning"]=f"模型解释不可用，已按现有事实继续比较：{type(error).__name__}"
            analysis["mode"]="rules_fallback"
    if not (d.context.get("demoMode") or any(c.origin=="fixture" for c in target.candidates)) and any(c.origin=="manual" for c in target.candidates):
        analysis["summary"]+="依据用户输入，尚未经外部核实。"
    elif analysis["mode"]=="model" and (d.context.get("demoMode") or any(c.origin=="fixture" for c in target.candidates)):
        analysis["summary"]+="以上依据演示数据，不代表真实情况。"
    analysis["sources"]=sources
    info["analysis"]=analysis
    speech=analysis["summary"]
    for key,label in [("reasons","依据"),("tradeoffs","取舍")]:
        lines=[r["text"] for r in analysis[key]][:2]
        if lines: speech+="\n"+label+"："+"；".join(lines)
    question=context.data.get("fact_question") or analysis.get("question")
    if context.data.get("unhandled_turn") and analysis["mode"]!="model" and not info.get("changes"):
        question="这句话我还没整理成可比较的信息。你想修改哪个候选的哪一点，或最看重什么？"
    analysis["question"]=question
    if question: speech+="\n"+question
    if not analysis["hypothetical"]:
        d.recommendation=Recommendation(primary_candidate_id=analysis["primaryCandidateId"],summary=analysis["summary"],ranking_method="grounded_qualitative" if d.domain_state.get("qualitative") else "weighted_sum",reasons=[RecommendationPoint(text=r["text"],candidate_id=r["candidateId"],evidence_ids=[r["sourceId"]]) for r in analysis["reasons"]],tradeoffs=[r["text"] for r in analysis["tradeoffs"]],generated_from_revision=d.revision)
    context.data["speech_text"]=speech
    transition_decision(d,DecisionStatus.DECIDED,DecisionNextAction.WAIT_USER)
    context.data["display_blocks"]=profile.display_blocks(context)
    return {"speechText":speech,"recommendations":context.data["display_blocks"]}
