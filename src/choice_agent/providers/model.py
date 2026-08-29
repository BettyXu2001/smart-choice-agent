from __future__ import annotations

import json
from urllib import request
from typing import Any, Protocol

from choice_agent.config import Settings


class ModelProvider(Protocol):
    @property
    def enabled(self) -> bool: ...

    def complete_json(self, system_prompt: str, user_prompt: str, model: str) -> dict[str, Any]: ...


class OpenAICompatibleProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.enable_llm and bool(self.settings.model_api_key)

    def complete_json(self, system_prompt: str, user_prompt: str, model: str) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("LLM provider is disabled")
        url = self.settings.model_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.settings.model_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(http_request, timeout=self.settings.model_timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        content = response_payload["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("Model response must be a JSON object")
        return parsed


class DisabledProvider:
    @property
    def enabled(self) -> bool:
        return False

    def complete_json(self, system_prompt: str, user_prompt: str, model: str) -> dict[str, Any]:
        raise RuntimeError("LLM provider is disabled")
