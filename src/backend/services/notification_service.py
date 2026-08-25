"""Notification service — development stub that logs instead of sending real messages."""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


async def send_notification(
    recipient_id: uuid.UUID,
    notification_type: str,
    subject: str,
    body: str,
    metadata: dict | None = None,
) -> None:
    logger.info(
        "Notification [%s] to=%s subject=%r metadata=%s",
        notification_type,
        recipient_id,
        subject,
        metadata,
    )


async def send_overdue_reminder(
    recipient_id: uuid.UUID,
    child_name: str,
    schedule_description: str,
) -> None:
    await send_notification(
        recipient_id=recipient_id,
        notification_type="overdue_reminder",
        subject=f"Overdue observation for {child_name}",
        body=f"An observation is overdue for {child_name}: {schedule_description}",
        metadata={"child_name": child_name, "schedule_description": schedule_description},
    )


async def send_actor_invitation(
    email: str,
    invited_by_name: str,
    child_name: str,
) -> None:
    logger.info(
        "Notification [actor_invitation] to_email=%s invited_by=%s child=%s",
        email,
        invited_by_name,
        child_name,
    )
