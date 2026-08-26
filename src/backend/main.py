"""FastAPI application entry point."""

from __future__ import annotations

import logging
import logging.config
import uuid
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text as sa_text

from src.backend.api.actors import router as actors_router
from src.backend.api.analytics import router as analytics_router
from src.backend.api.audit import router as audit_router
from src.backend.api.auth import router as auth_router
from src.backend.api.children import router as children_router
from src.backend.api.goals import router as goals_router
from src.backend.api.observations import router as observations_router
from src.backend.api.reports import router as reports_router
from src.backend.api.schedules import router as schedules_router
from src.backend.api.structured_records import router as records_router
from src.backend.config import settings

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "level": "INFO" if not settings.app_debug else "DEBUG",
        "handlers": ["console"],
    },
    "loggers": {
        "uvicorn": {"level": "INFO"},
        "sqlalchemy.engine": {"level": "WARNING"},
    },
}
logging.config.dictConfig(LOGGING_CONFIG)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "Application starting env=%s extraction_provider=%s cors=%s",
        settings.app_env,
        settings.extraction_provider,
        settings.cors_origins,
    )
    yield


app = FastAPI(
    title="Autism Intervention Tracker API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestIDMiddleware:
    def __init__(self, asgi_app):
        self.app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("Unhandled exception [request_id=%s]", request_id)
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error", "request_id": request_id},
            )
            await response(scope, receive, send)


app.add_middleware(RequestIDMiddleware)


@app.get("/health")
async def health() -> JSONResponse:
    from src.backend.database import async_session_factory

    db_ok = False
    try:
        async with async_session_factory() as session:
            await session.execute(sa_text("SELECT 1"))
            db_ok = True
    except Exception:
        pass

    if db_ok:
        return JSONResponse(content={"status": "ok", "database": "connected"})
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "degraded", "database": "disconnected"},
    )


app.include_router(auth_router)
app.include_router(children_router)
app.include_router(goals_router)
app.include_router(actors_router)
app.include_router(observations_router)
app.include_router(records_router)
app.include_router(schedules_router)
app.include_router(analytics_router)
app.include_router(reports_router)
app.include_router(audit_router)
