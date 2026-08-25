"""Schedule service — reporting expectations and overdue detection."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.models.observation import Observation, ObservationStatus
from src.backend.models.schedule import ReportingExpectation
from src.backend.schemas.api_schemas import OverdueInfo


async def create_schedule(
    db: AsyncSession,
    child_id: uuid.UUID,
    cadence_days: int,
    goal_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    setting: str | None = None,
    description: str | None = None,
) -> ReportingExpectation:
    schedule = ReportingExpectation(
        child_id=child_id,
        cadence_days=cadence_days,
        goal_id=goal_id,
        actor_id=actor_id,
        setting=setting,
        description=description,
    )
    db.add(schedule)
    await db.flush()
    return schedule


async def list_schedules(
    db: AsyncSession,
    child_id: uuid.UUID,
) -> list[ReportingExpectation]:
    stmt = (
        select(ReportingExpectation)
        .where(ReportingExpectation.child_id == child_id)
        .order_by(ReportingExpectation.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def check_overdue(
    db: AsyncSession,
    schedule: ReportingExpectation,
) -> OverdueInfo:
    stmt = (
        select(Observation.submitted_at)
        .where(
            Observation.child_id == schedule.child_id,
            Observation.status == ObservationStatus.FINALIZED,
        )
    )
    if schedule.actor_id is not None:
        stmt = stmt.where(Observation.submitted_by == schedule.actor_id)
    if schedule.setting is not None:
        stmt = stmt.where(Observation.setting == schedule.setting)
    stmt = stmt.order_by(Observation.submitted_at.desc()).limit(1)

    result = await db.execute(stmt)
    last_submitted = result.scalar_one_or_none()

    if last_submitted is None:
        base_date = schedule.created_at.date()
    else:
        base_date = last_submitted.date()

    due = base_date + timedelta(days=schedule.cadence_days)
    today = date.today()

    if today > due:
        return OverdueInfo(is_overdue=True, due_date=due, days_overdue=(today - due).days)
    return OverdueInfo(is_overdue=False, due_date=due, days_overdue=0)


async def detect_all_overdue(
    db: AsyncSession,
    child_id: uuid.UUID,
) -> list[dict]:
    schedules = await list_schedules(db, child_id)
    results: list[dict] = []
    for schedule in schedules:
        if not schedule.is_active:
            continue
        info = await check_overdue(db, schedule)
        if info.is_overdue:
            results.append({
                "schedule_id": str(schedule.id),
                "description": schedule.description,
                "cadence_days": schedule.cadence_days,
                "due_date": str(info.due_date),
                "days_overdue": info.days_overdue,
            })
    return results
