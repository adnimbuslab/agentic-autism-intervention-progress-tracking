"""API request/response schemas for all endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.backend.models.goal import GoalType
from src.backend.models.observation import ObservationStatus, RecordStatus
from src.backend.models.user import Role
from src.backend.schemas.observation_schema import Domain, Setting


# --- Auth ---


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    role: Role


# --- Children ---


class ChildCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)
    date_of_birth: Optional[date] = None


class ChildUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    date_of_birth: Optional[date] = None
    is_active: Optional[bool] = None


class ChildResponse(BaseModel):
    id: uuid.UUID
    display_name: str
    date_of_birth: Optional[datetime] = None
    created_by: uuid.UUID
    created_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


# --- Goals ---


class GoalCreate(BaseModel):
    goal_type: GoalType
    domain: Domain
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1)
    criteria: Optional[str] = None
    parent_goal_id: Optional[uuid.UUID] = None
    start_date: Optional[date] = None
    target_date: Optional[date] = None


class GoalUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=512)
    description: Optional[str] = Field(default=None, min_length=1)
    criteria: Optional[str] = None
    is_active: Optional[bool] = None


class GoalResponse(BaseModel):
    id: uuid.UUID
    child_id: uuid.UUID
    goal_type: GoalType
    domain: Domain
    title: str
    description: str
    criteria: Optional[str]
    parent_goal_id: Optional[uuid.UUID]
    start_date: Optional[date]
    target_date: Optional[date]
    is_active: bool
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Actors ---


class ActorInvite(BaseModel):
    email: str
    role: Role


class ActorResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    child_id: uuid.UUID
    role: Role
    invited_by: uuid.UUID
    invited_at: datetime
    invitation_email: Optional[str]
    revoked_at: Optional[datetime]

    model_config = {"from_attributes": True}


# --- Observations ---


class ObservationCreate(BaseModel):
    raw_text: str = Field(min_length=1)
    setting: Setting
    source_type: str = "conversational"
    goal_id: Optional[uuid.UUID] = None


class ClarificationSubmit(BaseModel):
    answer: Optional[str] = None
    declined: bool = False


class ClarificationTurnResponse(BaseModel):
    turn_number: int
    question: str
    answer: Optional[str]
    created_at: datetime
    answered_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ObservationResponse(BaseModel):
    id: uuid.UUID
    child_id: uuid.UUID
    submitted_by: uuid.UUID
    raw_text: str
    source_type: str
    setting: str
    status: ObservationStatus
    submitted_at: datetime
    finalized_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ObservationDetail(ObservationResponse):
    clarification_turns: list[ClarificationTurnResponse] = Field(default_factory=list)
    structured_record: Optional[RecordResponse] = None


class ConversationResponse(BaseModel):
    observation_id: uuid.UUID
    raw_text: str
    status: ObservationStatus
    clarification_turns: list[ClarificationTurnResponse] = Field(default_factory=list)
    pending_question: Optional[str] = None


class ObservationSubmitResponse(BaseModel):
    observation: ObservationResponse
    routing_decision: str
    clarification_question: Optional[str] = None


# --- Structured Records ---


class RecordResponse(BaseModel):
    id: uuid.UUID
    observation_id: uuid.UUID
    version: int
    status: RecordStatus
    record_data: dict
    validation_result: Optional[dict]
    corrected_by: Optional[uuid.UUID]
    correction_reason: Optional[str]
    provider: str
    model: str
    prompt_version: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RecordCorrection(BaseModel):
    record_data: dict
    correction_reason: str = Field(min_length=1)


# --- Schedules ---


class ScheduleCreate(BaseModel):
    goal_id: Optional[uuid.UUID] = None
    actor_id: Optional[uuid.UUID] = None
    setting: Optional[str] = None
    cadence_days: int = Field(ge=1)
    description: Optional[str] = None


class ScheduleUpdate(BaseModel):
    cadence_days: Optional[int] = Field(default=None, ge=1)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class OverdueInfo(BaseModel):
    is_overdue: bool
    due_date: Optional[date] = None
    days_overdue: int = 0


class ScheduleResponse(BaseModel):
    id: uuid.UUID
    child_id: uuid.UUID
    goal_id: Optional[uuid.UUID]
    actor_id: Optional[uuid.UUID]
    setting: Optional[str]
    cadence_days: int
    description: Optional[str]
    is_active: bool
    created_at: datetime
    overdue: Optional[OverdueInfo] = None

    model_config = {"from_attributes": True}


# --- Audit ---


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    child_id: Optional[uuid.UUID]
    action: str
    resource_type: str
    resource_id: Optional[str]
    detail: Optional[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Generic ---


class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int = 1
    page_size: int = 50
