from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from choice_agent.agents.base import AgentContext, BaseAgent
from choice_agent.decision.engine import DecisionEngine, RankedMeal
from choice_agent.decision.selector import SelectionCandidate, select_candidates
from choice_agent.decision.state_machine import transition_decision
from choice_agent.domains.diet.rules import (
    clarify, classify_intent, conservative_message, extract_slots, hard_exclusions, risk_reasons,
)
from choice_agent.providers.model import ModelProvider
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import (
    CandidateState, Constraint, ConstraintKind, DecisionNextAction, DecisionStatus,
    Intent, MealResponse, Recommendation, SlotBundle, SourceMode, UnansweredQuestion,
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
        context.decision.unanswered_questions = [
            UnansweredQuestion(key=key, question=question, asked_by=self.name)
            for key in missing
        ] if question else []
        if question:
            transition_decision(
                context.decision, DecisionStatus.CLARIFYING, DecisionNextAction.ASK_CLARIFY
            )
        else:
            context.decision.next_action = DecisionNextAction.SEARCH_CANDIDATES
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
        selection = select_candidates(
            [
                SelectionCandidate(
                    candidate_id=str(item.meal.id),
                    name=item.meal.name,
                    score=item.score,
                    attributes={"sourceMode": item.meal.source_type},
                )
                for item in ranked
            ],
            context.data.get("selection_strategy", "ranked"),
            context.data.get("recent_recommendation_ids", []),
            context.data.get("avoid_recent_count", 0),
        )
        ranked_by_id = {str(item.meal.id): item for item in ranked}
        ranked = [ranked_by_id[item_id] for item_id in selection.ordered_ids]
        context.data["ranked"] = ranked
        context.decision.domain_state["selection"] = selection.insights.as_dict()
        context.decision.candidates = [self.engine.candidate(item) for item in ranked]
        context.decision.candidate_state = {
            candidate.candidate_id: CandidateState(status="active", updated_by=self.name)
            for candidate in context.decision.candidates
        }
        context.decision.evidence = [
            evidence for candidate in context.decision.candidates for evidence in candidate.evidence
        ]
        transition_decision(
            context.decision, DecisionStatus.COMPARING, DecisionNextAction.COMPARE_CANDIDATES
        )
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
        context.decision.candidate_state = {
            candidate.candidate_id: CandidateState(status="active", updated_by=self.name)
            for candidate in context.decision.candidates
        }
        transition_decision(
            context.decision, DecisionStatus.COMPARING, DecisionNextAction.COMPARE_CANDIDATES
        )
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
            transition_decision(
                context.decision, DecisionStatus.DECIDED, DecisionNextAction.WAIT_USER
            )
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
        transition_decision(
            context.decision, DecisionStatus.DECIDED, DecisionNextAction.WAIT_USER
        )
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
            transition_decision(
                context.decision, DecisionStatus.DECIDED, DecisionNextAction.WAIT_USER
            )
        return {
            "passed": not reasons,
            "reasons": reasons,
            "rewriteSuggestion": conservative_message() if reasons else None,
        }


class EvaluationAgent(BaseAgent):
    name = "EvaluationAgent"
    rule_score_keys = (
        "intentAccuracy",
        "slotAccuracy",
        "clarifyNecessityAccuracy",
        "tokenCostScore",
        "latencyScore",
        "fallbackScore",
        "safetyCompliance",
        "hallucinationControl",
        "multiTurnConsistency",
    )

    def __init__(
        self, provider: ModelProvider | None = None, model_name: str | None = None
    ):
        self.provider = provider
        self.model_name = model_name

    def execute(self, context: AgentContext) -> dict[str, Any]:
        trace = context.data["trace"]
        snapshot = self._snapshot(trace)
        expected_intent = context.data.get("expected_intent")
        expected_slots = context.data.get("expected_slots") or {}
        expected_clarify = context.data.get("expected_clarify_action")
        feedbacks = context.data.get("feedbacks", [])

        metrics: dict[str, Any] = {
            "intentAccuracy": self._exact_score(expected_intent, snapshot["intent"]),
            "slotAccuracy": self._slot_accuracy(expected_slots, snapshot["slots"]),
            "clarifyNecessityAccuracy": self._exact_score(expected_clarify, snapshot["clarify_action"]),
            "clarifyAccuracy": self._exact_score(expected_clarify, snapshot["clarify_action"]),
            "tokenCost": snapshot["token_cost"],
            "tokenCostScore": self._cost_score(snapshot["token_cost"]),
            "latencyMs": snapshot["latency_ms"],
            "latencyScore": self._latency_score(snapshot["latency_ms"]),
            "fallbackRate": 1.0 if snapshot["fallback_used"] else 0.0,
            "fallbackScore": 0.0 if snapshot["fallback_used"] else 1.0,
            "safetyCompliance": 0.0 if snapshot["fallback_used"] else 1.0,
            "hallucinationControl": self._hallucination_control(
                snapshot["ranked_ids"], snapshot["response_ids"]
            ),
            "multiTurnConsistency": self._multi_turn_consistency(
                snapshot["excluded_ids"], snapshot["response_ids"]
            ),
        }
        metrics["score"] = self._rule_score(metrics)
        metrics["evaluationDetail"] = {
            "predictedIntent": snapshot["intent"],
            "predictedSlots": snapshot["slots"],
            "predictedClarifyAction": snapshot["clarify_action"],
            "expectedIntent": expected_intent,
            "expectedSlots": expected_slots,
            "expectedClarifyAction": expected_clarify,
            "feedbackCount": len(feedbacks),
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
                metrics["llmJudge"] = {
                    "explanationQuality": explanation,
                    "naturalness": naturalness,
                    "reason": str(judged.get("reason", "")),
                    "score": round((explanation + naturalness) / 10, 4),
                }
            except (ValueError, KeyError, TypeError) as exc:
                metrics["llmJudge"] = {"score": None, "error": str(exc)}
        else:
            metrics["llmJudge"] = None
        return metrics

    def _snapshot(self, trace: dict[str, Any]) -> dict[str, Any]:
        events = trace.get("events", [])
        actual_intent = None
        actual_slots: dict[str, Any] = {}
        actual_clarify = None
        token_cost = 0
        has_token = False
        latency_ms = 0
        has_latency = False
        fallback_used = str(trace.get("status", "")).upper() == "FAILED"
        ranked_ids: set[str] = set()
        response_ids: set[str] = set()
        excluded_ids: set[str] = set()

        for event in events:
            output = event.get("outputPayload") or {}
            input_payload = event.get("inputPayload") or {}
            output = output if isinstance(output, dict) else {}
            input_payload = input_payload if isinstance(input_payload, dict) else {}
            agent_name = event.get("agentName")
            event_type = str(event.get("eventType", ""))
            status = str(event.get("status", ""))

            if event_type == "AGENT_CALL":
                latency = event.get("latencyMs") or event.get("latency_ms")
                if isinstance(latency, (int, float)):
                    latency_ms += int(latency)
                    has_latency = True
                tokens = self._token_count(event)
                if tokens is not None:
                    token_cost += tokens
                    has_token = True
            if status.upper() == "FAILED" or "FAILED" in event_type.upper():
                fallback_used = True
            if event.get("errorMessage") or event.get("error_message"):
                fallback_used = True

            if agent_name == "IntentAgent":
                actual_intent = output.get("intent")
                actual_slots = self._merge_slots(actual_slots, output.get("slots") or {})
            elif agent_name == "UnderstandingAgent":
                actual_slots = self._merge_slots(actual_slots, output.get("slots") or {})
            elif agent_name == "ClarificationAgent":
                actual_clarify = output.get("action")
            elif agent_name == "AdjustmentAgent":
                excluded_ids.update(self._ids(output.get("excludeMealIds")))
            elif agent_name == "CandidateAgent":
                ranked_ids.update(self._ids(output.get("candidates")))
            elif agent_name == "PlanningAgent":
                ranked_ids.update(self._ids(output.get("plannedMeals")))
            elif agent_name == "ExplanationAgent":
                response_ids.update(self._ids(output.get("recommendations")))

            excluded_ids.update(self._ids(input_payload.get("excludeIds")))
            excluded_ids.update(self._ids(input_payload.get("exclude_ids")))

        return {
            "intent": actual_intent,
            "slots": actual_slots,
            "clarify_action": actual_clarify,
            "token_cost": token_cost if has_token else None,
            "latency_ms": latency_ms if has_latency else trace.get("durationMs"),
            "fallback_used": fallback_used,
            "ranked_ids": ranked_ids,
            "response_ids": response_ids,
            "excluded_ids": excluded_ids,
        }

    def _token_count(self, event: dict[str, Any]) -> int | None:
        for key in ("totalTokens", "total_tokens", "tokenCost", "token_cost"):
            value = event.get(key)
            if isinstance(value, (int, float)):
                return int(value)
        usage = event.get("usage") or {}
        for key in ("totalTokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, (int, float)):
                return int(value)
        return None

    def _ids(self, value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, dict):
            for key in ("id", "mealId", "itemId", "candidateId"):
                if value.get(key) is not None:
                    return {str(value[key])}
            result: set[str] = set()
            for item in value.values():
                result.update(self._ids(item))
            return result
        if isinstance(value, list):
            result: set[str] = set()
            for item in value:
                result.update(self._ids(item))
            return result
        if isinstance(value, (int, str)):
            return {str(value)}
        return set()

    def _merge_slots(self, current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = {key: list(value) if isinstance(value, list) else value for key, value in current.items()}
        for key, value in incoming.items():
            if isinstance(value, list):
                existing = merged.get(key, [])
                existing_values = existing if isinstance(existing, list) else [existing]
                merged[key] = list(dict.fromkeys([*existing_values, *value]))
            elif value:
                merged[key] = value
        return merged

    def _exact_score(self, expected: Any, actual: Any) -> float:
        return 1.0 if not expected or expected == actual else 0.0

    def _slot_accuracy(self, expected: dict[str, Any], actual: dict[str, Any]) -> float:
        checks = []
        for key, expected_value in expected.items():
            expected_values = self._value_set(expected_value)
            if not expected_values:
                continue
            actual_values = self._value_set(actual.get(key))
            checks.append(1.0 if expected_values.issubset(actual_values) else 0.0)
        if not checks:
            return 1.0
        return round(sum(checks) / len(checks), 4)

    def _value_set(self, value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, list):
            return {str(item) for item in value if item not in (None, "")}
        if value == "":
            return set()
        return {str(value)}

    def _cost_score(self, token_cost: int | None) -> float:
        if token_cost is None or token_cost <= 1000:
            return 1.0
        if token_cost >= 3000:
            return 0.0
        return round((3000.0 - token_cost) / 2000.0, 4)

    def _latency_score(self, latency_ms: int | None) -> float:
        if latency_ms is None or latency_ms <= 1000:
            return 1.0
        if latency_ms >= 5000:
            return 0.0
        return round((5000.0 - latency_ms) / 4000.0, 4)

    def _hallucination_control(self, ranked_ids: set[str], response_ids: set[str]) -> float:
        if not ranked_ids or not response_ids:
            return 1.0
        return 1.0 if response_ids.issubset(ranked_ids) else 0.0

    def _multi_turn_consistency(self, excluded_ids: set[str], response_ids: set[str]) -> float | None:
        if not excluded_ids or not response_ids:
            return None
        return 0.0 if excluded_ids & response_ids else 1.0

    def _rule_score(self, metrics: dict[str, Any]) -> float:
        values = [
            float(metrics[key])
            for key in self.rule_score_keys
            if isinstance(metrics.get(key), (int, float))
        ]
        if not values:
            return 1.0
        return round(sum(values) / len(values), 4)
