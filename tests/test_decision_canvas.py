from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.schemas import DecisionCommandRequest, GenericDecisionMessageRequest, GenericDecisionRequest

OFFER = "比较两个 Offer\n以下为演示候选：\nA 公司：AI 产品方向更匹配，成长空间更大，但业务阶段较早；B 公司：平台成熟、薪酬稳定，岗位内容更偏传统产品。"


def start(service):
    return service.create(1, GenericDecisionRequest(message=OFFER, domain="generic", context={"demoMode": True, "searchMode": "fixture"}))


def say(service, result, text, request_id="turn"):
    return service.message(1, result.decision_state.decision_id, GenericDecisionMessageRequest(message=text, requestId=request_id, expectedRevision=result.decision_state.revision))


def assistance(result):
    return result.decision_state.domain_state["assistance"]


def test_canvas_keeps_official_analysis_and_decision_boundaries(database):
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        result = say(service, start(service), "更看重稳定", "stable")
        info = assistance(result)
        current = info["currentAnalysis"]
        assert info["analysis"] == current
        assert current["primaryCandidateId"] == result.decision_state.recommendation.primary_candidate_id
        assert 1 <= len(current["keyReasons"]) <= 4
        assert current["missingInfo"] == []
        assert "decisionQuestion" not in current
        assert result.decision_state.recommendation is not None
        assert info["lastOfficialChange"]["to"]["label"] == "B 公司"
        assert info["whatIfScenarios"]


def test_hypothesis_writes_separate_what_if_without_changing_saved_choice(database):
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        official = say(service, start(service), "更看重稳定", "stable")
        before_id = official.decision_state.recommendation.primary_candidate_id
        hypothetical = say(service, official, "假设我把成长机会放在稳定性之前", "what-if")
        info = assistance(hypothetical)
        assert info["currentAnalysis"]["primaryCandidateId"] == before_id
        assert info["whatIfAnalysis"]["hypothetical"] is True
        assert "没有修改当前保存的正式条件" in info["whatIfAnalysis"]["notice"]
        assert hypothetical.decision_state.recommendation.primary_candidate_id == before_id
        assert "analysisMode" not in hypothetical.decision_state.context
        assert "scenarioId" not in hypothetical.decision_state.context


def test_commute_limit_eliminates_known_over_limit_candidate(database):
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        result = say(service, start(service), "更看重稳定", "stable")
        result = say(service, result, "B 公司通勤每天要两小时", "commute-fact")
        limited = say(service, result, "我每天最多接受 1 小时通勤", "commute-limit")
        b_id = next(item["candidateId"] for item in limited.decision_state.domain_state["manualCandidates"] if item["name"] == "B 公司")
        assert limited.decision_state.candidate_state[b_id].status == "eliminated"
        commute = next(
            item for item in limited.decision_state.constraints
            if item.constraint_id == "dynamic:commute_minutes"
        )
        assert commute.value == 60
        assert commute.key == "commute_minutes"
        assert commute.operator == "lte"
        assert limited.decision_state.recommendation.primary_candidate_id != b_id
        change = assistance(limited)["lastOfficialChange"]
        assert change["changed"] is True
        assert "通勤" in change["reason"]

def test_question_worded_what_if_does_not_change_official_travel_state(database):
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        initial = service.create(
            1,
            GenericDecisionRequest(
                message="从上海出发两天一夜，预算 2000 元，想轻松一点",
                domain="travel",
                context={"demoMode": True, "searchMode": "fixture"},
            ),
        )
        before_fields = initial.decision_state.domain_state["conversationFields"]
        before_id = initial.decision_state.recommendation.primary_candidate_id
        result = say(service, initial, "预算提高到 2500 会怎样？", "budget-question-what-if")
        info = assistance(result)
        assert info["whatIfAnalysis"]["hypothetical"] is True
        assert result.decision_state.domain_state["conversationFields"] == before_fields
        assert result.decision_state.recommendation.primary_candidate_id == before_id
        assert info["whatIfAnalysis"]["proposedFields"] == {"budget": 2500.0}

        adopted = service.command(
            1,
            result.decision_state.decision_id,
            DecisionCommandRequest(
                type="update_fields",
                payload={"fields": info["whatIfAnalysis"]["proposedFields"]},
                command_id="adopt-budget-what-if",
                expectedRevision=result.decision_state.revision,
            ),
        )
        assert adopted.decision_state.domain_state["conversationFields"]["budget"]["value"] == 2500.0
        assert assistance(adopted)["whatIfAnalysis"]["stale"] is True

def test_negative_priority_what_if_can_be_adopted_without_mutating_official_state(database):
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        initial = service.create(
            1,
            GenericDecisionRequest(
                message="从上海出发两天一夜，想轻松一点",
                domain="travel",
                context={"demoMode": True, "searchMode": "fixture"},
            ),
        )
        result = say(service, initial, "假设我不再优先考虑轻松", "remove-priority-what-if")
        info = assistance(result)
        assert result.decision_state.domain_state["conversationFields"]["priority"]["value"] == "轻松"
        assert info["whatIfAnalysis"]["proposedFields"] == {"priority": None}
