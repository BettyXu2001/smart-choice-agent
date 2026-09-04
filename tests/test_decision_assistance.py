import json
import pytest
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.schemas import GenericDecisionRequest, GenericDecisionMessageRequest, DecisionCommandRequest

OFFER = "比较两个 Offer\n以下为演示候选：\nA 公司：AI 产品方向更匹配，成长空间更大，但业务阶段较早；B 公司：平台成熟、薪酬稳定，岗位内容更偏传统产品。"
LEARNING = "选择入门 AI Agent 的学习路径\n以下为演示候选：\n结构化在线课程：路径完整、上手稳定，适合需要系统框架的学习者；开源项目实战：实践反馈快，但需要自行补齐概念和调试能力；文档与论文路线：信息质量高、自由度大，但学习路径容易分散。"


def start(service, text=OFFER, domain="generic"):
    return service.create(1,GenericDecisionRequest(message=text,domain=domain,context={"demoMode":True,"searchMode":"fixture"}))


def say(service, result, text):
    return service.message(1,result.decision_state.decision_id,GenericDecisionMessageRequest(message=text,expected_revision=result.decision_state.revision))


def analysis(result):
    return result.decision_state.domain_state["assistance"]["analysis"]


def chosen_name(result):
    return next((c.name for c in result.decision_state.candidates if c.candidate_id==analysis(result)["primaryCandidateId"]),None)


def test_offline_offer_three_turns_change_the_decision(database):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db);first=start(service)
        assert first.decision_state.domain_state["conversationFields"]["priority"]["value"] is None
        stable=say(service,first,"更看重稳定")
        assert chosen_name(stable)=="B 公司"
        assert "平台成熟" in stable.speech_text and "业务阶段较早" in stable.speech_text
        why=say(service,stable,"那为什么不选 A 公司？")
        assert "关于你问的 A 公司" in why.speech_text
        assert "优先满足稳定" in why.speech_text
        commute=say(service,why,"B 公司通勤每天要两小时，我不太能接受")
        assert chosen_name(commute) is None
        assert "新增的顾虑改变了取舍" in commute.speech_text
        assert "两小时" in commute.speech_text
        assert any(f["concern"] for f in commute.decision_state.domain_state["assistance"]["facts"])
        assert any("两小时" in f["text"] for block in commute.display_blocks for f in block["facts"])
        assert commute.decision_state.domain_state["conversationTurns"][-1]["analysis"]==analysis(commute)


def test_candidate_fact_correction_removes_outdated_concern(database):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db);first=say(service,start(service),"更看重稳定")
        blocked=say(service,first,"B 公司通勤每天两小时，我不能接受")
        corrected=say(service,blocked,"纠正一下，B 公司通勤是半小时，可以接受")
        assert chosen_name(corrected)=="B 公司"
        facts=corrected.decision_state.domain_state["assistance"]["facts"]
        assert len(facts)==1 and not facts[0]["concern"] and "半小时" in facts[0]["text"]


def test_learning_background_and_time_update_without_scores(database):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db);first=start(service,LEARNING)
        beginner=say(service,first,"零编程基础，每周三小时")
        assert chosen_name(beginner)=="结构化在线课程"
        assert beginner.decision_state.domain_state["conversationFields"]["weeklyHours"]["value"]==3
        experienced=say(service,beginner,"其实已有 Python 基础，更想动手实践")
        assert chosen_name(experienced)=="开源项目实战"
        assert "已有" in experienced.decision_state.domain_state["conversationFields"]["background"]["value"]
        assert all(not c.score_breakdown for c in experienced.decision_state.candidates)


def test_hypothesis_preserves_saved_budget_and_recommendation(database):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db);first=start(service,"买电脑，预算 8000","shopping")
        hypothetical=say(service,first,"如果预算改成 6000 呢？")
        assert analysis(hypothetical)["hypothetical"]
        assert "没有满足条件" in hypothetical.speech_text
        assert hypothetical.decision_state.domain_state["conversationFields"]["budget"]["value"]==8000
        assert hypothetical.decision_state.recommendation.primary_candidate_id==first.decision_state.recommendation.primary_candidate_id
        actual=say(service,hypothetical,"预算改成 7000")
        assert not analysis(actual)["hypothetical"]
        assert all(c.attributes["price"]<=7000 for c in actual.decision_state.candidates)


