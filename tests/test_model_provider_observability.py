import json

import pytest

from choice_agent.config import Settings
from choice_agent.providers.model import OpenAICompatibleProvider
from choice_agent.providers.observability import ProviderResponseError


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def provider(pricing=None):
    return OpenAICompatibleProvider(Settings(
        enable_llm=True,
        model_api_key="test-key",
        model_provider_name="test-compatible",
        model_pricing=pricing or {},
    ))


def test_openai_compatible_provider_reads_real_usage_and_configured_cost(monkeypatch):
    payload = {
        "model": "priced-model",
        "choices": [{"message": {"content": '{"answer":"ok"}'}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 25, "total_tokens": 125},
    }
    monkeypatch.setattr("choice_agent.providers.model.request.urlopen", lambda *args, **kwargs: FakeResponse(payload))

    result = provider({
        "priced-model": {"inputPer1MTokens": 2.0, "outputPer1MTokens": 8.0}
    }).complete_json("system", "user", "requested-model")

    assert result == {"answer": "ok"}
    assert result.metadata.provider == "test-compatible"
    assert result.metadata.model == "priced-model"
    assert result.metadata.input_tokens == 100
    assert result.metadata.output_tokens == 25
    assert result.metadata.total_tokens == 125
    assert result.metadata.estimated_cost == 0.0004
    assert result.metadata.prompt_version.startswith("sha256:")


def test_usage_and_unknown_price_remain_null(monkeypatch):
    payload = {
        "choices": [{"message": {"content": '{"answer":"ok"}'}}],
    }
    monkeypatch.setattr("choice_agent.providers.model.request.urlopen", lambda *args, **kwargs: FakeResponse(payload))

    result = provider().complete_json("system", "user", "unknown-model")

    assert result.metadata.input_tokens is None
    assert result.metadata.output_tokens is None
    assert result.metadata.total_tokens is None
    assert result.metadata.estimated_cost is None


def test_invalid_json_error_keeps_response_usage(monkeypatch):
    payload = {
        "model": "priced-model",
        "choices": [{"message": {"content": "not-json"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }
    monkeypatch.setattr("choice_agent.providers.model.request.urlopen", lambda *args, **kwargs: FakeResponse(payload))

    with pytest.raises(ProviderResponseError) as captured:
        provider().complete_json("system", "user", "priced-model")

    assert captured.value.metadata.total_tokens == 12
    assert captured.value.metadata.estimated_cost is None


def test_non_finite_configured_price_is_rejected(monkeypatch):
    monkeypatch.setenv(
        "CHOICE_AGENT_MODEL_PRICING_JSON",
        '{"bad-model":{"inputPer1MTokens":NaN,"outputPer1MTokens":1}}',
    )

    with pytest.raises(ValueError, match="inputPer1MTokens"):
        Settings.from_env()
