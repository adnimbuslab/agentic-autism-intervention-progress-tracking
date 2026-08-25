"""Analytics routes (stub for Phase 4)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from src.backend.api.deps import DBSession, RequireInterventionist, authorize_child_access

router = APIRouter(tags=["analytics"])


@router.get("/children/{child_id}/analytics")
async def get_analytics(
    child_id: uuid.UUID,
    user: RequireInterventionist,
    db: DBSession,
) -> None:
    await authorize_child_access(user, child_id, db)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Analytics will be available in Phase 4",
    )
