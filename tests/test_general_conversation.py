import pytest
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.domains.registry import DomainRegistry
from choice_agent.schemas import GenericDecisionRequest, GenericDecisionMessageRequest, DecisionCommandRequest
from choice_agent.decision.state_machine import DecisionRevisionError


def create(service, message="买电脑，预算 8000", domain="shopping", request_id="create"):
    return service.create(1, GenericDecisionRequest(message=message,domain=domain,request_id=request_id))


def message(service, result, text, request_id="message"):
    return service.message(1,result.decision_state.decision_id,GenericDecisionMessageRequest(message=text,request_id=request_id,expected_revision=result.decision_state.revision))


def command(service, result, type="update_fields", payload=None, identifier="edit"):
    return service.command(1,result.decision_state.decision_id,DecisionCommandRequest(type=type,payload=payload or {},command_id=identifier,expected_revision=result.decision_state.revision))


@pytest.mark.parametrize("text,domain,clarify",[("周末买耳机","shopping",False),("推荐一下","generic",False),("买票","generic",False),("从上海出发两天一夜","travel",False),("去杭州玩，吃什么","generic",True)])
def test_conservative_domain_resolution(text,domain,clarify):
    result=DomainRegistry().identify(text)
    assert result["domain"] == domain
    assert result["needsClarification"] == clarify


def test_budget_replace_clear_and_manual_constraint_survives(database):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db)
        first=create(service,"买电脑，预算 6000")
        assert not first.decision_state.candidates
        second=message(service,first,"改到 8000")
        assert len(second.decision_state.candidates)==2
        manual=command(service,second,"set_constraint",{"constraint":{"key":"performance","kind":"hard","operator":"gte","value":70,"source":"user"}})
        cleared=command(service,manual,payload={"fields":{"budget":None}},identifier="clear")
        follow=message(service,cleared,"帮我比较一下","follow")
        assert follow.decision_state.domain_state["conversationFields"]["budget"]["cleared"]
        assert not any(c.key=="price" for c in follow.decision_state.constraints)
        assert any(c.key=="performance" for c in follow.decision_state.constraints)
        assert len(follow.decision_state.candidates)==3


def test_priority_affects_weight_and_manual_override(database):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db);first=create(service)
        second=message(service,first,"更看重续航")
        assert next(c.weight for c in second.decision_state.criteria if c.key=="battery")==2
        manual=command(service,second,"set_criterion_weight",{"criterionKey":"battery","weight":0.5})
        follow=message(service,manual,"更看重续航","follow")
        assert next(c.weight for c in follow.decision_state.criteria if c.key=="battery")==0.5


def test_category_change_and_clear_required_field(database):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db);first=create(service)
        changed=command(service,first,payload={"fields":{"category":"headphones"}})
        assert all("耳机" in c.name for c in changed.decision_state.candidates)
        cleared=command(service,changed,payload={"fields":{"category":None}},identifier="clear")
        assert cleared.decision_state.status.value=="clarifying"
        assert cleared.display_blocks==[] and cleared.decision_state.recommendation is None
        follow=message(service,cleared,"帮我比较一下")
        assert follow.decision_state.status.value=="clarifying"


def test_qualitative_candidates_and_edit_without_invented_winner(database):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db)
        result=create(service,"A 离家近但薪资低，B 薪资高但通勤长","generic")
        assert len(result.decision_state.candidates)==2
        assert not result.decision_state.recommendation.primary_candidate_id
        assert all(not c.score_breakdown for c in result.decision_state.candidates)
        cid=result.decision_state.candidates[0].candidate_id
        edited=command(service,result,"update_candidate",{"candidateId":cid,"summary":"离家近，成长空间大"})
        assert "成长空间大" in edited.speech_text
        excluded=message(service,edited,"排除 A")
        assert cid in excluded.decision_state.excluded_candidates


def test_idempotency_collision_snapshots_and_owner(database):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db);first=create(service)
        assert create(service).trace_id==first.trace_id
        with pytest.raises(ValueError): create(service,"买耳机")
        second=message(service,first,"预算 9000")
        replay=message(service,first,"预算 9000")
        assert replay.trace_id==second.trace_id
        assert replay.decision_state.revision==2
        assert "conversationReceipts" not in replay.decision_state.domain_state
        latest=service.repository.get(first.decision_state.decision_id)
        assert len(latest.messages)==4
        assert len(latest.domain_state["conversationTurns"])==2
        with pytest.raises(ValueError): message(service,second,"预算 7000")
        with pytest.raises(KeyError): service.message(2,latest.decision_id,GenericDecisionMessageRequest(message="hello"))
        with pytest.raises(DecisionRevisionError): message(service,first,"预算 7000","other")


def test_command_retry_and_failure_rollback(database,monkeypatch):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db);first=create(service)
        edited=command(service,first,payload={"fields":{"budget":9000}})
        replay=command(service,first,payload={"fields":{"budget":9000}})
        assert replay.trace_id==edited.trace_id
        original=service.repository.save
        def fail(decision):
            original(decision)
            raise RuntimeError("simulated write failure")
        monkeypatch.setattr(service.repository,"save",fail)
        with pytest.raises(RuntimeError): message(service,edited,"预算 10000")
        stored=service.repository.get(first.decision_state.decision_id)
        assert stored.revision==2 and len(stored.messages)==4
        assert stored.domain_state["conversationFields"]["budget"]["value"]==9000


