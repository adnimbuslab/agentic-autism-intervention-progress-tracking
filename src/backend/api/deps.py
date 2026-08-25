"""Shared FastAPI dependencies — auth, RBAC, database session, child-level authorization."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.config import settings
from src.backend.database import get_session
from src.backend.models.actor import ActorAssignment
from src.backend.models.user import Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

DBSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DBSession,
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        raise credentials_exception

    user = await db.get(User, user_id)
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: Role):
    """Dependency factory: require the current user to have one of the given roles."""

    async def _check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role.value}' is not authorized for this operation",
            )
        return user

    return _check


RequireInterventionist = Annotated[User, Depends(require_role(Role.INTERVENTIONIST))]


async def get_authorized_children(
    user: User,
    db: AsyncSession,
) -> list[uuid.UUID]:
    """Return child IDs the user is authorized to access."""
    if user.role == Role.INTERVENTIONIST:
        from src.backend.models.child import Child

        result = await db.execute(
            select(Child.id).where(Child.created_by == user.id, Child.is_active.is_(True))
        )
        owned = list(result.scalars().all())

        result = await db.execute(
            select(ActorAssignment.child_id).where(
                ActorAssignment.user_id == user.id,
                ActorAssignment.revoked_at.is_(None),
            )
        )
        assigned = list(result.scalars().all())

        return list(set(owned + assigned))

    result = await db.execute(
        select(ActorAssignment.child_id).where(
            ActorAssignment.user_id == user.id,
            ActorAssignment.revoked_at.is_(None),
        )
    )
    return list(result.scalars().all())


async def authorize_child_access(
    user: User,
    child_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Raise 403 if user is not authorized to access the given child."""
    authorized = await get_authorized_children(user, db)
    if child_id not in authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this child",
        )
