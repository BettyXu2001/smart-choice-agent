from __future__ import annotations

import pytest

from choice_agent.config import Settings
from choice_agent.database import Database
from choice_agent.domains.diet.seed import seed_legacy_data


@pytest.fixture
def database(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    database = Database(settings)
    database.create_all()
    with database.session_factory() as db:
        seed_legacy_data(db)
    return database


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")



@pytest.fixture
def web(tmp_path):
    """Exercise the real ASGI router without adding an HTTP client dependency."""
    import asyncio
    import json
    from http.cookies import SimpleCookie
    from urllib.parse import urlsplit
    from choice_agent.main import create_app

    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'http.db'}",
                              session_secret="test-secret-" * 4))
    loop = asyncio.new_event_loop()
    lifespan = app.router.lifespan_context(app)
    loop.run_until_complete(lifespan.__aenter__())

    class Client:
        def __init__(self):
            self.cookies = {}
            self.app = app

        def fork(self):
            return Client()

        def call(self, method, path, body=None, headers=None, raw=None):
            async def request():
                parsed = urlsplit(path)
                data = raw if raw is not None else json.dumps(body).encode() if body is not None else b""
                request_headers = {"content-type": "application/json", **(headers or {})}
                if self.cookies:
                    request_headers.setdefault("cookie", "; ".join(f"{k}={v}" for k, v in self.cookies.items()))
                scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                         "method": method, "scheme": "https", "path": parsed.path,
                         "raw_path": parsed.path.encode(), "root_path": "", "query_string": parsed.query.encode(),
                         "headers": [(k.lower().encode(), str(v).encode()) for k, v in request_headers.items()],
                         "server": ("test", 443), "client": ("127.0.0.1", 1234)}
                sent = False
                done = asyncio.Event()
                messages = []

                async def receive():
                    nonlocal sent
                    if not sent:
                        sent = True
                        return {"type": "http.request", "body": data, "more_body": False}
                    await done.wait()
                    return {"type": "http.disconnect"}

                async def send(message):
                    messages.append(message)
                    if message["type"] == "http.response.body" and not message.get("more_body", False):
                        done.set()

                await app(scope, receive, send)
                start = next(m for m in messages if m["type"] == "http.response.start")
                response_headers = dict((k.decode(), v.decode()) for k, v in start["headers"])
                for key, value in start["headers"]:
                    if key == b"set-cookie":
                        cookie = SimpleCookie(value.decode())
                        self.cookies.update({k: v.value for k, v in cookie.items()})
                content = b"".join(m.get("body", b"") for m in messages).decode()
                try:
                    result = json.loads(content)
                except json.JSONDecodeError:
                    result = content
                return start["status"], result, response_headers

            return loop.run_until_complete(request())

    try:
        yield Client()
    finally:
        loop.run_until_complete(lifespan.__aexit__(None, None, None))
        loop.close()
