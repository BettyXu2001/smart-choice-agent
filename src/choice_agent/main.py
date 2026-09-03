from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from choice_agent.api.routes import router
from choice_agent.config import Settings
from choice_agent.database import Database
from choice_agent.domains.diet.seed import seed_legacy_data
from choice_agent.providers.model import OpenAICompatibleProvider


STATIC_DIR = Path(__file__).with_name("static")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()
    database = Database(resolved)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.create_all()
        with database.session_factory() as db:
            seed_legacy_data(db)
        app.state.settings = resolved
        app.state.database = database
        app.state.provider = OpenAICompatibleProvider(resolved)
        yield

    app = FastAPI(
        title="Choice Agent V2",
        version="0.1.0",
        description="通用多 Agent 决策系统，饮食为首个完整领域。",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"message": error.detail})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"message": "请求参数不合法", "errors": error.errors()},
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()

