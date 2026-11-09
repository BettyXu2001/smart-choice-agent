import asyncio
from dataclasses import replace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from choice_agent.auth import COOKIE_NAME, SESSION_MAX_AGE, allocate_identity, sign_identity, verify_identity
from choice_agent.config import Settings
from choice_agent.db_models import AnonymousIdentityRecord, DecisionRecord, UserProfileRecord
from choice_agent.main import create_app
from choice_agent.schemas import DecisionState


def test_anonymous_cookie_is_stable_and_cannot_be_selected_by_header(web):
    assert web.call("GET", "/api/v1/profile", headers={"X-User-Id": "1"})[0] == 401
    status, identity, headers = web.call("GET", "/api/v1/identity")
    assert status == 200 and identity["userId"] >= 2
    cookie = headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "Domain=" not in cookie and headers["cache-control"] == "no-store"
    assert web.call("PUT", "/api/v1/profile", {"notes": "private"})[0] == 200
    assert web.call("GET", "/api/v1/identity")[1] == identity
    other = web.fork()
    other_id = other.call("GET", "/api/v1/identity")[1]["userId"]
    assert other_id != identity["userId"]
    assert other.call("GET", "/api/v1/profile", headers={"X-User-Id": identity["userId"]})[1]["notes"] is None
    assert other.call("PUT", "/api/v1/profile", {"notes": "other"}, headers={"X-User-Id": identity["userId"]})[0] == 200
    assert web.call("GET", "/api/v1/profile")[1]["notes"] == "private"
    other.cookies[COOKIE_NAME] = web.cookies[COOKIE_NAME][:-1] + "x"
    assert other.call("GET", "/api/v1/profile")[0] == 401
    assert other.call("GET", "/api/v1/identity")[1]["userId"] not in {identity["userId"], other_id}


def test_signature_expiry_key_rotation_and_identity_reservation(web):
    identity = web.call("GET", "/api/v1/identity")[1]["userId"]
    secret = web.app.state.settings.session_secret
    token = web.cookies[COOKIE_NAME]
    assert verify_identity(token, secret) == identity
    assert verify_identity(token, "different" * 8) is None
    for issued_at in (0, 10**15):
        assert verify_identity(sign_identity(identity, secret, issued_at), secret) is None
    assert verify_identity(sign_identity(1, secret), secret) is None
    for invalid in ("x", "v1.1.2.汉字", "x" * 201):
        assert verify_identity(invalid, secret) is None
    web.cookies[COOKIE_NAME] = sign_identity(12345, secret)
    assert web.call("GET", "/api/v1/profile")[0] == 401
    web.cookies[COOKIE_NAME] = token
    original = web.app.state.settings
    web.app.state.settings = replace(original, session_secret="new-secret" * 4)
    assert web.call("GET", "/api/v1/profile")[0] == 401
    web.app.state.settings = original
    assert web.call("GET", "/api/v1/profile")[0] == 200


