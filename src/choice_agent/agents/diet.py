from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from choice_agent.agents.base import AgentContext, BaseAgent
from choice_agent.decision.engine import DecisionEngine, RankedMeal
from choice_agent.domains.diet.rules import (
    clarify, classify_intent, conservative_message, extract_slots, hard_exclusions, risk_reasons,
)
from choice_agent.providers.model import ModelProvider
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import (
    Constraint, ConstraintKind, DecisionStatus, Intent, MealResponse,
    Recommendation, SlotBundle, SourceMode,
)


PROMPT_DIR = Path(__file__).parents[1] / "prompts" / "diet"


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


class IntentAgent(BaseAgent):
    name = "IntentAgent"

    def __init__(self, provider: ModelProvider, model_name: str):
        self.provider = provider
        self.model_name = model_name

    def execute(self, context: AgentContext) -> dict[str, Any]:
        options = context.data["slot_options"]
        slots = extract_slots(context.message, options)
        intent, confidence = classify_intent(
            context.message, bool(context.data.get("last_recommendations"))
        )
        if self.provider.enabled:
            try:
                parsed = self.provider.complete_json(
                    _prompt("intent.txt"),
                    json.dumps({
                        "message": context.message,
                        "currentSlots": context.data.get("current_slots", {}),
                        "recentMessages": context.data.get("recent_messages", []),
                    }, ensure_ascii=False),
                    self.model_name,
                )
                intent = Intent(parsed.get("intent", intent.value))
                slots = slots.merged_with(SlotBundle.model_validate(parsed.get("slots", {})))
                confidence = float(parsed.get("confidence", confidence))
            except (ValueError, KeyError, TypeError):
                pass
        context.decision.intent = intent
        context.data["incoming_slots"] = slots
        return {"intent": intent.value, "slots": slots.model_dump(by_alias=True), "confidence": confidence}


class UnderstandingAgent(BaseAgent):
    name = "UnderstandingAgent"

    def execute(self, context: AgentContext) -> dict[str, Any]:
        current = SlotBundle.model_validate(context.data.get("current_slots", {}))
        incoming = context.data["incoming_slots"]
        merged = current.merged_with(incoming)
        banned = hard_exclusions(context.message, context.data["slot_options"])
        context.data["slots"] = merged
        context.data["hard_exclusions"] = banned
        context.decision.user_goal = context.message
        context.decision.criteria = list(DecisionEngine.criteria)
        context.decision.constraints = [
            Constraint(key="diet_exclusion", kind=ConstraintKind.HARD, values=banned)
        ] if banned else []
        for key, values in merged.model_dump().items():
            if values:
                context.decision.constraints.append(
                    Constraint(key=key, kind=ConstraintKind.SOFT, values=values)
                )
        context.decision.domain_state["slots"] = merged.model_dump(by_alias=True)
        return {
            "slots": merged.model_dump(by_alias=True),
            "hardExclusions": banned,
            "criteria": [item.model_dump(by_alias=True) for item in context.decision.criteria],
        }


class ClarificationAgent(BaseAgent):
    name = "ClarificationAgent"

    def execute(self, context: AgentContext) -> dict[str, Any]:
        action, question, missing = clarify(context.data["slots"])
        context.data["clarify_action"] = action
        context.data["clarify_question"] = question
        context.data["missing_slots"] = missing
        context.decision.clarifying_questions = [question] if question else []
        if question:
            context.decision.status = DecisionStatus.CLARIFYING
        return {"action": action.value, "questionToAsk": question, "missingSlots": missing}


class CandidateAgent(BaseAgent):
    name = "CandidateAgent"

    def __init__(self, repository: DietRepository, engine: DecisionEngine):
        self.repository = repository
        self.engine = engine

    def execute(self, context: AgentContext) -> dict[str, Any]:
        source = SourceMode(context.data["source_mode"])
        meals = self.repository.list_meals(source, context.user_id)
        ranked = self.engine.rank(
            meals, context.data["slots"], context.data.get("exclude_ids", []),
            context.data.get("hard_exclusions", []),
        )
        context.data["ranked"] = ranked
        context.decision.candidates = [self.engine.candidate(item) for item in ranked]
        context.decision.evidence = [
            evidence for candidate in context.decision.candidates for evidence in candidate.evidence
        ]
        context.decision.status = DecisionStatus.COMPARING
        return {
            "sourceMode": source.value,
            "candidateCount": len(ranked),
            "candidates": [
                {"id": item.meal.id, "name": item.meal.name, "score": item.score}
                for item in ranked
            ],
        }


