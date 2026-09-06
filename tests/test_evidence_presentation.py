import json

from choice_agent.decision.commands import apply_command
from choice_agent.decision.evidence import EvidenceValidator
from choice_agent.orchestration.generic import GenericDecisionOrchestrator
from choice_agent.providers.search import OpenAIWebSearchProvider
from choice_agent.schemas import (
    Candidate,
    DecisionCommandRequest,
    DecisionState,
    Evidence,
    GenericDecisionMessageRequest,
    GenericDecisionRequest,
    SourceDocument,
)
from choice_agent.agents.base import AgentContext


def start(service, text, domain="generic"):
    return service.create(
        1,
        GenericDecisionRequest(
            message=text,
            domain=domain,
            context={"demoMode": True, "searchMode": "fixture"},
        ),
    )


def say(service, result, text):
    return service.message(
        1,
        result.decision_state.decision_id,
        GenericDecisionMessageRequest(
            message=text,
            expected_revision=result.decision_state.revision,
        ),
    )


def test_recommendation_reasons_resolve_to_evidence_snapshot(database):
    text = "比较两个 Offer\n以下为演示候选：\nA 公司：成长空间更大，但业务阶段较早；B 公司：平台成熟、薪酬稳定，岗位更传统。"
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        result = say(service, start(service, text), "更看重稳定")
        analysis = result.decision_state.domain_state["assistance"]["analysis"]
        evidence_ids = {item.evidence_id for item in result.decision_state.evidence}

        assert analysis["reasons"]
        assert all(item["evidenceIds"] for item in analysis["reasons"])
        assert all(evidence_id in evidence_ids for item in analysis["reasons"] for evidence_id in item["evidenceIds"])
        first_source = analysis["sources"][analysis["reasons"][0]["evidenceIds"][0]]["evidence"]
        assert first_source["sourceKind"] == "fixture"
        assert first_source["claimStatus"] == "not_applicable"
        assert "演示数据" in first_source["verificationNote"]
        assert result.decision_state.recommendation.reasons[0].evidence_ids == analysis["reasons"][0]["evidenceIds"]
        assert result.decision_state.domain_state["conversationTurns"][-1]["analysis"]["sources"]


def test_numeric_comparison_references_both_candidates(database):
    with database.session_factory() as db:
        service = GenericDecisionOrchestrator(db)
        result = service.create(
            1,
            GenericDecisionRequest(
                message="买电脑，预算 9000",
                domain="shopping",
                context={"demoMode": True, "searchMode": "fixture"},
            ),
        )
        reason = result.decision_state.recommendation.reasons[0]
        assert len(reason.evidence_ids) >= 2
        candidates = {
            result.decision_state.domain_state["assistance"]["analysis"]["sources"][evidence_id]["candidateId"]
            for evidence_id in reason.evidence_ids
        }
        assert len(candidates) >= 2
        assert result.decision_state.recommendation.tradeoff_details


def test_web_source_match_is_not_claim_verification():
    payload = {
        "id": "resp-1",
        "output_text": json.dumps({
            "candidates": [{
                "id": "hotel-a",
                "name": "Hotel A",
                "summary": "周末可订",
                "attributes": {"price": 1000},
                "evidence": [{
                    "key": "price",
                    "value": 1000,
                    "claim": "周末价格约 1000",
                    "sourceTitle": "Hotel Site",
                    "sourceUrl": "https://hotel.example/a",
                }],
            }]
        }),
        "output": [{"content": [{"type": "output_text", "text": "", "annotations": [
            {"type": "url_citation", "url": "https://hotel.example/a", "title": "Hotel Site"}
        ]}]}],
    }

    provider = OpenAIWebSearchProvider(
        "key", "https://api.openai.com/v1", "gpt-test", transport=lambda request, timeout: payload
    )
    decision = DecisionState(decision_id="d", session_id="s", domain="travel", user_goal="订酒店")
    result = provider.search(AgentContext("s", "t", 1, "订酒店", decision, {}))
    _, evidence, warnings = EvidenceValidator().validate(result.candidates, result.sources)

    assert not warnings
    assert evidence[0].verification_status.value == "verified"
    assert evidence[0].citation_status.value == "matched"
    assert evidence[0].claim_status.value == "unverified"
    assert "内容未独立核实" in evidence[0].verification_note
    assert evidence[0].retrieved_at is not None


def test_manual_candidate_cannot_supply_trusted_evidence_metadata():
    decision = DecisionState(decision_id="d", session_id="s", domain="generic", user_goal="选方案")
    request = DecisionCommandRequest(
        command_id="manual",
        type="add_candidate",
        expected_revision=0,
        payload={
            "candidate": {
                "candidateId": "manual:a",
                "name": "A",
                "summary": "我觉得稳定",
                "evidence": [{
                    "evidenceId": "trusted",
                    "key": "summary",
                    "value": "我觉得稳定",
                    "sourceTitle": "Official",
                    "verificationStatus": "verified",
                    "sourceKind": "web",
                    "citationStatus": "matched",
                    "claimStatus": "verified",
                    "supportingEvidenceIds": ["external"],
                }],
            }
        },
    )

    apply_command(decision, request)
    candidate = Candidate.model_validate(decision.domain_state["manualCandidates"][0])
    evidence = candidate.evidence[0]
    assert evidence.evidence_id is None
    assert evidence.verification_status.value == "unverified"
    assert evidence.source_kind == "user"
    assert evidence.statement_kind == "subjective_judgment"
    assert evidence.citation_status.value == "not_applicable"
    assert evidence.claim_status.value == "unverified"
    assert evidence.supporting_evidence_ids == []


def test_invalid_web_url_is_rejected_and_not_matched():
    candidate = Candidate(
        candidate_id="a",
        name="A",
        origin="web",
        evidence=[Evidence(key="price", value=100, source_title="Bad", source_url="javascript:alert(1)")],
    )
    _, evidence, warnings = EvidenceValidator().validate(
        [candidate],
        [SourceDocument(source_id="web:1", title="Allowed", url="https://allowed.example", kind="web")],
    )
    assert warnings
    assert evidence[0].verification_status.value == "rejected"
    assert evidence[0].citation_status.value == "rejected"
    assert evidence[0].claim_status.value == "unverified"