def test_cross_origin_identity_and_mutations_are_rejected(web):
    assert web.call("GET", "/api/v1/identity", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert web.call("GET", "/api/v1/identity", headers={"Origin": "https://evil.test"})[0] == 403
    assert web.call("GET", "/api/v1/identity", headers={"Origin": "https://test"})[0] == 200
    assert web.call("PUT", "/api/v1/profile", {}, headers={"Origin": "null"})[0] == 403
    assert web.call("PUT", "/api/v1/profile", {}, headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert web.call("PUT", "/api/v1/profile", {}, headers={"Origin": "https://test"})[0] == 200


def test_allocation_skips_legacy_users_and_existing_identities(database):
    with database.session_factory() as db:
        db.add(UserProfileRecord(user_id=42, profile_json={"notes": "legacy"}))
        decision = DecisionState(decision_id="legacy42", session_id="s", domain="travel", owner_user_id=43)
        db.add(DecisionRecord(id=decision.decision_id, session_id="s", state_json=decision.model_dump(mode="json", by_alias=True)))
        db.add(AnonymousIdentityRecord(user_id=44))
        db.commit()
    with patch("choice_agent.auth.secrets.randbelow", side_effect=[40, 41, 42, 43]):
        assert allocate_identity(database) == 45
    with patch("choice_agent.auth.secrets.randbelow", return_value=40):
        with pytest.raises(HTTPException) as caught:
            allocate_identity(database)
    assert caught.value.status_code == 503


def test_startup_requires_persistent_secret_and_env_defaults(tmp_path, monkeypatch):
    for secret in ("", "short"):
        app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'bad.db'}", session_secret=secret))
        async def start():
            async with app.router.lifespan_context(app):
                pytest.fail("invalid secret must not start")
        with pytest.raises(ValueError, match="SESSION_SECRET"):
            asyncio.run(start())
    monkeypatch.setenv("CHOICE_AGENT_SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("CHOICE_AGENT_COOKIE_SECURE", "false")
    assert Settings.from_env().session_secret == "s" * 32
    assert Settings.from_env().cookie_secure is False


def test_cookie_survives_restart_and_secure_flag_can_be_disabled(web):
    identity = web.call("GET", "/api/v1/identity")[1]
    app = create_app(web.app.state.settings)
    async def restart():
        async with app.router.lifespan_context(app):
            from starlette.requests import Request
            from choice_agent.auth import current_identity
            req = Request({"type": "http", "app": app, "headers": [(b"cookie", f"{COOKIE_NAME}={web.cookies[COOKIE_NAME]}".encode())]})
            assert current_identity(req) == identity["userId"]
    asyncio.run(restart())
    web.app.state.settings = replace(web.app.state.settings, cookie_secure=False)
    assert "Secure" not in web.fork().call("GET", "/api/v1/identity")[2]["set-cookie"]


def test_normal_and_stream_decisions_share_identity_and_owner_checks(web):
    web.call("GET", "/api/v1/identity")
    request = {"message": "周末从上海出发两天一夜", "domain": "travel", "context": {"demoMode": True}}
    status, created, _ = web.call("POST", "/api/v1/decisions", request)
    assert status == 200
    decision = created["decisionState"]
    did = decision["decisionId"]
    other = web.fork()
    other.call("GET", "/api/v1/identity")
    assert other.call("GET", f"/api/v1/decisions/{did}")[0] == 404
    status, stream, _ = web.call("POST", f"/api/v1/decisions/{did}/messages/stream",
                                {"message": "为什么这样推荐", "expectedRevision": decision["revision"]})
    import json
    events = [json.loads(line) for line in stream.splitlines()]
    final = next(event["response"] for event in events if event["type"] == "final")
    assert status == 200 and final["decisionState"]["revision"] == decision["revision"] + 1
    assert final["decisionState"]["ownerUserId"] == decision["ownerUserId"]
    assert len(web.call("GET", "/api/v1/decision-history")[1]["items"]) == 1
    assert other.call("GET", "/api/v1/decision-history")[1]["items"] == []


def test_concurrent_identity_allocation_retries_unique_key_race(database, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, local
    from sqlalchemy.orm import Session
    rendezvous, attempts = Barrier(2), local()
    def candidate(_limit):
        count = getattr(attempts, "count", 0)
        attempts.count = count + 1
        return 123456 + count
    original_commit = Session.commit
    def commit(db):
        if any(isinstance(row, AnonymousIdentityRecord) and row.user_id == 123458 for row in db.new):
            rendezvous.wait(timeout=10)
        return original_commit(db)
    monkeypatch.setattr("choice_agent.auth.secrets.randbelow", candidate)
    monkeypatch.setattr(Session, "commit", commit)
    with ThreadPoolExecutor(max_workers=2) as workers:
        users = list(workers.map(lambda _: allocate_identity(database), range(2)))
    assert sorted(users) == [123458, 123459]
