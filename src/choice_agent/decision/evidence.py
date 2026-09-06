from __future__ import annotations

from hashlib import sha256
from urllib.parse import urlparse

from choice_agent.schemas import (
    Candidate,
    DecisionState,
    Evidence,
    EvidenceCitationStatus,
    EvidenceClaimStatus,
    EvidenceVerificationStatus,
    SourceDocument,
)


def source_kind_for_origin(origin: str | None) -> str:
    return {
        "manual": "user",
        "conversation": "user",
        "demo": "fixture",
        "fixture": "fixture",
        "database": "database",
        "web": "web",
        "model": "system",
        "system": "system",
    }.get(str(origin or "unknown"), "unknown")


def is_scoring_evidence(item: Evidence, criterion_key: str, value: object | None = None) -> bool:
    if item.verification_status == EvidenceVerificationStatus.REJECTED:
        return False
    if (item.criterion_key or item.key) != criterion_key:
        return False
    if value is not None and item.value != value:
        return False
    if item.source_kind == "web":
        return (
            item.verification_status == EvidenceVerificationStatus.VERIFIED
            and item.citation_status == EvidenceCitationStatus.MATCHED
        )
    return item.source_kind in {"user", "fixture", "database", "system", "unknown"}


class EvidenceValidator:
    def validate(
        self,
        candidates: list[Candidate],
        sources: list[SourceDocument],
    ) -> tuple[list[Candidate], list[Evidence], list[str]]:
        by_url = {source.url: source for source in sources if source.kind == "web" and source.url}
        allowed_urls = set(by_url)
        evidence: list[Evidence] = []
        warnings: list[str] = []
        validated: list[Candidate] = []
        for candidate in candidates:
            items: list[Evidence] = []
            for item in candidate.evidence:
                evidence_id = item.evidence_id or self._id(candidate.candidate_id, item)
                source_kind = item.source_kind
                if source_kind == "unknown":
                    source_kind = source_kind_for_origin(candidate.origin)
                status = item.verification_status
                citation_status = item.citation_status
                claim_status = item.claim_status
                verification_note = item.verification_note
                if candidate.origin in {"manual", "web", "unknown"}:
                    status = EvidenceVerificationStatus.UNVERIFIED
                    claim_status = EvidenceClaimStatus.UNVERIFIED
                    verification_note = verification_note or "内容尚未经过独立事实核验"
                if item.source_url:
                    parsed = urlparse(item.source_url)
                    valid_url = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
                    if not valid_url or item.source_url not in allowed_urls:
                        status = EvidenceVerificationStatus.REJECTED
                        citation_status = EvidenceCitationStatus.REJECTED
                        claim_status = EvidenceClaimStatus.UNVERIFIED
                        verification_note = "来源链接未通过工具结果校验"
                        warnings.append(f"候选 {candidate.candidate_id} 的来源未通过校验")
                    elif item.source_url in allowed_urls:
                        status = EvidenceVerificationStatus.VERIFIED
                        citation_status = EvidenceCitationStatus.MATCHED
                        claim_status = EvidenceClaimStatus.UNVERIFIED
                        verification_note = "来源链接已校验，内容未独立核实"
                elif source_kind in {"user", "system", "fixture", "database"}:
                    citation_status = EvidenceCitationStatus.NOT_APPLICABLE
                    if source_kind in {"fixture", "database"} and status == EvidenceVerificationStatus.VERIFIED:
                        claim_status = EvidenceClaimStatus.NOT_APPLICABLE
                        verification_note = verification_note or "项目内置资料，未代表外部事实核验"
                    else:
                        claim_status = EvidenceClaimStatus.UNVERIFIED if source_kind == "user" else EvidenceClaimStatus.NOT_APPLICABLE
                        verification_note = verification_note or (
                            "用户输入，未外部核实" if source_kind == "user" else "系统推断，需查看其支撑依据"
                        )
                source = by_url.get(item.source_url or "")
                normalized = item.model_copy(
                    update={
                        "evidence_id": evidence_id,
                        "candidate_id": candidate.candidate_id,
                        "criterion_key": item.criterion_key or item.key,
                        "claim": item.claim or f"{item.key}: {item.value}",
                        "verification_status": status,
                        "source_kind": source_kind,
                        "statement_kind": item.statement_kind if item.statement_kind != "unknown" else "reported_fact",
                        "citation_status": citation_status,
                        "claim_status": claim_status,
                        "verification_note": verification_note,
                        "source_id": item.source_id or (source.source_id if source else None),
                        "publisher": item.publisher or (source.publisher if source else None),
                        "source_quote": item.source_quote or (item.claim or f"{item.key}: {item.value}"),
                    }
                )
                items.append(normalized)
                evidence.append(normalized)
            validated.append(
                candidate.model_copy(
                    update={
                        "evidence": items,
                        "evidence_ids": [item.evidence_id for item in items if item.evidence_id],
                    }
                )
            )
        return validated, evidence, list(dict.fromkeys(warnings))

    def _id(self, candidate_id: str, evidence: Evidence) -> str:
        raw = f"{candidate_id}|{evidence.key}|{evidence.value}|{evidence.source_title}|{evidence.source_url or ''}"
        return sha256(raw.encode("utf-8")).hexdigest()[:24]


def sync_decision_evidence(decision: DecisionState) -> list[Evidence]:
    merged: dict[str, Evidence] = {}
    for item in decision.evidence:
        if item.evidence_id:
            merged[item.evidence_id] = item
    for candidate in decision.candidates:
        for item in candidate.evidence:
            if item.evidence_id:
                merged[item.evidence_id] = item
    decision.evidence = list(merged.values())
    return decision.evidence
