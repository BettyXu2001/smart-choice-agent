from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./choice_agent.db"
    model_api_key: str = ""
    model_base_url: str = "https://api.openai.com/v1"
    main_model: str = "gpt-5"
    light_model: str = "gpt-5-mini"
    model_timeout_seconds: float = 30.0
    enable_llm: bool = False
    debug: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv("CHOICE_AGENT_DATABASE_URL", cls.database_url),
            model_api_key=os.getenv("CHOICE_AGENT_MODEL_API_KEY", ""),
            model_base_url=os.getenv("CHOICE_AGENT_MODEL_BASE_URL", cls.model_base_url),
            main_model=os.getenv("CHOICE_AGENT_MAIN_MODEL", cls.main_model),
            light_model=os.getenv("CHOICE_AGENT_LIGHT_MODEL", cls.light_model),
            model_timeout_seconds=float(os.getenv("CHOICE_AGENT_MODEL_TIMEOUT_SECONDS", "30")),
            enable_llm=_as_bool(os.getenv("CHOICE_AGENT_ENABLE_LLM")),
            debug=_as_bool(os.getenv("CHOICE_AGENT_DEBUG"), True),
        )
