"""FastAPI application entry point."""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Autism Intervention Tracker API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Unhandled exception [request_id=%s]", request_id)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "request_id": request_id},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
