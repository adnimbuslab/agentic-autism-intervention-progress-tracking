"""Report routes (stub for Phase 4)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from src.backend.api.deps import DBSession, RequireInterventionist, authorize_child_access

router = APIRouter(tags=["reports"])


@router.post("/children/{child_id}/reports/generate")
async def generate_report(
    child_id: uuid.UUID,
    user: RequireInterventionist,
    db: DBSession,
) -> None:
    await authorize_child_access(user, child_id, db)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Report generation will be available in Phase 4",
    )


@router.get("/reports/{report_id}")
async def get_report(
    report_id: uuid.UUID,
    user: RequireInterventionist,
    db: DBSession,
) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Report retrieval will be available in Phase 4",
    )


@router.post("/reports/{report_id}/flag")
async def flag_report(
    report_id: uuid.UUID,
    user: RequireInterventionist,
    db: DBSession,
) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Report flagging will be available in Phase 4",
    )
