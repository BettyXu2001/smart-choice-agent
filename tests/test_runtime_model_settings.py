from __future__ import annotations

import json

from choice_agent.api.routes import runtime_model_from_headers
from choice_agent.config import Settings
from choice_agent.orchestration.diet import DietOrchestrator
from choice_agent.providers.model import DisabledProvider
from choice_agent.repositories.diet_repository import DietRepository
from choice_agent.schemas import ChatRequest, SourceMode


def test_runtime_model_headers_create_enabled_temporary_provider():
    base_settings = Settings(
        database_url="sqlite:///./test.db",
        model_base_url="https://server.example/v1",
        main_model="server-main",
        light_model="server-light",
        enable_llm=False,
    )

    runtime_settings, provider = runtime_model_from_headers(
        base_settings,
        DisabledProvider(),
        "true",
        " browser-test-key ",
        "https://browser.example/v1/",
        "browser-main",
        "browser-light",
    )

    assert runtime_settings.model_api_key == "browser-test-key"
    assert runtime_settings.model_base_url == "https://browser.example/v1/"
    assert runtime_settings.main_model == "browser-main"
    assert runtime_settings.light_model == "browser-light"
    assert runtime_settings.enable_llm is True
    assert provider.enabled is True


def test_runtime_model_headers_fall_back_without_enabled_key():
    base_settings = Settings(database_url="sqlite:///./test.db")
    base_provider = DisabledProvider()

    runtime_settings, provider = runtime_model_from_headers(
        base_settings,
        base_provider,
        "false",
        "browser-test-key",
        "https://browser.example/v1",
        "browser-main",
        "browser-light",
    )

    assert runtime_settings is base_settings
    assert provider is base_provider


def test_browser_model_key_header_value_is_not_part_of_chat_trace(database):
    secret = "browser-secret-should-not-be-persisted"
    base_settings = Settings()
    runtime_settings, provider = runtime_model_from_headers(
        base_settings,
        DisabledProvider(),
        "false",
        secret,
        "https://browser.example/v1",
        "browser-main",
        "browser-light",
    )

    with database.session_factory() as db:
        response = DietOrchestrator(db, runtime_settings, provider).chat(
            1,
            ChatRequest(message="晚餐想吃清淡一点", source_mode=SourceMode.PUBLIC),
        )
        trace = DietRepository(db).trace(1, response.trace_id)

    assert trace is not None
    trace_json = json.dumps(trace.trace_json, ensure_ascii=False)
    assert secret not in trace_json