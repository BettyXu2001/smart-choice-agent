from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from uuid import uuid4

from choice_agent.schemas import Candidate, Constraint, DecisionCommandRequest, EvidenceVerificationStatus


@dataclass(frozen=True)
class CommandMutation:
    mode: str
    message: str | None = None


def apply_command(decision, request: DecisionCommandRequest) -> CommandMutation:
    payload = request.payload
    command_type = request.type
    if command_type in {"update_fields", "confirm_fields"}:
        from choice_agent.decision.conversation import fields, patch_fields
        if decision.domain == "diet": raise ValueError("饮食条件请使用饮食会话接口")
        patch = payload.get("fields", {})
        if command_type == "confirm_fields":
            current = fields(decision)
            if not isinstance(patch, list) or any(k not in current for k in patch): raise ValueError("确认条件需要已知字段列表")
            patch = {k: current[k]["value"] for k in patch}
        patch_fields(decision, patch)
        return CommandMutation("refresh")
    if command_type == "update_candidate":
        identifier = payload.get("candidateId")
        existing = next((c for c in decision.domain_state.get("manualCandidates", []) if c["candidateId"] == identifier), None)
        if existing is None: raise ValueError("只能编辑自己提供的候选")
        allowed = {k: v for k, v in payload.items() if k in {"name", "summary", "attributes"}}
        payload = {"candidate": {**existing, **allowed}}
        command_type = "add_candidate"
    if command_type == "answer_question":
        answer = payload.get("answer")
        answer = answer.strip() if isinstance(answer, str) else ""
        if not answer:
            raise ValueError("answer_question 需要非空 answer")
        return CommandMutation("full", answer)

    if command_type == "set_constraint":
        raw = payload.get("constraint", payload)
        constraint = Constraint.model_validate(raw)
        if constraint.operator not in {"contains_any", "contains_all", "not_contains", "eq", "ne", "lt", "lte", "gt", "gte"}:
            raise ValueError("不支持的约束 operator")
        if not constraint.constraint_id:
            constraint.constraint_id = f"constraint:{request.command_id}"
        decision.constraints = [
            item for item in decision.constraints
            if item.constraint_id != constraint.constraint_id and item.key != constraint.key
        ] + [constraint]
        return CommandMutation("refresh")

    if command_type == "remove_constraint":
        identifier = str(payload.get("constraintId") or payload.get("key") or "").strip()
        if not identifier:
            raise ValueError("remove_constraint 需要 constraintId 或 key")
        decision.constraints = [
            item for item in decision.constraints
            if item.constraint_id != identifier and item.key != identifier
        ]
        return CommandMutation("refresh")

    if command_type == "set_criterion_weight":
        key = str(payload.get("criterionKey", "")).strip()
        if not key:
            raise ValueError("set_criterion_weight 需要 criterionKey")
        try:
            weight = float(payload["weight"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("weight 必须是非负数") from error
        if not isfinite(weight) or weight < 0:
            raise ValueError("weight 必须是非负数")
        found = False
        for criterion in decision.criteria:
            if criterion.key == key:
                criterion.weight = weight
                found = True
        if not found:
            raise ValueError(f"未知 criterion：{key}")
        decision.domain_state.setdefault("manualWeights", {})[key] = weight
        return CommandMutation("rank")

    if command_type == "add_candidate":
        if decision.domain == "diet":
            raise ValueError("请通过个人餐食库添加餐食后刷新候选")
        raw = dict(payload.get("candidate", payload))
        raw.setdefault("candidateId", f"manual:{uuid4().hex}")
        raw["origin"] = "manual"
        if not str(raw.get("name", "")).strip():
            raise ValueError("候选名称不能为空")
        candidate_id = str(raw["candidateId"])
        if any(item.get("candidateId") == candidate_id and item.get("origin") != "manual"
               for item in decision.domain_state.get("candidatePool", [])):
            raise ValueError("不能覆盖外部候选 ID")
        candidate = Candidate.model_validate(raw)
        candidate.score = 0
        candidate.score_breakdown = []
        for item in candidate.evidence:
            item.verification_status = EvidenceVerificationStatus.UNVERIFIED
        candidate.evidence_ids = []
        manual = decision.domain_state.setdefault("manualCandidates", [])
        manual[:] = [item for item in manual if item.get("candidateId") != candidate.candidate_id]
        manual.append(candidate.model_dump(mode="json", by_alias=True))
        pool = decision.domain_state.setdefault("candidatePool", [])
        pool[:] = [item for item in pool if item.get("candidateId") != candidate.candidate_id]
        pool.append(candidate.model_dump(mode="json", by_alias=True))
        return CommandMutation("rank")

    if command_type in {"exclude_candidate", "restore_candidate"}:
        candidate_id = str(payload.get("candidateId", "")).strip()
        if not candidate_id:
            raise ValueError(f"{command_type} 需要 candidateId")
        excluded = set(decision.excluded_candidates)
        if command_type == "exclude_candidate":
            excluded.add(candidate_id)
        else:
            excluded.discard(candidate_id)
        decision.excluded_candidates = sorted(excluded)
        return CommandMutation("rank")

    if command_type == "refresh_candidates":
        return CommandMutation("refresh")
    if command_type == "generate_recommendation":
        return CommandMutation("rank")
    raise ValueError(f"不支持的 command：{command_type}")