def test_unknown_free_text_is_not_silently_treated_as_understood(database):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db);first=start(service)
        result=say(service,first,"我觉得有一种说不出来的感觉")
        assert "还没整理成可比较的信息" in result.speech_text
        assert result.decision_state.domain_state["assistance"]["facts"]==[]


def test_rain_hypothesis_does_not_invent_weather(database):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db);first=start(service,"从上海出发两天一夜","travel")
        result=say(service,first,"如果下雨呢？")
        assert "没有天气或室内备选资料" in result.speech_text
        assert analysis(result)["primaryCandidateId"] is None
        assert result.decision_state.recommendation.primary_candidate_id==first.decision_state.recommendation.primary_candidate_id


class GroundedModel:
    enabled=True
    def __init__(self): self.calls=[]
    def complete_json(self,system_prompt,user_prompt,model):
        data=json.loads(user_prompt);self.calls.append(data)
        if "source_catalog" not in data:
            return {"fields":{},"question":None,"intent":"compare","candidate_updates":[]}
        allowed=data["allowed_primary_ids"]
        primary=allowed[0] if allowed else None
        source_id,source=next((k,v) for k,v in data["source_catalog"].items() if primary is None or v["candidateId"]==primary)
        return {"primary_candidate_id":primary,"summary":"结合你的优先项，先考虑已有依据支持的选项。","reasons":[{"candidate_id":source["candidateId"],"source_id":source_id,"quote":source["text"],"text":"这项已有信息是当前建议的依据。"}],"tradeoffs":[],"question":None}


def test_model_receives_context_even_when_rules_extract_a_field(database):
    with database.session_factory() as db:
        model=GroundedModel();service=GenericDecisionOrchestrator(db,provider=model);first=start(service)
        model.calls.clear()
        result=say(service,first,"更看重稳定，为什么选它？")
        assert len(model.calls)==2
        understand,explain=model.calls
        assert understand["candidates"] and len(understand["recent_messages"])>=3
        assert understand["fields"]["priority"]["value"]
        assert "previous_question" in understand
        assert explain["source_catalog"] and analysis(result)["mode"]=="model"


@pytest.mark.parametrize("failure",["unknown_id","false_quote","invented_number","timeout"])
def test_invalid_model_explanations_fall_back_to_grounded_rules(database,failure):
    class InvalidModel(GroundedModel):
        def complete_json(self,**kwargs):
            data=json.loads(kwargs["user_prompt"])
            value=super().complete_json(**kwargs)
            if "source_catalog" in data:
                if failure=="unknown_id": value["primary_candidate_id"]="not-a-candidate"
                elif failure=="false_quote": value["reasons"][0]["quote"]="编造资料"
                elif failure=="invented_number": value["summary"]="年薪 guaranteed 999999"
                else: raise TimeoutError("simulated")
            return value
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db,provider=InvalidModel());first=start(service)
        result=say(service,first,"更看重稳定")
        assert chosen_name(result)=="B 公司"
        assert analysis(result)["mode"]=="rules_fallback"
        assert "模型解释不可用" in result.decision_state.domain_state["assistance"]["warning"]


def test_model_cannot_recommend_filtered_candidate(database):
    class WrongCandidate(GroundedModel):
        def complete_json(self,**kwargs):
            value=super().complete_json(**kwargs)
            if "source_catalog" in json.loads(kwargs["user_prompt"]): value["primary_candidate_id"]="creator-16"
            return value
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db,provider=WrongCandidate())
        result=start(service,"买电脑，预算 7000","shopping")
        assert all(c.attributes["price"]<=7000 for c in result.decision_state.candidates)
        assert analysis(result)["mode"]=="rules_fallback"
        assert result.decision_state.recommendation.primary_candidate_id in {c.candidate_id for c in result.decision_state.candidates}


def test_model_candidate_update_requires_current_quote_and_known_id(database):
    class UpdateModel(GroundedModel):
        def complete_json(self,**kwargs):
            data=json.loads(kwargs["user_prompt"])
            if "source_catalog" not in data:
                return {"fields":{},"candidate_updates":[{"candidate_id":"missing","text":"虚构信息","quote":"虚构信息","concern":False}]}
            return super().complete_json(**kwargs)
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db,provider=UpdateModel());result=start(service)
        assert not result.decision_state.domain_state["assistance"]["facts"]
        assert "模型理解不可用" in result.decision_state.domain_state["interpretationWarning"]
