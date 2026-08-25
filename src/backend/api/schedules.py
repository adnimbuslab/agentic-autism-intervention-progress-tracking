"""Schedule routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from src.backend.api.deps import (
    DBSession,
    RequireInterventionist,
    authorize_child_access,
)
from src.backend.schemas.api_schemas import ScheduleCreate, ScheduleResponse
from src.backend.services import audit_service, schedule_service

router = APIRouter(tags=["schedules"])


@router.post(
    "/children/{child_id}/schedules",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_schedule(
    child_id: uuid.UUID,
    body: ScheduleCreate,
    user: RequireInterventionist,
    db: DBSession,
) -> ScheduleResponse:
    await authorize_child_access(user, child_id, db)
    schedule = await schedule_service.create_schedule(
        db,
        child_id=child_id,
        cadence_days=body.cadence_days,
        goal_id=body.goal_id,
        actor_id=body.actor_id,
        setting=body.setting,
        description=body.description,
    )
    await audit_service.log_event(
        db,
        user_id=user.id,
        action="create_schedule",
        resource_type="reporting_expectation",
        resource_id=str(schedule.id),
        child_id=child_id,
    )
    await db.commit()
    return ScheduleResponse.model_validate(schedule)


@router.get("/children/{child_id}/schedules", response_model=list[ScheduleResponse])
async def list_schedules(
    child_id: uuid.UUID,
    user: RequireInterventionist,
    db: DBSession,
) -> list[ScheduleResponse]:
    await authorize_child_access(user, child_id, db)
    schedules = await schedule_service.list_schedules(db, child_id)
    return [ScheduleResponse.model_validate(s) for s in schedules]
