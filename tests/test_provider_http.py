import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from choice_agent.api.routes import runtime_model_from_headers
from choice_agent.config import Settings
from choice_agent.providers.http import authorize_base_url, normalize_base_url, open_provider_request
from choice_agent.providers.model import DisabledProvider


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000", "https://[::1]", "https://10.0.0.1", "https://169.254.169.254",
    "https://untrusted.example/v1", "https://api.openai.com.evil.example/v1",
    "https://api.openai.com/v1/extra", "https://api.openai.com/v1/../internal",
    "https://api.openai.com/v1/%2e%2e", "https://api.openai.com/v1?target=internal",
    "https://api.openai.com/v1#ignored", "https://user@api.openai.com/v1",
    "https://api.openai.com\\@evil.example/v1", "https://api.openai.com\n/v1",
    "file:///etc/passwd", "https://api.openai.com:invalid/v1",
])
def test_untrusted_or_ambiguous_targets_are_rejected(url):
    with pytest.raises(ValueError):
        authorize_base_url(url, Settings.model_base_url, ())


def test_exact_authorization_and_operator_local_endpoint():
    assert normalize_base_url("HTTPS://API.OPENAI.COM:443/v1/") == "https://api.openai.com/v1"
    assert authorize_base_url("https://api.openai.com/v1/", Settings.model_base_url, ()) == "https://api.openai.com/v1"
    assert authorize_base_url("https://gateway.example/v1", Settings.model_base_url,
                              ("https://gateway.example/v1/",)) == "https://gateway.example/v1"
    assert authorize_base_url("http://127.0.0.1:11434/v1", "http://127.0.0.1:11434/v1", ()) == "http://127.0.0.1:11434/v1"
    with pytest.raises(ValueError):
        authorize_base_url("https://api.deepseek.com", Settings.search_base_url, (), search=True)


def test_allowlist_environment_configuration(monkeypatch):
    monkeypatch.setenv("CHOICE_AGENT_MODEL_BASE_URL_ALLOWLIST", '["https://gateway.example:443/v1/"]')
    monkeypatch.setenv("CHOICE_AGENT_SEARCH_BASE_URL_ALLOWLIST", '["https://search.example/api"]')
    settings = Settings.from_env()
    assert settings.model_base_url_allowlist == ("https://gateway.example/v1",)
    assert settings.search_base_url_allowlist == ("https://search.example/api",)
    for invalid in ('{}', '[1]', '["http://localhost"]', '["https://host/path?query"]', 'invalid'):
        monkeypatch.setenv("CHOICE_AGENT_MODEL_BASE_URL_ALLOWLIST", invalid)
        with pytest.raises(ValueError):
            Settings.from_env()


@pytest.mark.parametrize("kind", ["Model", "Search"])
@pytest.mark.parametrize("path,method,body", [
    ("/api/v1/decisions", "POST", {"domain": "generic", "message": "compare A and B"}),
    ("/api/v1/decisions/stream", "POST", {"domain": "generic", "message": "compare A and B"}),
    ("/api/v1/search/capabilities", "GET", None),
])
def test_http_rejects_target_before_network_and_does_not_expose_key(web, monkeypatch, kind, path, method, body):
    calls = []
    monkeypatch.setattr("choice_agent.providers.model.open_provider_request", lambda *a, **k: calls.append(a))
    monkeypatch.setattr("choice_agent.providers.search.open_provider_request", lambda *a, **k: calls.append(a))
    web.call("GET", "/api/v1/identity")
    headers = {f"X-Choice-Agent-{kind}-Enabled": "true", f"X-Choice-Agent-{kind}-Api-Key": "secret-probe",
               f"X-Choice-Agent-{kind}-Base-Url": "http://127.0.0.1:54321/internal"}
    status, response, _ = web.call(method, path, body, headers=headers)
    assert status == 400 and not calls
    assert "secret-probe" not in json.dumps(response) and "54321" not in json.dumps(response)


def test_enabled_runtime_keys_and_server_fallback_do_not_cross_configuration():
    base = Settings(model_base_url="https://server.example/v1")
    settings, provider = runtime_model_from_headers(base, DisabledProvider(), "true", "own-key", " ", None, None)
    assert provider.enabled and settings.model_base_url == base.model_base_url
    assert settings.model_api_key == "own-key" and base.model_api_key == ""
    settings, provider = runtime_model_from_headers(base, DisabledProvider(), "true", "", "http://evil", None, None)
    assert settings is base and not provider.enabled


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
def test_real_transport_never_follows_redirects(code):
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            hits.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(code)
            self.send_header("Location", "/internal")
            self.end_headers()

        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        req = Request(f"http://127.0.0.1:{server.server_port}/provider", data=b"{}",
                      headers={"Authorization": "Bearer test-only"})
        with pytest.raises(HTTPError) as error:
            open_provider_request(req, timeout=2)
        assert error.value.code == code
        error.value.close()
        assert hits == ["/provider"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
