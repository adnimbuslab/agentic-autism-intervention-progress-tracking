"""Actor assignment routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from src.backend.api.deps import (
    DBSession,
    RequireInterventionist,
    authorize_child_access,
)
from src.backend.schemas.api_schemas import ActorInvite, ActorResponse
from src.backend.services import audit_service, auth_service, workspace_service

router = APIRouter(tags=["actors"])


@router.post(
    "/children/{child_id}/actors",
    response_model=ActorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_actor(
    child_id: uuid.UUID,
    body: ActorInvite,
    user: RequireInterventionist,
    db: DBSession,
) -> ActorResponse:
    await authorize_child_access(user, child_id, db)
    target_user = await auth_service.get_user_by_email(db, body.email)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user found with that email",
        )
    assignment = await workspace_service.invite_actor(
        db,
        child_id=child_id,
        user_id=target_user.id,
        role=body.role,
        invited_by=user.id,
        invitation_email=body.email,
    )
    await audit_service.log_event(
        db,
        user_id=user.id,
        action="invite_actor",
        resource_type="actor_assignment",
        resource_id=str(assignment.id),
        child_id=child_id,
        detail={"invited_user_id": str(target_user.id), "role": body.role.value},
    )
    await db.commit()
    return ActorResponse.model_validate(assignment)


@router.get("/children/{child_id}/actors", response_model=list[ActorResponse])
async def list_actors(
    child_id: uuid.UUID,
    user: RequireInterventionist,
    db: DBSession,
) -> list[ActorResponse]:
    await authorize_child_access(user, child_id, db)
    actors = await workspace_service.list_actors(db, child_id)
    return [ActorResponse.model_validate(a) for a in actors]


@router.delete("/actors/{assignment_id}", response_model=ActorResponse)
async def revoke_actor(
    assignment_id: uuid.UUID,
    user: RequireInterventionist,
    db: DBSession,
) -> ActorResponse:
    from src.backend.models.actor import ActorAssignment as ActorModel

    existing = await db.get(ActorModel, assignment_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Actor assignment not found",
        )
    await authorize_child_access(user, existing.child_id, db)
    assignment = await workspace_service.revoke_actor(db, assignment_id)
    await audit_service.log_event(
        db,
        user_id=user.id,
        action="revoke_actor",
        resource_type="actor_assignment",
        resource_id=str(assignment.id),
        child_id=assignment.child_id,
    )
    await db.commit()
    return ActorResponse.model_validate(assignment)