class AdjustmentAgent(BaseAgent):
    name = "AdjustmentAgent"

    def execute(self, context: AgentContext) -> dict[str, Any]:
        excluded = list(dict.fromkeys(context.data.get("last_recommendations", [])))
        context.data["exclude_ids"] = excluded
        context.decision.excluded_candidates = [str(item) for item in excluded]
        return {"excludeMealIds": excluded}


class PlanningAgent(BaseAgent):
    name = "PlanningAgent"
    default_meal_times = ["早餐", "午餐", "晚餐"]

    def __init__(self, repository: DietRepository, engine: DecisionEngine):
        self.repository = repository
        self.engine = engine

    def execute(self, context: AgentContext) -> dict[str, Any]:
        slots: SlotBundle = context.data["slots"]
        requested = [value for value in slots.meal_time if value != "三餐"]
        meal_times = requested if len(requested) >= 2 else self.default_meal_times
        used: list[int] = []
        planned: list[tuple[str, RankedMeal | None]] = []
        source = SourceMode(context.data["source_mode"])
        meals = self.repository.list_meals(source, context.user_id)
        for meal_time in meal_times:
            query = slots.model_copy(update={"meal_time": [meal_time]})
            ranked = self.engine.rank(
                meals, query, [*context.data.get("exclude_ids", []), *used],
                context.data.get("hard_exclusions", []),
            )
            selected = ranked[0] if ranked else None
            if selected:
                used.append(selected.meal.id)
            planned.append((meal_time, selected))
        context.data["planned"] = planned
        context.data["ranked"] = [item for _, item in planned if item is not None]
        context.decision.candidates = [
            self.engine.candidate(item) for item in context.data["ranked"]
        ]
        context.decision.status = DecisionStatus.COMPARING
        return {
            "mealTimes": meal_times,
            "plannedMeals": [
                {"mealTime": meal_time, "mealId": item.meal.id if item else None}
                for meal_time, item in planned
            ],
        }


class CriticAgent(BaseAgent):
    name = "CriticAgent"

    def execute(self, context: AgentContext) -> dict[str, Any]:
        ranked: list[RankedMeal] = context.data.get("ranked", [])
        issues: list[str] = []
        ids = [item.meal.id for item in ranked]
        if len(ids) != len(set(ids)):
            issues.append("候选项存在重复")
        if any(item.score < 0 or item.score > 1 for item in ranked):
            issues.append("候选评分超出范围")
        if set(ids) & set(context.data.get("exclude_ids", [])):
            issues.append("候选包含明确排除项")
        context.data["critic_issues"] = issues
        return {"passed": not issues, "issues": issues}


def _meal_response(item: RankedMeal, reason: str) -> MealResponse:
    meal = item.meal
    return MealResponse(
        id=meal.id, source_type=SourceMode(meal.source_type), name=meal.name,
        meal_time=meal.meal_time, mood=meal.mood, scene=meal.scene,
        health_goal=meal.health_goal, cuisine=meal.cuisine, taste=meal.taste,
        convenience=meal.convenience, match_score=item.score, reason=reason,
    )


