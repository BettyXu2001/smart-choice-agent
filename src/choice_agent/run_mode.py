from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from choice_agent.config import Settings


RunMode = Literal["demo", "live"]


def resolve_run_mode(
    settings: Settings,
    context: Mapping[str, Any] | None = None,
) -> RunMode:
    data = context or {}
    search_mode = str(data.get("searchMode") or data.get("search_mode") or "").lower()
    if data.get("demoMode") is True or data.get("demo_mode") is True or search_mode == "fixture":
        return "demo"

    model_live = settings.enable_llm and bool(settings.model_api_key.strip())
    search_live = bool(settings.search_api_key.strip())
    return "live" if model_live or search_live else "demo"
