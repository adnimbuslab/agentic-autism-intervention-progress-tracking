"""Goal routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from src.backend.api.deps import (
    CurrentUser,
    DBSession,
    RequireInterventionist,
    authorize_child_access,
)
from src.backend.schemas.api_schemas import GoalCreate, GoalResponse, GoalUpdate
from src.backend.services import audit_service, workspace_service

router = APIRouter(tags=["goals"])


@router.post(
    "/children/{child_id}/goals",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_goal(
    child_id: uuid.UUID,
    body: GoalCreate,
    user: RequireInterventionist,
    db: DBSession,
) -> GoalResponse:
    await authorize_child_access(user, child_id, db)
    goal = await workspace_service.create_goal(
        db,
        child_id=child_id,
        created_by=user.id,
        goal_type=body.goal_type,
        domain=body.domain,
        title=body.title,
        description=body.description,
        criteria=body.criteria,
        parent_goal_id=body.parent_goal_id,
        start_date=body.start_date,
        target_date=body.target_date,
    )
    await audit_service.log_event(
        db,
        user_id=user.id,
        action="create_goal",
        resource_type="goal",
        resource_id=str(goal.id),
        child_id=child_id,
    )
    await db.commit()
    return GoalResponse.model_validate(goal)


@router.get("/children/{child_id}/goals", response_model=list[GoalResponse])
async def list_goals(
    child_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> list[GoalResponse]:
    await authorize_child_access(user, child_id, db)
    goals = await workspace_service.list_goals(db, child_id)
    return [GoalResponse.model_validate(g) for g in goals]


@router.patch("/goals/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: uuid.UUID,
    body: GoalUpdate,
    user: RequireInterventionist,
    db: DBSession,
) -> GoalResponse:
    goal = await workspace_service.get_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    await authorize_child_access(user, goal.child_id, db)
    goal = await workspace_service.update_goal(
        db,
        goal,
        title=body.title,
        description=body.description,
        criteria=body.criteria,
        is_active=body.is_active,
    )
    await audit_service.log_event(
        db,
        user_id=user.id,
        action="update_goal",
        resource_type="goal",
        resource_id=str(goal.id),
        child_id=goal.child_id,
    )
    await db.commit()
    return GoalResponse.model_validate(goal)
