from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from math import isfinite


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _model_pricing(value: str | None) -> dict[str, dict[str, float]]:
    if not value or not value.strip():
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("CHOICE_AGENT_MODEL_PRICING_JSON must be a JSON object")
    result: dict[str, dict[str, float]] = {}
    for model, raw in parsed.items():
        if not isinstance(model, str) or not model.strip() or not isinstance(raw, dict):
            raise ValueError("Each model price must be an object keyed by a non-empty model name")
        normalized: dict[str, float] = {}
        for key in ("inputPer1MTokens", "outputPer1MTokens"):
            price = raw.get(key)
            if (
                isinstance(price, bool)
                or not isinstance(price, (int, float))
                or not isfinite(price)
                or price < 0
            ):
                raise ValueError(f"{model}.{key} must be a non-negative number")
            normalized[key] = float(price)
        result[model.strip()] = normalized
    return result


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./choice_agent.db"
    model_api_key: str = ""
    model_base_url: str = "https://api.deepseek.com"
    model_provider_name: str = "openai-compatible"
    model_pricing: dict[str, dict[str, float]] = field(default_factory=dict)
    main_model: str = "deepseek-v4-pro"
    light_model: str = "deepseek-flash"
    model_timeout_seconds: float = 30.0
    enable_llm: bool = False
    debug: bool = True
    search_provider: str = "fixture"
    search_api_key: str = ""
    search_base_url: str = "https://api.openai.com/v1"
    search_model: str = "gpt-5-mini"
    search_timeout_seconds: float = 20.0
    search_max_queries: int = 2

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv("CHOICE_AGENT_DATABASE_URL", cls.database_url),
            model_api_key=os.getenv("CHOICE_AGENT_MODEL_API_KEY", ""),
            model_base_url=os.getenv("CHOICE_AGENT_MODEL_BASE_URL", cls.model_base_url),
            model_provider_name=os.getenv("CHOICE_AGENT_MODEL_PROVIDER_NAME", cls.model_provider_name).strip() or cls.model_provider_name,
            model_pricing=_model_pricing(os.getenv("CHOICE_AGENT_MODEL_PRICING_JSON")),
            main_model=os.getenv("CHOICE_AGENT_MAIN_MODEL", cls.main_model),
            light_model=os.getenv("CHOICE_AGENT_LIGHT_MODEL", cls.light_model),
            model_timeout_seconds=float(os.getenv("CHOICE_AGENT_MODEL_TIMEOUT_SECONDS", "30")),
            enable_llm=_as_bool(os.getenv("CHOICE_AGENT_ENABLE_LLM")),
            debug=_as_bool(os.getenv("CHOICE_AGENT_DEBUG"), True),
            search_provider=os.getenv("CHOICE_AGENT_SEARCH_PROVIDER", "fixture").strip().lower(),
            search_api_key=os.getenv("CHOICE_AGENT_SEARCH_API_KEY", ""),
            search_base_url=os.getenv("CHOICE_AGENT_SEARCH_BASE_URL", cls.search_base_url),
            search_model=os.getenv("CHOICE_AGENT_SEARCH_MODEL", cls.search_model),
            search_timeout_seconds=float(os.getenv("CHOICE_AGENT_SEARCH_TIMEOUT_SECONDS", "20")),
            search_max_queries=int(os.getenv("CHOICE_AGENT_SEARCH_MAX_QUERIES", "2")),
        )
