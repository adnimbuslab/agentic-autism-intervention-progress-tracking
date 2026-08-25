"""Audit trail routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from src.backend.api.deps import (
    DBSession,
    RequireInterventionist,
    authorize_child_access,
)
from src.backend.schemas.api_schemas import AuditEventResponse
from src.backend.services import audit_service

router = APIRouter(tags=["audit"])


@router.get("/children/{child_id}/audit", response_model=list[AuditEventResponse])
async def get_audit_trail(
    child_id: uuid.UUID,
    user: RequireInterventionist,
    db: DBSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[AuditEventResponse]:
    await authorize_child_access(user, child_id, db)
    events = await audit_service.get_audit_trail(db, child_id, limit=limit, offset=offset)
    return [AuditEventResponse.model_validate(e) for e in events]
