from choice_agent.config import Settings
from choice_agent.orchestration.diet import DietOrchestrator
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.providers.model import DisabledProvider
from choice_agent.schemas import ChatRequest, GenericDecisionMessageRequest, GenericDecisionRequest


def _displayed_candidate_ids(decision):
    mapping = decision.domain_state.get("displayCandidateMap", {})
    return {
        str(mapping.get(str(block["id"]), block["id"]))
        for block in decision.domain_state.get("displayBlocks", [])
        if block.get("id") is not None
    }


def test_diet_batch_reject_refreshes_and_excludes_current_batch(database):
    with database.session_factory() as db:
        service = DietOrchestrator(db, Settings(), DisabledProvider())
        first = service.chat(1, ChatRequest(
            message="晚餐想吃清淡一点",
            request_id="diet-batch-first",
        ))
        shown = _displayed_candidate_ids(first.decision_state)
        assert shown

        second = service.chat(1, ChatRequest(
            session_id=first.session_id,
            message="都不太想吃",
            expected_revision=first.decision_state.revision,
            request_id="diet-batch-second",
        ))
        turn = second.decision_state.domain_state["dietTurns"][-1]

    assert turn["feedbackType"] == "batch_reject"
    assert turn["sourceSnapshot"]["retrieved"] is True
    assert turn["sourceSnapshot"]["reusedCandidatePool"] is False
    assert shown.issubset(set(second.decision_state.excluded_candidates))


def test_travel_batch_reject_uses_refresh_path(database):
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        first = service.create(1, GenericDecisionRequest(
            message="从上海出发两天一夜，预算 1500 元以内，想轻松一点",
            domain="travel",
            context={"demoMode": True, "searchMode": "fixture"},
            request_id="travel-batch-first",
        ))
        previous = {item.candidate_id for item in first.decision_state.candidates}
        assert previous

        second = service.message(1, first.decision_state.decision_id, GenericDecisionMessageRequest(
            message="换一批",
            expected_revision=first.decision_state.revision,
            request_id="travel-batch-second",
        ))
        turn = second.decision_state.domain_state["conversationTurns"][-1]

    assert turn["feedbackType"] == "batch_reject"
    assert turn["sourceSnapshot"]["retrieved"] is True
    assert previous.issubset(set(second.decision_state.excluded_candidates))


def test_shopping_preference_update_reuses_candidate_pool(database):
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        first = service.create(1, GenericDecisionRequest(
            message="买电脑，预算 8000 元，主要用来学习办公",
            domain="shopping",
            context={"demoMode": True, "searchMode": "fixture"},
            request_id="shopping-pref-first",
        ))
        second = service.message(1, first.decision_state.decision_id, GenericDecisionMessageRequest(
            message="更看重性能",
            expected_revision=first.decision_state.revision,
            request_id="shopping-pref-second",
        ))
        turn = second.decision_state.domain_state["conversationTurns"][-1]

    assert turn["feedbackType"] == "preference_update"
    assert turn["sourceSnapshot"]["retrieved"] is False
    assert turn["sourceSnapshot"]["reusedCandidatePool"] is True


def test_generic_candidate_dislike_reranks_without_search(database):
    message = "比较两个 Offer\n以下为演示候选：\nA 公司：成长快但波动大；B 公司：平台成熟且稳定。"
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        first = service.create(1, GenericDecisionRequest(
            message=message,
            domain="generic",
            context={"demoMode": True, "searchMode": "fixture"},
            request_id="generic-dislike-first",
        ))
        a = next(item for item in first.decision_state.candidates if item.name == "A 公司")
        second = service.message(1, first.decision_state.decision_id, GenericDecisionMessageRequest(
            message="我不喜欢 A 公司",
            expected_revision=first.decision_state.revision,
            request_id="generic-dislike-second",
        ))
        turn = second.decision_state.domain_state["conversationTurns"][-1]

    assert turn["feedbackType"] == "candidate_dislike"
    assert a.candidate_id in second.decision_state.excluded_candidates
    assert turn["sourceSnapshot"]["retrieved"] is False
    assert turn["sourceSnapshot"]["reusedCandidatePool"] is True
