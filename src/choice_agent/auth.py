"""Server-issued anonymous identities; a client-supplied user ID is never trusted."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from choice_agent.config import Settings
from choice_agent.database import Database
from choice_agent.db_models import (
    AnonymousIdentityRecord, DecisionRecord, EvaluationCaseRecord,
    EvaluationDatasetRecord, EvaluationRunRecord, FeedbackRecord, MealRecord,
    SessionRecord, TraceRecord, UserProfileRecord,
)

COOKIE_NAME = "choice_agent_identity"
SESSION_MAX_AGE = 365 * 24 * 60 * 60


def validate_session_settings(settings: Settings) -> None:
    if len(settings.session_secret.encode("utf-8")) < 32:
        raise ValueError("CHOICE_AGENT_SESSION_SECRET must contain at least 32 bytes")


def sign_identity(user_id: int, secret: str, issued_at: int | None = None) -> str:
    payload = f"v1.{user_id}.{int(time.time()) if issued_at is None else issued_at}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify_identity(token: str, secret: str) -> int | None:
    if len(token) > 200:
        return None
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != "v1":
        return None
    payload = ".".join(parts[:3])
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not parts[3].isascii() or not hmac.compare_digest(parts[3], expected):
        return None
    try:
        user_id, issued_at = int(parts[1]), int(parts[2])
    except ValueError:
        return None
    age = int(time.time()) - issued_at
    return user_id if 2 <= user_id <= 2**31 - 1 and 0 <= age < SESSION_MAX_AGE else None


def check_same_origin(request: Request) -> None:
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise HTTPException(status_code=403, detail="不允许跨站请求")
    origin = request.headers.get("origin")
    if origin:
        try:
            supplied = urlsplit(origin)
            expected = urlsplit(str(request.base_url))
        except ValueError as error:
            raise HTTPException(status_code=403, detail="请求来源不合法") from error
        if (supplied.scheme, supplied.netloc) != (expected.scheme, expected.netloc):
            raise HTTPException(status_code=403, detail="不允许跨源请求")


def current_identity(request: Request) -> int | None:
    token = request.cookies.get(COOKIE_NAME, "")
    user_id = verify_identity(token, request.app.state.settings.session_secret)
    if user_id is None:
        return None
    with request.app.state.database.session_factory() as db:
        return user_id if db.get(AnonymousIdentityRecord, user_id) is not None else None


def require_identity(request: Request) -> int:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_same_origin(request)
    user_id = current_identity(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="匿名会话已失效，请重新初始化后刷新页面")
    return user_id


def allocate_identity(database: Database) -> int:
    owner_columns = (
        AnonymousIdentityRecord.user_id, SessionRecord.user_id, MealRecord.owner_user_id,
        FeedbackRecord.user_id, TraceRecord.user_id, UserProfileRecord.user_id,
        EvaluationCaseRecord.owner_user_id, EvaluationDatasetRecord.owner_user_id,
        EvaluationRunRecord.owner_user_id,
        DecisionRecord.state_json["ownerUserId"].as_integer(),
    )
    for _ in range(8):
        user_id = secrets.randbelow(2**31 - 2) + 2
        with database.session_factory() as db:
            if any(db.scalar(select(column).where(column == user_id).limit(1)) is not None
                   for column in owner_columns):
                continue
            db.add(AnonymousIdentityRecord(user_id=user_id))
            try:
                db.commit()
                return user_id
            except IntegrityError:
                # Another first-visit request reserved this ID. Try a fresh one.
                db.rollback()
    raise HTTPException(status_code=503, detail="暂时无法分配匿名身份，请重试")


def identity(request: Request, response: Response) -> dict[str, int]:
    check_same_origin(request)
    response.headers["Cache-Control"] = "no-store"
    user_id = current_identity(request)
    if user_id is None:
        user_id = allocate_identity(request.app.state.database)
        settings = request.app.state.settings
        response.set_cookie(
            COOKIE_NAME, sign_identity(user_id, settings.session_secret),
            max_age=SESSION_MAX_AGE, httponly=True, secure=settings.cookie_secure,
            samesite="lax", path="/",
        )
    return {"userId": user_id}
