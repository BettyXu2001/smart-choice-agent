"""Bounded what-if scenario helpers for conversation decisions."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def candidate_label(decision, candidate_id: str | None) -> str | None:
    if not candidate_id:
        return None
    pool = decision.domain_state.get("manualCandidates") or decision.domain_state.get("candidatePool", [])
    match = next((item for item in pool if item.get("candidateId") == candidate_id), None)
    if match:
        return match.get("name")
    match = next((item for item in decision.candidates if item.candidate_id == candidate_id), None)
    return match.name if match else candidate_id


def official_baseline(decision) -> dict[str, Any]:
    info = decision.domain_state.get("assistance", {})
    analysis = info.get("currentAnalysis") or info.get("analysis") or {}
    return {
        "primaryCandidateId": decision.recommendation.primary_candidate_id if decision.recommendation else analysis.get("primaryCandidateId"),
        "summary": decision.recommendation.summary if decision.recommendation else analysis.get("summary"),
        "fields": deepcopy(decision.domain_state.get("conversationFields", {})),
        "candidateState": {key: value.model_dump(mode="json") for key, value in decision.candidate_state.items()},
    }


def official_change(decision, baseline: dict[str, Any] | None, analysis: dict[str, Any]) -> dict[str, Any]:
    new_id = analysis.get("primaryCandidateId")
    if not baseline:
        return {
            "changed": bool(new_id),
            "from": None,
            "to": {"candidateId": new_id, "label": candidate_label(decision, new_id)} if new_id else None,
            "reason": "当前条件形成了这轮倾向。" if new_id else "当前信息仍不足以形成稳定倾向。",
            "evidence": analysis.get("changes", [])[:3],
        }
    old_id = baseline.get("primaryCandidateId")
    old_label = candidate_label(decision, old_id)
    new_label = candidate_label(decision, new_id)
    changes = [str(item) for item in analysis.get("changes", []) if item][:3]
    reason_head = "；".join(changes) if changes else "本轮补充信息"
    if old_id != new_id:
        if old_id and new_id:
            reason = f"{reason_head}，因此当前倾向从 {old_label} 转向 {new_label}。"
        elif new_id:
            reason = f"{reason_head}，因此当前形成了对 {new_label} 的倾向。"
        else:
            reason = f"{reason_head}，因此当前不再给出确定推荐。"
    else:
        reason = f"{reason_head}，当前倾向未变，但判断依据已更新。" if changes else "本轮没有改变当前倾向。"
    return {
        "changed": old_id != new_id,
        "from": {"candidateId": old_id, "label": old_label} if old_id else None,
        "to": {"candidateId": new_id, "label": new_label} if new_id else None,
        "reason": reason,
        "evidence": changes,
    }


def missing_info(decision, analysis: dict[str, Any]) -> list[str]:
    question = analysis.get("question")
    items: list[str] = [question] if question else []
    if decision.domain == "generic":
        facts = decision.domain_state.get("assistance", {}).get("facts", [])
        commute_known = {fact.get("candidateId") for fact in facts if fact.get("kind") == "commute"}
        salary_known = {fact.get("candidateId") for fact in facts if fact.get("kind") == "salary"}
        pool = decision.domain_state.get("manualCandidates") or decision.domain_state.get("candidatePool", [])
        if len(pool) >= 2 and 0 < len(commute_known) < len(pool):
            items.append("仍缺少部分候选的通勤时间，若通勤是硬条件，结论可能变化。")
        if len(pool) >= 2 and 0 < len(salary_known) < len(pool):
            items.append("仍缺少部分候选的薪资信息，若薪资权重提高，结论可能变化。")
        if not any("工作强度" in str(fact.get("text", "")) or "加班" in str(fact.get("text", "")) for fact in facts):
            items.append("当前仍缺少实际工作强度信息，如果这一点很重要，结论可能发生变化。")
    return list(dict.fromkeys(item for item in items if item))[:3]


def scenarios(decision, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    current = decision.domain_state.get("conversationFields", {})
    priority = str(current.get("priority", {}).get("value") or "")
    primary = analysis.get("primaryCandidateId")
    result: list[dict[str, Any]] = []
    pool = decision.domain_state.get("manualCandidates") or decision.domain_state.get("candidatePool", [])
    others = [item for item in pool if item.get("candidateId") != primary]
    if priority and others:
        if "稳定" in priority:
            prompt = "假设我把成长机会放在稳定性之前"
            label = "如果你把成长机会放在稳定性之前，其他候选可能更占优势。"
        elif any(word in priority for word in ["成长", "方向", "匹配"]):
            prompt = "假设我把稳定性放在成长机会之前"
            label = "如果你把稳定性放在成长机会之前，当前推荐可能重新平衡。"
        else:
            prompt = f"假设我不再优先考虑{priority}"
            label = f"如果你不再优先考虑{priority}，当前排序可能变化。"
        result.append({"id": "priority-shift", "label": label, "prompt": prompt, "impact": "可能改变当前建议"})
    commute = current.get("maxCommuteMinutes", {}).get("value")
    if commute:
        result.append({
            "id": "commute-relaxed",
            "label": f"如果通勤上限放宽到 {int(commute * 2)} 分钟，被通勤排除的候选可能重新进入比较。",
            "prompt": f"假设我可以接受每天通勤 {int(commute * 2)} 分钟",
            "impact": "会改变候选风险",
        })
    else:
        commute_facts = [fact for fact in decision.domain_state.get("assistance", {}).get("facts", []) if fact.get("kind") == "commute"]
        if commute_facts:
            result.append({
                "id": "commute-limit",
                "label": "如果你设置明确通勤上限，通勤较远的候选可能被排除。",
                "prompt": "假设我每天最多接受 1 小时通勤",
                "impact": "可能改变当前建议",
            })
    if decision.domain == "shopping" and current.get("budget", {}).get("value"):
        budget = current["budget"]["value"]
        result.append({
            "id": "budget-relaxed",
            "label": f"如果预算提高到 {int(budget * 1.25)} 元，高价候选可能重新进入比较。",
            "prompt": f"假设我的预算提高到 {int(budget * 1.25)} 元",
            "impact": "会改变候选范围",
        })
    if decision.domain == "travel" and current.get("maxTransitHours", {}).get("value"):
        hours = current["maxTransitHours"]["value"]
        result.append({
            "id": "transit-relaxed",
            "label": f"如果交通时间上限放宽到 {hours * 1.5:g} 小时，更多目的地会进入比较。",
            "prompt": f"假设我可以接受 {hours * 1.5:g} 小时交通",
            "impact": "会改变候选范围",
        })
    return result[:3]