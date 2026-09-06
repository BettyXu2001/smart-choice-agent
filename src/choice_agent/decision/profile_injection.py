from __future__ import annotations

from typing import Any

from choice_agent.schemas import Assumption, UserProfile


PROFILE_SOURCE = "user_profile"


def _clean_text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _clean_list(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))


def _preference_text(*parts: Any) -> str | None:
    values: list[str] = []
    for part in parts:
        if isinstance(part, str):
            text = _clean_text(part)
            if text:
                values.append(text)
        elif isinstance(part, list):
            values.extend(_clean_list([str(item) for item in part]))
    return "；".join(dict.fromkeys(values)) or None


def profile_suggestions_for_domain(profile: UserProfile, domain: str) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    budget = _clean_text(profile.budget_habit)
    cities = _clean_list(profile.preferred_cities)
    diet = _clean_list(profile.diet_preferences)
    notes = _clean_text(profile.notes)

    def add(identifier: str, label: str, value: Any, field_key: str | None = None) -> None:
        if value is None or value == []:
            return
        suggestions.append(
            {
                "id": identifier,
                "label": label,
                "value": value,
                "fieldKey": field_key,
                "source": PROFILE_SOURCE,
                "status": "available",
            }
        )

    if domain == "diet":
        add("profile:diet_preferences", "口味偏好", diet, "taste")
        if notes:
            add("profile:diet_notes", "饮食资料备注", notes)
    elif domain == "travel":
        add("profile:travel_priority", "旅行偏好", _preference_text(budget, cities, notes), "priority")
    elif domain == "shopping":
        add("profile:shopping_priority", "购物偏好", _preference_text(budget, notes), "priority")
    elif domain == "generic":
        add("profile:generic_priority", "通用偏好", _preference_text(budget, notes), "priority")
    return suggestions


def _add_assumptions(decision, suggestions: list[dict[str, Any]]) -> None:
    existing = {item.key for item in decision.assumptions}
    for suggestion in suggestions:
        key = suggestion["id"].replace("profile:", "profile.")
        if key in existing:
            continue
        decision.assumptions.append(
            Assumption(
                key=key,
                value=suggestion["value"],
                confidence=0.6,
                source=PROFILE_SOURCE,
            )
        )


def apply_user_profile_to_decision(
    decision,
    profile: UserProfile,
    *,
    diet_options: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    suggestions = profile_suggestions_for_domain(profile, decision.domain)
    if not suggestions:
        return []
    _add_assumptions(decision, suggestions)

    if decision.domain == "diet":
        from choice_agent.domains.diet.state import apply_fields, metadata, values

        current = values(decision)
        states = metadata(decision)
        patch: dict[str, list[str]] = {}
        for suggestion in suggestions:
            field_key = suggestion.get("fieldKey")
            if field_key != "taste":
                continue
            if current.get(field_key) or states.get(field_key, {}).get("cleared"):
                suggestion["status"] = "skipped_existing_decision_state"
                continue
            patch[field_key] = list(suggestion["value"])
            suggestion["status"] = "applied_to_field"
        if patch:
            apply_fields(decision, patch, diet_options or {}, source=PROFILE_SOURCE, validate=False)
    else:
        from choice_agent.decision.conversation import fields, patch_fields

        current = fields(decision)
        patch: dict[str, Any] = {}
        for suggestion in suggestions:
            field_key = suggestion.get("fieldKey")
            if not field_key or field_key not in current:
                continue
            field = current[field_key]
            if field.get("value") is not None or field.get("cleared"):
                suggestion["status"] = "skipped_existing_decision_state"
                continue
            patch[field_key] = suggestion["value"]
            suggestion["status"] = "applied_to_field"
        if patch:
            patch_fields(decision, patch, source=PROFILE_SOURCE, confirmed=False)

    decision.domain_state["profileSuggestions"] = suggestions
    return suggestions