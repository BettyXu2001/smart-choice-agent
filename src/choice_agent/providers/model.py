from __future__ import annotations

import json
from urllib import request
from typing import Any, Protocol

from choice_agent.config import Settings
from choice_agent.providers.observability import (
    ModelCompletion,
    ProviderResponseError,
    metadata_from_usage,
    prompt_fingerprint,
)


class ModelProvider(Protocol):
    @property
    def enabled(self) -> bool: ...

    def complete_json(self, system_prompt: str, user_prompt: str, model: str) -> dict[str, Any]: ...


class OpenAICompatibleProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.name = settings.model_provider_name

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
        actual_model = str(response_payload.get("model") or model)
        metadata = metadata_from_usage(
            response_payload.get("usage"),
            provider=self.name,
            model=actual_model,
            prompt_version=prompt_fingerprint(system_prompt),
            pricing=self.settings.model_pricing,
            input_key="prompt_tokens",
            output_key="completion_tokens",
        )
        try:
            content = response_payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("Model response must be a JSON object")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ProviderResponseError(
                f"Invalid model response: {type(error).__name__}: {error}",
                metadata,
            ) from error
        return ModelCompletion(parsed, metadata)


class DisabledProvider:
    name = "disabled"
    @property
    def enabled(self) -> bool:
        return False

    def complete_json(self, system_prompt: str, user_prompt: str, model: str) -> dict[str, Any]:
        raise RuntimeError("LLM provider is disabled")
