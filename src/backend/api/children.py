"""Child workspace routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from src.backend.api.deps import (
    CurrentUser,
    DBSession,
    RequireInterventionist,
    authorize_child_access,
    get_authorized_children,
)
from src.backend.schemas.api_schemas import ChildCreate, ChildResponse, ChildUpdate
from src.backend.services import audit_service, workspace_service

router = APIRouter(prefix="/children", tags=["children"])


@router.post("/", response_model=ChildResponse, status_code=status.HTTP_201_CREATED)
async def create_child(
    body: ChildCreate,
    user: RequireInterventionist,
    db: DBSession,
) -> ChildResponse:
    child = await workspace_service.create_child(
        db,
        display_name=body.display_name,
        created_by=user.id,
        date_of_birth=body.date_of_birth,
    )
    await audit_service.log_event(
        db,
        user_id=user.id,
        action="create_child",
        resource_type="child",
        resource_id=str(child.id),
        child_id=child.id,
    )
    await db.commit()
    return ChildResponse.model_validate(child)


@router.get("/", response_model=list[ChildResponse])
async def list_children(user: CurrentUser, db: DBSession) -> list[ChildResponse]:
    authorized_ids = await get_authorized_children(user, db)
    children = await workspace_service.list_children(db, user.id, authorized_ids)
    return [ChildResponse.model_validate(c) for c in children]


@router.get("/{child_id}", response_model=ChildResponse)
async def get_child(child_id: uuid.UUID, user: CurrentUser, db: DBSession) -> ChildResponse:
    await authorize_child_access(user, child_id, db)
    child = await workspace_service.get_child(db, child_id)
    if child is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Child not found")
    return ChildResponse.model_validate(child)


@router.patch("/{child_id}", response_model=ChildResponse)
async def update_child(
    child_id: uuid.UUID,
    body: ChildUpdate,
    user: RequireInterventionist,
    db: DBSession,
) -> ChildResponse:
    await authorize_child_access(user, child_id, db)
    child = await workspace_service.get_child(db, child_id)
    if child is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Child not found")
    update_kwargs: dict = {}
    if body.display_name is not None:
        update_kwargs["display_name"] = body.display_name
    if "date_of_birth" in body.model_fields_set:
        update_kwargs["date_of_birth"] = body.date_of_birth
    if body.is_active is not None:
        update_kwargs["is_active"] = body.is_active
    child = await workspace_service.update_child(db, child, **update_kwargs)
    await audit_service.log_event(
        db,
        user_id=user.id,
        action="update_child",
        resource_type="child",
        resource_id=str(child.id),
        child_id=child.id,
    )
    await db.commit()
    return ChildResponse.model_validate(child)
