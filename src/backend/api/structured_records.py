"""Structured record routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from src.backend.api.deps import (
    DBSession,
    RequireInterventionist,
    authorize_child_access,
)
from src.backend.schemas.api_schemas import RecordCorrection, RecordResponse
from src.backend.services import audit_service, observation_service

router = APIRouter(tags=["records"])


@router.get("/children/{child_id}/records", response_model=list[RecordResponse])
async def list_records(
    child_id: uuid.UUID,
    user: RequireInterventionist,
    db: DBSession,
) -> list[RecordResponse]:
    await authorize_child_access(user, child_id, db)
    records = await observation_service.list_records(db, child_id)
    return [RecordResponse.model_validate(r) for r in records]


@router.post("/records/{record_id}/correct", response_model=RecordResponse)
async def correct_record(
    record_id: uuid.UUID,
    body: RecordCorrection,
    user: RequireInterventionist,
    db: DBSession,
) -> RecordResponse:
    record = await observation_service.get_record(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found",
        )
    observation = await observation_service.get_observation(db, record.observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Parent observation not found",
        )
    await authorize_child_access(user, observation.child_id, db)
    new_record = await observation_service.correct_record(
        db,
        record_id=record_id,
        corrected_by=user.id,
        record_data=body.record_data,
        correction_reason=body.correction_reason,
    )
    await audit_service.log_event(
        db,
        user_id=user.id,
        action="correct_record",
        resource_type="structured_record",
        resource_id=str(new_record.id),
        child_id=observation.child_id,
        detail={"previous_record_id": str(record_id), "reason": body.correction_reason},
    )
    await db.commit()
    return RecordResponse.model_validate(new_record)


@router.get("/records/{record_id}/history", response_model=list[RecordResponse])
async def get_record_history(
    record_id: uuid.UUID,
    user: RequireInterventionist,
    db: DBSession,
) -> list[RecordResponse]:
    record = await observation_service.get_record(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found",
        )
    observation = await observation_service.get_observation(db, record.observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Parent observation not found",
        )
    await authorize_child_access(user, observation.child_id, db)
    history = await observation_service.get_record_history(db, record_id)
    return [RecordResponse.model_validate(r) for r in history]
