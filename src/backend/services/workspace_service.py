"""Workspace service — child, actor assignment, and goal management."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.models.actor import ActorAssignment
from src.backend.models.child import Child
from src.backend.models.goal import Goal, GoalType
from src.backend.models.user import Role
from src.backend.schemas.observation_schema import Domain

_UNSET: object = object()


async def create_child(
    db: AsyncSession,
    display_name: str,
    created_by: uuid.UUID,
    date_of_birth: datetime | None = None,
) -> Child:
    child = Child(
        display_name=display_name,
        created_by=created_by,
        date_of_birth=date_of_birth,
    )
    db.add(child)
    await db.flush()
    return child


async def get_child(db: AsyncSession, child_id: uuid.UUID) -> Child | None:
    return await db.get(Child, child_id)


async def list_children(
    db: AsyncSession,
    user_id: uuid.UUID,
    authorized_child_ids: list[uuid.UUID],
) -> list[Child]:
    if not authorized_child_ids:
        return []
    stmt = (
        select(Child)
        .where(Child.id.in_(authorized_child_ids), Child.is_active.is_(True))
        .order_by(Child.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_child(
    db: AsyncSession,
    child: Child,
    display_name: str | None = None,
    date_of_birth: object = _UNSET,
    is_active: bool | None = None,
) -> Child:
    if display_name is not None:
        child.display_name = display_name
    if date_of_birth is not _UNSET:
        child.date_of_birth = date_of_birth  # type: ignore[assignment]
    if is_active is not None:
        child.is_active = is_active
    await db.flush()
    return child


# --- Actor assignments ---


async def invite_actor(
    db: AsyncSession,
    child_id: uuid.UUID,
    user_id: uuid.UUID,
    role: Role,
    invited_by: uuid.UUID,
    invitation_email: str | None = None,
) -> ActorAssignment:
    assignment = ActorAssignment(
        child_id=child_id,
        user_id=user_id,
        role=role,
        invited_by=invited_by,
        invitation_email=invitation_email,
    )
    db.add(assignment)
    await db.flush()
    return assignment


async def list_actors(
    db: AsyncSession,
    child_id: uuid.UUID,
) -> list[ActorAssignment]:
    stmt = (
        select(ActorAssignment)
        .where(ActorAssignment.child_id == child_id)
        .order_by(ActorAssignment.invited_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def revoke_actor(
    db: AsyncSession,
    assignment_id: uuid.UUID,
) -> ActorAssignment:
    assignment = await db.get(ActorAssignment, assignment_id)
    if assignment is None:
        raise ValueError(f"ActorAssignment {assignment_id} not found")
    assignment.revoked_at = datetime.now(UTC)
    await db.flush()
    return assignment


# --- Goals ---


async def create_goal(
    db: AsyncSession,
    child_id: uuid.UUID,
    created_by: uuid.UUID,
    goal_type: GoalType,
    domain: Domain,
    title: str,
    description: str,
    criteria: str | None = None,
    parent_goal_id: uuid.UUID | None = None,
    start_date: date | None = None,
    target_date: date | None = None,
) -> Goal:
    goal = Goal(
        child_id=child_id,
        created_by=created_by,
        goal_type=goal_type,
        domain=domain,
        title=title,
        description=description,
        criteria=criteria,
        parent_goal_id=parent_goal_id,
        start_date=start_date,
        target_date=target_date,
    )
    db.add(goal)
    await db.flush()
    return goal


async def list_goals(
    db: AsyncSession,
    child_id: uuid.UUID,
) -> list[Goal]:
    stmt = (
        select(Goal)
        .where(Goal.child_id == child_id)
        .order_by(Goal.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_goal(db: AsyncSession, goal_id: uuid.UUID) -> Goal | None:
    return await db.get(Goal, goal_id)


async def update_goal(
    db: AsyncSession,
    goal: Goal,
    title: str | None = None,
    description: str | None = None,
    criteria: object = _UNSET,
    is_active: bool | None = None,
) -> Goal:
    if title is not None:
        goal.title = title
    if description is not None:
        goal.description = description
    if criteria is not _UNSET:
        goal.criteria = criteria  # type: ignore[assignment]
    if is_active is not None:
        goal.is_active = is_active
    goal.version += 1
    await db.flush()
    return goal