def test_travel_missing_context_and_budget_units(database):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db);first=create(service,"想出去旅行","travel")
        assert first.decision_state.status.value=="clarifying"
        ready=message(service,first,"从上海出发两天一夜，交通不超过 2 小时")
        assert ready.decision_state.status.value=="decided"
        assert all(c.attributes["travel_hours"]<=2 for c in ready.decision_state.candidates)
        assert ready.decision_state.domain_state["conversationFields"]["budget"]["value"] is None
        ambiguous=message(service,ready,"人均预算 1000","ambiguous")
        assert ambiguous.decision_state.status.value=="clarifying"
        assert not ambiguous.display_blocks


def test_model_suggestions_require_confirmation_and_cannot_restore_clear(database):
    class FakeModel:
        enabled=True
        def complete_json(self,**kwargs): return {"fields":{"budget":1000},"question":None}
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db,provider=FakeModel());first=create(service,"买电脑")
        inferred=message(service,first,"帮我考虑一下")
        assert not inferred.decision_state.domain_state["conversationFields"]["budget"]["confirmed"]
        assert len(inferred.decision_state.candidates)==3
        confirmed=command(service,inferred,"confirm_fields",{"fields":["budget"]})
        assert not confirmed.decision_state.candidates
        cleared=command(service,confirmed,payload={"fields":{"budget":None}},identifier="clear")
        follow=message(service,cleared,"帮我考虑一下","follow")
        assert follow.decision_state.domain_state["conversationFields"]["budget"]["value"] is None


def test_scene_suggestion_does_not_mutate_existing_domain(database):
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db);first=create(service)
        changed=message(service,first,"从上海出发两天一夜")
        assert changed.decision_state.domain=="shopping"
        assert changed.decision_state.domain_state["suggestedDomain"]["domain"]=="travel"
        assert changed.decision_state.domain_state["conversationFields"]["category"]["value"]=="laptop"


def test_concurrent_creation_has_one_receipt(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import select, func
    from choice_agent.db_models import DecisionRecord
    barrier = Barrier(2)
    def worker():
        with database.session_factory() as db:
            service=GenericDecisionOrchestrator(db)
            original=service._run
            def wait_then_run(*args, **kwargs):
                barrier.wait(timeout=10)
                return original(*args, **kwargs)
            service._run=wait_then_run
            return create(service)
    with ThreadPoolExecutor(max_workers=2) as pool:
        left,right=list(pool.map(lambda _:worker(),range(2)))
    assert left.trace_id==right.trace_id
    assert left.decision_state.decision_id==right.decision_state.decision_id
    with database.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(DecisionRecord))==1


def test_model_failure_is_visible_and_preserves_confirmed_fields(database):
    class FailingModel:
        enabled=True
        def complete_json(self,**kwargs): raise RuntimeError("unavailable")
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db,provider=FailingModel());first=create(service)
        result=message(service,first,"再帮我想想")
        assert result.decision_state.domain_state["conversationFields"]["budget"]["value"]==8000
        assert "模型理解不可用" in result.decision_state.domain_state["interpretationWarning"]
        assert len(result.decision_state.candidates)==2


def test_mixed_scene_clarifies_and_invalid_patch_is_atomic(database):
    from choice_agent.decision.conversation import patch_fields
    with database.session_factory() as db:
        service=GenericDecisionOrchestrator(db)
        mixed=create(service,"去杭州玩，吃什么",None)
        assert mixed.decision_state.status.value=="clarifying"
        assert "先聊" in mixed.speech_text
        first=create(service,request_id="shopping")
        with pytest.raises(ValueError): patch_fields(first.decision_state,{"budget":5000,"unknown":"bad"})
        assert first.decision_state.domain_state["conversationFields"]["budget"]["value"]==8000


def test_legacy_diet_session_keeps_id_and_hides_receipts(database):
    from choice_agent.orchestration.diet import DietOrchestrator
    from choice_agent.config import Settings
    from choice_agent.providers.model import DisabledProvider
    from choice_agent.schemas import ChatRequest
    with database.session_factory() as db:
        legacy=create(GenericDecisionOrchestrator(db),"晚餐想吃清淡一点","diet")
        diet=DietOrchestrator(db,Settings(),DisabledProvider())
        restored=diet.state(1,legacy.decision_state.session_id)
        assert restored["decisionState"]["decisionId"]==legacy.decision_state.decision_id
        assert "conversationReceipts" not in restored["decisionState"]["domainState"]
        next_turn=diet.chat(1,ChatRequest(session_id=legacy.decision_state.session_id,message="换一批",expected_revision=legacy.decision_state.revision,request_id="diet-turn"))
        assert next_turn.decision_state.decision_id==legacy.decision_state.decision_id
        assert "conversationReceipts" not in next_turn.decision_state.domain_state
