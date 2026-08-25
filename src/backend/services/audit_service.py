"""Audit trail service — append-only event logging."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.models.audit import AuditEvent


async def log_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    child_id: uuid.UUID | None = None,
    detail: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        user_id=user_id,
        child_id=child_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
    )
    db.add(event)
    await db.flush()
    return event


async def get_audit_trail(
    db: AsyncSession,
    child_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEvent]:
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.child_id == child_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
