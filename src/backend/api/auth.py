"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from src.backend.api.deps import CurrentUser, DBSession
from src.backend.config import settings
from src.backend.schemas.api_schemas import (
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from src.backend.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, db: DBSession) -> TokenResponse:
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        email = str(form.get("username", ""))
        password = str(form.get("password", ""))
    else:
        try:
            body = await request.json()
            parsed = LoginRequest(**body)
        except Exception:
            raise HTTPException(
                status_code=422,
                detail="Invalid request body: expected JSON with 'email' and 'password'",
            )
        email = parsed.email
        password = parsed.password

    user = await auth_service.authenticate_user(db, email, password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_service.create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(body: UserCreate, db: DBSession) -> UserResponse:
    existing = await auth_service.get_user_by_email(db, body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )
    user = await auth_service.create_user(
        db, body.email, body.password, body.full_name, body.role,
    )
    await db.commit()
    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
