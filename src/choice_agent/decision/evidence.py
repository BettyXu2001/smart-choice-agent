from __future__ import annotations

from hashlib import sha256
from urllib.parse import urlparse

from choice_agent.schemas import Candidate, Evidence, EvidenceVerificationStatus, SourceDocument


class EvidenceValidator:
    def validate(
        self,
        candidates: list[Candidate],
        sources: list[SourceDocument],
    ) -> tuple[list[Candidate], list[Evidence], list[str]]:
        allowed_urls = {source.url for source in sources if source.kind == "web" and source.url}
        evidence: list[Evidence] = []
        warnings: list[str] = []
        validated: list[Candidate] = []
        for candidate in candidates:
            items: list[Evidence] = []
            for item in candidate.evidence:
                evidence_id = item.evidence_id or self._id(candidate.candidate_id, item)
                status = item.verification_status
                if candidate.origin in {"manual", "web", "unknown"}:
                    status = EvidenceVerificationStatus.UNVERIFIED
                if item.source_url:
                    parsed = urlparse(item.source_url)
                    valid_url = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
                    if not valid_url or item.source_url not in allowed_urls:
                        status = EvidenceVerificationStatus.REJECTED
                        warnings.append(f"候选 {candidate.candidate_id} 的来源未通过校验")
                    elif item.source_url in allowed_urls:
                        status = EvidenceVerificationStatus.VERIFIED
                normalized = item.model_copy(
                    update={
                        "evidence_id": evidence_id,
                        "candidate_id": candidate.candidate_id,
                        "criterion_key": item.criterion_key or item.key,
                        "claim": item.claim or f"{item.key}: {item.value}",
                        "verification_status": status,
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