class ExplanationAgent(BaseAgent):
    name = "ExplanationAgent"

    def __init__(self, provider: ModelProvider, model_name: str):
        self.provider = provider
        self.model_name = model_name

    def _reason(self, item: RankedMeal, slots: SlotBundle) -> str:
        if slots.health_goal:
            return f"{item.meal.name}比较符合你提到的{'、'.join(slots.health_goal)}诉求。"
        if slots.taste:
            return f"{item.meal.name}比较贴近你想要的{'、'.join(slots.taste)}口味。"
        return f"{item.meal.name}和你这轮表达的就餐偏好匹配度较高。"

    def execute(self, context: AgentContext) -> dict[str, Any]:
        slots: SlotBundle = context.data["slots"]
        ranked: list[RankedMeal] = context.data.get("ranked", [])
        if not ranked:
            speech = "暂时没有找到很匹配的餐食，你可以先补充对应特征的餐食。"
            context.data["display_blocks"] = []
            context.data["speech_text"] = speech
            context.decision.recommendation = Recommendation(summary=speech)
            return {"speechText": speech, "recommendations": []}

        selected = ranked[:3]
        reasons = {item.meal.id: self._reason(item, slots) for item in selected}
        if self.provider.enabled:
            try:
                parsed = self.provider.complete_json(
                    _prompt("recommend-response.txt"),
                    json.dumps({
                        "message": context.message,
                        "slots": slots.model_dump(by_alias=True),
                        "candidates": [
                            {"id": item.meal.id, "name": item.meal.name, "score": item.score}
                            for item in selected
                        ],
                    }, ensure_ascii=False),
                    self.model_name,
                )
                for option in parsed.get("recommendations", []):
                    meal_id = int(option.get("mealId", option.get("itemId", 0)))
                    if meal_id in reasons and str(option.get("reason", "")).strip():
                        reasons[meal_id] = str(option["reason"]).strip()
            except (ValueError, KeyError, TypeError):
                pass
        blocks = [_meal_response(item, reasons[item.meal.id]) for item in selected]
        if context.decision.intent == Intent.MEAL_PLAN:
            lines = ["我为你安排了这几餐："]
            for meal_time, item in context.data.get("planned", []):
                lines.append(f"- {meal_time}：{item.meal.name if item else '暂时没有匹配项'}")
        else:
            lines = ["我优先给你推荐这几款："]
            lines.extend(f"- {block.name}：{block.reason}" for block in blocks)
        if any(value in {"减脂", "低糖", "控碳水", "养胃"} for value in slots.health_goal):
            lines.append("这些建议只做日常饮食参考，如有明确疾病或特殊身体情况，请咨询医生或营养师。")
        speech = "\n".join(lines)
        context.data["display_blocks"] = blocks
        context.data["speech_text"] = speech
        context.decision.recommendation = Recommendation(
            primary_candidate_id=str(selected[0].meal.id),
            alternative_candidate_ids=[str(item.meal.id) for item in selected[1:]],
            summary=speech,
            tradeoffs=[block.reason or "" for block in blocks],
        )
        context.decision.status = DecisionStatus.DECIDED
        return {
            "speechText": speech,
            "recommendations": [block.model_dump(by_alias=True) for block in blocks],
        }


class RiskAgent(BaseAgent):
    name = "RiskAgent"

    def execute(self, context: AgentContext) -> dict[str, Any]:
        reasons = risk_reasons(context.message, context.data.get("speech_text", ""))
        if context.decision.intent == Intent.HEALTH_RISK and "命中 HEALTH_RISK 意图" not in reasons:
            reasons.insert(0, "命中 HEALTH_RISK 意图")
        context.decision.risk_flags = reasons
        if reasons:
            context.data["speech_text"] = conservative_message()
            context.data["display_blocks"] = []
        return {
            "passed": not reasons,
            "reasons": reasons,
            "rewriteSuggestion": conservative_message() if reasons else None,
        }


class EvaluationAgent(BaseAgent):
    name = "EvaluationAgent"

    def __init__(
        self, provider: ModelProvider | None = None, model_name: str | None = None
    ):
        self.provider = provider
        self.model_name = model_name

    def execute(self, context: AgentContext) -> dict[str, Any]:
        trace = context.data["trace"]
        events = trace.get("events", [])
        actual_intent = None
        actual_clarify = None
        for event in events:
            if event.get("agentName") == "IntentAgent":
                actual_intent = (event.get("outputPayload") or {}).get("intent")
            if event.get("agentName") == "ClarificationAgent":
                actual_clarify = (event.get("outputPayload") or {}).get("action")
        expected_intent = context.data.get("expected_intent")
        expected_clarify = context.data.get("expected_clarify_action")
        intent_score = 1.0 if not expected_intent or expected_intent == actual_intent else 0.0
        clarify_score = 1.0 if not expected_clarify or expected_clarify == actual_clarify else 0.0
        safety = not any(
            event.get("status") == "FAILED"
            for event in events
            if event.get("eventType") == "AGENT_CALL"
        )
        score = round((intent_score + clarify_score + (1.0 if safety else 0.0)) / 3, 4)
        result = {
            "score": score,
            "intentAccuracy": intent_score,
            "clarifyAccuracy": clarify_score,
            "safetyCompliance": safety,
        }
        include_judge = bool(context.data.get("include_llm_judge"))
        if include_judge and self.provider and self.provider.enabled and self.model_name:
            try:
                judged = self.provider.complete_json(
                    _prompt("evaluation-judge.txt"),
                    json.dumps(trace, ensure_ascii=False),
                    self.model_name,
                )
                explanation = max(1.0, min(5.0, float(judged["explanationQuality"])))
                naturalness = max(1.0, min(5.0, float(judged["naturalness"])))
                result["llmJudge"] = {
                    "explanationQuality": explanation,
                    "naturalness": naturalness,
                    "reason": str(judged.get("reason", "")),
                    "score": round((explanation + naturalness) / 10, 4),
                }
            except (ValueError, KeyError, TypeError):
                result["llmJudge"] = None
        else:
            result["llmJudge"] = None
        return result
